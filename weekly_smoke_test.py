"""Regression checks for honest weekly package-change reporting and frozen editions."""

import json
import sys
import tempfile
from datetime import date
from pathlib import Path

BASE = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE / "engine"))
from weekly_brief import WeeklyBrief, completed_week, extract_week_events

issues = []


def check(condition, label):
    print(("PASS " if condition else "FAIL ") + label)
    if not condition:
        issues.append(label)


def state(day, version, deps=None, meta=None):
    return {
        "date": day,
        "version": version,
        "dependency_declarations": deps or {},
        "mutable_metadata": meta or {},
    }


npm = {
    "packages": {
        "react": {
            "state_history": [
                state("2026-10-10", "19.0.0", {"dependencies": {"demo": "^1"}}),
                state("2026-10-15", "19.1.0", {"dependencies": {"demo": "^2"}}, {"engines": {"node": ">=22"}}),
            ]
        },
        "typescript": {"state_history": [state("2026-10-15", "5.0")]},  # first observation: NOT a release
        "angular": {  # explicitly retired from tracked packages
            "state_history": [state("2026-10-10", "1.0"), state("2026-10-16", "2.0")]
        },
    }
}
pypi = {
    "packages": {
        "pillow": {
            "state_history": [
                state("2026-10-11", "12.0", {"requires_dist": ["numpy>=1"]},
                      {"requires_python": ">=3.10"}),
                state("2026-10-17", "13.0", {"requires_dist": ["numpy>=2"]},
                      {"requires_python": ">=3.11<script>alert(1)</script>"}),
            ]
        }
    }
}
events = extract_week_events(npm, pypi, date(2026, 10, 12), date(2026, 10, 18))
check(
    completed_week(date(2026, 10, 20)) == (date(2026, 10, 12), date(2026, 10, 18))
    and completed_week(date(2026, 10, 18)) == (date(2026, 10, 5), date(2026, 10, 11)),
    "A report covers the last *completed* Monday-Sunday UTC week",
)
check(
    len([x for x in events if x["registry"] == "npm" and x["package"] == "react"]) == 3
    and len([x for x in events if x["registry"] == "pypi" and x["package"] == "pillow"]) == 3
    and not any(x["package"] in {"angular", "typescript"} for x in events),
    "Observed version, dependency, engine, and Python changes but not baselines/retired packages",
)
check(
    any(">=3.10" in x["detail"] and ">=3.11" in x["detail"]
        for x in events if x["category"] == "compatibility"),
    "Compatibility comparisons include the recorded before/after requirements",
)

with tempfile.TemporaryDirectory() as temporary:
    root = Path(temporary)
    data = root / "data"
    output = root / "output"
    (data / "history").mkdir(parents=True)
    output.mkdir()
    (output / "index.html").write_text(
        '<html><body><main><dl class="stats-grid"></dl></main></body></html>',
        encoding="utf-8",
    )
    (output / "sitemap.xml").write_text(
        '<?xml version="1.0"?><urlset></urlset>', encoding="utf-8"
    )
    for name, doc in (("npm", npm), ("pypi", pypi)):
        (data / "history" / f"{name}.json").write_text(json.dumps(doc), encoding="utf-8")

    brief = WeeklyBrief(data, output)
    result = brief.build(as_of=date(2026, 10, 20))
    stored = data / "history" / "weekly_reports" / "2026-10-18.json"
    frozen = stored.read_bytes()
    edition_html = (output / "weekly" / "2026-10-18.html").read_text(encoding="utf-8")
    latest_html = (output / "weekly.html").read_text(encoding="utf-8")
    homepage = (output / "index.html").read_text(encoding="utf-8")
    sitemap = (output / "sitemap.xml").read_text(encoding="utf-8")

    check(
        result["week_end"] == "2026-10-18" and result["events"] == len(events)
        and stored.exists() and (output / "weekly" / "2026-10-18.html").is_file(),
        "Completed edition is archived as JSON and static HTML",
    )
    check(
        "Python version requirement changed" in latest_html
        and "Runtime engine requirement changed" in latest_html
        and "Dependency requirement changes" in latest_html
        and "https://pypi.org/project/pillow/" in latest_html
        and 'href="pages/pillow.html"' in latest_html,
        "Report visibly explains compatibility and dependencies and links to evidence",
    )
    check(
        "&lt;script&gt;" in latest_html and "<script>alert(1)</script>" not in latest_html,
        "Registry-provided text is HTML-escaped",
    )
    check(
        'href="weekly.html"' in homepage
        and 'id="brief-home-title"' in homepage
        and sitemap.count("<loc>https://ecosystempulse.dev/weekly.html</loc>") == 1
        and sitemap.count("<loc>https://ecosystempulse.dev/weekly/2026-10-18.html</loc>") == 1
        and 'href="../css/style.css"' in edition_html,
        "Homepage teaser, sitemap, canonical archive and relative assets are correct",
    )
    pypi["packages"]["pillow"]["state_history"][-1]["version"] = "14.0"
    (data / "history" / "pypi.json").write_text(json.dumps(pypi), encoding="utf-8")
    brief.build(as_of=date(2026, 10, 20))
    check(
        stored.read_bytes() == frozen
        and (output / "sitemap.xml").read_text(encoding="utf-8").count(
            "<loc>https://ecosystempulse.dev/weekly.html</loc>"
        ) == 1,
        "Repeated daily builds cannot silently rewrite a frozen edition or duplicate URLs",
    )

# Inspect the real generated build, after run.py, without depending on any fixed version.
output = BASE / "output"
real_weekly = output / "weekly.html"
real_home = output / "index.html"
check(
    real_weekly.is_file()
    and "What changed this week?" in real_weekly.read_text(encoding="utf-8")
    and "weekly.html" in real_home.read_text(encoding="utf-8")
    and any((output / "weekly").glob("*.html")),
    "Production build contains discoverable, automatically generated weekly report",
)

if issues:
    raise SystemExit("Weekly briefing tests failed: " + ", ".join(issues))
print("ALL WEEKLY CHANGE BRIEF CHECKS PASSED")
