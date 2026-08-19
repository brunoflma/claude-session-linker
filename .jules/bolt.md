## 2024-05-24 - Fast-path Substring Matching Before JSON Parsing
**Learning:** Parsing JSON sequentially via `json.loads` is a significant CPU bottleneck when reading large log/transcript files line-by-line, especially when the majority of lines are irrelevant.
**Action:** Always use a fast-path substring check (e.g. `if "keyword" not in line`) to filter out irrelevant lines *before* attempting expensive operations like JSON parsing or regex matching.
