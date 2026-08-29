## 2024-08-29 - Prevent DoS via Disk Exhaustion in Error Log
**Vulnerability:** The error logger (`_log`) appended to `ERR_LOG` without any size bounds, which could allow a local Denial of Service (DoS) vulnerability via disk exhaustion if rapid/continuous errors were generated.
**Learning:** Even internal GUI application loggers need rotation or file size bounds, as bounded storage is a core component of defense in depth against DoS, especially in desktop applications where users might not monitor log sizes.
**Prevention:** Implement file size limits (e.g., 5MB) and basic rotation (renaming to `.1` and deleting older backups) for continuously appended log files, while ensuring checks like `not is_symlink()` are included to avoid TOCTOU hijack during rotation.
