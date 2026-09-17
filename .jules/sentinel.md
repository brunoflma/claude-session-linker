## 2025-02-27 - Harden Path Traversal and Secure File Operations
**Vulnerability:**
1. Naive string matching (`if ".." in name`) was used in `_get_system_executable` to block path traversal, which could cause false positives for valid files containing ".." (e.g., `file..exe`).
2. Atomic file creation using `os.open` with `O_TRUNC` and `0o600` was gated behind an `if os.name == "posix":` check. Windows systems fell back to `Path.write_text()` or `open()`, making them theoretically vulnerable to symlink hijacking or race conditions in environments where advanced Windows symlinks are present.
**Learning:**
Validating logical path segments using `Path.parts` is both more secure and prevents false positives compared to raw substring checks. Furthermore, Python's `os.open()` supports standard POSIX flags like `O_WRONLY`, `O_CREAT`, `O_TRUNC`, and `O_EXCL` across all platforms (including Windows). It is best practice to unconditionally apply these strict flags, incorporating `getattr(os, "O_NOFOLLOW", 0)` gracefully so that protection scales natively when available.
**Prevention:**
Always validate logical path components using `if ".." in Path(path).parts:` rather than simple string matching. Always use cross-platform compatible `os.open()` with strict mode and flags to guarantee atomic file operations and permissions.
