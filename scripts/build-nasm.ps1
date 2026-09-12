$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'
if ($env:GITHUB_ACTIONS -ne 'true' -or $env:RUNNER_OS -ne 'Windows') { throw 'GITHUB_WINDOWS_ONLY' }
$recipe = Split-Path $PSScriptRoot -Parent
$source = Join-Path $env:GITHUB_WORKSPACE 'nasm-src'
$pin = '4a56d66ed9626d5a3ded5414c9d8b7f1a48ce065'
if (-not (Test-Path -LiteralPath $source -PathType Container)) { throw 'NASM_SOURCE_MISSING' }
if ((Get-Item -LiteralPath $source).Attributes -band [IO.FileAttributes]::ReparsePoint) { throw 'NASM_REPARSE_DENIED' }
$head = (& git -C $source rev-parse HEAD)
if ($LASTEXITCODE -ne 0 -or $head -ne $pin) { throw 'NASM_COMMIT_MISMATCH' }
$tree = (& git -C $source rev-parse 'HEAD^{tree}')
if ($LASTEXITCODE -ne 0 -or $tree -notmatch '^[0-9a-f]{40}$') { throw 'NASM_TREE_INVALID' }
$status = (& git -C $source status --porcelain --untracked-files=all)
if ($LASTEXITCODE -ne 0 -or $status) { throw 'NASM_SOURCE_NOT_CLEAN' }
if ([IO.File]::ReadAllText((Join-Path $source 'version')).Trim() -ne '3.02') { throw 'NASM_SOURCE_VERSION_MISMATCH' }
if (Test-Path -LiteralPath (Join-Path $recipe 'nasm-provenance.json')) { throw 'NASM_EVIDENCE_EXISTS' }
$python = Get-Command python -ErrorAction SilentlyContinue
if (-not $python) { throw 'MISSING_PYTHON_NO_INSTALL' }
& $python.Source -B (Join-Path $PSScriptRoot 'nasm_backport.py') apply --source $source
if ($LASTEXITCODE -ne 0) { throw 'NASM_BACKPORT_REJECTED' }
# Emit only the reviewed public source diff before generated/build files exist.
& git -C $source diff --no-ext-diff --no-color -- nasmlib/file.c
if ($LASTEXITCODE -ne 0) { throw 'NASM_DIFF_FAILED' }

# Use only the runner's installed VS 2022 developer environment, in this process.
$vswhere = Join-Path ${env:ProgramFiles(x86)} 'Microsoft Visual Studio\Installer\vswhere.exe'
if (-not (Test-Path -LiteralPath $vswhere)) { throw 'MISSING_VSWHERE_NO_INSTALL' }
$instances = & $vswhere -products '*' -version '[17.0,18.0)' -requires Microsoft.VisualStudio.Component.VC.Tools.x86.x64 -format json | ConvertFrom-Json
if ($LASTEXITCODE -ne 0 -or -not $instances) { throw 'MISSING_MSVC_NO_INSTALL' }
$instance = $instances | Sort-Object { [version]$_.installationVersion } -Descending | Select-Object -First 1
$devcmd = Join-Path $instance.installationPath 'Common7\Tools\VsDevCmd.bat'
if (-not (Test-Path -LiteralPath $devcmd)) { throw 'MISSING_VSDEVCMD_NO_INSTALL' }
# One cmd.exe owns VsDevCmd, both compile probes and NMAKE; no SET capture.
$probeRoot = Join-Path $env:RUNNER_TEMP 'nasm-architecture'
if (Test-Path -LiteralPath $probeRoot) { throw 'ARCHITECTURE_PROBE_DIR_NOT_FRESH' }
New-Item -ItemType Directory -Path $probeRoot | Out-Null
$sessionScript = Join-Path $PSScriptRoot 'nasm-session.cmd'
foreach ($path in @($devcmd,$recipe,$source,$probeRoot,$sessionScript)) {
    if ($path -match '[%!?&|<>^"\r\n]') { throw 'UNSAFE_CMD_ARGUMENT' }
}
& $env:ComSpec /d /s /c "call `"$sessionScript`" `"$devcmd`" `"$recipe`" `"$source`" `"$probeRoot`""
if ($LASTEXITCODE -ne 0) { throw "NASM_SESSION_FAILED_NO_RETRY_EXIT_$LASTEXITCODE" }
$session = Get-Content -LiteralPath (Join-Path $probeRoot 'native-session.json') -Raw | ConvertFrom-Json
if ($session.build_variables.VSCMD_ARG_TGT_ARCH -ne 'x64' -or $session.build_variables.VSCMD_ARG_HOST_ARCH -ne 'x64') { throw 'NATIVE_SESSION_EVIDENCE_INVALID' }
$binary = Join-Path $source 'nasm.exe'
if (-not (Test-Path -LiteralPath $binary -PathType Leaf)) { throw 'NASM_BINARY_MISSING' }
$version = (& $binary -v)
if ($LASTEXITCODE -ne 0 -or $version -notmatch '^NASM version 3\.02(?:\s|$)') { throw 'NASM_BINARY_VERSION_MISMATCH' }
& $python.Source -B (Join-Path $PSScriptRoot 'nasm_backport.py') verify --source $source
if ($LASTEXITCODE -ne 0) { throw 'NASM_BACKPORT_CHANGED_DURING_BUILD' }
$generated = @(& git -C $source ls-files --others)
if ($LASTEXITCODE -ne 0) { throw 'NASM_GENERATED_INVENTORY_FAILED' }
$generatedSources = @('msvc.dep','version.h','version.mac','version.mak','version.sed','nsis/version.nsh',
    'x86/insns.xda','x86/insnsb.c','x86/insnsa.c','x86/insnsd.c','x86/insnsi.h','x86/insnsn.c',
    'x86/regs.c','x86/regs.h','x86/regflags.c','x86/regdis.c','x86/regdis.h','x86/regvals.c',
    'x86/iflag.c','x86/iflaggen.h','asm/tokhash.c','asm/tokens.h','asm/pptok.h','asm/pptok.c',
    'asm/pptok.ph','asm/directbl.c','asm/directiv.h','asm/warnings_c.h','include/warnings.h',
    'doc/warnings.src','macros/macros.c')
foreach ($name in $generated) {
    if ($name -notin $generatedSources -and $name -notmatch '^(?:[A-Za-z0-9_-]+/)*[A-Za-z0-9_-]+\.(obj|lib|pdb|ilk)$' -and $name -notin @('nasm.exe','ndisasm.exe')) {
        throw 'NASM_UNEXPECTED_GENERATED_FILE'
    }
}
$metadata = [ordered]@{
    repository = 'https://github.com/netwide-assembler/nasm'
    source_commit = $head
    source_tree = $tree
    source_version = '3.02'
    upstream_fix_source = 'ace0078261329437224d4875b289647279a41fa1'
    patched_file = 'nasmlib/file.c'
    patch_sha256 = (Get-FileHash -LiteralPath (Join-Path $recipe 'nasm-windows-sdk.patch') -Algorithm SHA256).Hash.ToLowerInvariant()
    patch_reason = 'official upstream Windows SDK compatibility fix'
    build_command = 'nmake /f Mkfiles\msvc.mak'
    visual_studio_version = $instance.installationVersion
    cl_version = $session.cl_version
    link_version = $session.link_version
    nmake_version = $session.nmake_version
    perl_version = $session.perl_version
    native_session = $session
    architecture_probe = 'PASS: intrinsic x64 macros and windows.h compile'
    generated_files = @($generated | Sort-Object)
    nasm_version = $version
    binary_sha256 = (Get-FileHash -LiteralPath $binary -Algorithm SHA256).Hash.ToLowerInvariant()
}
$metadata | ConvertTo-Json -Depth 4 | Set-Content -LiteralPath (Join-Path $recipe 'nasm-provenance.json') -Encoding utf8
# Only the official job-local path file; no user/system PATH or software installation.
if ($source.Contains("`r") -or $source.Contains("`n") -or -not $env:GITHUB_PATH) { throw 'INVALID_GITHUB_PATH' }
$source | Out-File -LiteralPath $env:GITHUB_PATH -Append -Encoding utf8
$metadata | ConvertTo-Json -Depth 4
