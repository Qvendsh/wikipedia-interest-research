from __future__ import annotations

import datetime as dt
import json
import os
import subprocess
import sys
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
API_URL = "https://openrouter.ai/api/v1/chat/completions"
TOOL_NAME = "run_wikipedia_research"


def load_environment_file(path: Path) -> None:
    if not path.exists():
        return
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        name, value = line.split("=", 1)
        name = name.strip()
        value = value.strip().strip("\"'")
        if name:
            os.environ.setdefault(name, value)


def request_completion(model: str, messages: list[dict[str, Any]], api_key: str) -> dict[str, Any]:
    payload = json.dumps({
        "model": model,
        "messages": messages,
        "tools": [{
            "type": "function",
            "function": {
                "name": TOOL_NAME,
                "description": "Fetch, validate, analyze, chart, and report Wikipedia page views for the requested language edition articles and date range.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "series": {"type": "array", "items": {"type": "string"}, "minItems": 1, "maxItems": 6, "description": "Article series in LANG:TITLE format, such as uk:Астрономія."},
                        "start": {"type": "string", "description": "Inclusive start date in YYYY-MM-DD format."},
                        "end": {"type": "string", "description": "Inclusive end date in YYYY-MM-DD format."},
                    },
                    "required": ["series", "start", "end"],
                    "additionalProperties": False,
                },
            },
        }],
        "tool_choice": "auto",
        "parallel_tool_calls": False,
        "temperature": 0,
        "max_tokens": 1200,
    }).encode("utf-8")
    request = urllib.request.Request(API_URL, data=payload, headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}, method="POST")
    try:
        with urllib.request.urlopen(request, timeout=120) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")[:1200]
        raise RuntimeError(f"OpenRouter returned HTTP {exc.code}: {detail}") from exc
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"OpenRouter request failed: {exc}") from exc


def run_research(arguments: dict[str, Any]) -> dict[str, Any]:
    series = arguments.get("series")
    start = arguments.get("start")
    end = arguments.get("end")
    if not isinstance(series, list) or not series or not all(isinstance(item, str) for item in series):
        raise ValueError("series must be a non-empty list of LANG:TITLE strings")
    for date_value in (start, end):
        if not isinstance(date_value, str):
            raise ValueError("start and end are required ISO dates")
        dt.date.fromisoformat(date_value)
    output_dir = ROOT / "output" / "model-evaluation"
    command = [sys.executable, str(ROOT / "scripts" / "wiki_interest.py")]
    for item in series:
        command.extend(["--series", item])
    command.extend(["--start", start, "--end", end, "--output-dir", str(output_dir)])
    completed = subprocess.run(command, cwd=ROOT, capture_output=True, text=True, timeout=240, check=False)
    if completed.returncode not in (0, 1):
        raise RuntimeError(completed.stderr[-1200:] or completed.stdout[-1200:] or f"Research command exited with {completed.returncode}")
    result_path = output_dir / "result.json"
    if not result_path.exists():
        raise RuntimeError("Research command did not write result.json")
    result = json.loads(result_path.read_text(encoding="utf-8"))
    compact_series = []
    for row in result.get("series", []):
        compact_series.append({key: value for key, value in row.items() if key != "daily_views"})
    return {
        "period": result.get("period"),
        "project": result.get("project"),
        "series": compact_series,
        "errors": result.get("errors", []),
        "artifacts": result.get("artifacts", {}),
    }


def evaluate() -> dict[str, Any]:
    load_environment_file(ROOT / ".env")
    api_key = os.environ.get("OPENROUTER_API_KEY")
    if not api_key:
        raise RuntimeError("Set OPENROUTER_API_KEY in the environment before running this script. Do not paste the key into chat or save it in this repository.")
    model = os.environ.get("OPENROUTER_MODEL", "openrouter/free")
    today = dt.date.today()
    end = today - dt.timedelta(days=1)
    try:
        start = end.replace(year=end.year - 2)
    except ValueError:
        start = end.replace(year=end.year - 2, day=28)
    skill = (ROOT / "SKILL.md").read_text(encoding="utf-8")
    user_request = f"Compare how interest in astronomy changed in Ukrainian and English Wikipedia over the last two years, ending on {end.isoformat()}. Explain how reliable the descriptive trend is, report any important data quality or spike caveats, and provide the chart and one-page PDF paths. Use the research tool and follow the skill instructions."
    messages: list[dict[str, Any]] = [
        {"role": "system", "content": f"You are an AI agent using this skill. Follow its workflow and limits.\n\n{skill}"},
        {"role": "user", "content": user_request},
    ]
    transcript: dict[str, Any] = {"requested_model": model, "request": user_request, "turns": []}
    for _ in range(4):
        response = request_completion(model, messages, api_key)
        actual_model = response.get("model")
        if actual_model:
            transcript["actual_model"] = actual_model
        choices = response.get("choices", [])
        if not choices:
            raise RuntimeError("OpenRouter returned no completion choices")
        message = choices[0].get("message", {})
        messages.append(message)
        calls = message.get("tool_calls", [])
        if not calls:
            transcript["answer"] = message.get("content", "")
            transcript["usage"] = response.get("usage")
            return transcript
        for call in calls:
            function = call.get("function", {})
            if function.get("name") != TOOL_NAME:
                tool_result = {"error": f"Unsupported tool requested: {function.get('name')}"}
            else:
                try:
                    arguments = json.loads(function.get("arguments", "{}"))
                    tool_result = run_research(arguments)
                except (ValueError, RuntimeError, json.JSONDecodeError, subprocess.TimeoutExpired) as exc:
                    tool_result = {"error": str(exc)}
            transcript["turns"].append({"tool": function.get("name"), "arguments": function.get("arguments"), "result": tool_result})
            messages.append({"role": "tool", "tool_call_id": call.get("id", ""), "name": function.get("name", TOOL_NAME), "content": json.dumps(tool_result, ensure_ascii=False)})
    raise RuntimeError("The model exceeded the four-step tool interaction limit")


def main() -> int:
    try:
        transcript = evaluate()
    except RuntimeError as exc:
        print(json.dumps({"error": str(exc)}, ensure_ascii=True), file=sys.stderr)
        return 1
    output_dir = ROOT / "output" / "model-evaluation"
    output_dir.mkdir(parents=True, exist_ok=True)
    transcript_path = output_dir / "transcript.json"
    transcript_path.write_text(json.dumps(transcript, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps({"requested_model": transcript.get("requested_model"), "actual_model": transcript.get("actual_model"), "transcript": str(transcript_path), "answer": transcript.get("answer", "")}, indent=2, ensure_ascii=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
