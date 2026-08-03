## 2024-08-03 - [Preventing TOCTOU Symlink Hijacking during Atomic File Creation]
**Vulnerability:** The application used `os.open` with `os.O_WRONLY | os.O_CREAT | os.O_TRUNC` to create files atomatically with tight permissions, but on POSIX systems this can still follow symlinks if one was created at the target path just before the open call.
**Learning:** Even when attempting atomic file creation with safe permissions on POSIX systems, failing to pass `os.O_NOFOLLOW` allows an attacker to pre-create a symlink and force the application to overwrite an arbitrary file.
**Prevention:** Always mix in `getattr(os, 'O_NOFOLLOW', 0)` when calling `os.open` for secure file creation/overwriting on POSIX systems to prevent TOCTOU symlink hijacking.
