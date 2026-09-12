"""Offline artifact verification; synthetic execution requires a separate explicit flag."""
import argparse
import json
import os
from pathlib import Path
import re
import secrets
import subprocess
import sys
import tempfile
from verify import COMMIT, TARGET, child_env, contains_marker, markers, scan_tree, sha

def verify_artifact(folder, expected_provenance_sha):
    names = {'codex-safe.exe','safe-logging-probe.exe','provenance.json','SHA256SUMS'}
    if {p.name for p in folder.iterdir()} != names:
        raise RuntimeError('ARTIFACT_ALLOWLIST_FAILED')
    for p in folder.iterdir():
        if not p.is_file() or p.is_symlink() or p.is_junction():
            raise RuntimeError('ARTIFACT_REPARSE_DENIED')
    if not re.fullmatch('[0-9a-f]{64}', expected_provenance_sha) or sha(folder/'provenance.json') != expected_provenance_sha:
        raise RuntimeError('INDEPENDENT_PROVENANCE_HASH_MISMATCH')
    meta = json.loads((folder/'provenance.json').read_text())
    if meta['source_commit'] != COMMIT or meta['target'] != TARGET:
        raise RuntimeError('SOURCE_PIN_MISMATCH')
    if sha(folder/'codex-safe.exe') != meta['binary_sha256'] or sha(folder/'safe-logging-probe.exe') != meta['probe_sha256']:
        raise RuntimeError('BINARY_HASH_MISMATCH')
    if meta['test_summary']['secret_matches'] != 0 or meta['test_summary']['request_completed_events'] != 2:
        raise RuntimeError('TEST_EVIDENCE_INVALID')
    expected = ''.join(f'{sha(folder/n)}  {n}\n' for n in ('codex-safe.exe','safe-logging-probe.exe','provenance.json'))
    if (folder/'SHA256SUMS').read_text() != expected:
        raise RuntimeError('HASH_LIST_MISMATCH')
    return meta

def main():
    p = argparse.ArgumentParser()
    p.add_argument('--artifact',type=Path,required=True)
    p.add_argument('--expected-provenance-sha',required=True)
    p.add_argument('--run-approved-synthetic-test',action='store_true')
    p.add_argument('--empty-lab-parent',type=Path)
    a = p.parse_args()
    folder = a.artifact.resolve()
    verify_artifact(folder,a.expected_provenance_sha)
    if a.run_approved_synthetic_test:
        if a.empty_lab_parent is None or not a.empty_lab_parent.is_dir() or any(a.empty_lab_parent.iterdir()):
            raise RuntimeError('EMPTY_LAB_PARENT_REQUIRED')
        parent = a.empty_lab_parent.absolute()
        if any(x.is_symlink() or x.is_junction() for x in [parent,*parent.parents]):
            raise RuntimeError('REPARSE_DENIED')
        with tempfile.TemporaryDirectory(prefix='synthetic-',dir=parent) as td:
            root = Path(td)
            (root/'.synthetic-only').write_text('synthetic only')
            (root/'empty-home').mkdir()
            seed = secrets.token_hex(16)
            values = markers(seed)
            env = child_env()
            # No existing user profile/config or auth store is supplied to this harness.
            for key in ('USERPROFILE','APPDATA','LOCALAPPDATA','CODEX_HOME','HOME','TEMP','TMP'):
                env[key] = str(root/'empty-home')
            env.update(SAFE_LOGGING_ROOT=str(root),SAFE_LOGGING_SEED=seed)
            run = subprocess.run([str(folder/'safe-logging-probe.exe'),'--exact','worker_safe_logging','--test-threads=1'],cwd=root,env=env,capture_output=True,timeout=90)
            if contains_marker(run.stdout+run.stderr,values):raise RuntimeError('SYNTHETIC_STDIO_LEAK')
            scan_tree(root,values)
            if run.returncode:raise RuntimeError('SYNTHETIC_TEST_FAILED')
            summary = json.loads((root/'summary.json').read_text())
            if summary.get('request_completed_events') != 2 or summary.get('secret_matches') != 0 or summary.get('wal_shm_checked') is not True:
                raise RuntimeError('SYNTHETIC_SUMMARY_INVALID')
        print('OFFLINE_INTEGRITY_AND_SYNTHETIC_PASS')
    else:
        print('OFFLINE_INTEGRITY_PASS_PROVENANCE_IDENTITY_REVIEW_STILL_REQUIRED')

if __name__ == '__main__':
    try:main()
    except BaseException:
        print('POSTDOWNLOAD_FAIL_CLOSED_NO_PAYLOAD_EXPORTED')
        sys.exit(1)
