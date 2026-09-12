import contextlib
import io
import subprocess
import unittest
from unittest.mock import patch
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import verify as v

class DiagnosticTests(unittest.TestCase):
    def test_each_phase_failure_is_safe_and_single_call(self):
        for name in v.PHASES:
            with self.subTest(name=name):
                out=io.StringIO()
                result=subprocess.CompletedProcess([],1,b'PRIVATE_PAYLOAD',b'PRIVATE_PAYLOAD')
                with contextlib.redirect_stdout(out),patch.object(v.subprocess,'run',return_value=result) as run:
                    with self.assertRaisesRegex(RuntimeError,'^'+name+'_FAILED$'):
                        v.phase_command(name,['fake'],Path('.'),{})
                self.assertEqual(run.call_count,1)
                self.assertNotIn('PRIVATE',out.getvalue())
                self.assertIn(name+'_START',out.getvalue())
                self.assertNotIn(name+'_PASS',out.getvalue())
    def test_timeout_safe_and_not_retried(self):
        out=io.StringIO()
        with contextlib.redirect_stdout(out),patch.object(v.subprocess,'run',side_effect=subprocess.TimeoutExpired('PRIVATE',1,output=b'PRIVATE')) as run:
            with self.assertRaisesRegex(RuntimeError,'HTTP_CLIENT_LIB_TEST_FAILED'):
                v.phase_command('HTTP_CLIENT_LIB_TEST',['fake'],Path('.'),{})
        self.assertEqual(run.call_count,1)
        self.assertNotIn('PRIVATE',out.getvalue())
    def test_success_returns_capture_and_marks_pass(self):
        with contextlib.redirect_stdout(io.StringIO()) as out,patch.object(v.subprocess,'run',return_value=subprocess.CompletedProcess([],0,b'PRIVATE',b'')):
            self.assertEqual(v.phase_command('SYNTHETIC_TEST_COMPILE',['fake'],Path('.'),{}),b'PRIVATE')
        self.assertNotIn('PRIVATE',out.getvalue())
        self.assertIn('SYNTHETIC_TEST_COMPILE_PASS',out.getvalue())
    def test_closed_output_vocabulary(self):
        for e in (RuntimeError('PRIVATE_SECRET'),ValueError('PRIVATE'),RuntimeError(['PRIVATE'])):
            self.assertEqual(v.safe_error(e),'FAIL_CLOSED_NO_PAYLOAD_EXPORTED')
        self.assertEqual(v.classify(b'error[E9999]: PRIVATE'),['RUST_COMPILER_ERROR'])
        self.assertEqual(v.classify(b'nasm openssl PRIVATE'),['UNKNOWN'])
        self.assertEqual(v.classify(b'lock file PRIVATE needs to be updated'),['LOCKFILE_REJECTED'])
    def test_synthetic_validation_has_phase(self):
        source=(v.ROOT/'scripts/verify.py').read_text()
        self.assertIn("with phase('SYNTHETIC_TEST'):",source)
        self.assertIn("'SYNTHETIC_TEST_FAILED'",v.SAFE_ERRORS.__repr__())
    def test_action_input_removed_pin_preserved(self):
        source=(v.ROOT/'.github/workflows/codex-safe.yml').read_text()
        self.assertNotIn('toolchain: 1.95.0',source)
        self.assertIn('dtolnay/rust-toolchain@e081816240890017053eacbb1bdf337761dc5582',source)

if __name__=='__main__':unittest.main()
