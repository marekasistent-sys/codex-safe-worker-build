"""In-memory stderr classification; return one fixed constant, never matched text."""
import re

RULES=(
    ('LOCKFILE_REJECTED',(rb'lock (?:file|file at)[^\r\n]*needs to be updated[^\r\n]*--locked',
                          rb'cannot update the lock file[^\r\n]*--locked')),
    ('DEPENDENCY_RESOLUTION_FAILED',(rb'failed to select a version for',rb'no matching package named',
                                     rb'failed to select a version for the requirement')),
    ('DEPENDENCY_DOWNLOAD_FAILED',(rb'failed to download',rb'download of [^\r\n]+ failed')),
    ('GIT_FETCH_FAILED',(rb'failed to fetch into',rb'failed to clone into',rb'unable to update [^\r\n]*git')),
    ('PACKAGE_OR_TARGET_SELECTION_ERROR',(rb'package id specification [^\r\n]* did not match any packages',
        rb'no library targets found',rb'no test target named',rb'no bin target named',rb'no targets specified in the manifest')),
    ('TARGET_NOT_INSTALLED',(rb'the [^\r\n]+ target may not be installed',rb'target [^\r\n]+ is not installed')),
    ('RUST_VERSION_INCOMPATIBLE',(rb'rustc [^\r\n]+ is not supported by the following packages',
                                 rb'requires rustc [0-9]',rb'requires rust [0-9]')),
    ('BUILD_SCRIPT_FAILED',(rb'failed to run custom build command for',)),
    ('LINKER_NOT_FOUND',(rb'linker [^\r\n]+ not found',)),
    ('LINKER_FAILED',(rb'linking with [^\r\n]+ failed',)),
    ('CARGO_CONFIG_ERROR',(rb'could not load cargo configuration',rb'failed to parse manifest at',
                           rb'failed to parse config',rb'failed to load config')),
)
CATEGORIES=frozenset(name for name,_ in RULES)|{'UNKNOWN'}

def classify_stderr(data):
    if not isinstance(data,bytes):return 'UNKNOWN'
    lowered=data.lower()
    matches={name for name,patterns in RULES if any(re.search(p,lowered) for p in patterns)}
    # Conflicting evidence is not resolved by guessing a primary cause.
    return next(iter(matches)) if len(matches)==1 else 'UNKNOWN'
