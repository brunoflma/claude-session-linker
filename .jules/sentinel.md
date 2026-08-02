## 2024-10-24 - [O_NOFOLLOW for secure file creation]
**Vulnerability:** Symlink path traversal on Linux/macOS could lead to overwriting files elsewhere through TOCTOU symlink injection in `os.open` during logging or file writing.
**Learning:** In python on posix systems `os.O_NOFOLLOW` prevents `os.open` from following symlinks and instead throws an error, resolving TOCTOU path-traversal vulnerabilities during open/creation.
**Prevention:** Use `getattr(os, "O_NOFOLLOW", 0)` mixed into flags for `os.open`.
