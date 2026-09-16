"""EcosystemPulse V3 main runner."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "engine"))

from config import DATA_DIR, OUTPUT_DIR, TRACKED_ECOSYSTEMS
from data_collector import DataCollector
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
    """Collect -> preserve history -> calculate trends -> render -> instrument."""
    print("=" * 64)
    print("EcosystemPulse V3 — Durable Developer Ecosystem Trends")
    print("=" * 64)

    print("\n[1/5] Collecting current npm and PyPI registry data...")
    collector = DataCollector(DATA_DIR)
    data = collector.collect_ecosystem_data(TRACKED_ECOSYSTEMS)

    print("\n[2/5] Preserving durable observations and backfilling npm history...")
    history = HistoryStore(DATA_DIR)
    history_result = history.update(data, collector)

    print("\n[3/5] Calculating explainable trend metrics...")
    trends = TrendAnalyzer(DATA_DIR).analyze(data)

    print("\n[4/5] Generating static site...")
    generator = PageGenerator(DATA_DIR, OUTPUT_DIR)
    result = generator.generate_all_pages()

    print("\n[5/5] Installing Cloudflare Web Analytics...")
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
    print(f"npm packages with 7-day momentum: {npm_with_momentum}")
    print(f"Individual package pages: {result['npm_pages'] + result['pypi_pages']}")
    print(f"Listing pages: {result['listing_pages']}")
    print(f"Index page: {'yes' if result['index'] else 'no'}")
    print(f"Analytics pages updated: {analytics_pages}")
    print(f"Durable history: {DATA_DIR / 'history'}")
    print(f"Output: {OUTPUT_DIR}")
    print()
    print("V3 adds:")
    print("  - Git-tracked durable package observations")
    print("  - 30-day npm daily-download backfill")
    print("  - 7-day vs prior-7-day momentum")
    print("  - release recency and cadence measurements")
    print("  - inline trend sparklines with no client chart dependency")
    print("  - evidence-first metrics instead of a subjective health score")


if __name__ == "__main__":
    main()
