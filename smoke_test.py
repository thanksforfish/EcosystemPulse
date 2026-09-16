"""EcosystemPulse V3 smoke tests for fresh local/CI builds."""

import json
import re
from pathlib import Path
from urllib.parse import urlsplit

BASE = Path(__file__).resolve().parent
OUTPUT = BASE / "output"
DATA = BASE / "data"
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
record(series_with_14 >= 20, "CHECK 22", f"{series_with_14} npm packages have >=14 complete daily download points")

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
record(trends_path.exists() and trends.get("schema_version") == 1 and len(npm_trends) >= 30 and len(pypi_trends) >= 25 and len(with_change) >= 20,
       "CHECK 24", f"trends cover {len(npm_trends)} npm + {len(pypi_trends)} pypi; {len(with_change)} npm momentum values")

trend_math_ok = False
for item in with_change:
    points = item.get("download_points", [])
    values = [int(p.get("downloads", 0)) for p in points if isinstance(p, dict)]
    if len(values) < 14:
        continue
    last7 = sum(values[-7:])
    prev7 = sum(values[-14:-7])
    if prev7 <= 0:
        continue
    expected_change = round(((last7 - prev7) / prev7) * 100, 1)
    if expected_change == item.get("change_7d_pct") and last7 == item.get("downloads_7d") and prev7 == item.get("downloads_previous_7d"):
        trend_math_ok = True
        break
record(trend_math_ok, "CHECK 25", "7-day momentum recomputes from stored evidence")

npm_trend_pages = 0
pypi_release_pages = 0
for name in d.get("npm", {}):
    page = pages_dir / f"{name}.html"
    if page.exists():
        text = page.read_text(encoding="utf-8", errors="ignore")
        if "Download momentum" in text and "class=\"sparkline\"" in text and "previous 7" in text:
            npm_trend_pages += 1
for name in d.get("pypi", {}):
    page = pages_dir / f"{name}.html"
    if page.exists() and "Release activity" in page.read_text(encoding="utf-8", errors="ignore"):
        pypi_release_pages += 1
record(npm_trend_pages >= 20, "CHECK 26", f"{npm_trend_pages} npm package pages render evidence-backed trend panels")
record(pypi_release_pages >= 25, "CHECK 27", f"{pypi_release_pages} PyPI package pages render release activity")

record("Fastest-rising tracked npm packages" in index_html or "Download momentum is warming up" in index_html,
       "CHECK 28", "homepage exposes measured momentum state")

canonical_package_pages = 0
for f in html_files:
    text = f.read_text(encoding="utf-8", errors="ignore")
    if f'<link rel="canonical" href="https://ecosystempulse.dev/pages/' in text:
        canonical_package_pages += 1
record(canonical_package_pages >= 60, "CHECK 29", f"canonical custom-domain URLs on {canonical_package_pages} package pages")

print("\n=== RESULT ===")
if errors:
    for e in errors:
        print("  " + e)
    raise SystemExit(1)
print("ALL 29 CHECKS PASSED")
