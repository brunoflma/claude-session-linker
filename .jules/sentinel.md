## 2024-05-18 - Avoid Security Theater on Static Files
**Vulnerability:** Adding symlink or size checks on static, hardcoded application files (like VERSION or result files inside the app dir) where attackers would already need write access to modify them.
**Learning:** These checks are considered "security theater" and provide no real-world protection, as modifying them implies the attacker already has access to modify the source code.
**Prevention:** Focus defense-in-depth on user-supplied input, external environments, or untrusted directories. Do not add arbitrary filesystem checks to static app files.
