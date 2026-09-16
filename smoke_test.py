"""EcosystemPulse V3.1 smoke tests for fresh local/CI builds."""

import json
import re
import sys
import tempfile
from datetime import date, timedelta
from pathlib import Path
from urllib.parse import urlsplit

BASE = Path(__file__).resolve().parent
OUTPUT = BASE / "output"
DATA = BASE / "data"
sys.path.insert(0, str(BASE / "engine"))

from history_store import HistoryStore
from trend_analyzer import TrendAnalyzer

errors = []


def record(condition, label, detail=""):
    status = "PASS" if condition else "FAIL"
    print(f"{label} {status}" + (f": {detail}" if detail else ""))
    if not condition:
        errors.append(f"{label} FAIL" + (f": {detail}" if detail else ""))


def load_json(path, default):
    if not path.exists():
        return default
    try:
        with path.open(encoding="utf-8") as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError):
        return default


collected = DATA / "collected_data.json"
d = load_json(collected, {})
npm_count = len(d.get("npm", {}))
pypi_count = len(d.get("pypi", {}))
record(collected.exists() and npm_count >= 30 and pypi_count >= 25,
       "CHECK 1", f"collected {npm_count} npm + {pypi_count} pypi")

expected = ["index.html", "npm.html", "pypi.html", "search.html", "robots.txt", "sitemap.xml", "css/style.css"]
missing = [name for name in expected if not (OUTPUT / name).exists()]
record(not missing, "CHECK 2", f"{len(expected)-len(missing)}/{len(expected)} files" + (f"; missing={missing}" if missing else ""))

pages_dir = OUTPUT / "pages"
html_files = list(pages_dir.glob("*.html")) if pages_dir.exists() else []
record(len(html_files) >= 60, "CHECK 3", f"{len(html_files)} package pages")

broken = []
for page in OUTPUT.rglob("*.html"):
    content = page.read_text(encoding="utf-8", errors="ignore")
    for href in re.findall(r'href=["\']([^"\']+)["\']', content):
        parts = urlsplit(href)
        if parts.scheme or href.startswith("//") or href.startswith("#") or href.startswith("mailto:"):
            continue
        target_text = parts.path
        if not target_text:
            continue
        target = (page.parent / target_text).resolve()
        try:
            target.relative_to(OUTPUT.resolve())
        except ValueError:
            broken.append(f"{page.relative_to(OUTPUT)} -> {href} (escapes output)")
            continue
        if target.is_dir():
            target = target / "index.html"
        if not target.exists():
            broken.append(f"{page.relative_to(OUTPUT)} -> {href}")
record(not broken, "CHECK 4", f"{len(broken)} broken internal links")
if broken:
    errors.extend("BROKEN: " + item for item in broken[:20])

giant = [f"{f.name}({f.stat().st_size})" for f in html_files if f.stat().st_size > 30000]
record(not giant, "CHECK 5", f"{len(giant)} giant package pages")

sitemap = OUTPUT / "sitemap.xml"
sc = sitemap.read_text(encoding="utf-8") if sitemap.exists() else ""
url_count = sc.count("<url>")
valid_sitemap = "<urlset" in sc and "</urlset>" in sc and "/pages/" in sc and "/package/" not in sc
record(valid_sitemap, "CHECK 6", f"{url_count} URLs")

robots = OUTPUT / "robots.txt"
rc = robots.read_text(encoding="utf-8") if robots.exists() else ""
record("Sitemap:" in rc and rc.strip().endswith("sitemap.xml"), "CHECK 7")

react = d.get("npm", {}).get("react", {}) if d else {}
record(bool(react.get("latest_version")) and bool(react.get("description")),
       "CHECK 8", f"react={react.get('latest_version', 'missing')}")

empty = [str(f.relative_to(OUTPUT)) for f in OUTPUT.rglob("*.html") if f.stat().st_size < 100]
record(not empty, "CHECK 9", f"{len(empty)} empty pages")

search_path = OUTPUT / "search.html"
search_html = search_path.read_text(encoding="utf-8") if search_path.exists() else ""
has_npm = "registry.npmjs.org" in search_html
has_pypi_link = "pypi.org/search" in search_html
record(has_npm and has_pypi_link, "CHECK 10")

leaks = []
for f in OUTPUT.rglob("*"):
    if f.is_file() and f.suffix.lower() in {".html", ".xml", ".txt", ".css", ".js"}:
        c = f.read_text(encoding="utf-8", errors="ignore")
        if re.search(r'\b(api_key|api[-_]?secret|access[-_]?token|auth[-_]?token)\s*[=:]', c, re.IGNORECASE):
            leaks.append(str(f.relative_to(OUTPUT)))
record(not leaks, "CHECK 11", "no secrets in output" if not leaks else str(leaks))

windows_paths = []
for f in OUTPUT.rglob("*.html"):
    c = f.read_text(encoding="utf-8", errors="ignore")
    if "C:\\" in c or "Users\\" in c:
        windows_paths.append(str(f.relative_to(OUTPUT)))
record(not windows_paths, "CHECK 12", "no Windows paths")

index_html = (OUTPUT / "index.html").read_text(encoding="utf-8") if (OUTPUT / "index.html").exists() else ""
homepage_passes_query = 'action="search.html"' in index_html and 'name="q"' in index_html
record(homepage_passes_query, "CHECK 13", "homepage form -> search.html?q=...")

search_reads_query = "URLSearchParams" in search_html and "params.get('q')" in search_html and ("search(q.trim())" in search_html or "search(q)" in search_html)
record(search_reads_query, "CHECK 14", "search.html reads ?q= and auto-searches")

false_claim = bool(re.search(r'search.*pypi.*simultaneously|pypi.*search.*simultaneously', search_html, re.IGNORECASE))
record(not false_claim, "CHECK 15", "no false PyPI search claims")

record("Search PyPI for" in search_html and "pypi.org/search" in search_html, "CHECK 16", "PyPI section links to pypi.org/search")

root_relative = []
for f in OUTPUT.rglob("*.html"):
    c = f.read_text(encoding="utf-8", errors="ignore")
    for attr, val in re.findall(r'\b(href|src|action)=["\']([^"\']+)["\']', c):
        if val.startswith("/") and not val.startswith("//"):
            root_relative.append(f"{f.relative_to(OUTPUT)}: {attr}={val}")
record(not root_relative, "CHECK 17", "no root-relative internal asset/navigation paths")

custom_domain = "ecosystempulse.dev"
record(custom_domain in sc and custom_domain in rc and "thanksforfish.github.io/EcosystemPulse" not in sc and "thanksforfish.github.io/EcosystemPulse" not in rc,
       "CHECK 18", "deployment URLs target ecosystempulse.dev")

all_html = list(OUTPUT.rglob("*.html"))
missing_analytics = []
for f in all_html:
    c = f.read_text(encoding="utf-8", errors="ignore")
    if "static.cloudflareinsights.com/beacon.min.js" not in c or "12deb59ddd504e9294658e00ad85255a" not in c:
        missing_analytics.append(str(f.relative_to(OUTPUT)))
record(bool(all_html) and not missing_analytics, "CHECK 19",
       f"Cloudflare analytics present on {len(all_html)} HTML pages" if not missing_analytics else f"missing on {missing_analytics[:10]}")

# V3 durable-history checks
npm_history_path = DATA / "history" / "npm.json"
pypi_history_path = DATA / "history" / "pypi.json"
npm_history = load_json(npm_history_path, {})
pypi_history = load_json(pypi_history_path, {})
record(npm_history_path.exists() and pypi_history_path.exists() and npm_history.get("schema_version") == 1 and pypi_history.get("schema_version") == 1,
       "CHECK 20", "durable history files + schema v1")

npm_hist_packages = npm_history.get("packages", {})
pypi_hist_packages = pypi_history.get("packages", {})
record(len(npm_hist_packages) >= 30 and len(pypi_hist_packages) >= 25,
       "CHECK 21", f"history covers {len(npm_hist_packages)} npm + {len(pypi_hist_packages)} pypi")

series_with_14 = sum(
    1 for item in npm_hist_packages.values()
    if len(item.get("daily_downloads", [])) >= 14
)
record(series_with_14 >= 20, "CHECK 22", f"{series_with_14} npm packages have >=14 stored download observations")

history_integrity_problems = []
for name, item in npm_hist_packages.items():
    daily = item.get("daily_downloads", [])
    days = [p.get("day") for p in daily if isinstance(p, dict)]
    snapshots = item.get("snapshots", [])
    snap_days = [p.get("date") for p in snapshots if isinstance(p, dict)]
    if days != sorted(set(days)):
        history_integrity_problems.append(f"{name}: daily dates not sorted/unique")
    if snap_days != sorted(set(snap_days)):
        history_integrity_problems.append(f"{name}: snapshot dates not sorted/unique")
record(not history_integrity_problems, "CHECK 23", "history dates sorted and de-duplicated")

trends_path = DATA / "trends.json"
trends = load_json(trends_path, {})
npm_trends = trends.get("npm", {})
pypi_trends = trends.get("pypi", {})
with_change = [item for item in npm_trends.values() if item.get("change_7d_pct") is not None]
quality_fields_present = all(
    "momentum_available" in item and "download_observation_days" in item
    for item in npm_trends.values()
)
record(trends_path.exists() and trends.get("schema_version") == 1 and len(npm_trends) >= 30 and len(pypi_trends) >= 25 and quality_fields_present,
       "CHECK 24", f"trends cover {len(npm_trends)} npm + {len(pypi_trends)} pypi; {len(with_change)} reliable npm momentum values")

# Momentum math must use 14 consecutive calendar days, not merely the last 14 stored points.
start_day = date(2026, 1, 1)
contiguous_points = [
    {"day": (start_day + timedelta(days=i)).isoformat(), "downloads": 100 if i < 7 else 120}
    for i in range(14)
]
synthetic_metrics = TrendAnalyzer._download_metrics({"daily_downloads": contiguous_points})
record(
    synthetic_metrics.get("momentum_available")
    and synthetic_metrics.get("downloads_previous_7d") == 700
    and synthetic_metrics.get("downloads_7d") == 840
    and synthetic_metrics.get("change_7d_pct") == 20.0,
    "CHECK 25",
    "7-day momentum recomputes from 14 consecutive reliable days",
)

npm_trend_pages = 0
pypi_release_pages = 0
for name in d.get("npm", {}):
    page = pages_dir / f"{name}.html"
    if page.exists():
        text = page.read_text(encoding="utf-8", errors="ignore")
        if "Download momentum" in text and "class=\"sparkline\"" in text and "npm daily downloads" in text:
            npm_trend_pages += 1
for name in d.get("pypi", {}):
    page = pages_dir / f"{name}.html"
    if page.exists() and "Release activity" in page.read_text(encoding="utf-8", errors="ignore"):
        pypi_release_pages += 1
record(npm_trend_pages >= 20, "CHECK 26", f"{npm_trend_pages} npm package pages render quality-aware trend panels")
record(pypi_release_pages >= 25, "CHECK 27", f"{pypi_release_pages} PyPI package pages render release activity")

record("Fastest-rising tracked npm packages" in index_html or "Download momentum is warming up" in index_html,
       "CHECK 28", "homepage exposes measured momentum state")

canonical_package_pages = 0
for f in html_files:
    text = f.read_text(encoding="utf-8", errors="ignore")
    if f'<link rel="canonical" href="https://ecosystempulse.dev/pages/' in text:
        canonical_package_pages += 1
record(canonical_package_pages >= 60, "CHECK 29", f"canonical custom-domain URLs on {canonical_package_pages} package pages")

# V3.1 data-integrity regression checks.
excluded = npm_history.get("excluded_download_days", {})
if not isinstance(excluded, dict):
    excluded = {}
excluded_leaks = []
for name, item in npm_hist_packages.items():
    stored_days = {
        str(point.get("day")) for point in item.get("daily_downloads", [])
        if isinstance(point, dict) and point.get("day")
    }
    overlap = stored_days & set(excluded)
    if overlap:
        excluded_leaks.append(f"{name}: {sorted(overlap)}")
record(not excluded_leaks, "CHECK 30", f"{len(excluded)} registry-wide anomaly day(s) excluded from stored series")

synthetic_series = {}
for i in range(12):
    synthetic_series[f"pkg{i}"] = [
        {"day": "2026-01-01", "downloads": 0 if i < 10 else 15},
        {"day": "2026-01-02", "downloads": 100 + i},
    ]
flagged = HistoryStore._find_suspect_zero_days(synthetic_series)
record("2026-01-01" in flagged and "2026-01-02" not in flagged,
       "CHECK 31", "registry-wide zero anomaly detector flags coordinated zeros, not normal days")

gapped_points = contiguous_points[:6] + contiguous_points[7:] + [
    {"day": (start_day - timedelta(days=1)).isoformat(), "downloads": 100}
]
gapped_metrics = TrendAnalyzer._download_metrics({"daily_downloads": gapped_points})
record(not gapped_metrics.get("momentum_available") and gapped_metrics.get("change_7d_pct") is None,
       "CHECK 32", "momentum is withheld when the comparison window contains a calendar gap")

# A later corrected npm range must restore a date that was previously excluded as a coordinated zero.
repair_ok = False
with tempfile.TemporaryDirectory() as tmp:
    tmp_data = Path(tmp)
    store = HistoryStore(tmp_data)
    packages = {
        f"pkg{i}": {
            "name": f"pkg{i}",
            "latest_version": "1.0.0",
            "all_versions": ["1.0.0"],
            "dependencies": [],
        }
        for i in range(12)
    }
    collected_stub = {"collected_at": "2026-01-03T00:00:00+00:00", "npm": packages, "pypi": {}}

    class FakeCollector:
        def __init__(self, corrected=False):
            self.corrected = corrected

        def get_npm_download_ranges(self, names, days=30):
            value = 100 if self.corrected else 0
            return {
                name: {
                    "daily": [{"day": "2026-01-01", "downloads": value}],
                    "total": value,
                }
                for name in names
            }

    store.update(collected_stub, FakeCollector(corrected=False))
    first = load_json(tmp_data / "history" / "npm.json", {})
    first_excluded = "2026-01-01" in first.get("excluded_download_days", {})
    first_absent = all(
        not entry.get("daily_downloads")
        for entry in first.get("packages", {}).values()
    )

    collected_stub["collected_at"] = "2026-01-04T00:00:00+00:00"
    store.update(collected_stub, FakeCollector(corrected=True))
    second = load_json(tmp_data / "history" / "npm.json", {})
    second_restored = all(
        entry.get("daily_downloads") == [{"day": "2026-01-01", "downloads": 100}]
        for entry in second.get("packages", {}).values()
    )
    second_cleared = "2026-01-01" not in second.get("excluded_download_days", {})
    repair_ok = first_excluded and first_absent and second_restored and second_cleared
record(repair_ok, "CHECK 33", "later corrected npm data restores a previously excluded anomaly day")

print("\n=== RESULT ===")
if errors:
    for e in errors:
        print("  " + e)
    raise SystemExit(1)
print("ALL 33 CHECKS PASSED")
