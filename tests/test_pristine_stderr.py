import contextlib
import io
from pathlib import Path
import subprocess
import sys
import unittest
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import verify as v
from safe_cargo_stderr import classify_stderr,CATEGORIES

class StderrTests(unittest.TestCase):
    def test_each_fixed_category_without_payload(self):
        samples={
            'LOCKFILE_REJECTED':b'the lock file PRIVATE needs to be updated but --locked was passed',
            'DEPENDENCY_RESOLUTION_FAILED':b'failed to select a version for PRIVATE',
            'DEPENDENCY_DOWNLOAD_FAILED':b'failed to download PRIVATE',
            'GIT_FETCH_FAILED':b'failed to fetch into PRIVATE',
            'PACKAGE_OR_TARGET_SELECTION_ERROR':b'package ID specification PRIVATE did not match any packages',
            'TARGET_NOT_INSTALLED':b'the PRIVATE target may not be installed',
            'RUST_VERSION_INCOMPATIBLE':b'PRIVATE requires rustc 9.99',
            'BUILD_SCRIPT_FAILED':b'failed to run custom build command for PRIVATE',
            'LINKER_NOT_FOUND':b'linker PRIVATE not found',
            'LINKER_FAILED':b'linking with PRIVATE failed',
            'CARGO_CONFIG_ERROR':b'could not load Cargo configuration PRIVATE'}
        self.assertEqual(set(samples),CATEGORIES-{'UNKNOWN'})
        for category,data in samples.items():
            with self.subTest(category=category):
                with contextlib.redirect_stdout(io.StringIO()) as out,contextlib.redirect_stderr(io.StringIO()) as err:
                    self.assertEqual(classify_stderr(data),category)
                self.assertEqual(out.getvalue()+err.getvalue(),'')
    def test_unknown_ambiguous_and_non_bytes(self):
        for data in (b'PRIVATE',b'linker PRIVATE not found\nfailed to download PRIVATE',None,'PRIVATE',b''):
            self.assertEqual(classify_stderr(data),'UNKNOWN')
    def test_only_constant_not_captured_path_url_or_message(self):
        for value in (b'C:\\PRIVATE\\secret',b'https://private.invalid/SECRET',b'Bearer PRIVATE',b'--PRIVATE'):
            result=classify_stderr(b'failed to download '+value)
            self.assertEqual(result,'DEPENDENCY_DOWNLOAD_FAILED')
    def test_compile_keeps_stderr_in_ram_and_one_call(self):
        fake=subprocess.CompletedProcess([],1,b'',b'failed to download PRIVATE_SECRET')
        with patch.object(Path,'exists',return_value=False),patch.object(v.subprocess,'run',return_value=fake) as run,contextlib.redirect_stdout(io.StringIO()) as out,contextlib.redirect_stderr(io.StringIO()) as err:
            self.assertEqual(v.compile_variant('PRISTINE','cargo',Path('.'),{},Path('target'),stderr_diagnostics=True),(False,None))
        self.assertEqual(run.call_count,1)
        self.assertNotIn('PRIVATE',out.getvalue()+err.getvalue())
        self.assertIn('DEPENDENCY_DOWNLOAD_FAILED',out.getvalue())
        self.assertIn('--message-format=json',run.call_args.args[0])
    def test_pristine_only_both_outcomes_no_patch_or_tests(self):
        for ok in (True,False):
            with patch.object(v,'pristine_check') as clean,patch.object(v,'sha',return_value='same'),patch.object(v,'compile_variant',return_value=(ok,None)) as compile,patch.object(v,'prepare') as prep,patch.object(v,'phase_command') as test:
                if ok:v.pristine_diagnostic(Path('.'),'cargo',{},Path('target'))
                else:
                    with self.assertRaisesRegex(RuntimeError,'PRISTINE_DIAGNOSTIC_FAILED'):
                        v.pristine_diagnostic(Path('.'),'cargo',{},Path('target'))
                self.assertEqual(compile.call_count,1);self.assertEqual(clean.call_count,2)
                prep.assert_not_called();test.assert_not_called()
    def test_uncertain_process_no_retry_or_payload(self):
        with patch.object(Path,'exists',return_value=False),patch.object(v.subprocess,'run',side_effect=subprocess.TimeoutExpired('PRIVATE',1,stderr=b'PRIVATE')) as run,contextlib.redirect_stdout(io.StringIO()) as out:
            with self.assertRaisesRegex(RuntimeError,'HTTP_DIFFERENTIAL_COMPILE_FAILED'):
                v.compile_variant('PRISTINE','cargo',Path('.'),{},Path('target'),stderr_diagnostics=True)
        self.assertEqual(run.call_count,1);self.assertNotIn('PRIVATE',out.getvalue())
    def test_workflow_diagnostic_mode_and_upload_disabled(self):
        source=(v.ROOT/'.github/workflows/codex-safe.yml').read_text()
        self.assertIn('verify.py run --source ./upstream --pristine-only',source)
        self.assertIn('if: ${{ false }}',source)

if __name__=='__main__':unittest.main()
