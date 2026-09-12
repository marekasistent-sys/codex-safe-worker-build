"""Static safety-contract checks; no compiler, NASM, Perl or network execution."""
from pathlib import Path
import unittest

ROOT=Path(__file__).resolve().parents[1]

class NasmRecipeTests(unittest.TestCase):
    def test_pin_and_check_before_build(self):
        s=(ROOT/'scripts/build-nasm.ps1').read_text()
        self.assertIn('4a56d66ed9626d5a3ded5414c9d8b7f1a48ce065',s)
        build=s.index('& $env:ComSpec /d /s /c')
        for gate in ('NASM_COMMIT_MISMATCH','NASM_SOURCE_VERSION_MISMATCH'):
            self.assertLess(s.index(gate),build)
        self.assertLess(s.index('NASM_BINARY_VERSION_MISMATCH'),s.index('$source | Out-File'))
        self.assertLess(s.index('NASM_UNEXPECTED_GENERATED_FILE'),s.index('$source | Out-File'))
    def test_provenance_and_no_download(self):
        s=(ROOT/'scripts/build-nasm.ps1').read_text()
        for field in ('source_tree','source_commit','perl_version','generated_files','binary_sha256','cl_version','link_version','native_session','architecture_probe'):
            self.assertIn(field,s)
        for command in ('Invoke-WebRequest','Invoke-RestMethod','Start-BitsTransfer','winget ','choco ','Expand-Archive'):
            self.assertNotIn(command,s)
        self.assertNotIn('$env:PATH =',s)
        self.assertIn('$env:GITHUB_PATH',s)
    def test_nasm_preflight_before_codex_build(self):
        w=(ROOT/'.github/workflows/codex-safe.yml').read_text()
        self.assertLess(w.index('build-nasm.ps1'),w.index('preflight.ps1'))
        self.assertLess(w.index('preflight.ps1'),w.index('verify.py run'))
        p=(ROOT/'scripts/preflight.ps1').read_text()
        self.assertIn('--version',p)
        self.assertIn('NASM_SOURCE_BUILT_PATH_REQUIRED',p)
        self.assertIn('NASM_PROVENANCE_MISMATCH',p)
        self.assertIn('nasm_source_build = $nasmEvidence',p)

if __name__=='__main__':unittest.main()
