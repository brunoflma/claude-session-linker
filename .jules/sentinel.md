## 2024-05-27 - [Defense-in-depth against Path Traversal in Copy Operations]
**Vulnerability:** Path traversal vulnerabilities can occur not just on file writes but also on file reads if the source path (`src`) contains logical `..` segments that traverse outside the intended directory.
**Learning:** Validating only the destination path (`dest.parts`) against `..` segments is insufficient. The source path (`src.parts`) must also be validated to prevent arbitrary file read and exfiltration.
**Prevention:** Always validate both source and destination paths using `if ".." in src.parts or ".." in dest.parts:` in custom secure copy implementations.
