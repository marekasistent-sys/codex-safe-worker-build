from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
import nasm_backport as b

class BackportTests(unittest.TestCase):
    def test_only_uniform_line_endings(self):
        self.assertEqual(b.normalized(b'a\r\nb\r\n'),b'a\nb\n')
        for data in (b'a\r\nb\n',b'a\rb',b'a\r\r\n'):
            with self.assertRaisesRegex(RuntimeError,'LINE_ENDINGS'):b.normalized(data)
    def test_postimage_lf_crlf_equivalent_but_content_exact(self):
        data=b'public synthetic\ncontent\n'
        with patch.object(b,'POST_HASH',b.digest(data)):
            b.postimage(data);b.postimage(data.replace(b'\n',b'\r\n'))
            with self.assertRaisesRegex(RuntimeError,'POSTIMAGE'):b.postimage(data+b' ')
    def test_safe_error_closed_set(self):
        for reason in b.REASONS:
            self.assertEqual(b.safe_reason(RuntimeError(reason)),reason)
        for error in (RuntimeError('synthetic-private-value'),RuntimeError(['private']),
                      ValueError('private'),RuntimeError('NASM_BASE_COMMIT_MISMATCH','private')):
            self.assertEqual(b.safe_reason(error),'NASM_BACKPORT_UNKNOWN_FAILURE')
    def test_wrong_base(self):
        with patch.object(b,'git',return_value=b'wrong'):
            with self.assertRaisesRegex(RuntimeError,'BASE_COMMIT'):b.identity(Path('.'))
    def test_wrong_patch(self):
        with patch.object(b,'git',return_value=b.BASE.encode()),patch.object(b,'PATCH_HASH','wrong'):
            with self.assertRaisesRegex(RuntimeError,'PATCH_HASH'):b.identity(Path('.'))
    def test_wrong_canonical_blob(self):
        with patch.object(b,'git',side_effect=[b.BASE.encode(),b'wrong']):
            with self.assertRaisesRegex(RuntimeError,'CANONICAL_BLOB'):b.identity(Path('.'))
    def test_dirty_source(self):
        with patch.object(b,'identity'),patch.object(b,'git',return_value=b'changed'):
            with self.assertRaisesRegex(RuntimeError,'REQUIRES_CLEAN'):b.apply(Path('.'))
    def test_apply_check_failure_enum_and_no_apply(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);(root/'nasmlib').mkdir();(root/b.FILE).write_bytes(b.PREIMAGE)
            with patch.object(b,'identity'),patch.object(b,'preimage'),patch.object(b,'git',side_effect=[b'',RuntimeError('NASM_GIT_APPLY_CHECK_FAILED')]) as g:
                with self.assertRaisesRegex(RuntimeError,'GIT_APPLY_CHECK_FAILED'):b.apply(root)
                self.assertEqual(g.call_count,2)
    def test_patch_digest_and_scope(self):
        data=b.PATCH.read_bytes()
        self.assertEqual(b.digest(data),b.PATCH_HASH)
        text=data.decode()
        self.assertEqual(text.count('diff --git '),1)
        self.assertIn('a/nasmlib/file.c b/nasmlib/file.c',text)
        self.assertIn('-#include <stringapiset.h>',text)
        self.assertIn('+#define WIN32_LEAN_AND_MEAN\n+#include <windows.h>',text)
    def test_changed_preimage_rejected(self):
        for data in (b.PREIMAGE,b.PREIMAGE.replace(b'wchar',b'changed'),b.PREIMAGE+b.PREIMAGE):
            with self.assertRaisesRegex(RuntimeError,'EXACT_PREIMAGE'):b.preimage(data)
    def test_duplicate_preimage_rejected_even_with_matching_hash(self):
        data=b.PREIMAGE+b'\n'+b.PREIMAGE
        with patch.object(b,'PRE_HASH',b.digest(data)):
            with self.assertRaisesRegex(RuntimeError,'EXACT_PREIMAGE'):b.preimage(data)
    def test_postimage_changes_rejected(self):
        with self.assertRaisesRegex(RuntimeError,'EXACT_POSTIMAGE'):b.postimage(b'changed')
    def test_scope_rejects_other_tracked_file(self):
        with patch.object(b,'identity'),patch.object(b,'git',return_value=b'nasmlib/file.c\nother.c\n'):
            with self.assertRaisesRegex(RuntimeError,'SCOPE_MISMATCH'):b.verify(Path('synthetic'))
    def test_no_apply_after_bad_preimage(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);(root/'nasmlib').mkdir();(root/b.FILE).write_bytes(b.PREIMAGE)
            with patch.object(b,'identity'),patch.object(b,'git',return_value=b'') as git:
                with self.assertRaisesRegex(RuntimeError,'EXACT_PREIMAGE'):b.apply(root)
                self.assertFalse(any('apply' in call.args for call in git.call_args_list))
    def test_build_revalidates_after_session(self):
        s=(ROOT/'scripts/build-nasm.ps1').read_text()
        self.assertLess(s.index(' apply --source'),s.index('& $env:ComSpec'))
        self.assertGreater(s.index(' verify --source'),s.index('& $env:ComSpec'))
        self.assertIn(b.FIX,s)
        self.assertIn('official upstream Windows SDK compatibility fix',s)

if __name__=='__main__':unittest.main()
