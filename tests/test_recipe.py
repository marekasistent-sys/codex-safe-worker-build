"""Local stdlib-only checks: no Rust execution, HTTP, authentication or GitHub API."""
import contextlib
import importlib.util
import io
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
import verify
import postdownload

class RecipeTests(unittest.TestCase):
    def test_all_marker_encodings(self):
        for value in verify.markers('0'*32):
            for enc in ('utf-8','utf-16le','utf-16be'):
                with self.subTest(encoding=enc):
                    self.assertTrue(verify.contains_marker(b'prefix'+value.encode(enc)+b'suffix',[value]))
    def test_header_names_are_not_values(self):
        self.assertFalse(verify.contains_marker(b'Set-Cookie Authorization Request completed',verify.markers('0'*32)))
    def test_nested_file_detection_is_redacted(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td); (root/'sub').mkdir()
            values=verify.markers('1'*32)
            (root/'sub/logs_2.sqlite-wal').write_bytes(values[0].encode())
            out=io.StringIO()
            with contextlib.redirect_stdout(out),contextlib.redirect_stderr(out):
                with self.assertRaisesRegex(RuntimeError,'^SYNTHETIC_SECRET_DETECTED$'):
                    verify.scan_tree(root,values)
            self.assertEqual(out.getvalue(),'')
    def test_clean_tree(self):
        with tempfile.TemporaryDirectory() as td:
            (Path(td)/'safe').write_text('method GET status 200')
            self.assertEqual(verify.scan_tree(td,verify.markers('2'*32)),1)
    def test_wrong_source_fails_closed(self):
        with self.assertRaisesRegex(RuntimeError,'^PINNED_SOURCE_FRAGMENT_MISMATCH$'):
            verify.original_check(b'synthetic invalid source')
    def test_local_run_refused_before_source_access(self):
        with patch.dict(os.environ,{},clear=True):
            with self.assertRaisesRegex(RuntimeError,'^REMOTE_RUN_REQUIRES_EXPLICITLY_DISPATCHED_ACTION$'):
                verify.run(Path('nonexistent'))
    def test_credentials_not_forwarded(self):
        with patch.dict(os.environ,{'OPENAI_API_KEY':'SYNTHETIC','GITHUB_TOKEN':'SYNTHETIC','HTTP_PROXY':'SYNTHETIC'},clear=True):
            env=verify.child_env()
            self.assertNotIn('OPENAI_API_KEY',env)
            self.assertNotIn('GITHUB_TOKEN',env)
            self.assertNotIn('HTTP_PROXY',env)
    def test_process_error_does_not_export_payload(self):
        fake=subprocess.CompletedProcess([],1,b'SYNTHETIC_PRIVATE_PAYLOAD',b'SYNTHETIC_PRIVATE_PAYLOAD')
        with patch.object(subprocess,'run',return_value=fake):
            with self.assertRaisesRegex(RuntimeError,'^COMMAND_FAILED$'):
                verify.command(['fake'],ROOT)
    def test_timeout_not_retried(self):
        with patch.object(subprocess,'run',side_effect=subprocess.TimeoutExpired('fake',1)) as run:
            with self.assertRaises(subprocess.TimeoutExpired):verify.command(['fake'],ROOT)
            self.assertEqual(run.call_count,1)
    def test_manifest(self):
        self.assertGreaterEqual(len(verify.verify_bundle()),7)
    def test_actions_pinned_and_manual_only(self):
        text=(ROOT/'.github/workflows/codex-safe.yml').read_text()
        import re
        pins=re.findall(r'uses:\s+([^\s]+)',text)
        self.assertEqual(len(pins),4)
        self.assertTrue(all(re.fullmatch(r'[\w/-]+@[0-9a-f]{40}',p) for p in pins))
        self.assertIn('runs-on: windows-2022',text)
        self.assertIn('workflow_dispatch:',text)
        self.assertNotIn('pull_request:',text)
        self.assertNotIn('push:',text)
        self.assertEqual(text.count('persist-credentials: false'),2)
        self.assertNotIn('secrets.',text)
    def test_patch_only_logging(self):
        text=(ROOT/'logging.patch').read_text()
        added=[l for l in text.splitlines() if l.startswith('+') and not l.startswith('+++')]
        removed=[l for l in text.splitlines() if l.startswith('-') and not l.startswith('---')]
        self.assertEqual(len(added),1)
        self.assertIn('_url: &str',added[0])
        self.assertEqual(len(removed),5)
        self.assertEqual(sum('headers = ?response.headers()' in l for l in removed),2)
    def test_artifact_extras_denied(self):
        with tempfile.TemporaryDirectory() as td:
            (Path(td)/'unapproved').write_text('synthetic')
            with self.assertRaisesRegex(RuntimeError,'^ARTIFACT_ALLOWLIST_FAILED$'):
                postdownload.verify_artifact(Path(td),'0'*64)

if __name__=='__main__':unittest.main()
