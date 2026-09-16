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


def main():
    """Run the full V2 pipeline: collect data → generate pages."""
    print("=" * 60)
    print("EcosystemPulse V2 — Developer Ecosystem Intelligence")
    print("=" * 60)

    # Step 1: Collect real data from public APIs
    print("\n[1/2] Collecting data from npm and PyPI APIs...")
    collector = DataCollector(DATA_DIR)
    data = collector.collect_ecosystem_data(TRACKED_ECOSYSTEMS)

    # Step 2: Generate pages from real data
    print("\n[2/2] Generating pages from collected data...")
    generator = PageGenerator(DATA_DIR, OUTPUT_DIR)
    result = generator.generate_all_pages()

    # Summary
    print(f"\n{'='*60}")
    print("COMPLETE")
    print(f"{'='*60}")
    print(f"npm packages collected: {len(data['npm'])}")
    print(f"pypi packages collected: {len(data['pypi'])}")
    print(f"Individual package pages: {result['npm_pages'] + result['pypi_pages']}")
    print(f"Listing pages: {result['listing_pages']}")
    print(f"Index page: {'yes' if result['index'] else 'no'}")
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
