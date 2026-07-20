## 2025-05-18 - [Insecure Default Permissions on Backups]
**Vulnerability:** Directories for backups and logs were created with default permissions (usually 0o755), exposing sensitive session data to other users on the system.
**Learning:** Default directory creation in Python (`Path.mkdir`) and Bash (`mkdir -p`) does not restrict access.
**Prevention:** Explicitly use `mode=0o700` (Python) or `mkdir -m 700` (Bash) when creating directories intended to store sensitive local data.
