$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'
if ($env:GITHUB_ACTIONS -ne 'true' -or $env:RUNNER_OS -ne 'Windows') { throw 'GITHUB_WINDOWS_ONLY' }
foreach ($name in @('OPENAI_API_KEY','CODEX_API_KEY','CHATGPT_TOKEN','OPENAI_ACCESS_TOKEN','OPENAI_REFRESH_TOKEN')) {
    if ([Environment]::GetEnvironmentVariable($name)) { throw 'FORBIDDEN_AUTH_ENV_PRESENT' }
}
$recipeRoot = Split-Path $PSScriptRoot -Parent
$inventoryPath = Join-Path $recipeRoot 'runner.json'
if (Test-Path $inventoryPath) { throw 'INVENTORY_ALREADY_EXISTS' }
$nasm = Get-Command nasm.exe -ErrorAction SilentlyContinue
if (-not $nasm) {
    foreach ($candidate in @('C:\Program Files\NASM\nasm.exe','C:\Program Files (x86)\NASM\nasm.exe')) {
        if (Test-Path -LiteralPath $candidate) { $nasm = Get-Item -LiteralPath $candidate; break }
    }
}
if (-not $nasm) { throw 'MISSING_DEPENDENCY_NASM_NO_INSTALL_ATTEMPTED' }
$nasmPath = if ($nasm.Source) { $nasm.Source } else { $nasm.FullName }
$expectedNasm = Join-Path $env:GITHUB_WORKSPACE 'nasm-src\nasm.exe'
if ([IO.Path]::GetFullPath($nasmPath) -ne [IO.Path]::GetFullPath($expectedNasm)) { throw 'NASM_SOURCE_BUILT_PATH_REQUIRED' }
$nasmEvidence = Get-Content -LiteralPath (Join-Path $recipeRoot 'nasm-provenance.json') -Raw | ConvertFrom-Json
$nasmVersion = (& $nasmPath --version)
if ($LASTEXITCODE -ne 0 -or $nasmVersion -notmatch '^NASM version 3\.02(?:\s|$)') { throw 'NASM_302_REQUIRED' }
if ($nasmEvidence.source_commit -ne '4a56d66ed9626d5a3ded5414c9d8b7f1a48ce065' -or (Get-FileHash -LiteralPath $nasmPath -Algorithm SHA256).Hash.ToLowerInvariant() -ne $nasmEvidence.binary_sha256) { throw 'NASM_PROVENANCE_MISMATCH' }
foreach ($tool in @('python','git','rustup')) {
    if (-not (Get-Command $tool -ErrorAction SilentlyContinue)) { throw "MISSING_DEPENDENCY_$tool" }
}
$vswhere = Join-Path ${env:ProgramFiles(x86)} 'Microsoft Visual Studio\Installer\vswhere.exe'
if (-not (Test-Path $vswhere)) { throw 'MISSING_DEPENDENCY_VSWHERE' }
$instances = & $vswhere -products Microsoft.VisualStudio.Product.BuildTools Microsoft.VisualStudio.Product.Enterprise Microsoft.VisualStudio.Product.Professional Microsoft.VisualStudio.Product.Community -version '[17.0,18.0)' -requires Microsoft.VisualStudio.Component.VC.Tools.x86.x64 -format json | ConvertFrom-Json
if (-not $instances) { throw 'MISSING_DEPENDENCY_MSVC_X64' }
$instance = $instances | Sort-Object { [version]$_.installationVersion } -Descending | Select-Object -First 1
$devcmd = Join-Path $instance.installationPath 'Common7\Tools\VsDevCmd.bat'
if (-not (Test-Path $devcmd)) { throw 'MISSING_DEPENDENCY_VSDEVCMD' }
# Import only the native developer variables into this runner process; never enumerate secrets.
$vars = & $env:ComSpec /d /s /c "call `"$devcmd`" -no_logo -arch=x64 -host_arch=x64 >nul && set"
if ($LASTEXITCODE -ne 0) { throw 'VS_ENV_FAILED' }
$allow = @('PATH','INCLUDE','LIB','LIBPATH','UCRTVersion','UniversalCRTSdkDir','VCToolsInstallDir','VCINSTALLDIR','WindowsSdkDir','WindowsSDKVersion','WindowsSDKLibVersion','WindowsSdkBinPath')
foreach ($line in $vars) {
    if ($line -match '^([^=]+)=(.*)$' -and $allow -contains $Matches[1]) {
        [Environment]::SetEnvironmentVariable($Matches[1], $Matches[2], 'Process')
    }
}
$cl = (Get-Command cl.exe -ErrorAction Stop).Source
$link = (Get-Command link.exe -ErrorAction Stop).Source
$sdk = $env:WindowsSDKVersion.TrimEnd('\')
foreach ($path in @((Join-Path $env:WindowsSdkDir "Include\$sdk\um\Windows.h"),(Join-Path $env:WindowsSdkDir "Lib\$sdk\um\x64\kernel32.lib"),(Join-Path $env:WindowsSdkDir "Lib\$sdk\ucrt\x64\ucrt.lib"))) {
    if (-not (Test-Path $path)) { throw 'MISSING_DEPENDENCY_SDK_HEADERS_OR_LIBS' }
}
$allSdk = @(Get-ChildItem -LiteralPath (Join-Path $env:WindowsSdkDir 'Include') -Directory | Select-Object -ExpandProperty Name)
$metadata = [ordered]@{
    image_version = $env:ImageVersion
    image_os = $env:ImageOS
    os_build = [Environment]::OSVersion.Version.ToString()
    visual_studio_version = $instance.installationVersion
    cl_version = (Get-Item $cl).VersionInfo.FileVersion
    link_version = (Get-Item $link).VersionInfo.FileVersion
    selected_sdk = $sdk
    installed_sdk_versions = $allSdk
    nasm_version = $nasmVersion
    nasm_source_build = $nasmEvidence
    git_version = ((& git --version) -join ' ')
}
if (-not $metadata.image_version) { throw 'MISSING_RUNNER_IMAGE_VERSION' }
$metadata | ConvertTo-Json -Depth 4 | Set-Content -LiteralPath $inventoryPath -Encoding utf8
# Job-local environment only, via the official Actions environment file.
foreach ($name in $allow) {
    $value = [Environment]::GetEnvironmentVariable($name)
    if ($value) {
        if ($value.Contains("`r") -or $value.Contains("`n")) { throw 'INVALID_NATIVE_ENV' }
        "$name=$value" | Out-File -LiteralPath $env:GITHUB_ENV -Append -Encoding utf8
    }
}
$metadata | ConvertTo-Json -Depth 4
