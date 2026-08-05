## 2024-05-18 - [Optimize Recursive Directory Traversal with os.scandir]
**Learning:** `pathlib.Path.iterdir()` returns new `Path` objects which re-evaluate `stat()` for every `.is_dir()`, `.is_file()`, and `.is_symlink()` call, causing a massive penalty (N^2 syscalls) during deep traversals.
**Action:** Use `os.scandir()` which yields `os.DirEntry` objects that inherently cache these attributes, heavily reducing redundant filesystem I/O operations and providing a massive speed boost during file system walks (e.g. up to 5x faster).
