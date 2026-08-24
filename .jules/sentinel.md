
## 2024-08-24 - [Path Traversal in Subprocess Executable Resolution]
**Vulnerability:** The `_get_system_executable` function attempted to prevent binary planting and path traversal by prepending a base directory (`C:\Windows\System32`), but it used simple string concatenation (`os.path.join(base_dir, name)`) where `name` could be a user-controlled string like `..\..\..\cmd.exe`.
**Learning:** `os.path.join` on Python evaluates relative paths (`..`). Without normalizing the resulting path and checking if it stays within the expected base directory (`.startswith()`), it allows escaping the restrictive directory boundary.
**Prevention:** Always use `os.path.normpath(os.path.join(base_dir, user_input))` and then strictly verify `candidate.startswith(base_dir)` to enforce directory boundaries securely.

## 2024-08-24 - [Weak Directory Traversal Detection]
**Vulnerability:** The path traversal check in `_secure_write_text` and `_secure_copy` used `if ".." in str(path):`, which is fragile.
**Learning:** String matching `".." ` can yield false positives for legitimate files like `my..file.txt`, and might fail against obfuscated paths or alternative separators if incorrectly parsed.
**Prevention:** Always use `path.parts` from `pathlib.Path` to inspect logical path segments (`if ".." in path.parts:`) to accurately and robustly detect directory traversal tokens.
