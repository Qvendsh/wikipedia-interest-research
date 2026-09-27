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

An actual low-cost model run was not available in this environment because no OpenRouter credential or compatible model runner was configured. The skill keeps the agent workflow to parameter extraction, one CLI invocation, and reading a stable JSON result, but this does not replace an actual model integration check. Run the sample in `SKILL.md` with a tool-enabled low-cost model before claiming model-level validation.

## AI-assisted development

Codex was used to draft and refine the skill, Python implementation, tests, and report. The implementation was reviewed against Wikimedia's official Analytics API documentation, exercised with mocked responses, and run against Wikimedia's live API. The generated PDF was independently rendered with Poppler for layout review.
