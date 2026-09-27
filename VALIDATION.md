# Validation Record

## Automated checks

Command:

```powershell
python -m unittest discover -s tests -v
```

Result: all 3 tests passed. The suite covers series parsing, missing observations and trend direction, and a complete CLI run using mocked Wikimedia responses. The mocked run checks the documented Wikimedia request format and validates the JSON, SVG, and one-page PDF outputs.

## Live Wikimedia check

The live run compared `Астрономія` in Ukrainian Wikipedia with `Astronomy` in English Wikipedia for 2024-09-27 through 2026-09-26. Both pages resolved, the API returned 100% daily coverage for each series, and the command generated `result.json`, `chart.svg`, and a one-page `report.pdf` in `output/live-example`.

A separate title-resolution check confirmed that a nonexistent supplied article is reported with search candidates instead of being silently replaced.

## PDF review

The generated PDF was checked with Poppler. It contains one Letter page. The page was rendered to PNG and visually reviewed for clipping, overlap, title rendering, and report flow. Non-Latin titles are transliterated in the PDF; exact titles remain in JSON.

## Low-cost model check

The `scripts/evaluate_agent.py` harness sent `SKILL.md` to OpenRouter's free router and let the model invoke the local research CLI. The end-to-end request compared Ukrainian `Астрономія` with English `Astronomy` from 2024-09-26 through 2026-09-26. The tool resolved both articles and returned 731 of 731 daily points for each. The model reported the declining trends, used the signal ratings and quality data, avoided a seasonal conclusion, and included the chart and PDF paths.

OpenRouter reported zero inference cost for the run. The router used `nvidia/nemotron-3-ultra-550b-a55b:free` for the tool-call response and `inclusionai/ling-3.0-flash-fin:free` for the final answer. The final completion ended with `stop`. Numeric statements were checked against `result.json`. The transcript, tool arguments, model IDs, cost, and answer are saved under `output/model-evaluation`.

## AI-assisted development

Codex was used to draft and refine the skill, Python implementation, tests, and report. The implementation was reviewed against Wikimedia's official Analytics API documentation, exercised with mocked responses, and run against Wikimedia's live API. The generated PDF was independently rendered with Poppler for layout review.
