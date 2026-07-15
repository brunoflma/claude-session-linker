## 2024-07-15 - Redundant JSON parsing in loop
**Learning:** Found an N+1 disk read and JSON decoding pattern inside `scan_sessions` and `scan_cowork_sessions` where `get_link_metadata(f)` read from `LINKS_FILE` on every file in the directory.
**Action:** Lift static or semi-static data lookups (like registries) out of N-iteration loops and pre-load into memory.
