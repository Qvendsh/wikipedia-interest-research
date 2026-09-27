import datetime as dt
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts import wiki_interest


class FakeResponse:
    def __init__(self, value):
        self.value = json.dumps(value).encode("utf-8")

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def read(self):
        return self.value


class ResearchTests(unittest.TestCase):
    def test_parse_series_preserves_title_colons(self):
        self.assertEqual(wiki_interest.parse_series("uk:Стаття: уточнення"), ("uk", "Стаття: уточнення"))

    def test_analysis_marks_missing_points_and_detects_trend(self):
        start = dt.date(2024, 1, 1)
        end = dt.date(2024, 12, 31)
        views = {}
        day = start
        while day <= end:
            views[day] = 100 + (day.month * 15)
            day += dt.timedelta(days=1)
        views.pop(dt.date(2024, 4, 10))
        result = wiki_interest.analyze_series("uk", "Topic", "Topic", views, start, end)
        self.assertEqual(result["trend"]["direction"], "increasing")
        self.assertEqual(result["quality"]["returned_daily_points"], 365)
        self.assertIn("2024-04-10", result["quality"]["missing_dates"])

    def test_cli_end_to_end_with_mocked_wikimedia(self):
        start = dt.date(2025, 1, 1)
        end = dt.date(2025, 12, 31)
        requested_urls = []

        def fake_open(request, timeout):
            url = request.full_url
            requested_urls.append(url)
            if "/w/api.php?" in url:
                return FakeResponse({"query": {"pages": {"42": {"pageid": 42, "title": "Example topic"}}}})
            items = []
            day = start
            while day <= end:
                items.append({"timestamp": day.strftime("%Y%m%d") + "00", "views": 100 + day.month * 4})
                day += dt.timedelta(days=1)
            return FakeResponse({"items": items})

        with tempfile.TemporaryDirectory() as temp_dir:
            output_dir = Path(temp_dir) / "output"
            with patch.object(wiki_interest.urllib.request, "urlopen", side_effect=fake_open):
                code = wiki_interest.main([
                    "--series", "en:Example topic", "--start", start.isoformat(), "--end", end.isoformat(),
                    "--output-dir", str(output_dir),
                ])
            self.assertEqual(code, 0)
            result = json.loads((output_dir / "result.json").read_text(encoding="utf-8"))
            self.assertEqual(result["series"][0]["resolved_title"], "Example topic")
            self.assertEqual(result["series"][0]["quality"]["coverage_percent"], 100.0)
            self.assertTrue(any("/per-article/en.wikipedia.org/" in url and "/daily/20250101/20251231" in url for url in requested_urls))
            self.assertTrue((output_dir / "chart.svg").read_text(encoding="utf-8").startswith("<svg"))
            pdf = (output_dir / "report.pdf").read_bytes()
            self.assertTrue(pdf.startswith(b"%PDF-1.4"))
            self.assertIn(b"/Count 1", pdf)


if __name__ == "__main__":
    unittest.main()
