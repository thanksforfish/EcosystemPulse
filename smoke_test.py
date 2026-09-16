"""EcosystemPulse smoke tests for fresh local/CI builds."""
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

collected = DATA / "collected_data.json"
if collected.exists():
    with collected.open(encoding="utf-8") as f:
        d = json.load(f)
    npm_count = len(d.get("npm", {}))
    pypi_count = len(d.get("pypi", {}))
else:
    d, npm_count, pypi_count = {}, 0, 0
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

giant = [f"{f.name}({f.stat().st_size})" for f in html_files if f.stat().st_size > 20000]
record(not giant, "CHECK 5", f"{len(giant)} giant pages")

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

placeholder_domain = "ecosystempulse.dev" in sc or "ecosystempulse.dev" in rc
record(not placeholder_domain and "thanksforfish.github.io/EcosystemPulse" in sc and "thanksforfish.github.io/EcosystemPulse" in rc,
       "CHECK 18", "deployment URLs target GitHub Pages")

print("\n=== RESULT ===")
if errors:
    for e in errors:
        print("  " + e)
    raise SystemExit(1)
print("ALL 18 CHECKS PASSED")
