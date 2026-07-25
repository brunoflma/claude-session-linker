## 2025-02-13 - [MEDIUM] Fix Symlink Overwrite and Add Input Limits
**Vulnerability:** Symlink arbitrary file overwrite and potential DoS through excessive input length.
**Learning:** `pathlib.Path.write_text` does not check for symlinks before overwriting the file. User input wasn't properly checked before writing to the `.json` database file.
**Prevention:** Check if the file is a symlink using `pathlib.Path.is_symlink()` before overwriting. Always validate input length limit from the user.
