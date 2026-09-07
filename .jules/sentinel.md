## 2025-02-15 - [Remove TOCTOU vulnerability in file size check]
**Vulnerability:** [Checking file size via path.stat().st_size before opening the file is vulnerable to TOCTOU symlink attacks]
**Learning:** [Using path.stat() can be subverted if the file is replaced with a symlink between the check and opening the file, potentially leading to DoS by reading huge files.]
**Prevention:** [Open the file first, and then evaluate its size via the file descriptor (e.g. os.fstat(f.fileno()).st_size) before proceeding.]
