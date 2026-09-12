import contextlib
import io
import json
from pathlib import Path
import subprocess
import sys
import unittest
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from http_test_failures import failure_names
import verify

PREFIX='route_aware_client_pool::tls_fallback_tests::'
ISSUE_NAMES=sorted(PREFIX+n for n in (
    'does_not_retry_a_non_replayable_streaming_request',
    'retries_a_native_tls_failure_after_another_request_caches_rustls',
    'retries_a_native_tls_protocol_failure_once_with_rustls',
    'retries_a_tls_protocol_failure_when_request_url_contains_certificate_markers',
    'successful_rustls_fallback_replays_the_request_and_reuses_the_destination'))
def summary(names,count=None):
    return ('failures:\n\n'+''.join('    '+n+'\n' for n in names)+
        '\ntest result: FAILED. 0 passed; '+str(len(names) if count is None else count)+
        ' failed; 0 ignored; 0 measured; 0 filtered out; finished in 0.10s\n').encode()

class FailureNameTests(unittest.TestCase):
    def test_exact_issue_set(self):
        self.assertEqual(failure_names(summary(ISSUE_NAMES)),{'failed_tests':ISSUE_NAMES,'failed_test_count':5})
    def test_different_known_test(self):
        names=json.loads((verify.ROOT/'http-client-test-names.json').read_text())['names']
        other=next(n for n in names if n not in ISSUE_NAMES)
        self.assertEqual(failure_names(summary([other]))['failed_tests'],[other])
    def test_raw_panic_content_never_exported(self):
        raw=b'failures:\n\n---- PRIVATE_SECRET stdout ----\nPRIVATE_SECRET\n'+summary(ISSUE_NAMES)
        out=json.dumps(failure_names(raw))
        self.assertNotIn('PRIVATE',out)
        self.assertEqual(json.loads(out)['failed_test_count'],5)
    def test_malformed_and_secret_names_fail_closed(self):
        for data in (b'error: PRIVATE',summary(['PRIVATE_SECRET']),summary(ISSUE_NAMES,4),
                     summary([ISSUE_NAMES[0]]*2),summary(ISSUE_NAMES)*2,
                     summary([]),summary(ISSUE_NAMES).replace(b'    ',b'  '),
                     summary(ISSUE_NAMES).replace(b'finished in',b'PRIVATE')):
            with self.subTest():self.assertEqual(failure_names(data),{'failed_tests':None,'failed_test_count':None})
    def test_crlf(self):
        self.assertEqual(failure_names(summary(ISSUE_NAMES).replace(b'\n',b'\r\n'))['failed_test_count'],5)
    def test_http_only_and_no_stderr_export(self):
        out=io.StringIO()
        fake=subprocess.CompletedProcess([],101,summary(ISSUE_NAMES),b'PRIVATE_SECRET')
        with contextlib.redirect_stdout(out),patch.object(verify.subprocess,'run',return_value=fake) as run:
            with self.assertRaisesRegex(RuntimeError,'HTTP_CLIENT_LIB_TEST_FAILED'):
                verify.phase_command('HTTP_CLIENT_LIB_TEST',['fake'],Path('.'),{})
        self.assertEqual(run.call_count,1)
        self.assertNotIn('PRIVATE',out.getvalue())
        self.assertNotIn('diagnostic_categories',out.getvalue())
        self.assertEqual(json.loads(out.getvalue().splitlines()[1])['failed_tests'],ISSUE_NAMES)

if __name__=='__main__':unittest.main()
