## 2024-05-18 - Path Traversal / DoS in Transcript Search
**Vulnerability:** The `find_transcript_path` function passes unvalidated `cli_session_id` directly into `rglob`. An attacker could specify absolute paths (causing a `NotImplementedError` DoS) or path traversal components (`../`) to leak or manipulate files outside the expected directory.
**Learning:** Functions that accept external identifiers and use them in glob patterns or path resolution must sanitize the input, even if the expected format is a simple UUID.
**Prevention:** Always validate that external identifiers match the expected format (e.g., using `re.match(r"^[A-Za-z0-9\-]+$", id)`) before using them in file system operations.
