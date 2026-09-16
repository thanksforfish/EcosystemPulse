"""EcosystemPulse V4 main runner."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "engine"))

from config import DATA_DIR, OUTPUT_DIR, TRACKED_ECOSYSTEMS
from data_collector import DataCollector
from discovery_builder import DiscoveryBuilder
from history_store import HistoryStore
from page_generator import PageGenerator
from trend_analyzer import TrendAnalyzer


CLOUDFLARE_ANALYTICS = (
    "<!-- Cloudflare Web Analytics -->"
    "<script type='module' src='https://static.cloudflareinsights.com/beacon.min.js' "
    "data-cf-beacon='{\"token\": \"12deb59ddd504e9294658e00ad85255a\"}'></script>"
    "<!-- End Cloudflare Web Analytics -->"
)


def install_analytics(output_dir: Path) -> int:
    """Inject the privacy-first Cloudflare beacon into every generated HTML page."""
    updated = 0
    for page in output_dir.rglob("*.html"):
        html = page.read_text(encoding="utf-8")
        if "static.cloudflareinsights.com/beacon.min.js" in html:
            continue
        if "</head>" not in html:
            continue
        html = html.replace("</head>", f"    {CLOUDFLARE_ANALYTICS}\n</head>", 1)
        page.write_text(html, encoding="utf-8")
        updated += 1
    return updated


def main() -> None:
    """Collect -> preserve -> analyze -> render -> build discovery -> instrument."""
    print("=" * 64)
    print("EcosystemPulse V4 — Trends, Comparisons, and Search Discovery")
    print("=" * 64)

    print("\n[1/6] Collecting current npm and PyPI registry data...")
    collector = DataCollector(DATA_DIR)
    data = collector.collect_ecosystem_data(TRACKED_ECOSYSTEMS)

    print("\n[2/6] Preserving durable observations and validating npm history...")
    history = HistoryStore(DATA_DIR)
    history_result = history.update(data, collector)

    print("\n[3/6] Calculating explainable trend metrics...")
    trends = TrendAnalyzer(DATA_DIR).analyze(data)

    print("\n[4/6] Generating core static site...")
    generator = PageGenerator(DATA_DIR, OUTPUT_DIR)
    result = generator.generate_all_pages()

    print("\n[5/6] Building movers, comparisons, internal discovery, and SEO structure...")
    discovery_result = DiscoveryBuilder(DATA_DIR, OUTPUT_DIR).build()

    print("\n[6/6] Installing Cloudflare Web Analytics...")
    analytics_pages = install_analytics(OUTPUT_DIR)

    npm_with_momentum = sum(
        1
        for item in trends.get("npm", {}).values()
        if item.get("change_7d_pct") is not None
    )

    print(f"\n{'=' * 64}")
    print("COMPLETE")
    print(f"{'=' * 64}")
    print(f"npm packages collected: {len(data.get('npm', {}))}")
    print(f"PyPI packages collected: {len(data.get('pypi', {}))}")
    print(f"npm history packages: {history_result['npm_packages']}")
    print(f"PyPI history packages: {history_result['pypi_packages']}")
    print(f"npm 30-day download series refreshed: {history_result['npm_download_series']}")
    print(f"npm packages with reliable 7-day momentum: {npm_with_momentum}")
    print(f"Individual package pages: {result['npm_pages'] + result['pypi_pages']}")
    print(f"Comparison pages: {discovery_result['comparison_pages']}")
    print(f"Movers page: {'yes' if discovery_result['movers'] else 'no'}")
    print(f"Comparison hub: {'yes' if discovery_result['comparison_hub'] else 'no'}")
    print(f"Package pages SEO-enhanced: {discovery_result['package_pages_enhanced']}")
    print(f"Sitemap discovery URLs added: {discovery_result['sitemap_urls_added']}")
    print(f"Analytics pages updated: {analytics_pages}")
    print(f"Durable history: {DATA_DIR / 'history'}")
    print(f"Output: {OUTPUT_DIR}")
    print()
    print("V4 adds:")
    print("  - a dedicated npm movers/search destination")
    print("  - evidence-first package comparison pages")
    print("  - search-intent titles and descriptions on package pages")
    print("  - site-wide internal links to Movers and Compare")
    print("  - BreadcrumbList and ItemList structured data where appropriate")
    print("  - sitemap entries for the new discovery pages")
    print("  - no meta-keyword stuffing and no fabricated package winner")


if __name__ == "__main__":
    main()
