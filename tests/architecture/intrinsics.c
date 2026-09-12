#if !defined(_MSC_VER)
#error MSVC_REQUIRED
#endif
#if !defined(_M_X64) || !defined(_M_AMD64) || !defined(_WIN64)
#error X64_INTRINSICS_REQUIRED
#endif
#if defined(_M_IX86) || defined(_M_ARM64) || defined(_M_ARM64EC)
#error WRONG_TARGET_ARCHITECTURE
#endif
typedef char pointer_must_be_64_bit[(sizeof(void *) == 8) ? 1 : -1];
int architecture_probe(void) { return 0; }
