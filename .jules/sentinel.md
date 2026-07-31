## 2024-05-24 - Secure Directory Traversal
**Vulnerability:** The application used `path.rglob("*")` which implicitly follows symlinked directories, potentially allowing out-of-bounds path traversal during backups and string replacements.
**Learning:** Even though files found via `rglob` were checked for symlinks before access, the `rglob` traversal itself could follow malicious symlinked directories outside the intended bounds before the check occurred.
**Prevention:** Implement and use a custom `_safe_walk_files` recursive generator that explicitly checks and skips symlinks (`path.is_symlink()`) *before* iterating over children, replacing `rglob` for sensitive operations.
