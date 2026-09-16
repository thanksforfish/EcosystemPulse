"""
EcosystemPulse V2 — Main Runner
Collects real data and generates useful pages
"""
import sys
from pathlib import Path

# Add engine dir to path
sys.path.insert(0, str(Path(__file__).parent / "engine"))

from config import TRACKED_ECOSYSTEMS, DATA_DIR, OUTPUT_DIR
from data_collector import DataCollector
from page_generator import PageGenerator  # noqa: E402


CLOUDFLARE_ANALYTICS = (
    "<!-- Cloudflare Web Analytics -->"
    "<script type='module' src='https://static.cloudflareinsights.com/beacon.min.js' "
    "data-cf-beacon='{\"token\": \"12deb59ddd504e9294658e00ad85255a\"}'></script>"
    "<!-- End Cloudflare Web Analytics -->"
)


def install_analytics(output_dir: Path) -> int:
    """Inject the Cloudflare Web Analytics beacon into every generated HTML page."""
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


def main():
    """Run the full V2 pipeline: collect data → generate pages → add analytics."""
    print("=" * 60)
    print("EcosystemPulse V2 — Developer Ecosystem Intelligence")
    print("=" * 60)

    # Step 1: Collect real data from public APIs
    print("\n[1/3] Collecting data from npm and PyPI APIs...")
    collector = DataCollector(DATA_DIR)
    data = collector.collect_ecosystem_data(TRACKED_ECOSYSTEMS)

    # Step 2: Generate pages from real data
    print("\n[2/3] Generating pages from collected data...")
    generator = PageGenerator(DATA_DIR, OUTPUT_DIR)
    result = generator.generate_all_pages()

    # Step 3: Add privacy-first analytics to every HTML page
    print("\n[3/3] Installing Cloudflare Web Analytics...")
    analytics_pages = install_analytics(OUTPUT_DIR)

    # Summary
    print(f"\n{'='*60}")
    print("COMPLETE")
    print(f"{'='*60}")
    print(f"npm packages collected: {len(data['npm'])}")
    print(f"pypi packages collected: {len(data['pypi'])}")
    print(f"Individual package pages: {result['npm_pages'] + result['pypi_pages']}")
    print(f"Listing pages: {result['listing_pages']}")
    print(f"Index page: {'yes' if result['index'] else 'no'}")
    print(f"Analytics pages updated: {analytics_pages}")
    print(f"Output: {OUTPUT_DIR}")
    print()
    print("What's different from V1:")
    print("  - REAL data from public APIs (npm registry, PyPI)")
    print("  - REAL download statistics")
    print("  - REAL version histories")
    print("  - REAL dependency lists")
    print("  - No fabricated ratings or reviews")
    print("  - No affiliate links")
    print("  - No SEO spam")


if __name__ == "__main__":
    main()
