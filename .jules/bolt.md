## 2024-09-09 - [Delay Expensive I/O validation checks during data filtering]
**Learning:** Checking for file availability (via disk I/O) on every single item before grouping data into duplicates is an O(N) bottleneck that severely impacts performance when filtering large numbers of sessions.
**Action:** Delay expensive validations (like disk I/O) until after grouping and applying cheap filtering conditions (e.g. checking length > 1 in a map) so the expensive checks are only performed when necessary.
