## 2024-05-18 - Fix symlink traversal vulnerability
**Vulnerability:** `pathlib.Path.is_file()` follows symlinks implicitly, which can lead to path traversal vulnerabilities when reading or processing user-controlled files like `config.json`, session indexes, and labels files.
**Learning:** In Python's `pathlib`, always evaluate `.is_symlink()` FIRST before checking `.is_file()` or `.is_dir()` if preventing symlink attacks and path traversals is necessary.
**Prevention:** Add explicit `.is_symlink()` checks before any file reading or processing operation in the codebase, mirroring the existing defenses on directory traversal.
