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

The `scripts/evaluate_agent.py` harness is ready to send `SKILL.md` to a tool-enabled model, let it invoke the local research CLI, and save the full result and final answer. An actual model run has not been performed because this environment has no OpenRouter credential. Use the PowerShell instructions in `README.md` to run it with `openrouter/free` or a specific free model that supports tool calling. Until that run succeeds, model-level validation remains outstanding.

## AI-assisted development

Codex was used to draft and refine the skill, Python implementation, tests, and report. The implementation was reviewed against Wikimedia's official Analytics API documentation, exercised with mocked responses, and run against Wikimedia's live API. The generated PDF was independently rendered with Poppler for layout review.
