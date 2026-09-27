---
name: wikipedia-interest-research
description: Research topic interest using Wikipedia article page views, compare language editions, validate data, and create shareable charts and one-page PDF reports.
---

# Wikipedia Interest Research

Use this skill when a user wants to compare or understand changes in attention to a topic using Wikipedia page views. Page views are a directional research signal. They do not measure product demand, audience size, willingness to pay, or causality.

## Workflow

1. Extract the topic, one or more Wikipedia language editions, article titles for each edition, date range, and requested deliverables.
2. Confirm unresolved choices that materially affect the result. When the user says "last two years", use the most recent complete day and the same date range for each edition. Default to daily API data, summarized monthly for trend analysis.
3. Match each topic to the correct article in each language. Article titles can differ across languages. Do not assume a literal translation is the right article. If a title is uncertain, use Wikipedia search or ask the user to confirm it. The program checks that a supplied page exists and follows redirects, but cannot establish that a page is semantically equivalent to the intended topic.
4. Run `scripts/wiki_interest.py` with one `--series` argument per language edition. Each argument is `language:title`; titles containing spaces are accepted. Use ISO dates. Example:

   ```bash
   python scripts/wiki_interest.py \
     --series pl:Post przerywany \
     --series cs:Přerušovaný půst \
     --start 2024-01-01 --end 2025-12-31 \
     --output-dir output/intermittent-fasting
   ```

   On PowerShell, put the command on one line or use its backtick continuation character.

5. Read the JSON result at `result.json`. Check each series' `quality`, `trend`, and `events` fields before writing conclusions. Confirm the resolved article title and coverage. If the tool reports a missing page, API error, low coverage, or short history, do not describe the result as reliable growth. Correct the title or range and rerun when appropriate.
6. Use the generated chart and PDF as supporting artifacts. Explain findings in plain language, identify the date range and page titles, and include relevant caveats. Never describe a visual difference in raw totals as a difference in audience-level popularity across language editions. Compare normalized indices for relative direction, and show raw views separately.
7. For a follow-up, change only the relevant titles, languages, dates, or output directory and rerun. Do not reuse old results after parameters change.

## Reading the analysis

The program requests daily views, aggregates them into monthly mean daily views, and calculates a within-series index with the first month's mean set to 100. Monthly Theil-Sen slope and first-half versus second-half change describe direction and consistency. A heuristic signal rating is based on data coverage, history length, direction agreement, and whether flagged daily spikes dominate the range. It is not a statistical probability or a forecast.

Describe calendar patterns as observations, not established seasonality. Do not claim seasonal effects from one or two annual cycles. A seasonal conclusion requires multiple complete annual cycles and an explicit seasonal analysis. Monthly averages for the first and last months may cover only part of those months.

The quality report includes expected and returned daily points, zero-view days, missing dates, coverage, and unusually large daily changes. A missing API point is not silently treated as a zero. The API may omit the most recent days; select a complete historical range and review the reported coverage. A sudden spike may reflect news, seasonality, bots, a change in article naming, or other causes. The data alone cannot identify its cause.

Article moves and redirects can affect continuity. Review the resolved title and check for title changes during the study period when a trend has a sharp break. The PDF transliterates titles with non-Latin characters for font compatibility; use the JSON for exact titles.

## Parameters and outputs

- `--series LANG:TITLE`: repeat for every language edition. Use the local article title, not the topic translated by guesswork.
- `--start YYYY-MM-DD` and `--end YYYY-MM-DD`: inclusive dates, no more than five years apart.
- `--output-dir PATH`: directory for generated files.
- `--cache-dir PATH`: optional cache directory. Defaults to `.cache` inside the output directory.
- `--refresh`: fetch again instead of using cached responses.
- `--project wikipedia`: optional Wikimedia project, for example `wiki` or `wiktionary`.

The tool writes `result.json`, `chart.svg`, and `report.pdf`. The JSON is the source of truth for the agent. The PDF contains the period, pages, key metrics, chart, quality notes, and limitations on one page.

## Failure handling

If the API is unavailable, report that the request failed and retain the error details from the JSON when available. Do not fabricate values. If no article exists, use the language edition's search to identify a likely page, then confirm it with the user when multiple candidates could change the result. If fewer than six complete months are available, treat trend interpretation as exploratory. If coverage is below 90%, state that limitation prominently.

## Extending the skill

Develop in small, verifiable steps: add reproducible fixtures first, then new analyses behind explicit fields, then additional data sources or larger-scale ingestion. Preserve the JSON contract where possible. For broad studies, add bounded concurrency, resumable fetches, a persistent cache, batch storage such as Parquet, and a separate analysis layer. For stronger research claims, add seasonal adjustment, sensitivity checks across article variants, event annotations, and validated uncertainty estimates. Keep the one-page report concise and move detailed methods or large result tables to a separate artifact.
