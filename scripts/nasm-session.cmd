@echo off
setlocal DisableDelayedExpansion
if not "%GITHUB_ACTIONS%"=="true" exit /b 90
call "%~1" -no_logo -arch=x64 -host_arch=x64
if errorlevel 1 exit /b 91
if /I not "%VSCMD_ARG_TGT_ARCH%"=="x64" exit /b 92
if /I not "%VSCMD_ARG_HOST_ARCH%"=="x64" exit /b 93
rem Inspect only named safe build metadata, never SET or an environment dump.
pwsh -NoProfile -File "%~2\scripts\native-session-evidence.ps1" -OutputDirectory "%~4"
if errorlevel 1 exit /b 94
pushd "%~4"
if errorlevel 1 exit /b 95
where cl.exe
if errorlevel 1 exit /b 96
cl.exe /Bv /nologo /std:c11 /c "%~2\tests\architecture\intrinsics.c" /Fo:intrinsics.obj
if errorlevel 1 exit /b 97
cl.exe /nologo /std:c11 /c "%~2\tests\architecture\windows.c" /Fo:windows.obj
if errorlevel 1 exit /b 98
popd
pushd "%~3"
if errorlevel 1 exit /b 99
nmake.exe /f Mkfiles\msvc.mak
if errorlevel 1 exit /b 100
popd
exit /b 0
