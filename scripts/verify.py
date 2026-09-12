"""Build recipe supervisor. No credentials, client auth, model or remote dispatch API."""
import argparse
from contextlib import contextmanager
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
from http_test_failures import failure_names
from safe_cargo_json import summarize as cargo_json_summary
from safe_cargo_stderr import classify_stderr

ROOT = Path(__file__).resolve().parents[1]
COMMIT = '3d2ee51ca2d5db578f328aa75e20aa22c0197c9a'
TARGET = 'x86_64-pc-windows-msvc'
SOURCE = Path('codex-rs/http-client/src/client.rs')
ORIGINAL_BLOB = '9cda749aa27581101a4f718644151f88c508100d'
STEPS = []
PHASES = frozenset(('RUST_VERSION_PROBE','CARGO_VERSION_PROBE','SOURCE_PREPARE',
    'HTTP_CLIENT_LIB_COMPILE','HTTP_CLIENT_LIB_TEST','CODEX_CLI_LIB_COMPILE','SYNTHETIC_TEST_COMPILE',
    'SYNTHETIC_TEST','CODEX_RELEASE_BUILD'))

@contextmanager
def phase(name):
    if name not in PHASES:
        raise RuntimeError('DIAGNOSTIC_PHASE_INVALID')
    print(name+'_START', flush=True)
    try:
        yield
    except BaseException:
        # No exception value, command, path, stdout or stderr is exported.
        raise RuntimeError(name+'_FAILED') from None
    print(name+'_PASS', flush=True)

def classify(data):
    data=data.lower()
    patterns=(('LOCKFILE_REJECTED',(b'lock file',b'needs to be updated')),
              ('DEPENDENCY_RESOLUTION_FAILED',(b'failed to select a version',)),
              ('DEPENDENCY_DOWNLOAD_FAILED',(b'failed to download',)),
              ('GIT_FETCH_FAILED',(b'failed to fetch',)),
              ('LINKER_FAILED',(b'linking with',b'failed')),
              ('BUILD_SCRIPT_FAILED',(b'failed to run custom build command',)),
              ('RUST_COMPILER_ERROR',(b'error[e',)),
              ('TEST_ASSERTION_FAILED',(b'panicked at',)),
              ('LIB_TARGET_MISSING',(b'no library targets found',)))
    return [label for label,terms in patterns if all(t in data for t in terms)] or ['UNKNOWN']

def phase_command(name,args,cwd,env):
    with phase(name):
        if name=='HTTP_CLIENT_LIB_TEST':
            return command(args,cwd,env,http_test_names=True)
        return command(args,cwd,env)

def http_test_binary(raw,cwd,target_dir):
    candidates=[]
    expected_source=(cwd/'http-client/src/lib.rs').resolve()
    for line in raw.splitlines():
        try:item=json.loads(line)
        except ValueError:continue
        if not isinstance(item,dict) or item.get('reason')!='compiler-artifact':continue
        target=item.get('target',{})
        if target.get('name')!='codex_http_client' or target.get('kind')!=['lib'] or item.get('profile',{}).get('test') is not True:continue
        if Path(target.get('src_path','')).resolve()!=expected_source:continue
        if item.get('executable'):candidates.append(Path(item['executable']))
    if len(candidates)!=1:raise RuntimeError('HTTP_TEST_BINARY_INVALID')
    exe=candidates[0]
    expected_dir=(target_dir/TARGET/'release/deps').resolve()
    if not exe.is_absolute() or exe.resolve().parent!=expected_dir or not re.fullmatch(r'codex_http_client-[0-9a-f]+\.exe',exe.name):
        raise RuntimeError('HTTP_TEST_BINARY_INVALID')
    # Reject reparse traversal even when its resolved destination is in target_dir.
    for p in (exe,*exe.parents):
        if p.is_symlink() or (hasattr(p,'is_junction') and p.is_junction()):
            raise RuntimeError('HTTP_TEST_BINARY_INVALID')
    if not exe.is_file():raise RuntimeError('HTTP_TEST_BINARY_INVALID')
    return exe.resolve()

def validate_http_client(cargo,cwd,env,target_dir):
    with phase('HTTP_CLIENT_LIB_COMPILE'):
        raw=command([cargo,'test','--locked','--release','--target',TARGET,
                     '-p','codex-http-client','--lib','--no-run','--message-format=json'],cwd,env)
        try:exe=http_test_binary(raw,cwd,target_dir)
        except Exception:
            print(json.dumps({'diagnostic_categories':['UNKNOWN']}),flush=True)
            raise RuntimeError('HTTP_TEST_BINARY_INVALID') from None
    STEPS.append('upstream_http_client_lib_compile_PASS')
    # Direct execution: Cargo is not invoked a second time, so no implicit rebuild.
    phase_command('HTTP_CLIENT_LIB_TEST',[str(exe)],cwd,env)
    STEPS.append('upstream_http_client_lib_PASS')

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

def command(args, cwd, env=None, timeout=7200, *, http_test_names=False):
    try:
        p = subprocess.run(args, cwd=cwd, env=env, capture_output=True, timeout=timeout)
    except (OSError,subprocess.TimeoutExpired):
        print(json.dumps({'failed_tests':None,'failed_test_count':None} if http_test_names else
                         {'diagnostic_categories':['UNKNOWN']}),flush=True)
        raise
    if p.returncode:
        # No arbitrary exception, compiler output, stdout, environment or payload export.
        if http_test_names:
            print(json.dumps(failure_names(p.stdout)),flush=True)
        elif '--message-format=json' in args:
            print(json.dumps(cargo_json_summary(p.stdout)),flush=True)
        else:
            print(json.dumps({'diagnostic_categories':classify(p.stdout+p.stderr)}),flush=True)
        raise RuntimeError('COMMAND_FAILED')
    return p.stdout

def verify_bundle():
    manifest = json.loads((ROOT / 'recipe-files.json').read_text(encoding='utf-8'))
    for name, digest in manifest.items():
        p = ROOT / name
        if Path(name).is_absolute() or '..' in Path(name).parts or not p.is_file() or p.is_symlink() or sha(p) != digest:
            raise RuntimeError('RECIPE_INTEGRITY_FAILED')
    return manifest

def pristine_check(source):
    if command(['git', 'rev-parse', 'HEAD'], source).decode().strip() != COMMIT:
        raise RuntimeError('SOURCE_COMMIT_MISMATCH')
    if command(['git', 'status', '--porcelain'], source).strip():
        raise RuntimeError('SOURCE_NOT_CLEAN')
    original_check((source / SOURCE).read_bytes())

def prepare(source,install_synthetic=True):
    pristine_check(source)
    patch = ROOT / 'logging.patch'
    command(['git', 'apply', '--check', '--whitespace=error', str(patch)], source)
    command(['git', 'apply', '--whitespace=error', str(patch)], source)
    command(['git', 'diff', '--check'], source)
    changed = command(['git', 'diff', '--name-only'], source).decode().splitlines()
    if changed != [SOURCE.as_posix()]:
        raise RuntimeError('PATCH_SCOPE_CHANGED')
    if b'headers = ?response.headers(),' in (source / SOURCE).read_bytes():
        raise RuntimeError('HEADER_LOGGING_REMAINS')
    if install_synthetic:install_synthetic_test(source)

def install_synthetic_test(source):
    destination = source / 'codex-rs/app-server/tests/worker_safe_logging.rs'
    if destination.exists():
        raise RuntimeError('SYNTHETIC_TEST_COLLISION')
    shutil.copyfile(ROOT / 'tests/worker_safe_logging.rs', destination)

def compile_variant(label,cargo,cwd,env,target_dir,*,stderr_diagnostics=False):
    if label not in ('PRISTINE','PATCHED'):raise RuntimeError('DIAGNOSTIC_PHASE_INVALID')
    if target_dir.exists():raise RuntimeError('TARGET_DIR_NOT_FRESH')
    build_env=dict(env,CARGO_TARGET_DIR=str(target_dir))
    args=[cargo,'test','--locked','--release','--target',TARGET,
          '-p','codex-http-client','--lib','--no-run','--message-format=json']
    try:
        result=subprocess.run(args,cwd=cwd,env=build_env,capture_output=True,timeout=7200)
    except (OSError,subprocess.TimeoutExpired):
        print(json.dumps(cargo_json_summary(b'')),flush=True)
        if stderr_diagnostics:print('UNKNOWN',flush=True)
        print(label+'_HTTP_COMPILE_FAIL',flush=True)
        # Do not start another compile after an uncertain process outcome.
        raise RuntimeError('HTTP_DIFFERENTIAL_COMPILE_FAILED') from None
    ok=result.returncode==0;exe=None
    if ok:
        try:exe=http_test_binary(result.stdout,cwd,target_dir)
        except Exception:ok=False
    if not ok:
        print(json.dumps(cargo_json_summary(result.stdout)),flush=True)
        if stderr_diagnostics:print(classify_stderr(result.stderr),flush=True)
    print(label+'_HTTP_COMPILE_'+('PASS' if ok else 'FAIL'),flush=True)
    return ok,exe

def differential_http_compile(source,cargo,env,target_dir):
    pristine_check(source)
    cwd=source/'codex-rs'
    lock_hash=sha(cwd/'Cargo.lock')
    pristine_dir=target_dir.with_name(target_dir.name+'-pristine')
    pristine_ok,_=compile_variant('PRISTINE',cargo,cwd,env,pristine_dir)
    # Recheck clean source after compilation; do not hide a build-script mutation.
    pristine_check(source)
    if sha(cwd/'Cargo.lock')!=lock_hash:raise RuntimeError('RECIPE_INTEGRITY_FAILED')
    prepare(source,install_synthetic=False)
    patched_hash=sha(source/SOURCE)
    patched_ok,exe=compile_variant('PATCHED',cargo,cwd,env,target_dir)
    if sha(source/SOURCE)!=patched_hash:raise RuntimeError('PATCH_SCOPE_CHANGED')
    if sha(cwd/'Cargo.lock')!=lock_hash:raise RuntimeError('RECIPE_INTEGRITY_FAILED')
    if command(['git','diff','--name-only'],source).decode().splitlines()!=[SOURCE.as_posix()]:
        raise RuntimeError('PATCH_SCOPE_CHANGED')
    if not pristine_ok or not patched_ok:raise RuntimeError('HTTP_DIFFERENTIAL_COMPILE_FAILED')
    STEPS.extend(('pristine_http_compile_PASS','patched_http_compile_PASS'))
    return exe

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

def pristine_diagnostic(source,cargo,env,target_dir):
    pristine_check(source)
    lock_hash=sha(source/'codex-rs/Cargo.lock')
    ok,_=compile_variant('PRISTINE',cargo,source/'codex-rs',env,target_dir,stderr_diagnostics=True)
    pristine_check(source)
    if sha(source/'codex-rs/Cargo.lock')!=lock_hash:raise RuntimeError('RECIPE_INTEGRITY_FAILED')
    if not ok:raise RuntimeError('PRISTINE_DIAGNOSTIC_FAILED')

def run(source,*,pristine_only=False,reconcile_lock=False):
    if os.environ.get('GITHUB_ACTIONS') != 'true':
        raise RuntimeError('REMOTE_RUN_REQUIRES_EXPLICITLY_DISPATCHED_ACTION')
    recipe_hashes = verify_bundle()
    runner = {} if reconcile_lock else json.loads((ROOT / 'runner.json').read_text(encoding='utf-8-sig'))
    env = child_env()
    cargo = shutil.which('cargo', path=env['PATH'])
    rustc = shutil.which('rustc', path=env['PATH'])
    if not cargo or not rustc:
        raise RuntimeError('MISSING_RUST_TOOLCHAIN')
    rust_version = phase_command('RUST_VERSION_PROBE',[rustc, '--version'], ROOT, env).decode().strip()
    cargo_version = phase_command('CARGO_VERSION_PROBE',[cargo, '--version'], ROOT, env).decode().strip()
    if not rust_version.startswith('rustc 1.95.0 ') or not cargo_version.startswith('cargo 1.95.0 '):
        raise RuntimeError('RUST_VERSION_MISMATCH')
    runner.update(rustc=rust_version, cargo=cargo_version)
    if reconcile_lock:
        from reconcile_lockfile import run as reconcile
        reconcile(source,cargo,env)
        return
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
        if pristine_only:
            pristine_diagnostic(source,cargo,env,target_dir)
            return
        base = [cargo, 'test', '--locked', '--release', '--target', TARGET]
        exe_http=differential_http_compile(source,cargo,env,target_dir)
        phase_command('HTTP_CLIENT_LIB_TEST',[str(exe_http)],cwd,env)
        STEPS.append('upstream_http_client_lib_PASS')
        install_synthetic_test(source)
        phase_command('CODEX_CLI_LIB_COMPILE',base + ['-p','codex-cli','--lib','--no-run'], cwd, env)
        STEPS.append('codex_cli_lib_compile_PASS')
        raw = phase_command('SYNTHETIC_TEST_COMPILE',base + ['-p','codex-app-server','--test','worker_safe_logging','--no-run','--message-format=json'], cwd, env)
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
        with phase('SYNTHETIC_TEST'):
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
        phase_command('CODEX_RELEASE_BUILD', [cargo,'build','--locked','--release','--target',TARGET,'-p','codex-cli','--bin','codex'], cwd, env)
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
    parser.add_argument('--pristine-only',action='store_true')
    parser.add_argument('--reconcile-lockfile',action='store_true')
    args = parser.parse_args()
    if args.mode == 'verify-bundle':
        verify_bundle(); print('RECIPE_INTEGRITY_PASS')
    else:
        if args.source is None:raise RuntimeError('SOURCE_REQUIRED')
        if args.pristine_only and args.reconcile_lockfile:raise RuntimeError('DIAGNOSTIC_PHASE_INVALID')
        run(args.source.resolve(),pristine_only=args.pristine_only,reconcile_lock=args.reconcile_lockfile)


SAFE_ERRORS=frozenset(('ARTIFACT_ALLOWLIST_FAILED','ARTIFACT_DIR_NOT_FRESH','COMMAND_FAILED','DIAGNOSTIC_PHASE_INVALID','HEADER_LOGGING_REMAINS','MISSING_RUST_TOOLCHAIN','PATCH_SCOPE_CHANGED','PINNED_SOURCE_FRAGMENT_MISMATCH','RECIPE_INTEGRITY_FAILED','RELEASE_BINARY_MISSING','REMOTE_RUN_REQUIRES_EXPLICITLY_DISPATCHED_ACTION','REPARSE_DENIED','RUST_VERSION_MISMATCH','SOURCE_COMMIT_MISMATCH','SOURCE_NOT_CLEAN','SOURCE_REQUIRED','SYNTHETIC_BINARY_NOT_FOUND','SYNTHETIC_BINARY_PATH_DENIED','SYNTHETIC_SECRET_DETECTED','SYNTHETIC_STDIO_LEAK','SYNTHETIC_SUMMARY_INVALID','SYNTHETIC_TEST_COLLISION','SYNTHETIC_TEST_FAILED_NO_PAYLOAD_EXPORTED','TARGET_DIR_NOT_FRESH','UNEXPECTED_EVENT_COUNT',)) | frozenset(n+'_FAILED' for n in PHASES)
def safe_error(exc):
    lock_errors=frozenset(('LOCK_STRUCTURE_REJECTED','LOCK_DIAGNOSTIC_PYTHON_UNSUPPORTED',
        'LOCK_RECONCILIATION_COMMAND_FAILED','LOCK_ARCHIVE_SCOPE_REJECTED',
        'LOCK_WORKSPACE_IDENTITY_REJECTED','LOCK_NON_LOCKFILE_CHANGE_REJECTED','LOCK_RECONCILIATION_REJECTED'))
    if type(exc) is RuntimeError and len(exc.args)==1 and type(exc.args[0]) is str and exc.args[0] in lock_errors:
        return exc.args[0]
    if type(exc) is RuntimeError and exc.args==('PRISTINE_DIAGNOSTIC_FAILED',):
        return 'PRISTINE_DIAGNOSTIC_FAILED'
    if type(exc) is RuntimeError and exc.args==('HTTP_DIFFERENTIAL_COMPILE_FAILED',):
        return 'HTTP_DIFFERENTIAL_COMPILE_FAILED'
    if type(exc) is RuntimeError and len(exc.args)==1 and type(exc.args[0]) is str and exc.args[0] in SAFE_ERRORS:
        return exc.args[0]
    return 'FAIL_CLOSED_NO_PAYLOAD_EXPORTED'

if __name__ == '__main__':
    try:main()
    except BaseException as exc:
        # Only our fixed diagnostic vocabulary, never OS/provider exception text.
        print(safe_error(exc))
        sys.exit(1)
