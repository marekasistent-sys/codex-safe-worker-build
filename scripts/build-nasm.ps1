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

# Use only the runner's installed VS 2022 developer environment, in this process.
$vswhere = Join-Path ${env:ProgramFiles(x86)} 'Microsoft Visual Studio\Installer\vswhere.exe'
if (-not (Test-Path -LiteralPath $vswhere)) { throw 'MISSING_VSWHERE_NO_INSTALL' }
$instances = & $vswhere -products '*' -version '[17.0,18.0)' -requires Microsoft.VisualStudio.Component.VC.Tools.x86.x64 -format json | ConvertFrom-Json
if ($LASTEXITCODE -ne 0 -or -not $instances) { throw 'MISSING_MSVC_NO_INSTALL' }
$instance = $instances | Sort-Object { [version]$_.installationVersion } -Descending | Select-Object -First 1
$devcmd = Join-Path $instance.installationPath 'Common7\Tools\VsDevCmd.bat'
if (-not (Test-Path -LiteralPath $devcmd)) { throw 'MISSING_VSDEVCMD_NO_INSTALL' }
$vars = & $env:ComSpec /d /s /c "call `"$devcmd`" -no_logo -arch=x64 -host_arch=x64 >nul && set"
if ($LASTEXITCODE -ne 0) { throw 'NASM_VS_ENV_FAILED' }
$allow = @('PATH','INCLUDE','LIB','LIBPATH','UCRTVersion','UniversalCRTSdkDir','VCToolsInstallDir','VCINSTALLDIR','WindowsSdkDir','WindowsSDKVersion','WindowsSDKLibVersion','WindowsSdkBinPath')
foreach ($entry in $vars) {
    if ($entry -match '^([^=]+)=(.*)$' -and $allow -contains $Matches[1]) {
        [Environment]::SetEnvironmentVariable($Matches[1],$Matches[2],'Process')
    }
}
$tools = @{}
foreach ($name in @('nmake.exe','cl.exe','link.exe','lib.exe','perl.exe')) {
    $tool = Get-Command $name -ErrorAction SilentlyContinue
    if (-not $tool) { throw "MISSING_REQUIRED_TOOL_NO_INSTALL: $name" }
    $tools[$name] = $tool.Source
}
$perlVersion = (& $tools['perl.exe'] -e 'print "$^V\n"')
if ($LASTEXITCODE -ne 0 -or $perlVersion -notmatch '^v[0-9]+\.[0-9]+\.[0-9]+$') { throw 'PERL_VERSION_CHECK_FAILED' }

# NMAKE's official rules are the only generator. Never patch or bootstrap upstream.
Push-Location $source
try {
    & $tools['nmake.exe'] /f 'Mkfiles\msvc.mak'
    if ($LASTEXITCODE -ne 0) { throw 'NASM_BUILD_FAILED_NO_RETRY_OR_INSTALL' }
} finally { Pop-Location }
$binary = Join-Path $source 'nasm.exe'
if (-not (Test-Path -LiteralPath $binary -PathType Leaf)) { throw 'NASM_BINARY_MISSING' }
$version = (& $binary -v)
if ($LASTEXITCODE -ne 0 -or $version -notmatch '^NASM version 3\.02(?:\s|$)') { throw 'NASM_BINARY_VERSION_MISMATCH' }
$trackedChanges = @(& git -C $source diff --name-only HEAD)
if ($LASTEXITCODE -ne 0 -or $trackedChanges.Count -ne 0) { throw 'NASM_TRACKED_SOURCE_CHANGED' }
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
    build_command = 'nmake /f Mkfiles\msvc.mak'
    visual_studio_version = $instance.installationVersion
    cl_version = (Get-Item $tools['cl.exe']).VersionInfo.FileVersion
    link_version = (Get-Item $tools['link.exe']).VersionInfo.FileVersion
    nmake_version = (Get-Item $tools['nmake.exe']).VersionInfo.FileVersion
    perl_version = $perlVersion
    generated_files = @($generated | Sort-Object)
    nasm_version = $version
    binary_sha256 = (Get-FileHash -LiteralPath $binary -Algorithm SHA256).Hash.ToLowerInvariant()
}
$metadata | ConvertTo-Json -Depth 4 | Set-Content -LiteralPath (Join-Path $recipe 'nasm-provenance.json') -Encoding utf8
# Only the official job-local path file; no user/system PATH or software installation.
if ($source.Contains("`r") -or $source.Contains("`n") -or -not $env:GITHUB_PATH) { throw 'INVALID_GITHUB_PATH' }
$source | Out-File -LiteralPath $env:GITHUB_PATH -Append -Encoding utf8
$metadata | ConvertTo-Json -Depth 4
