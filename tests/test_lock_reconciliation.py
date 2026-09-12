import copy
import contextlib
import io
from pathlib import Path
import sys
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from reconcile_lockfile import compare

class LockTests(unittest.TestCase):
    def fixture(self):
        old={'version':4,'package':[{'name':'internal','version':'0.0.0','dependencies':['external']},
            {'name':'external','version':'1.2.3','source':'registry+SYNTHETIC','checksum':'SYNTHETIC'}]}
        new=copy.deepcopy(old);new['package'][0]['version']='0.153.4'
        return old,new
    def test_exact_internal_version_only(self):
        old,new=self.fixture();summary,ok=compare(old,new,{'internal'})
        self.assertTrue(ok);self.assertEqual(summary['changed_package_entries'],1)
        self.assertEqual(summary['workspace_version_changes'],['internal'])
    def test_each_external_mutation_rejected(self):
        for field,value in [('version','2'),('source','OTHER'),('checksum','OTHER'),('dependencies',['OTHER'])]:
            old,new=self.fixture();new['package'][1][field]=value
            with contextlib.redirect_stdout(io.StringIO()) as out:
                summary,ok=compare(old,new,{'internal'})
            self.assertFalse(ok);self.assertEqual(out.getvalue(),'')
            self.assertNotIn('OTHER',str(summary));self.assertNotIn('SYNTHETIC',str(summary))
    def test_external_add_remove(self):
        old,new=self.fixture();new['package'].pop()
        summary,ok=compare(old,new,{'internal'});self.assertFalse(ok);self.assertTrue(summary['external_removed'])
        old,new=self.fixture();new['package'].append({'name':'extra','version':'1','source':'PRIVATE'})
        summary,ok=compare(old,new,{'internal'});self.assertFalse(ok);self.assertTrue(summary['external_added'])
    def test_unexpected_internal_change_rejected(self):
        old,new=self.fixture();new['package'][0]['dependencies']=[]
        self.assertFalse(compare(old,new,{'internal'})[1])
        old,new=self.fixture();new['package'][0]['version']='0.153.5'
        self.assertFalse(compare(old,new,{'internal'})[1])
    def test_expected_internal_dependency_reference(self):
        old,new=self.fixture()
        old['package'].append({'name':'consumer','version':'0.0.0','dependencies':['internal 0.0.0']})
        new['package'].append({'name':'consumer','version':'0.153.4','dependencies':['internal 0.153.4']})
        self.assertTrue(compare(old,new,{'internal','consumer'})[1])
    def test_format_and_duplicate_rejected(self):
        old,new=self.fixture();new['version']=5
        self.assertFalse(compare(old,new,{'internal'})[1])
        old,new=self.fixture();new['package'].append(new['package'][0])
        with self.assertRaisesRegex(RuntimeError,'LOCK_STRUCTURE_REJECTED'):compare(old,new,{'internal'})
    def test_build_locked_and_no_upload(self):
        root=Path(__file__).resolve().parents[1]
        script=(root/'scripts/verify.py').read_text()
        self.assertIn("[cargo,'build','--locked','--release'",script)
        workflow=(root/'.github/workflows/codex-safe.yml').read_text()
        self.assertIn('--reconcile-lockfile',workflow)
        self.assertEqual(workflow.count('if: ${{ false }}'),3)

if __name__=='__main__':unittest.main()
