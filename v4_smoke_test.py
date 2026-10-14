"""Focused regression checks for EcosystemPulse V4 discovery and SEO output."""

import re
from pathlib import Path

BASE = Path(__file__).resolve().parent
OUTPUT = BASE / "output"
errors = []


def record(condition, label, detail=""):
    status = "PASS" if condition else "FAIL"
    print(f"{label} {status}" + (f": {detail}" if detail else ""))
    if not condition:
        errors.append(f"{label} FAIL" + (f": {detail}" if detail else ""))


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="ignore") if path.exists() else ""


movers = OUTPUT / "movers.html"
hub = OUTPUT / "comparisons.html"
compare_dir = OUTPUT / "comparisons"
comparison_pages = sorted(compare_dir.glob("*.html")) if compare_dir.exists() else []
record(movers.exists() and hub.exists() and len(comparison_pages) >= 7,
       "V4 CHECK 1", f"movers + comparison hub + {len(comparison_pages)} comparison pages")

sitemap = read(OUTPUT / "sitemap.xml")
required_sitemap = [
    "/movers.html",
    "/comparisons.html",
    "/comparisons/react-vs-vue-vs-svelte.html",
    "/comparisons/vite-vs-webpack-vs-esbuild.html",
    "/comparisons/express-vs-fastify-vs-hono.html",
]
missing_sitemap = [item for item in required_sitemap if item not in sitemap]
record(not missing_sitemap, "V4 CHECK 2",
       "new search destinations are in sitemap" if not missing_sitemap else f"missing={missing_sitemap}")

nav_failures = []
root_pages = [OUTPUT / name for name in ("index.html", "npm.html", "pypi.html", "search.html")]
for page in root_pages:
    text = read(page)
    if 'href="movers.html"' not in text or 'href="comparisons.html"' not in text:
        nav_failures.append(page.name)
react_page = OUTPUT / "pages" / "react.html"
react_text = read(react_page)
if 'href="../movers.html"' not in react_text or 'href="../comparisons.html"' not in react_text:
    nav_failures.append("pages/react.html")
record(not nav_failures, "V4 CHECK 3",
       "Movers and Compare linked site-wide" if not nav_failures else f"missing nav={nav_failures}")

index_html = read(OUTPUT / "index.html")
record("Explore package trends and comparisons" in index_html
       and "React vs Vue vs Svelte" in index_html
       and 'href="movers.html"' in index_html,
       "V4 CHECK 4", "homepage exposes search-oriented discovery destinations")

package_title_ok = (
    "react npm Downloads, Trends, Releases &amp; Versions | EcosystemPulse" in react_text
    or "react npm Downloads, Trends, Releases & Versions | EcosystemPulse" in react_text
)
django_text = read(OUTPUT / "pages" / "django.html")
pypi_title_ok = "django PyPI Releases, Versions &amp; Package Activity | EcosystemPulse" in django_text or "django PyPI Releases, Versions & Package Activity | EcosystemPulse" in django_text
record(package_title_ok and pypi_title_ok,
       "V4 CHECK 5", "package titles target concrete npm/PyPI search intent")

structured_failures = []
for page in [movers, hub, react_page] + comparison_pages:
    text = read(page)
    if "application/ld+json" not in text or "BreadcrumbList" not in text:
        structured_failures.append(str(page.relative_to(OUTPUT)))
for page in comparison_pages:
    if "ItemList" not in read(page):
        structured_failures.append(str(page.relative_to(OUTPUT)) + " missing ItemList")
record(not structured_failures, "V4 CHECK 6",
       "BreadcrumbList + comparison ItemList structured data" if not structured_failures else str(structured_failures[:10]))

seo_failures = []
new_pages = [movers, hub] + comparison_pages
for page in new_pages:
    text = read(page)
    if "<link rel=\"canonical\" href=\"https://ecosystempulse.dev/" not in text:
        seo_failures.append(str(page.relative_to(OUTPUT)) + " canonical")
    if '<meta name="description"' not in text:
        seo_failures.append(str(page.relative_to(OUTPUT)) + " description")
    if "static.cloudflareinsights.com/beacon.min.js" not in text:
        seo_failures.append(str(page.relative_to(OUTPUT)) + " analytics")
record(not seo_failures, "V4 CHECK 7",
       "canonical + descriptions + analytics on discovery pages" if not seo_failures else str(seo_failures[:10]))

all_html = list(OUTPUT.rglob("*.html"))
keyword_meta = [str(page.relative_to(OUTPUT)) for page in all_html if re.search(r'<meta\s+name=["\']keywords["\']', read(page), re.IGNORECASE)]
record(not keyword_meta, "V4 CHECK 8", "no obsolete meta-keyword stuffing")

react_compare = read(OUTPUT / "comparisons" / "react-vs-vue-vs-svelte.html")
comparison_content_ok = all(
    phrase in react_compare
    for phrase in (
        "Trailing-week npm downloads",
        "7d vs previous 7d",
        "Days since latest release",
        "Releases in 90 days",
        "Direct dependencies",
        "Download history",
    )
)
record(comparison_content_ok, "V4 CHECK 9", "comparison pages expose evidence instead of a fabricated winner")

movers_text = read(movers)
mover_integrity = (
    "14 consecutive reliable calendar days" in movers_text
    and ("Reliable mover rankings are warming up" in movers_text or "Fastest-rising tracked npm packages" in movers_text)
)
record(mover_integrity, "V4 CHECK 10", "movers page preserves V3.1 reliability gate")

related_ok = "Related comparisons" in react_text and "react-vs-vue-vs-svelte.html" in react_text
record(related_ok, "V4 CHECK 11", "package pages internally link to relevant comparisons")

# Verify ranking semantics using deterministic fixtures, independently of today's
# registry data. Negative, steady, and stale values must never appear as rises.
import sys
sys.path.insert(0, str(BASE / "engine"))
from discovery_builder import DiscoveryBuilder
from page_generator import PageGenerator

fixture_npm = {
    name: {"weekly_downloads": 1000, "latest_version": "1.0"}
    for name in ("riser", "faller", "steady", "stale")
}
fixture_trends = {"npm": {
    "riser": {"momentum_available": True, "change_7d_pct": 12.0, "downloads_7d": 900},
    "faller": {"momentum_available": True, "change_7d_pct": -8.0, "downloads_7d": 800},
    "steady": {"momentum_available": True, "change_7d_pct": 2.0, "downloads_7d": 700},
    "stale": {"momentum_available": False, "change_7d_pct": 50.0, "downloads_7d": 600},
}}
fixture_builder = DiscoveryBuilder.__new__(DiscoveryBuilder)
fixture_builder.data = {"npm": fixture_npm}
fixture_builder.trends = fixture_trends
rising, falling, evidence_count = fixture_builder._mover_entries()
fixture_movers = fixture_builder._generate_movers_page()
falling_section = re.search(r"<h2>Fastest-falling tracked npm packages</h2>(.*?)</section>", fixture_movers, re.DOTALL)
falling_html = falling_section.group(1) if falling_section else ""
record(
    evidence_count == 3
    and [name for _, name, _ in rising] == ["riser"]
    and [name for _, name, _ in falling] == ["faller"]
    and "pages/faller.html" in falling_html
    and "pages/riser.html" not in falling_html
    and "pages/steady.html" not in falling_html
    and "pages/stale.html" not in falling_html
    and "<th scope=\"col\">Trailing week</th>" not in fixture_movers,
    "V4 CHECK 12", "Movers includes only genuine +/-5% changes, with no duplicate column",
)

fixture_pagegen = PageGenerator.__new__(PageGenerator)
fixture_pagegen.trends = fixture_trends
fixture_home = fixture_pagegen._generate_index_page(fixture_npm, {})
record(
    "pages/riser.html" in fixture_pagegen._momentum_rows(fixture_npm)
    and "pages/faller.html" not in fixture_pagegen._momentum_rows(fixture_npm)
    and "pages/stale.html" not in fixture_pagegen._momentum_rows(fixture_npm)
    and "Fastest-rising tracked npm packages" in fixture_home,
    "V4 CHECK 13", "Homepage momentum requires fresh reliable evidence and >=5% rise",
)

fixture_builder.trends = {"npm": {
    "faller": fixture_trends["npm"]["faller"],
    "steady": fixture_trends["npm"]["steady"],
}}
no_rises = fixture_builder._generate_movers_page()
fixture_pagegen.trends = fixture_builder.trends
no_rises_home = fixture_pagegen._generate_index_page(fixture_npm, {})
fixture_builder.trends = {"npm": {
    "stale": fixture_trends["npm"]["stale"],
}}
no_evidence = fixture_builder._generate_movers_page()
fixture_pagegen.trends = fixture_builder.trends
no_evidence_home = fixture_pagegen._generate_index_page(fixture_npm, {})
record(
    "No tracked npm package currently exceeds the +5% rising threshold" in no_rises
    and "pages/faller.html" in no_rises
    and "No qualifying npm download rises" in no_rises_home
    and "warming up" in no_evidence.lower()
    and "warming up" in no_evidence_home.lower(),
    "V4 CHECK 14", "No qualifying rises do not masquerade as missing data",
)

print("\n=== V4 RESULT ===")
if errors:
    for error in errors:
        print("  " + error)
    raise SystemExit(1)
print("ALL 14 V4 CHECKS PASSED")
