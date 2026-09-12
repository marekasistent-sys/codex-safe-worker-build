# Stage 3B.2 — MSVC architecture diagnosis

Existing run: https://github.com/marekasistent-sys/codex-safe-worker-build/actions/runs/34690230161
Job: 103544067157. No new run was executed to prepare this change.

## Findings and limits

The log confirms NASM compilation reached nasmlib/file.c and failed at Windows SDK 10.0.26100.0 um/winnt.h(169), C1189, No Target Architecture. The command uses cl with /std:c11. The log does not record the resolved compiler path, /Bv or predefined macros, so an incorrect target compiler is not proven.

The pinned NASM file includes compiler.h, nasmlib.h and error.h, then wchar.h and stringapiset.h under _WIN32, without including windows.h. The inspected compiler configuration does not supply a windows.h include. This is strong evidence of a Windows SDK header initialization/order problem. Compiler intrinsic _M_X64/_M_AMD64 and _WIN64 are distinct from the SDK's _AMD64_ architecture macro. Losing a VS environment variable does not itself remove intrinsic macros from an x64 cl.exe. The windows.h umbrella header establishes SDK context for the compiler's target. Microsoft documents Windows.h as the include for MultiByteToWideChar.

Consequently, the same-session change is a diagnostic and robustness improvement, not a demonstrated fix for this NASM source/header issue. Both architecture probes may pass and unmodified NASM may still fail at file.c. No source patch, forced include or manual architecture define is introduced; resolving a confirmed source issue would require separate authorization.

## A versus B

A previously ran VsDevCmd in cmd.exe, captured SET and copied a subset into PowerShell. PATH, INCLUDE, LIB, LIBPATH and selected SDK directories survived. VSCMD_ARG_TGT_ARCH, VSCMD_ARG_HOST_ARCH, Platform, VisualStudioVersion and VSINSTALLDIR were omitted from that transfer and could be absent or inherited stale. This loses session context and makes diagnosis fragile, even though the copied PATH can still select the correct x64 compiler.

B now keeps CALL VsDevCmd -arch=x64 -host_arch=x64, the probes and NMAKE in one cmd.exe environment. It uses Microsoft's developer setup directly, without reconstructing the compiler environment. A child PowerShell process reads only named safe metadata from that same session; it does not transfer the environment back.

| Variable | Meaning and treatment |
|---|---|
| VSCMD_ARG_TGT_ARCH | Target selected by VsDevCmd; require x64 |
| VSCMD_ARG_HOST_ARCH | Host selected by VsDevCmd; require x64 |
| Platform | Project/build-system platform label if supplied; record, not a C macro switch |
| VisualStudioVersion | VS/toolset selection context; record |
| VSINSTALLDIR | Selected Visual Studio installation root; record |
| VCToolsInstallDir | Selected MSVC toolset directory; record |
| WindowsSdkDir, WindowsSDKVersion, UCRTVersion | SDK/UCRT selection; record |
| PATH, INCLUDE, LIB, LIBPATH | Tool/header/library resolution; retain the full developer-session values without dumping them |
| CL, _CL_, LINK, _LINK_ | Implicit compiler/linker options; refuse unexpected values without printing them |

Expected compiler: the selected VS 2022 MSVC toolset's bin/Hostx64/x64/cl.exe, not Hostx64/x86/cl.exe. Its actual full path is checked and recorded. The numeric compiler version will be observed on the next explicitly authorized run.

## Probe and fail-closed behavior

Before NMAKE, require x64 host/target session values and installed tools. Record the resolved compiler path, file versions and only the named variables above. Compile intrinsics.c with cl /Bv: require intrinsic _M_X64, _M_AMD64 and _WIN64; reject x86/ARM64/ARM64EC and require a 64-bit pointer. Then compile windows.c containing windows.h and a minimal main function. No resulting probe executable is run. Every failure exits the cmd session before NMAKE, without retry. Probe objects and metadata live in a fresh runner TEMP directory, outside NASM source and outside artifact upload paths.

Exit codes: 91 developer setup failure; 92/93 wrong target/host; 94 metadata/tool gate; 97 intrinsic compile; 98 Windows SDK compile; 100 NMAKE failure. These distinguish target setup failures from the remaining NASM compilation issue. Successful evidence is embedded in NASM provenance through the existing runner metadata.

Local tests validate script contracts and execute the wrong-architecture guard using synthetic environment values without starting a compiler. They do not establish that the native probes pass on the runner.

Sources:
- https://github.com/netwide-assembler/nasm/blob/4a56d66ed9626d5a3ded5414c9d8b7f1a48ce065/nasmlib/file.c
- https://learn.microsoft.com/en-us/cpp/build/building-on-the-command-line?view=msvc-170
- https://learn.microsoft.com/en-us/cpp/preprocessor/predefined-macros?view=msvc-170
- https://learn.microsoft.com/en-us/windows/win32/api/stringapiset/nf-stringapiset-multibytetowidechar
