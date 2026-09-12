import contextlib
import io
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import verify as v

class CompileSplitTests(unittest.TestCase):
    def fixture(self,root):
        cwd=root/'codex-rs';cwd.mkdir()
        target=root/'target';exe=target/v.TARGET/'release/deps/codex_http_client-123abc.exe'
        exe.parent.mkdir(parents=True);exe.write_bytes(b'SYNTHETIC_NOT_EXECUTABLE')
        artifact={'reason':'compiler-artifact','target':{'name':'codex_http_client','kind':['lib'],
            'src_path':str(cwd/'http-client/src/lib.rs')},'profile':{'test':True},'executable':str(exe)}
        return cwd,target,exe,artifact
    def test_compile_failure_never_executes_tests(self):
        for output in (b'error[E0001]: PRIVATE',b'failed to select a version PRIVATE',b'PRIVATE'):
            with contextlib.redirect_stdout(io.StringIO()) as out,patch.object(v.subprocess,'run',return_value=subprocess.CompletedProcess([],1,output,b'PRIVATE')) as run:
                with self.assertRaisesRegex(RuntimeError,'HTTP_CLIENT_LIB_COMPILE_FAILED'):
                    v.validate_http_client('cargo',Path('.'),{},Path('target'))
            self.assertEqual(run.call_count,1)
            self.assertNotIn('HTTP_CLIENT_LIB_TEST_START',out.getvalue())
            self.assertNotIn('PRIVATE',out.getvalue())
            self.assertIn('diagnostic_categories',out.getvalue())
    def test_compile_then_exact_binary_no_second_cargo(self):
        with tempfile.TemporaryDirectory() as td:
            cwd,target,exe,a=self.fixture(Path(td))
            results=[subprocess.CompletedProcess([],0,json.dumps(a).encode(),b''),subprocess.CompletedProcess([],0,b'PRIVATE',b'PRIVATE')]
            with contextlib.redirect_stdout(io.StringIO()) as out,patch.object(v.subprocess,'run',side_effect=results) as run:
                v.validate_http_client('cargo',cwd,{},target)
            self.assertEqual(run.call_count,2)
            first=run.call_args_list[0].args[0]
            self.assertIn('--no-run',first);self.assertIn('--message-format=json',first)
            self.assertEqual(run.call_args_list[1].args[0],[str(exe.resolve())])
            self.assertLess(out.getvalue().index('HTTP_CLIENT_LIB_COMPILE_PASS'),out.getvalue().index('HTTP_CLIENT_LIB_TEST_START'))
            self.assertNotIn('PRIVATE',out.getvalue())
    def test_invalid_artifact_stops_before_run(self):
        with tempfile.TemporaryDirectory() as td:
            cwd,target,exe,a=self.fixture(Path(td))
            for raw in (b'',json.dumps(a).encode()+b'\n'+json.dumps(a).encode(),b'PRIVATE'):
                with contextlib.redirect_stdout(io.StringIO()),patch.object(v.subprocess,'run',return_value=subprocess.CompletedProcess([],0,raw,b'')) as run:
                    with self.assertRaisesRegex(RuntimeError,'HTTP_CLIENT_LIB_COMPILE_FAILED'):
                        v.validate_http_client('cargo',cwd,{},target)
                self.assertEqual(run.call_count,1)
    def test_artifact_scope_and_existence(self):
        with tempfile.TemporaryDirectory() as td:
            cwd,target,exe,a=self.fixture(Path(td))
            self.assertEqual(v.http_test_binary(json.dumps(a).encode(),cwd,target),exe.resolve())
            for field,value in [('name','other'),('kind',['bin']),('src_path',str(cwd/'other.rs'))]:
                b=json.loads(json.dumps(a));b['target'][field]=value
                with self.assertRaises(RuntimeError):v.http_test_binary(json.dumps(b).encode(),cwd,target)
            for value in (str(Path(td)/'outside.exe'),str(exe.parent/'other.exe')):
                b=dict(a,executable=value)
                with self.assertRaises(RuntimeError):v.http_test_binary(json.dumps(b).encode(),cwd,target)
            exe.unlink()
            with self.assertRaises(RuntimeError):v.http_test_binary(json.dumps(a).encode(),cwd,target)
    def test_compile_timeout_no_retry(self):
        with contextlib.redirect_stdout(io.StringIO()) as out,patch.object(v.subprocess,'run',side_effect=subprocess.TimeoutExpired('PRIVATE',1)) as run:
            with self.assertRaisesRegex(RuntimeError,'HTTP_CLIENT_LIB_COMPILE_FAILED'):
                v.validate_http_client('cargo',Path('.'),{},Path('target'))
        self.assertEqual(run.call_count,1)
        self.assertIn('UNKNOWN',out.getvalue());self.assertNotIn('PRIVATE',out.getvalue())

if __name__=='__main__':unittest.main()
