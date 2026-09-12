"""Disposable Cargo metadata reconciliation. No build, auth or artifact upload."""
import difflib
import hashlib
import io
import json
from pathlib import Path
import subprocess
import tarfile
import tempfile

def compare(before,after,workspace_names):
    def index(doc):
        result={}
        for p in doc.get('package',[]):
            key=(p['name'],p['version'],p.get('source'))
            if key in result:raise RuntimeError('LOCK_STRUCTURE_REJECTED')
            result[key]=p
        return result
    old=index(before);new=index(after)
    internal=lambda p:p['name'] in workspace_names and 'source' not in p
    oi={p['name']:p for p in old.values() if internal(p)}
    ni={p['name']:p for p in new.values() if internal(p)}
    oe={k:p for k,p in old.items() if not internal(p)}
    ne={k:p for k,p in new.items() if not internal(p)}
    def byname(packages,field):
        result={}
        for p in packages.values():result.setdefault(p['name'],set()).add(p.get(field))
        return result
    common=set(p['name'] for p in oe.values())&set(p['name'] for p in ne.values())
    versions_changed=any(byname(oe,'version')[n]!=byname(ne,'version')[n] for n in common)
    sources_changed=any(byname(oe,'source')[n]!=byname(ne,'source')[n] for n in common)
    checksums_changed=any(byname(oe,'checksum')[n]!=byname(ne,'checksum')[n] for n in common) or any(
        oe[k].get('checksum')!=ne[k].get('checksum') for k in oe.keys()&ne.keys())
    added=bool(set(ne)-set(oe));removed=bool(set(oe)-set(ne))
    changed_internal=sorted(n for n in set(oi)&set(ni) if oi[n]['version']!=ni[n]['version'])
    changed_entries=len(set(oi)^set(ni))+sum(oi[n]!=ni[n] for n in set(oi)&set(ni))
    changed_entries+=len(set(oe)^set(ne))+sum(oe[k]!=ne[k] for k in set(oe)&set(ne))
    summary=dict(changed_package_entries=changed_entries,workspace_version_changes=changed_internal,
        external_version_changed=versions_changed,external_source_changed=sources_changed,
        external_checksum_changed=checksums_changed,external_added=added,external_removed=removed)
    external_equal=oe==ne
    allowed=external_equal and set(oi)==set(ni) and bool(changed_internal)
    allowed=allowed and len(oi)==sum(internal(p) for p in old.values()) and len(ni)==sum(internal(p) for p in new.values())
    allowed=allowed and {k:v for k,v in before.items() if k!='package'}=={k:v for k,v in after.items() if k!='package'}
    for name in oi.keys()&ni.keys():
        expected=dict(oi[name])
        if name in changed_internal:
            allowed=allowed and expected['version']=='0.0.0' and ni[name]['version']=='0.153.4'
            expected['version']='0.153.4'
        if 'dependencies' in expected:
            replacements={n+' 0.0.0':n+' 0.153.4' for n in changed_internal}
            expected['dependencies']=[replacements.get(d,d) for d in expected['dependencies']]
        allowed=allowed and expected==ni[name]
    return summary,allowed

def run(source,cargo,env):
    try:import tomllib
    except ImportError:raise RuntimeError('LOCK_DIAGNOSTIC_PYTHON_UNSUPPORTED') from None
    from verify import pristine_check,COMMIT
    pristine_check(source)
    def invoke(args,cwd):
        try:r=subprocess.run(args,cwd=cwd,env=env,capture_output=True,timeout=600)
        except Exception:raise RuntimeError('LOCK_RECONCILIATION_COMMAND_FAILED') from None
        if r.returncode:raise RuntimeError('LOCK_RECONCILIATION_COMMAND_FAILED')
        return r.stdout
    archive=invoke(['git','archive','--format=tar',COMMIT],source)
    with tempfile.TemporaryDirectory(prefix='codex-lock-disposable-') as td:
        copy=Path(td)/'source';copy.mkdir()
        with tarfile.open(fileobj=io.BytesIO(archive)) as tar:
            regular=[];license_link=None
            for m in tar.getmembers():
                if not (copy/m.name).resolve().is_relative_to(copy.resolve()):
                    raise RuntimeError('LOCK_ARCHIVE_SCOPE_REJECTED')
                if m.issym() and m.name=='codex-rs/vendor/bubblewrap/LICENSE':
                    data=m.linkname.encode()
                    blob=hashlib.sha1(b'blob '+str(len(data)).encode()+b'\0'+data).hexdigest()
                    if blob!='d24842f3cdcf2e447f9a7a26fa387ad63f5c4b91':raise RuntimeError('LOCK_ARCHIVE_SCOPE_REJECTED')
                    license_link=(copy/m.name,data)
                elif m.isfile() or m.isdir():regular.append(m)
                else:raise RuntimeError('LOCK_ARCHIVE_SCOPE_REJECTED')
            tar.extractall(copy,members=regular,filter='data')
            # Match Git's normal Windows core.symlinks=false checkout representation.
            if license_link:license_link[0].write_bytes(license_link[1])
        cwd=copy/'codex-rs';lock=cwd/'Cargo.lock'
        before_bytes=lock.read_bytes()
        baseline={p.relative_to(copy):hashlib.sha256(p.read_bytes()).digest() for p in copy.rglob('*') if p.is_file()}
        diagnostic_env=dict(env,CARGO_TARGET_DIR=str(Path(td)/'unused-target'),CODEX_HOME=str(Path(td)/'empty-home'))
        # metadata resolves while retaining the existing lock where possible;
        # generate-lockfile/update could unnecessarily upgrade dependencies.
        try:r=subprocess.run([cargo,'metadata','--format-version','1'],cwd=cwd,env=diagnostic_env,capture_output=True,timeout=600)
        except Exception:raise RuntimeError('LOCK_RECONCILIATION_COMMAND_FAILED') from None
        if r.returncode:raise RuntimeError('LOCK_RECONCILIATION_COMMAND_FAILED')
        metadata=json.loads(r.stdout)
        workspace=set(metadata['workspace_members']);names=set()
        for p in metadata['packages']:
            if p['id'] not in workspace:continue
            manifest=Path(p['manifest_path']).resolve()
            if p.get('source') is not None or not manifest.is_relative_to(cwd.resolve()):
                raise RuntimeError('LOCK_WORKSPACE_IDENTITY_REJECTED')
            package=tomllib.loads(manifest.read_text(encoding='utf-8'))['package']
            if package['name']!=p['name']:raise RuntimeError('LOCK_WORKSPACE_IDENTITY_REJECTED')
            version=package.get('version')
            if version=={'workspace':True} and p['version']=='0.153.4':names.add(p['name'])
        # Fixed-version local members are treated as external and must stay exact.
        current={p.relative_to(copy):hashlib.sha256(p.read_bytes()).digest() for p in copy.rglob('*') if p.is_file()}
        delta={p for p in baseline.keys()|current.keys() if baseline.get(p)!=current.get(p)}
        if delta!={Path('codex-rs/Cargo.lock')}:raise RuntimeError('LOCK_NON_LOCKFILE_CHANGE_REJECTED')
        after_bytes=lock.read_bytes()
        summary,allowed=compare(tomllib.loads(before_bytes.decode()),tomllib.loads(after_bytes.decode()),names)
        print(json.dumps(summary),flush=True)
        if not allowed:raise RuntimeError('LOCK_RECONCILIATION_REJECTED')
        patch=''.join(difflib.unified_diff(before_bytes.decode().splitlines(keepends=True),
                    after_bytes.decode().splitlines(keepends=True),fromfile='a/codex-rs/Cargo.lock',tofile='b/codex-rs/Cargo.lock')).encode()
        # Disposable candidate only. No artifact publication or canonical application.
        (Path(td)/'release-lockfile.patch').write_bytes(patch)
        print(json.dumps({'lockfile_patch_sha256':hashlib.sha256(patch).hexdigest()}),flush=True)
    pristine_check(source)
