## 2024-05-30 - Add size limits to file reading
**Vulnerability:** Memory exhaustion (DoS) vulnerability due to unbounded file reading via `path.read_text()`.
**Learning:** Native filesystem paths were being read fully into memory without size checks. An attacker or unexpected large file in the expected directory structure could cause the application to consume excessive memory and crash.
**Prevention:** Always check `file.stat().st_size` against a reasonable threshold (e.g., 5MB for json, 25MB for text) before reading the entire file contents into memory.
