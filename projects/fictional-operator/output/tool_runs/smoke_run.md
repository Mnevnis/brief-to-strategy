# Tool smoke run — fictional-operator

**Run:** 2026-11-22 17:31:22–17:31:36 UTC  
**CI run:** [45049885788](https://github.com/Mnevnis/brief-to-strategy/actions/runs/45049885788)  
**Automated wall time:** 13.910 s  
**Manual time:** not measured  
**LLM/API calls:** 0 in this smoke run; this is not a full-agent run.

| Tool | Result | Wall time |
|---|---|---:|
| `parse_doc.py` — primary source-derived CSV | exit 0, 0 warnings | 0.386 s |
| `metrics.py check --strict` — primary CSV | exit 0, 0 warnings | 0.337 s |
| `parse_doc.py` — second mini-brief CSV | exit 0, 0 warnings | 0.344 s |
| `metrics.py check --strict` — second mini-brief CSV | exit 0, 0 warnings | 0.344 s |
| `cost_log.py init/check/report` | all exit 0 | 0.107 s total |
| `search.py` | exit 4; 0 usable results after DDG HTML, DDG Lite and SearXNG attempts | 10.323 s |
| `fetch_cache.py` | exit 0; official EDPB landing page cached (44,890 bytes), 0 injection flags | 2.069 s |

## Interpretation

- The parser and strict metrics audit succeeded on both checked-in, source-derived CSV fixtures.
- The original 11-page PDF was separately parsed with the exact repository parser blob; see `materials/parsed/source_pdf_run.md`.
- Search is **degraded**, not successful discovery: both DuckDuckGo parsers returned zero results and SearXNG requests failed. The EDPB page was fetched through an explicitly documented direct official-source fallback, not from search results.
- `cost_log.py` reports $0.00 recorded LLM spend because this smoke run made no LLM/API calls. This is not a cost estimate for the full agent, human work, GitHub Actions or indirect network costs.
- Human time, baseline comparison, full agent runtime, interviews, pilot and human gates remain unmeasured or not performed.
- The second mini-brief is a sub-scenario extracted from the same source brief, not an independent external task.

Raw machine-readable run evidence and parser/metrics metadata are retained in the GitHub Actions artifact `fictional-operator-tool-run`.
