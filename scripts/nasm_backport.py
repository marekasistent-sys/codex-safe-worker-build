"""Exact single-file upstream NASM backport. No network, credentials or retries."""
import argparse
import hashlib
from pathlib import Path
import subprocess
import sys

BASE='4a56d66ed9626d5a3ded5414c9d8b7f1a48ce065'
FIX='ace0078261329437224d4875b289647279a41fa1'
FILE='nasmlib/file.c'
PRE_BLOB='c8088326ad778931eda4081db9e9f4a63c59511b'
PRE_HASH='cecdbdb8652c0ae4cae9242920bb832faf43f451d6b4d92ff36872db4fa8805d'
POST_HASH='ddf6f4dd8bcfc572df1f3e588298bba72b19bebccf66a1a2ca20a256576b4767'
PATCH_HASH='591d8b3fb2d85465b58212ac0eb7a4a31273a856a815c08031aaafdc5d95b863'
PREIMAGE=b'#ifdef _WIN32\n#include <wchar.h>\n#include <stringapiset.h>'
PATCH=Path(__file__).resolve().parents[1]/'nasm-windows-sdk.patch'

def digest(data):return hashlib.sha256(data).hexdigest()

REASONS=frozenset(('NASM_BASE_COMMIT_MISMATCH','NASM_PATCH_HASH_MISMATCH',
    'NASM_UNEXPECTED_INDEX_CHANGE','NASM_CANONICAL_BLOB_MISMATCH',
    'NASM_EXACT_PREIMAGE_MISMATCH','NASM_EXACT_POSTIMAGE_MISMATCH',
    'NASM_BACKPORT_SCOPE_MISMATCH','NASM_BACKPORT_REQUIRES_CLEAN_SOURCE',
    'NASM_GIT_APPLY_CHECK_FAILED','NASM_GIT_APPLY_FAILED',
    'NASM_BACKPORT_GIT_FAILED','NASM_LINE_ENDINGS_REJECTED'))

def safe_reason(error):
    # Never print exception text unless it is an exact closed-set constant.
    return error.args[0] if type(error) is RuntimeError and len(error.args)==1 and type(error.args[0]) is str and error.args[0] in REASONS else 'NASM_BACKPORT_UNKNOWN_FAILURE'

def normalized(data):
    # Permit only uniform LF or uniform CRLF; reject mixed or bare CR.
    if b'\r' in data:
        if data.count(b'\r\n')!=data.count(b'\n') or data.count(b'\r')!=data.count(b'\n'):
            raise RuntimeError('NASM_LINE_ENDINGS_REJECTED')
        return data.replace(b'\r\n',b'\n')
    return data

def git(source,*args,reason='NASM_BACKPORT_GIT_FAILED'):
    r=subprocess.run(['git','--no-optional-locks','-C',str(source),*args],capture_output=True,timeout=30)
    if r.returncode:raise RuntimeError(reason)
    return r.stdout

def preimage(data):
    data=normalized(data)
    if digest(data)!=PRE_HASH or data.count(PREIMAGE)!=1:
        raise RuntimeError('NASM_EXACT_PREIMAGE_MISMATCH')

def postimage(data):
    data=normalized(data)
    if digest(data)!=POST_HASH:
        raise RuntimeError('NASM_EXACT_POSTIMAGE_MISMATCH')

def identity(source):
    if git(source,'rev-parse','HEAD').decode().strip()!=BASE:
        raise RuntimeError('NASM_BASE_COMMIT_MISMATCH')
    if digest(PATCH.read_bytes())!=PATCH_HASH:
        raise RuntimeError('NASM_PATCH_HASH_MISMATCH')
    if git(source,'rev-parse','HEAD:'+FILE).strip()!=PRE_BLOB.encode():
        raise RuntimeError('NASM_CANONICAL_BLOB_MISMATCH')
    canonical=git(source,'show','HEAD:'+FILE)
    if hashlib.sha1(b'blob '+str(len(canonical)).encode()+b'\0'+canonical).hexdigest()!=PRE_BLOB or digest(canonical)!=PRE_HASH:
        raise RuntimeError('NASM_CANONICAL_BLOB_MISMATCH')
    preimage(canonical)
    if git(source,'diff','--cached','--name-only').strip():
        raise RuntimeError('NASM_UNEXPECTED_INDEX_CHANGE')

def verify(source):
    identity(source)
    if git(source,'diff','--no-ext-diff','--name-only','HEAD').decode().splitlines()!=[FILE]:
        raise RuntimeError('NASM_BACKPORT_SCOPE_MISMATCH')
    postimage((source/FILE).read_bytes())
    git(source,'diff','--check')

def apply(source):
    identity(source)
    if git(source,'status','--porcelain','--untracked-files=all').strip():
        raise RuntimeError('NASM_BACKPORT_REQUIRES_CLEAN_SOURCE')
    preimage((source/FILE).read_bytes())
    git(source,'apply','--check','--whitespace=error',str(PATCH),reason='NASM_GIT_APPLY_CHECK_FAILED')
    git(source,'apply','--whitespace=error',str(PATCH),reason='NASM_GIT_APPLY_FAILED')
    verify(source)

def main():
    p=argparse.ArgumentParser()
    p.add_argument('mode',choices=['apply','verify'])
    p.add_argument('--source',type=Path,required=True)
    a=p.parse_args()
    (apply if a.mode=='apply' else verify)(a.source.resolve())
    print('NASM_EXACT_UPSTREAM_BACKPORT_PASS')

if __name__=='__main__':
    try:main()
    except Exception as error:
        print('NASM_BACKPORT_FAIL_CLOSED')
        print(safe_reason(error))
        sys.exit(1)
