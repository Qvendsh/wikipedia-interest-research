from __future__ import annotations

import argparse
import calendar
import datetime as dt
import json
import math
import re
import statistics
import sys
import textwrap
import unicodedata
import urllib.error
import urllib.parse
import urllib.request
import xml.sax.saxutils
from pathlib import Path
from typing import Any


USER_AGENT = "WikipediaInterestResearch/1.0 (research tool)"
API_TIMEOUT = 30


class ResearchError(Exception):
    pass


def parse_date(value: str) -> dt.date:
    try:
        return dt.date.fromisoformat(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(f"Invalid date {value!r}; use YYYY-MM-DD") from exc


def parse_series(value: str) -> tuple[str, str]:
    if ":" not in value:
        raise argparse.ArgumentTypeError("Series must use LANG:TITLE format")
    language, title = value.split(":", 1)
    language = language.strip().lower()
    title = title.strip()
    if not re.fullmatch(r"[a-z0-9-]+", language) or not title:
        raise argparse.ArgumentTypeError("Series must include a language code and article title")
    return language, title


def request_json(url: str) -> dict[str, Any]:
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": "application/json"})
    try:
        with urllib.request.urlopen(request, timeout=API_TIMEOUT) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")[:500]
        raise ResearchError(f"HTTP {exc.code} from Wikimedia: {detail}") from exc
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
        raise ResearchError(f"Wikimedia request failed: {exc}") from exc


def cached_json(cache_path: Path, url: str, refresh: bool) -> dict[str, Any]:
    if cache_path.exists() and not refresh:
        try:
            return json.loads(cache_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            cache_path.unlink(missing_ok=True)
    value = request_json(url)
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    cache_path.write_text(json.dumps(value, ensure_ascii=False), encoding="utf-8")
    return value


def resolve_article(language: str, title: str, project: str, cache_dir: Path, refresh: bool) -> str:
    host = f"{language}.{project}.org"
    params = urllib.parse.urlencode({"action": "query", "format": "json", "redirects": 1, "prop": "info", "titles": title})
    url = f"https://{host}/w/api.php?{params}"
    key = urllib.parse.quote(f"resolve-{language}-{project}-{title}", safe="")
    data = cached_json(cache_dir / f"{key}.json", url, refresh)
    pages = data.get("query", {}).get("pages", {})
    if not pages:
        raise ResearchError(f"Could not resolve {language}:{title}")
    page = next(iter(pages.values()))
    if "missing" in page:
        search_params = urllib.parse.urlencode({"action": "query", "format": "json", "list": "search", "srsearch": title, "srlimit": 5})
        search_url = f"https://{host}/w/api.php?{search_params}"
        try:
            search_data = cached_json(cache_dir / f"{key}-search.json", search_url, refresh)
            candidates = [item.get("title", "") for item in search_data.get("query", {}).get("search", [])]
        except ResearchError:
            candidates = []
        suggestion = f" Search candidates: {', '.join(candidates)}." if candidates else ""
        raise ResearchError(f"Article does not exist: {language}:{title}.{suggestion}")
    return str(page.get("title", title))


def fetch_views(language: str, title: str, project: str, start: dt.date, end: dt.date, cache_dir: Path, refresh: bool) -> dict[dt.date, int]:
    article = urllib.parse.quote(title.replace(" ", "_"), safe="")
    start_value = start.strftime("%Y%m%d")
    end_value = end.strftime("%Y%m%d")
    url = f"https://wikimedia.org/api/rest_v1/metrics/pageviews/per-article/{language}.{project}.org/all-access/user/{article}/daily/{start_value}/{end_value}"
    key = urllib.parse.quote(f"views-{language}-{project}-{title}-{start_value}-{end_value}", safe="")
    data = cached_json(cache_dir / f"{key}.json", url, refresh)
    rows = data.get("items")
    if not isinstance(rows, list):
        raise ResearchError(f"Unexpected pageviews response for {language}:{title}")
    values: dict[dt.date, int] = {}
    for row in rows:
        try:
            day = dt.datetime.strptime(str(row["timestamp"]), "%Y%m%d00").date()
            views = int(row["views"])
        except (KeyError, TypeError, ValueError) as exc:
            raise ResearchError(f"Malformed pageview row for {language}:{title}") from exc
        if start <= day <= end:
            values[day] = views
    return values


def month_key(day: dt.date) -> str:
    return day.strftime("%Y-%m")


def theil_sen_slope(points: list[tuple[int, float]]) -> float:
    slopes = [(right_y - left_y) / (right_x - left_x) for index, (left_x, left_y) in enumerate(points) for right_x, right_y in points[index + 1:] if right_x != left_x]
    return statistics.median(slopes) if slopes else 0.0


def analyze_series(language: str, requested_title: str, resolved_title: str, views: dict[dt.date, int], start: dt.date, end: dt.date) -> dict[str, Any]:
    expected_days = (end - start).days + 1
    all_days = [start + dt.timedelta(days=index) for index in range(expected_days)]
    observed = [views[day] for day in all_days if day in views]
    monthly_values: dict[str, list[int]] = {}
    for day in all_days:
        if day in views:
            monthly_values.setdefault(month_key(day), []).append(views[day])
    month_cursor = start.replace(day=1)
    month_keys = []
    while month_cursor <= end:
        month_keys.append(month_key(month_cursor))
        month_cursor = (month_cursor.replace(day=calendar.monthrange(month_cursor.year, month_cursor.month)[1]) + dt.timedelta(days=1)).replace(day=1)
    monthly_means = [statistics.mean(monthly_values[key]) if monthly_values.get(key) else None for key in month_keys]
    available = [value for value in monthly_means if value is not None]
    baseline_values = [value for value in available[:3]]
    baseline = statistics.mean(baseline_values) if baseline_values else 0.0
    index_values = [None if value is None or baseline <= 0 else value / baseline * 100 for value in monthly_means]
    usable = [(index, value) for index, value in enumerate(index_values) if value is not None]
    indexed = [value for _, value in usable]
    slope = theil_sen_slope(usable) * 12 if len(usable) >= 2 else None
    split = len(indexed) // 2
    early = statistics.mean(indexed[:split]) if split else None
    late = statistics.mean(indexed[split:]) if len(indexed) > split else None
    half_change = ((late / early) - 1) * 100 if early and late is not None else None
    positive_steps = sum(1 for left, right in zip(indexed, indexed[1:]) if right > left)
    nonflat_steps = sum(1 for left, right in zip(indexed, indexed[1:]) if right != left)
    direction_share = positive_steps / nonflat_steps if nonflat_steps else 0.5
    daily_changes = []
    for previous_day, current_day in zip(all_days, all_days[1:]):
        if previous_day in views and current_day in views:
            previous = views[previous_day]
            current = views[current_day]
            if previous > 0:
                daily_changes.append((current / previous, current_day, current))
    spike_candidates = [item for item in daily_changes if item[0] >= 5 and item[2] >= max(20, statistics.median(observed) * 3 if observed else 20)]
    spikes = [{"date": day.isoformat(), "multiple_of_previous_day": round(ratio, 1), "views": count} for ratio, day, count in sorted(spike_candidates, reverse=True)[:5]]
    coverage = len(views) / expected_days if expected_days else 0
    quality_flags = []
    if coverage < 0.9:
        quality_flags.append("Coverage is below 90%; missing days can affect the trend.")
    if len(available) < 6:
        quality_flags.append("Fewer than six observed months are available; trend interpretation is exploratory.")
    if baseline <= 0:
        quality_flags.append("The initial baseline is zero or unavailable; a relative index cannot be calculated.")
    if spikes:
        quality_flags.append("Large daily spikes were detected. Their causes are unknown and may not represent a sustained trend.")
    rating = "limited"
    if coverage >= 0.9 and len(available) >= 12 and baseline > 0:
        agrees = half_change is not None and slope is not None and (half_change >= 0) == (slope >= 0)
        if agrees and direction_share >= 0.6 and len(spikes) <= max(1, len(available) // 12):
            rating = "stronger descriptive signal"
        elif agrees:
            rating = "moderate descriptive signal"
    trend = "insufficient data"
    if slope is not None:
        if slope > 1:
            trend = "increasing"
        elif slope < -1:
            trend = "decreasing"
        else:
            trend = "roughly stable"
    return {
        "language": language,
        "requested_title": requested_title,
        "resolved_title": resolved_title,
        "daily_views": {day.isoformat(): views[day] for day in all_days if day in views},
        "quality": {
            "expected_daily_points": expected_days,
            "returned_daily_points": len(views),
            "coverage_percent": round(coverage * 100, 1),
            "missing_dates": [day.isoformat() for day in all_days if day not in views],
            "zero_view_days": sum(1 for value in views.values() if value == 0),
            "flags": quality_flags,
        },
        "trend": {
            "direction": trend,
            "signal_rating": rating,
            "monthly_theil_sen_index_points_per_year": round(slope, 2) if slope is not None else None,
            "first_half_to_second_half_change_percent": round(half_change, 1) if half_change is not None else None,
            "positive_monthly_steps_share": round(direction_share, 2),
            "baseline_mean_daily_views_first_three_months": round(baseline, 2) if baseline else None,
            "monthly_index_base_100": [{"month": key, "index": round(value, 2) if value is not None else None} for key, value in zip(month_keys, index_values)],
            "monthly_mean_daily_views": [{"month": key, "views": round(value, 2) if value is not None else None} for key, value in zip(month_keys, monthly_means)],
        },
        "events": {"large_daily_spikes": spikes},
        "observed_daily_views": {"mean": round(statistics.mean(observed), 2) if observed else None, "median": statistics.median(observed) if observed else None, "total": sum(observed)},
    }


def svg_chart(series: list[dict[str, Any]], start: dt.date, end: dt.date) -> str:
    width, height = 1000, 560
    left, right, top, bottom = 90, 35, 70, 85
    plot_width, plot_height = width - left - right, height - top - bottom
    points = [(row["language"], row["trend"]["monthly_index_base_100"]) for row in series]
    all_values = [item["index"] for _, values in points for item in values if item["index"] is not None]
    max_y = max(150, math.ceil(max(all_values, default=100) / 50) * 50)
    palette = ["#1459a6", "#c34c24", "#27834a", "#7547a8", "#ac7b00", "#b03d78"]
    chunks = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">', '<rect width="100%" height="100%" fill="white"/>', '<text x="90" y="35" font-family="Arial" font-size="24" font-weight="bold">Wikipedia attention index</text>', f'<text x="90" y="57" font-family="Arial" font-size="13" fill="#555">Monthly mean daily page views, first three observed months = 100 | {start} to {end}</text>']
    for tick in range(0, max_y + 1, max(25, max_y // 5)):
        y = top + plot_height * (1 - tick / max_y)
        chunks.append(f'<line x1="{left}" y1="{y:.1f}" x2="{width-right}" y2="{y:.1f}" stroke="#dddddd"/>')
        chunks.append(f'<text x="{left-12}" y="{y+4:.1f}" text-anchor="end" font-family="Arial" font-size="12" fill="#444">{tick}</text>')
    chunks.append(f'<line x1="{left}" y1="{top}" x2="{left}" y2="{height-bottom}" stroke="#555"/>')
    chunks.append(f'<line x1="{left}" y1="{height-bottom}" x2="{width-right}" y2="{height-bottom}" stroke="#555"/>')
    count = max((len(values) for _, values in points), default=1)
    for idx, (language, values) in enumerate(points):
        color = palette[idx % len(palette)]
        coordinates = []
        for position, item in enumerate(values):
            if item["index"] is not None:
                x = left + (plot_width * position / max(1, count - 1))
                y = top + plot_height * (1 - min(max_y, item["index"]) / max_y)
                coordinates.append((x, y))
            else:
                coordinates.append(None)
        for first, second in zip(coordinates, coordinates[1:]):
            if first is not None and second is not None:
                chunks.append(f'<line x1="{first[0]:.1f}" y1="{first[1]:.1f}" x2="{second[0]:.1f}" y2="{second[1]:.1f}" stroke="{color}" stroke-width="3"/>')
        chunks.append(f'<line x1="{left + idx*180}" y1="{height-35}" x2="{left + idx*180+24}" y2="{height-35}" stroke="{color}" stroke-width="4"/>')
        chunks.append(f'<text x="{left + idx*180+32}" y="{height-30}" font-family="Arial" font-size="14" fill="#222">{xml.sax.saxutils.escape(language)}</text>')
    chunks.append(f'<text x="{left + plot_width/2}" y="{height-5}" text-anchor="middle" font-family="Arial" font-size="13" fill="#555">Month</text>')
    chunks.append('</svg>')
    return "\n".join(chunks)


def pdf_escape(value: str) -> bytes:
    value = transliterate(value)
    return value.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)").encode("ascii", errors="replace")


def transliterate(value: str) -> str:
    replacements = str.maketrans({
        "А": "A", "Б": "B", "В": "V", "Г": "H", "Ґ": "G", "Д": "D", "Е": "E", "Є": "Ye", "Ж": "Zh", "З": "Z", "И": "Y", "І": "I", "Ї": "Yi", "Й": "Y", "К": "K", "Л": "L", "М": "M", "Н": "N", "О": "O", "П": "P", "Р": "R", "С": "S", "Т": "T", "У": "U", "Ф": "F", "Х": "Kh", "Ц": "Ts", "Ч": "Ch", "Ш": "Sh", "Щ": "Shch", "Ь": "", "Ю": "Yu", "Я": "Ya", "Ё": "Yo", "Ъ": "", "Ы": "Y", "Э": "E",
        "а": "a", "б": "b", "в": "v", "г": "h", "ґ": "g", "д": "d", "е": "e", "є": "ye", "ж": "zh", "з": "z", "и": "y", "і": "i", "ї": "yi", "й": "y", "к": "k", "л": "l", "м": "m", "н": "n", "о": "o", "п": "p", "р": "r", "с": "s", "т": "t", "у": "u", "ф": "f", "х": "kh", "ц": "ts", "ч": "ch", "ш": "sh", "щ": "shch", "ь": "", "ю": "yu", "я": "ya", "ё": "yo", "ъ": "", "ы": "y", "э": "e",
    })
    value = value.translate(replacements)
    value = "".join(character for character in unicodedata.normalize("NFKD", value) if not unicodedata.combining(character))
    return value.encode("ascii", errors="replace").decode("ascii")


def create_pdf(path: Path, result: dict[str, Any]) -> None:
    content: list[bytes] = []

    def text(x: float, y: float, size: int, value: str, font: str = "F1") -> None:
        content.append(b"BT /" + font.encode() + b" " + str(size).encode() + b" Tf " + f"{x:.1f} {y:.1f} Td ".encode() + b"(" + pdf_escape(value) + b") Tj ET\n")

    def line(x1: float, y1: float, x2: float, y2: float, color: tuple[float, float, float], thickness: float = 1) -> None:
        content.append(f"{color[0]} {color[1]} {color[2]} RG {thickness} w {x1:.1f} {y1:.1f} m {x2:.1f} {y2:.1f} l S\n".encode())

    start, end = result["period"]["start"], result["period"]["end"]
    text(42, 755, 20, "Wikipedia interest research", "F2")
    text(42, 735, 10, f"Period: {start} to {end} | Project: {result['project']}")
    text(42, 718, 9, "Wikimedia Analytics API | Relative index, monthly mean daily views; baseline = 100")
    colors = [(0.08, 0.35, 0.65), (0.76, 0.3, 0.14), (0.15, 0.5, 0.29), (0.45, 0.27, 0.65)]
    chart_x, chart_y, chart_w, chart_h = 62, 470, 490, 210
    max_value = max([150.0] + [item["index"] for row in result["series"] for item in row["trend"]["monthly_index_base_100"] if item["index"] is not None])
    max_value = math.ceil(max_value / 50) * 50
    for tick in range(0, int(max_value) + 1, max(25, int(max_value) // 5)):
        y = chart_y + chart_h * tick / max_value
        line(chart_x, y, chart_x + chart_w, y, (0.85, 0.85, 0.85), 0.5)
        text(chart_x - 28, y - 3, 8, str(tick))
    line(chart_x, chart_y, chart_x, chart_y + chart_h, (0.3, 0.3, 0.3), 0.8)
    line(chart_x, chart_y, chart_x + chart_w, chart_y, (0.3, 0.3, 0.3), 0.8)
    for idx, row in enumerate(result["series"]):
        values = row["trend"]["monthly_index_base_100"]
        color = colors[idx % len(colors)]
        coords = []
        for pos, item in enumerate(values):
            if item["index"] is not None:
                x = chart_x + chart_w * pos / max(1, len(values) - 1)
                y = chart_y + chart_h * min(item["index"], max_value) / max_value
                coords.append((x, y))
            else:
                coords.append(None)
        for p1, p2 in zip(coords, coords[1:]):
            if p1 is not None and p2 is not None:
                line(p1[0], p1[1], p2[0], p2[1], color, 2)
        text(62 + (idx % 2) * 250, 448 - (idx // 2) * 14, 9, f"{row['language']}: {row['resolved_title'][:38]}")
    text(42, 415, 13, "Findings", "F2")
    y = 397
    for row in result["series"]:
        trend = row["trend"]
        slope = trend["monthly_theil_sen_index_points_per_year"]
        slope_text = "not available" if slope is None else f"{slope:+.1f} index points/year"
        half = trend["first_half_to_second_half_change_percent"]
        half_text = "not available" if half is None else f"{half:+.1f}% first half to second half"
        summary = f"{row['language']} {transliterate(row['resolved_title'])[:24]}: {trend['direction']}; slope {slope_text}."
        text(48, y, 8, summary)
        y -= 12
        detail = f"{half_text}; signal: {trend['signal_rating']}; coverage: {row['quality']['coverage_percent']}%; spikes: {len(row['events']['large_daily_spikes'])}."
        for detail_line in textwrap.wrap(detail, width=95):
            text(58, y, 8, detail_line)
            y -= 10
        y -= 6
    notes_heading_y = max(120, y - 4)
    text(42, notes_heading_y, 12, "Data quality and interpretation", "F2")
    note_y = notes_heading_y - 18
    notes = ["Page views are an attention proxy, not product demand or willingness to pay.", "Normalized series show relative change within each language edition; raw totals are not directly comparable.", "Spike causes are unknown. The signal rating is heuristic, not a probability or forecast."]
    for row in result["series"]:
        notes.extend(row["quality"]["flags"][:1])
    for note in notes[:5]:
        for line_text in textwrap.wrap(transliterate(note), width=105)[:2]:
            text(48, note_y, 8, line_text)
            note_y -= 12
    stream = b"".join(content)
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Resources << /Font << /F1 4 0 R /F2 5 0 R >> >> /Contents 6 0 R >>",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica /Encoding /WinAnsiEncoding >>",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica-Bold /Encoding /WinAnsiEncoding >>",
        b"<< /Length " + str(len(stream)).encode() + b" >>\nstream\n" + stream + b"endstream",
    ]
    pdf = bytearray(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n")
    offsets = [0]
    for index, obj in enumerate(objects, 1):
        offsets.append(len(pdf))
        pdf.extend(f"{index} 0 obj\n".encode() + obj + b"\nendobj\n")
    xref = len(pdf)
    pdf.extend(f"xref\n0 {len(offsets)}\n0000000000 65535 f \n".encode())
    for offset in offsets[1:]:
        pdf.extend(f"{offset:010d} 00000 n \n".encode())
    pdf.extend(f"trailer\n<< /Size {len(offsets)} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode())
    path.write_bytes(pdf)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Analyze Wikipedia page views and create a chart and one-page PDF report.")
    parser.add_argument("--series", action="append", type=parse_series, required=True, metavar="LANG:TITLE")
    parser.add_argument("--start", type=parse_date, required=True)
    parser.add_argument("--end", type=parse_date, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--cache-dir", type=Path)
    parser.add_argument("--refresh", action="store_true")
    parser.add_argument("--project", default="wikipedia", choices=["wikipedia", "wiktionary"])
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    today = dt.date.today()
    if args.end < args.start:
        parser.error("--end must be on or after --start")
    if args.end >= today:
        parser.error("--end must be before today; use complete historical days")
    if (args.end - args.start).days > 5 * 366:
        parser.error("Date range cannot exceed five years")
    if len(args.series) > 6:
        parser.error("Compare no more than six series per report")
    if len(set(args.series)) != len(args.series):
        parser.error("Series must be unique")
    output_dir = args.output_dir.resolve()
    cache_dir = args.cache_dir.resolve() if args.cache_dir else output_dir / ".cache"
    output_dir.mkdir(parents=True, exist_ok=True)
    result: dict[str, Any] = {"schema_version": "1.0", "project": args.project, "period": {"start": args.start.isoformat(), "end": args.end.isoformat()}, "series": [], "artifacts": {}}
    errors = []
    for language, title in args.series:
        try:
            resolved = resolve_article(language, title, args.project, cache_dir, args.refresh)
            views = fetch_views(language, resolved, args.project, args.start, args.end, cache_dir, args.refresh)
            result["series"].append(analyze_series(language, title, resolved, views, args.start, args.end))
        except ResearchError as exc:
            errors.append({"language": language, "requested_title": title, "error": str(exc)})
    result["errors"] = errors
    if result["series"]:
        chart_path = output_dir / "chart.svg"
        pdf_path = output_dir / "report.pdf"
        chart_path.write_text(svg_chart(result["series"], args.start, args.end), encoding="utf-8")
        create_pdf(pdf_path, result)
        result["artifacts"] = {"chart": str(chart_path), "report": str(pdf_path)}
    result_path = output_dir / "result.json"
    result_path.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps({"result": str(result_path), "successful_series": len(result["series"]), "errors": errors, "artifacts": result["artifacts"]}, indent=2, ensure_ascii=True))
    return 1 if errors and not result["series"] else 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except ResearchError as exc:
        print(json.dumps({"error": str(exc)}, ensure_ascii=True), file=sys.stderr)
        raise SystemExit(2)
