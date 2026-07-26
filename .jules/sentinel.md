## 2025-02-27 - [Symlink check for shutil operations]
**Vulnerability:** A vulnerability to symlink attack exists during the copy, rename and delete process as shutil.copy2, shutil.copytree and shutil.rmtree might operate over symlinks.
**Learning:** Checking for symlinks with `.is_symlink()` is very important to avoid security vulnerabilities on Python's shutil file system operations.
**Prevention:** Avoid copy, delete or rename symlinks and verify with `is_symlink` before any of those operations.
