param([Parameter(Mandatory=$true)][string]$OutputDirectory)
$ErrorActionPreference = 'Stop'
if ($env:GITHUB_ACTIONS -ne 'true' -or $env:RUNNER_OS -ne 'Windows') { throw 'GITHUB_WINDOWS_ONLY' }
if ($env:VSCMD_ARG_TGT_ARCH -ne 'x64' -or $env:VSCMD_ARG_HOST_ARCH -ne 'x64') { throw 'X64_SESSION_REQUIRED' }
# Reject inherited compiler option injections; do not echo their values.
foreach ($key in @('CL','_CL_','LINK','_LINK_')) {
    if ([Environment]::GetEnvironmentVariable($key)) { throw 'UNEXPECTED_COMPILER_OPTION_ENV' }
}
$tools=@{}
foreach ($name in @('cl.exe','link.exe','nmake.exe','lib.exe','perl.exe')) {
    $tool=Get-Command $name -ErrorAction SilentlyContinue
    if (-not $tool) { throw "MISSING_REQUIRED_TOOL_NO_INSTALL: $name" }
    $tools[$name]=$tool.Source
}
if ($tools['cl.exe'] -notmatch '(?i)\\bin\\Hostx64\\x64\\cl\.exe$') { throw 'UNEXPECTED_CL_TARGET_PATH' }
$perlVersion=(& $tools['perl.exe'] -e 'print "$^V\n"')
if ($LASTEXITCODE -ne 0 -or $perlVersion -notmatch '^v[0-9]+\.[0-9]+\.[0-9]+$') { throw 'PERL_VERSION_CHECK_FAILED' }
$variables=[ordered]@{}
foreach ($key in @('VSCMD_ARG_TGT_ARCH','VSCMD_ARG_HOST_ARCH','Platform','VisualStudioVersion','VSINSTALLDIR','VCToolsInstallDir','WindowsSdkDir','WindowsSDKVersion','UCRTVersion')) {
    $variables[$key]=[Environment]::GetEnvironmentVariable($key)
}
$metadata=[ordered]@{
    build_variables=$variables
    cl_path=$tools['cl.exe']
    cl_version=(Get-Item $tools['cl.exe']).VersionInfo.FileVersion
    link_version=(Get-Item $tools['link.exe']).VersionInfo.FileVersion
    nmake_version=(Get-Item $tools['nmake.exe']).VersionInfo.FileVersion
    perl_version=$perlVersion
}
$metadata | ConvertTo-Json -Depth 4 | Set-Content -LiteralPath (Join-Path $OutputDirectory 'native-session.json') -Encoding utf8
$metadata | ConvertTo-Json -Depth 4
