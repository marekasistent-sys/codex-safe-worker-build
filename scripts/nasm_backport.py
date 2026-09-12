"""Exact single-file upstream NASM backport. No network, credentials or retries."""
import argparse
import hashlib
from pathlib import Path
import subprocess
import sys

BASE='4a56d66ed9626d5a3ded5414c9d8b7f1a48ce065'
FIX='ace0078261329437224d4875b289647279a41fa1'
FILE='nasmlib/file.c'
PRE_HASH='cecdbdb8652c0ae4cae9242920bb832faf43f451d6b4d92ff36872db4fa8805d'
POST_HASH='969abc93302ab7bc06a14e4d11e1ae234523e1b569eb3c7e6a6add2f891597f1'
PATCH_HASH='591d8b3fb2d85465b58212ac0eb7a4a31273a856a815c08031aaafdc5d95b863'
PREIMAGE=b'#ifdef _WIN32\n#include <wchar.h>\n#include <stringapiset.h>'
PATCH=Path(__file__).resolve().parents[1]/'nasm-windows-sdk.patch'

def digest(data):return hashlib.sha256(data).hexdigest()

def git(source,*args):
    r=subprocess.run(['git','--no-optional-locks','-C',str(source),*args],capture_output=True,timeout=30)
    if r.returncode:raise RuntimeError('NASM_BACKPORT_GIT_FAILED')
    return r.stdout

def preimage(data):
    if digest(data)!=PRE_HASH or data.count(PREIMAGE)!=1:
        raise RuntimeError('NASM_EXACT_PREIMAGE_MISMATCH')

def postimage(data):
    if digest(data)!=POST_HASH:
        raise RuntimeError('NASM_EXACT_POSTIMAGE_MISMATCH')

def identity(source):
    if git(source,'rev-parse','HEAD').decode().strip()!=BASE:
        raise RuntimeError('NASM_BASE_COMMIT_MISMATCH')
    if digest(PATCH.read_bytes())!=PATCH_HASH:
        raise RuntimeError('NASM_PATCH_HASH_MISMATCH')
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
    git(source,'apply','--check','--whitespace=error',str(PATCH))
    git(source,'apply','--whitespace=error',str(PATCH))
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
    except Exception:
        print('NASM_BACKPORT_FAIL_CLOSED')
        sys.exit(1)
