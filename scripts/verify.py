"""Build recipe supervisor. No credentials, client auth, model or remote dispatch API."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import secrets
import shutil
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
COMMIT = '3d2ee51ca2d5db578f328aa75e20aa22c0197c9a'
TARGET = 'x86_64-pc-windows-msvc'
SOURCE = Path('codex-rs/http-client/src/client.rs')
ORIGINAL_BLOB = '9cda749aa27581101a4f718644151f88c508100d'
STEPS = []

def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()

def markers(seed):
    return [f'eyJhbGciOiJub25lIn0.{seed}.SYNTHETIC_SIGNATURE', f'SYNTH_COOKIE_{seed}', f'SYNTH_AUTH_{seed}', f'SYNTH_NORMAL_{seed}']

def contains_marker(data, values):
    return any(v.encode(enc) in data for v in values for enc in ('utf-8', 'utf-16le', 'utf-16be'))

def scan_tree(root, values):
    count = 0
    for p in Path(root).rglob('*'):
        if p.is_symlink() or (hasattr(p, 'is_junction') and p.is_junction()):
            raise RuntimeError('REPARSE_DENIED')
        if p.is_file():
            if contains_marker(p.read_bytes(), values):
                raise RuntimeError('SYNTHETIC_SECRET_DETECTED')
            count += 1
    return count

def original_check(data):
    blob = hashlib.sha1(b'blob ' + str(len(data)).encode() + b'\0' + data).hexdigest()
    if blob != ORIGINAL_BLOB:
        raise RuntimeError('PINNED_SOURCE_FRAGMENT_MISMATCH')
    if data.count(b'headers = ?response.headers(),') != 2 or data.count(b'"Request completed"') != 2:
        raise RuntimeError('UNEXPECTED_EVENT_COUNT')

def command(args, cwd, env=None, timeout=7200):
    p = subprocess.run(args, cwd=cwd, env=env, capture_output=True, timeout=timeout)
    if p.returncode:
        # No arbitrary exception, compiler output, stdout, environment or payload export.
        diagnostic = (p.stdout + p.stderr).lower()
        missing = [n for n in ('nasm', 'cmake', 'ninja', 'clang', 'link.exe', 'openssl') if n.encode() in diagnostic]
        raise RuntimeError('COMMAND_FAILED' + ('_REVIEW_DEPENDENCIES_' + '_'.join(missing).upper().replace('.','_') if missing else ''))
    return p.stdout

def verify_bundle():
    manifest = json.loads((ROOT / 'recipe-files.json').read_text(encoding='utf-8'))
    for name, digest in manifest.items():
        p = ROOT / name
        if Path(name).is_absolute() or '..' in Path(name).parts or not p.is_file() or p.is_symlink() or sha(p) != digest:
            raise RuntimeError('RECIPE_INTEGRITY_FAILED')
    return manifest

def prepare(source):
    if command(['git', 'rev-parse', 'HEAD'], source).decode().strip() != COMMIT:
        raise RuntimeError('SOURCE_COMMIT_MISMATCH')
    if command(['git', 'status', '--porcelain'], source).strip():
        raise RuntimeError('SOURCE_NOT_CLEAN')
    original_check((source / SOURCE).read_bytes())
    patch = ROOT / 'logging.patch'
    command(['git', 'apply', '--check', '--whitespace=error', str(patch)], source)
    command(['git', 'apply', '--whitespace=error', str(patch)], source)
    command(['git', 'diff', '--check'], source)
    changed = command(['git', 'diff', '--name-only'], source).decode().splitlines()
    if changed != [SOURCE.as_posix()]:
        raise RuntimeError('PATCH_SCOPE_CHANGED')
    if b'headers = ?response.headers(),' in (source / SOURCE).read_bytes():
        raise RuntimeError('HEADER_LOGGING_REMAINS')
    destination = source / 'codex-rs/app-server/tests/worker_safe_logging.rs'
    if destination.exists():
        raise RuntimeError('SYNTHETIC_TEST_COLLISION')
    shutil.copyfile(ROOT / 'tests/worker_safe_logging.rs', destination)

def child_env():
    # Public Cargo downloads remain possible, but no GitHub/OpenAI tokens enter build/test children.
    allow = ('SystemRoot','WINDIR','SystemDrive','COMSPEC','PATHEXT','PATH','INCLUDE','LIB','LIBPATH',
             'USERPROFILE','APPDATA','LOCALAPPDATA','ProgramFiles','ProgramFiles(x86)','ProgramData',
             'TEMP','TMP','CARGO_HOME','RUSTUP_HOME','VCToolsInstallDir','VCINSTALLDIR','WindowsSdkDir',
             'WindowsSDKVersion','WindowsSDKLibVersion','WindowsSdkBinPath','UCRTVersion','UniversalCRTSdkDir')
    env = {k:os.environ[k] for k in allow if k in os.environ}
    env.update(LIBSQLITE3_FLAGS='SQLITE_DISABLE_INTRINSIC', CARGO_TERM_COLOR='never',
               CARGO_NET_GIT_FETCH_WITH_CLI='true', GIT_TERMINAL_PROMPT='0', GIT_CONFIG_COUNT='2',
               GIT_CONFIG_KEY_0='credential.helper', GIT_CONFIG_VALUE_0='',
               GIT_CONFIG_KEY_1='core.autocrlf', GIT_CONFIG_VALUE_1='false',
               NO_PROXY='127.0.0.1,localhost,::1', no_proxy='127.0.0.1,localhost,::1',
               RUSTUP_TOOLCHAIN='1.95.0-x86_64-pc-windows-msvc', RUST_BACKTRACE='0')
    return env

def run(source):
    if os.environ.get('GITHUB_ACTIONS') != 'true':
        raise RuntimeError('REMOTE_RUN_REQUIRES_EXPLICITLY_DISPATCHED_ACTION')
    recipe_hashes = verify_bundle()
    runner = json.loads((ROOT / 'runner.json').read_text(encoding='utf-8-sig'))
    env = child_env()
    cargo = shutil.which('cargo', path=env['PATH'])
    rustc = shutil.which('rustc', path=env['PATH'])
    if not cargo or not rustc:
        raise RuntimeError('MISSING_RUST_TOOLCHAIN')
    rust_version = command([rustc, '--version'], ROOT, env).decode().strip()
    cargo_version = command([cargo, '--version'], ROOT, env).decode().strip()
    if not rust_version.startswith('rustc 1.95.0 ') or not cargo_version.startswith('cargo 1.95.0 '):
        raise RuntimeError('RUST_VERSION_MISMATCH')
    runner.update(rustc=rust_version, cargo=cargo_version)
    prepare(source)
    cwd = source / 'codex-rs'
    target_dir = Path(os.environ['RUNNER_TEMP']) / 'codex-safe-target'
    if target_dir.exists():
        raise RuntimeError('TARGET_DIR_NOT_FRESH')
    env['CARGO_TARGET_DIR'] = str(target_dir)
    dist = ROOT / 'dist'
    if dist.exists():
        raise RuntimeError('ARTIFACT_DIR_NOT_FRESH')
    with tempfile.TemporaryDirectory(prefix='codex-safe-synthetic-', dir=os.environ['RUNNER_TEMP']) as td:
        root = Path(td)
        (root / '.synthetic-only').write_text('synthetic only', encoding='utf-8')
        env['CODEX_HOME'] = str(root / 'empty-home')
        (root / 'empty-home').mkdir()
        base = [cargo, 'test', '--locked', '--release', '--target', TARGET]
        command(base + ['-p','codex-http-client','--lib'], cwd, env)
        STEPS.append('upstream_http_client_lib_PASS')
        command(base + ['-p','codex-cli','--lib','--no-run'], cwd, env)
        STEPS.append('codex_cli_lib_compile_PASS')
        raw = command(base + ['-p','codex-app-server','--test','worker_safe_logging','--no-run','--message-format=json'], cwd, env)
        executables = []
        for line in raw.splitlines():
            try:item = json.loads(line)
            except ValueError:continue
            if item.get('reason') == 'compiler-artifact' and item.get('target',{}).get('name') == 'worker_safe_logging' and item.get('executable'):
                executables.append(Path(item['executable']))
        if len(set(executables)) != 1:
            raise RuntimeError('SYNTHETIC_BINARY_NOT_FOUND')
        exe = executables[0].resolve()
        if not exe.is_relative_to(target_dir.resolve()):
            raise RuntimeError('SYNTHETIC_BINARY_PATH_DENIED')
        seed = secrets.token_hex(16)
        values = markers(seed)
        test_env = dict(env, SAFE_LOGGING_SEED=seed, SAFE_LOGGING_ROOT=str(root))
        p = subprocess.run([str(exe), '--exact', 'worker_safe_logging', '--test-threads=1'], cwd=cwd, env=test_env, capture_output=True, timeout=90)
        if contains_marker(p.stdout + p.stderr, values):
            raise RuntimeError('SYNTHETIC_STDIO_LEAK')
        scan_tree(root, values)
        if p.returncode:
            raise RuntimeError('SYNTHETIC_TEST_FAILED_NO_PAYLOAD_EXPORTED')
        summary = json.loads((root / 'summary.json').read_text())
        if summary.get('secret_matches') != 0 or summary.get('request_completed_events') != 2 or summary.get('wal_shm_checked') is not True:
            raise RuntimeError('SYNTHETIC_SUMMARY_INVALID')
        STEPS.append('synthetic_http_sqlite_wal_shm_stdio_PASS')
        command([cargo,'build','--locked','--release','--target',TARGET,'-p','codex-cli','--bin','codex'], cwd, env)
        STEPS.append('codex_cli_release_build_PASS')
        binary = target_dir / TARGET / 'release/codex.exe'
        if not binary.is_file():
            raise RuntimeError('RELEASE_BINARY_MISSING')
        dist.mkdir()
        shutil.copyfile(binary, dist / 'codex-safe.exe')
        shutil.copyfile(exe, dist / 'safe-logging-probe.exe')
        provenance = dict(upstream_repository='https://github.com/openai/codex', source_commit=COMMIT,
                          source_tag='rust-v0.153.4', recipe_commit=os.environ.get('GITHUB_SHA'),
                          workflow_ref=os.environ.get('GITHUB_WORKFLOW_REF'), run_id=os.environ.get('GITHUB_RUN_ID'),
                          run_attempt=os.environ.get('GITHUB_RUN_ATTEMPT'), target=TARGET,
                          patch_sha256=sha(ROOT/'logging.patch'), recipe_files=recipe_hashes,
                          runner=runner, test_summary=summary, checks=STEPS,
                          binary_sha256=sha(dist/'codex-safe.exe'), probe_sha256=sha(dist/'safe-logging-probe.exe'), live_auth_operations=0, model_turns=0,
                          attestation='NOT_GENERATED_BY_THIS_WORKFLOW')
        (dist/'provenance.json').write_text(json.dumps(provenance,indent=2),encoding='utf-8')
        (dist/'SHA256SUMS').write_text('\n'.join(f'{sha(dist/n)}  {n}' for n in ('codex-safe.exe','safe-logging-probe.exe','provenance.json'))+'\n',encoding='ascii')
        scan_tree(dist, values)
        # Only the synthetic harness, product binary and provenance; no DB or raw logs.
        if {p.name for p in dist.iterdir()} != {'codex-safe.exe','safe-logging-probe.exe','provenance.json','SHA256SUMS'}:
            raise RuntimeError('ARTIFACT_ALLOWLIST_FAILED')
    print(json.dumps({'result':'PASS','checks':STEPS,'artifact_files':4}))

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('mode', choices=['run','verify-bundle'])
    parser.add_argument('--source', type=Path)
    args = parser.parse_args()
    if args.mode == 'verify-bundle':
        verify_bundle(); print('RECIPE_INTEGRITY_PASS')
    else:
        if args.source is None:raise RuntimeError('SOURCE_REQUIRED')
        run(args.source.resolve())

if __name__ == '__main__':
    try:main()
    except BaseException as exc:
        # Only our fixed diagnostic vocabulary, never OS/provider exception text.
        text = str(exc)
        print(text if re.fullmatch(r'[A-Z0-9_]{3,160}',text) else 'FAIL_CLOSED_NO_PAYLOAD_EXPORTED')
        sys.exit(1)
