"""EcosystemPulse V4.1 main runner."""

from __future__ import annotations

import math
import sys
from datetime import datetime, timezone
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
MIN_COLLECTION_COVERAGE = 0.90
MAX_COLLECTION_AGE_HOURS = 6


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


def validate_collection(data: dict) -> dict:
    """Refuse to publish a stale or badly incomplete collection."""
    coverage = {}
    for registry in ("npm", "pypi"):
        configured = TRACKED_ECOSYSTEMS.get(registry, {}).get("packages", [])
        expected = len(configured)
        actual = len(data.get(registry, {}))
        minimum = math.ceil(expected * MIN_COLLECTION_COVERAGE)
        coverage[registry] = {"expected": expected, "actual": actual, "minimum": minimum}
        if actual < minimum:
            raise RuntimeError(
                f"Refusing publication: {registry} collection coverage {actual}/{expected} "
                f"is below the {MIN_COLLECTION_COVERAGE:.0%} floor ({minimum})."
            )

    collected_at = data.get("collected_at")
    try:
        parsed = datetime.fromisoformat(str(collected_at).replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        age_hours = (datetime.now(timezone.utc) - parsed.astimezone(timezone.utc)).total_seconds() / 3600
    except (TypeError, ValueError) as exc:
        raise RuntimeError("Refusing publication: collected_at is missing or invalid") from exc
    if age_hours < -0.25 or age_hours > MAX_COLLECTION_AGE_HOURS:
        raise RuntimeError(
            f"Refusing publication: collection age is {age_hours:.1f}h; "
            f"allowed range is current through {MAX_COLLECTION_AGE_HOURS}h old."
        )
    coverage["age_hours"] = round(age_hours, 3)
    return coverage


def main() -> None:
    """Collect -> validate -> preserve -> analyze -> render -> discover -> instrument."""
    print("=" * 68)
    print("EcosystemPulse V4.1 — Trust, Recovery, and Future Data")
    print("=" * 68)

    print("\n[1/7] Collecting current npm and PyPI registry data...")
    collector = DataCollector(DATA_DIR)
    data = collector.collect_ecosystem_data(TRACKED_ECOSYSTEMS)

    print("\n[2/7] Verifying collection freshness and configured coverage...")
    coverage = validate_collection(data)

    print("\n[3/7] Preserving durable observations and validating history...")
    history = HistoryStore(DATA_DIR)
    history_result = history.update(data, collector)

    print("\n[4/7] Calculating explainable, freshness-gated trend metrics...")
    trends = TrendAnalyzer(DATA_DIR).analyze(data)

    print("\n[5/7] Generating core static site...")
    generator = PageGenerator(DATA_DIR, OUTPUT_DIR)
    result = generator.generate_all_pages()

    print("\n[6/7] Building movers, comparisons, internal discovery, and SEO structure...")
    discovery_result = DiscoveryBuilder(DATA_DIR, OUTPUT_DIR).build()

    print("\n[7/7] Installing Cloudflare Web Analytics...")
    analytics_pages = install_analytics(OUTPUT_DIR)

    npm_with_momentum = sum(
        1
        for item in trends.get("npm", {}).values()
        if item.get("change_7d_pct") is not None
    )

    print(f"\n{'=' * 68}")
    print("COMPLETE")
    print(f"{'=' * 68}")
    print(f"npm packages collected: {len(data.get('npm', {}))}/{coverage['npm']['expected']}")
    print(f"PyPI packages collected: {len(data.get('pypi', {}))}/{coverage['pypi']['expected']}")
    print(f"Collection age: {coverage['age_hours']:.3f}h")
    print(f"npm history packages: {history_result['npm_packages']}")
    print(f"PyPI history packages: {history_result['pypi_packages']}")
    print(f"npm 30-day download series refreshed: {history_result['npm_download_series']}")
    print(f"npm per-version windows archived: {history_result['npm_version_download_snapshots']}")
    print(f"npm package-state changes archived: {history_result['npm_state_changes']}")
    print(f"PyPI package-state changes archived: {history_result['pypi_state_changes']}")
    print(f"npm packages with fresh reliable 7-day momentum: {npm_with_momentum}")
    print(f"Individual package pages: {result['npm_pages'] + result['pypi_pages']}")
    print(f"Comparison pages: {discovery_result['comparison_pages']}")
    print(f"Movers page: {'yes' if discovery_result['movers'] else 'no'}")
    print(f"Comparison hub: {'yes' if discovery_result['comparison_hub'] else 'no'}")
    print(f"Package pages SEO-enhanced: {discovery_result['package_pages_enhanced']}")
    print(f"Sitemap discovery URLs added: {discovery_result['sitemap_urls_added']}")
    print(f"Analytics pages updated: {analytics_pages}")
    print(f"Durable history: {DATA_DIR / 'history'}")
    print(f"Recovery copies: {history_result['history_backups']}")
    print(f"Output: {OUTPUT_DIR}")
    print()
    print("V4.1 trust changes:")
    print("  - full release timestamp coverage for release metrics")
    print("  - fresh-data requirement for momentum rankings")
    print("  - gap-safe chart inputs")
    print("  - fail-safe history recovery copies")
    print("  - change-only dependency/mutable metadata history")
    print("  - bounded npm per-version download archive")
    print("  - publication freshness and cohort-coverage gate")
    print("  - tracked-package search routes back to EcosystemPulse")


if __name__ == "__main__":
    main()
