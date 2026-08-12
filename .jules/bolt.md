## 2024-05-30 - Initial

## 2024-05-30 - O(N) Disk I/O from Path.resolve()
**Learning:** `pathlib.Path.resolve()` is surprisingly slow because it performs strict symlink resolution, meaning it hits the disk for every path segment. Calling it repeatedly on session files during a loop (like reading 1000s of session files) creates a massive O(N) disk I/O bottleneck. Parent-directory-only caching breaks symlink resolution for the target file itself.
**Action:** When you need the absolute path of many files and need strict symlink resolution, globally cache the full `resolve()` result mapping the original string path to the resolved path. This preserves exact symlink resolution behavior while avoiding redundant disk hits.
