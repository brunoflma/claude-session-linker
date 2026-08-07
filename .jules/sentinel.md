## 2025-08-07 - [Security Theater Removal]
**Vulnerability:** Security theater (unnecessary `is_symlink` and file size limit checks on hardcoded static files like `VERSION` and `setup-result.txt` within the app folder) gave a false sense of security while cluttering the code.
**Learning:** These files are not user-controlled input. An attacker would already need write access to the codebase directory to exploit them, at which point the application is already compromised. Defense-in-depth should be applied to user-supplied input, external environments, or untrusted directories.
**Prevention:** Avoid adding symlink and size limit checks on static, hardcoded application files. Focus security checks on data that comes from untrusted boundaries.
