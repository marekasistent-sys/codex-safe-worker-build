import contextlib
import io
import json
from pathlib import Path
import subprocess
import sys
import unittest
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import verify as v
from safe_cargo_json import summarize

class JsonTests(unittest.TestCase):
    def test_only_approved_fields_escape(self):
        obj={'reason':'compiler-message','package_id':'registry+PRIVATE#codex-http-client@0.1',
             'target':{'name':'codex_http_client','kind':['lib'],'src_path':'PRIVATE'},
             'message':{'level':'error','code':{'code':'E0308','explanation':'PRIVATE'},
                        'message':'PRIVATE linker failed','rendered':'PRIVATE','spans':['PRIVATE']}}
        result=summarize(json.dumps(obj).encode())
        self.assertNotIn('PRIVATE',json.dumps(result))
        self.assertEqual(result['error_diagnostics'],1)
        self.assertEqual(result['diagnostics'][0]['error_code'],'E0308')
        self.assertEqual(result['categories'],['RUST_COMPILER_ERROR'])
    def test_unknown_strings_and_codes_not_exported(self):
        obj={'reason':'compiler-message','package_id':'PRIVATE','target':{'name':'PRIVATE'},
             'message':{'level':'error','code':{'code':'E1234PRIVATE'}}}
        r=summarize(json.dumps(obj).encode());self.assertNotIn('PRIVATE',json.dumps(r))
        self.assertIsNone(r['diagnostics'][0]['package']);self.assertIsNone(r['diagnostics'][0]['error_code'])
    def test_never_infers_failure_from_raw_or_success_event(self):
        for raw in (b'linking with PRIVATE failed',b'error[E0308] PRIVATE',
                    b'{"reason":"build-script-executed","env":[["PRIVATE","PRIVATE"]]}',
                    b'{"reason":"build-finished","success":false}',b'{}',b'[]'):
            r=summarize(raw);self.assertEqual(r['categories'],['UNKNOWN']);self.assertNotIn('PRIVATE',json.dumps(r))
    def test_structured_build_script_error(self):
        raw=json.dumps({'reason':'compiler-message','target':{'name':'build_script_build','kind':['custom-build']},'message':{'level':'error'}}).encode()
        self.assertEqual(summarize(raw)['categories'],['BUILD_SCRIPT_FAILED'])
    def test_malformed_types_fail_closed(self):
        for obj in ({'reason':[]},{'reason':'compiler-message','message':[],'target':{}},
                    {'reason':'compiler-message','message':{'level':[]},'target':{}}):
            self.assertEqual(summarize(json.dumps(obj).encode())['categories'],['UNKNOWN'])

class DifferentialTests(unittest.TestCase):
    def test_all_result_pairs_and_order(self):
        for pristine,patched in ((True,True),(True,False),(False,True),(False,False)):
            events=[]
            def compile(label,*args):events.append(label);return (pristine if label=='PRISTINE' else patched),Path('binary')
            with (patch.object(v,'pristine_check',side_effect=lambda s:events.append('CLEAN')),
                 patch.object(v,'sha',return_value='same'),patch.object(v,'compile_variant',side_effect=compile),
                 patch.object(v,'prepare',side_effect=lambda *a,**kw:events.append('PATCH')),
                 patch.object(v,'command',return_value=(v.SOURCE.as_posix()+'\n').encode())):
                if pristine and patched:self.assertEqual(v.differential_http_compile(Path('.'),'cargo',{},Path('target')),Path('binary'))
                else:
                    with self.assertRaisesRegex(RuntimeError,'HTTP_DIFFERENTIAL_COMPILE_FAILED'):
                        v.differential_http_compile(Path('.'),'cargo',{},Path('target'))
            self.assertEqual(events,['CLEAN','PRISTINE','CLEAN','PATCH','PATCHED'])
    def test_compile_failure_exports_json_only(self):
        fake=subprocess.CompletedProcess([],1,b'RAW_PRIVATE error[E0001]',b'PRIVATE')
        with patch.object(Path,'exists',return_value=False),patch.object(v.subprocess,'run',return_value=fake) as run,contextlib.redirect_stdout(io.StringIO()) as out:
            ok,exe=v.compile_variant('PRISTINE','cargo',Path('.'),{},Path('target'))
        self.assertFalse(ok);self.assertIsNone(exe);self.assertEqual(run.call_count,1)
        self.assertNotIn('PRIVATE',out.getvalue());self.assertIn('PRISTINE_HTTP_COMPILE_FAIL',out.getvalue())
        self.assertIn('--no-run',run.call_args.args[0])
    def test_source_mutation_prevents_patch(self):
        with patch.object(v,'pristine_check',side_effect=[None,RuntimeError('SOURCE_NOT_CLEAN')]),patch.object(v,'sha',return_value='same'),patch.object(v,'compile_variant',return_value=(False,None)),patch.object(v,'prepare') as prep:
            with self.assertRaisesRegex(RuntimeError,'SOURCE_NOT_CLEAN'):
                v.differential_http_compile(Path('.'),'cargo',{},Path('target'))
        prep.assert_not_called()

if __name__=='__main__':unittest.main()
