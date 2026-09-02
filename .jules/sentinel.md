## 2024-10-27 - [TOCTOU symlink checks: is_symlink before exists]
**Vulnerability:** Calling `.exists()` before `.is_symlink()` in `pathlib`.
**Learning:** `pathlib.Path.exists()` implicitly follows symlinks. If a symlink is broken, `.exists()` returns `False`, causing the `.is_symlink()` check to be bypassed. This allows broken symlinks to remain on the system or be manipulated in subsequent logic, defeating the purpose of checking for symlinks to prevent path traversal or arbitrary file manipulation.
**Prevention:** Always evaluate `.is_symlink()` before checking `.exists()` or `.is_dir()`/`.is_file()` when validating untrusted paths.
