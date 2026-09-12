import os
from pathlib import Path
import subprocess
import shutil
import unittest

ROOT=Path(__file__).resolve().parents[1]

class ArchitectureRecipeTests(unittest.TestCase):
    def test_single_session_order_and_failure_gates(self):
        s=(ROOT/'scripts/nasm-session.cmd').read_text()
        commands=['call "%~1" -no_logo -arch=x64 -host_arch=x64','native-session-evidence.ps1','cl.exe /Bv','architecture\\windows.c','nmake.exe /f Mkfiles\\msvc.mak']
        indexes=[s.index(c) for c in commands]
        self.assertEqual(indexes,sorted(indexes))
        for i,j in zip(indexes,indexes[1:]):self.assertIn('if errorlevel 1 exit /b',s[i:j])
        self.assertIn('VSCMD_ARG_TGT_ARCH',s)
        self.assertIn('VSCMD_ARG_HOST_ARCH',s)
    def test_macro_probe_and_no_manual_architecture(self):
        c=(ROOT/'tests/architecture/intrinsics.c').read_text()
        for macro in ('_M_X64','_M_AMD64','_WIN64'):
            self.assertIn('!defined('+macro+')',c)
        self.assertIn('#error X64_INTRINSICS_REQUIRED',c)
        self.assertIn('#include <windows.h>',(ROOT/'tests/architecture/windows.c').read_text())
        for p in [ROOT/'scripts/build-nasm.ps1',ROOT/'scripts/nasm-session.cmd',ROOT/'scripts/native-session-evidence.ps1',ROOT/'tests/architecture/intrinsics.c']:
            text=p.read_text()
            for bad in ('/D_AMD64_','/D_X86_','#define _AMD64_','#define _M_X64','/FI'):
                self.assertNotIn(bad,text)
    def test_environment_is_not_captured_or_rebuilt(self):
        s=(ROOT/'scripts/build-nasm.ps1').read_text()
        self.assertNotIn('&& set',s)
        self.assertNotIn('SetEnvironmentVariable',s)
        self.assertNotIn('$allow =',s)
    @unittest.skipUnless(os.name=='nt','Windows guard test')
    def test_wrong_architecture_stops_without_tools(self):
        shell=shutil.which('pwsh.exe')
        self.assertIsNotNone(shell,'Existing PowerShell 7 is required; no policy override or installation')
        env={k:os.environ[k] for k in ('SystemRoot','WINDIR','SystemDrive','TEMP','TMP') if k in os.environ}
        env.update(GITHUB_ACTIONS='true',RUNNER_OS='Windows',VSCMD_ARG_TGT_ARCH='x86',VSCMD_ARG_HOST_ARCH='x64')
        result=subprocess.run([str(shell),'-NoProfile','-File',str(ROOT/'scripts/native-session-evidence.ps1'),'-OutputDirectory',str(ROOT/'never-created')],env=env,capture_output=True,timeout=20)
        self.assertNotEqual(result.returncode,0)
        self.assertIn(b'X64_SESSION_REQUIRED',result.stdout+result.stderr)
        self.assertFalse((ROOT/'never-created').exists())

if __name__=='__main__':unittest.main()
