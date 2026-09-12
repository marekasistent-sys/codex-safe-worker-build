from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
import nasm_backport as b

class BackportTests(unittest.TestCase):
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
