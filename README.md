# Wikipedia Interest Research

An agent skill and small Python command line tool for researching Wikipedia page views. It validates article pages, fetches and caches daily data, summarizes trend and quality signals, then writes a chart and a one-page PDF.

## Requirements

- Python 3.10 or newer
- Network access to Wikimedia APIs for live research
- No third-party Python packages

## Run

From this directory:

```powershell
python scripts/wiki_interest.py --series "pl:Post przerywany" --series "cs:Přerušovaný půst" --start 2024-01-01 --end 2025-12-31 --output-dir output/intermittent-fasting
```

The date range is inclusive and must end before today. `--refresh` bypasses cached API responses. `--cache-dir` changes the default cache location, which is `output-dir/.cache`.

The output directory contains:

- `result.json` with resolved titles, observations, quality checks, trends, and artifact paths
- `chart.svg` with within-series normalized monthly trends
- `report.pdf` with the chart, key findings, quality notes, and limitations
- `.cache` with raw API responses for repeatable reruns

The cache contains only public API responses. Keep it with the output when you need to preserve the inputs for a rerun.

## Analysis notes

Daily page views are aggregated into monthly mean daily views. The monthly index uses the mean of the first three observed months as its baseline. The tool reports a Theil-Sen slope, first-half versus second-half change, coverage, missing dates, zero-view days, and unusually large daily changes.

The signal rating is a transparent heuristic, not a confidence interval, causal result, or forecast. Raw page view totals across language editions are not normalized for audience size. A rise in page views is not proof of demand for a product.

Article titles with non-Latin characters are transliterated in the PDF so the report works with built-in PDF fonts. `result.json` retains the exact article titles.

Article renames and redirects can affect continuity. Review the resolved titles and consider whether a page move or related page changed the series during the selected period.

## Verify

Run the standard-library test suite:

```powershell
python -m unittest discover -s tests -v
```

The tests use mocked Wikimedia responses and do not require network access. A separate live run is needed to verify current API availability.

## Agent integration

Read `SKILL.md` for the agent workflow and interpretation rules. The agent supplies one `--series LANG:TITLE` argument per language. It should verify ambiguous article mappings and inspect `result.json` before summarizing. The command line tool does not guess article translations or infer that different pages have equivalent scope.

## Further development

Start with reproducible fixtures and preserve the JSON contract. Add one analysis field at a time, then extend the fetch layer with bounded concurrency and resumable caching for larger studies. Further research work can add seasonal adjustment, sensitivity checks across related articles, event annotations, and statistically validated uncertainty estimates. Large studies can store observations in Parquet and build reports from a separate analysis stage.
