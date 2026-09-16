"""EcosystemPulse V3 page generator with explainable trend data."""

from __future__ import annotations

import json
import shutil
from datetime import datetime, timezone
from html import escape
from pathlib import Path
from typing import Dict, Iterable
from urllib.parse import urlsplit

from config import SITE_CONFIG


class PageGenerator:
    """Generate static pages from current registry data and durable trends."""

    def __init__(self, data_dir: Path, output_dir: Path):
        self.data_dir = data_dir
        self.output_dir = output_dir
        self.pages_dir = output_dir / "pages"
        self.pages_dir.mkdir(parents=True, exist_ok=True)
        self.trends = self._load_json(data_dir / "trends.json", {"npm": {}, "pypi": {}})

    @staticmethod
    def _load_json(path: Path, default: Dict) -> Dict:
        if not path.exists():
            return default
        try:
            with path.open(encoding="utf-8") as f:
                data = json.load(f)
            return data if isinstance(data, dict) else default
        except (OSError, json.JSONDecodeError):
            return default

    def load_data(self) -> Dict:
        return self._load_json(self.data_dir / "collected_data.json", {"npm": {}, "pypi": {}})

    @staticmethod
    def _fmt_number(value) -> str:
        if value is None:
            return "N/A"
        try:
            number = float(value)
        except (TypeError, ValueError):
            return "N/A"
        absolute = abs(number)
        if absolute >= 1_000_000_000:
            return f"{number / 1_000_000_000:.2f}B"
        if absolute >= 1_000_000:
            return f"{number / 1_000_000:.2f}M"
        if absolute >= 1_000:
            return f"{number / 1_000:.1f}K"
        return f"{int(number):,}"

    @staticmethod
    def _safe_url(value: object) -> str:
        if not isinstance(value, str) or not value:
            return ""
        try:
            parts = urlsplit(value)
        except ValueError:
            return ""
        return value if parts.scheme in {"http", "https"} else ""

    @staticmethod
    def _sparkline_svg(points: Iterable[Dict]) -> str:
        values = [int(item.get("downloads", 0)) for item in points if isinstance(item, dict)]
        if len(values) < 2:
            return ""
        width, height, pad = 640, 130, 10
        low, high = min(values), max(values)
        span = max(1, high - low)
        usable_w = width - pad * 2
        usable_h = height - pad * 2
        coords = []
        for idx, value in enumerate(values):
            x = pad + (usable_w * idx / max(1, len(values) - 1))
            y = pad + usable_h - ((value - low) / span * usable_h)
            coords.append(f"{x:.1f},{y:.1f}")
        return (
            f'<svg class="sparkline" viewBox="0 0 {width} {height}" role="img" '
            'aria-label="Daily npm downloads over the last 30 days">'
            f'<polyline points="{" ".join(coords)}" fill="none" '
            'stroke="currentColor" stroke-width="3" vector-effect="non-scaling-stroke" />'
            "</svg>"
        )

    @staticmethod
    def _change_html(change) -> str:
        if change is None:
            return '<span class="trend-neutral">N/A</span>'
        css = "trend-up" if change > 0 else "trend-down" if change < 0 else "trend-neutral"
        sign = "+" if change > 0 else ""
        return f'<span class="{css}">{sign}{change:.1f}%</span>'

    def _trend_panel(self, pkg: Dict, registry: str) -> str:
        name = pkg.get("name", "")
        trend = self.trends.get(registry, {}).get(name, {})
        if not trend:
            return ""

        release_cards = ""
        days_since = trend.get("days_since_release")
        releases_90 = trend.get("releases_90d")
        median_interval = trend.get("median_release_interval_days")
        if days_since is not None or releases_90 is not None:
            release_cards = f"""
            <div class="trend-grid release-grid">
                <div class="trend-card"><strong>{days_since if days_since is not None else 'N/A'}</strong><span>days since latest release</span></div>
                <div class="trend-card"><strong>{releases_90 if releases_90 is not None else 'N/A'}</strong><span>releases in 90 days</span></div>
                <div class="trend-card"><strong>{median_interval if median_interval is not None else 'N/A'}</strong><span>median days between recent releases</span></div>
            </div>"""

        if registry != "npm":
            return f"""
            <section class="trend-section">
                <div class="section-heading">
                    <h2>Release activity</h2>
                    <span class="evidence-badge">registry timestamps</span>
                </div>
                {release_cards}
                <p class="method-note">These are direct release-timestamp measurements. EcosystemPulse does not assign a subjective package health score.</p>
            </section>"""

        points = trend.get("download_points", [])
        history_days = trend.get("download_history_days", 0)
        sparkline = self._sparkline_svg(points)
        change = trend.get("change_7d_pct")
        momentum = escape(str(trend.get("momentum", "insufficient data")))

        if history_days < 14:
            download_block = f"""
                <p class="method-note">Historical npm download coverage is still accumulating ({history_days} complete day(s) available). A 7-day comparison appears after 14 complete days are available.</p>
                {sparkline}
            """
        else:
            download_block = f"""
                <div class="trend-grid">
                    <div class="trend-card"><strong>{self._change_html(change)}</strong><span>7d vs previous 7d</span></div>
                    <div class="trend-card"><strong>{self._fmt_number(trend.get('downloads_7d'))}</strong><span>downloads, last 7 days</span></div>
                    <div class="trend-card"><strong>{self._fmt_number(trend.get('downloads_30d'))}</strong><span>downloads, last 30 days</span></div>
                    <div class="trend-card"><strong>{momentum}</strong><span>momentum label</span></div>
                </div>
                {sparkline}
                <p class="method-note">Momentum compares the latest 7 complete npm download days with the preceding 7. “Rising” and “falling” require at least a 5% change.</p>
            """

        return f"""
        <section class="trend-section">
            <div class="section-heading">
                <h2>Download momentum</h2>
                <span class="evidence-badge">npm daily downloads</span>
            </div>
            {download_block}
            <div class="section-heading release-heading"><h2>Release activity</h2></div>
            {release_cards}
        </section>"""

    def _generate_package_page(self, pkg: Dict, registry: str) -> str:
        name_raw = str(pkg.get("name", ""))
        name = escape(name_raw)
        version = escape(str(pkg.get("latest_version", "N/A")))
        description_raw = str(pkg.get("description", "") or "")
        description = escape(description_raw)
        downloads = pkg.get("weekly_downloads")
        versions = pkg.get("all_versions", []) or []
        created = str(pkg.get("created", "") or "")
        modified = str(pkg.get("modified", "") or "")
        license_info = escape(str(pkg.get("license", "") or ""))
        homepage_raw = pkg.get("homepage", "") or pkg.get("home_page", "")
        homepage = self._safe_url(homepage_raw)
        dependencies = pkg.get("dependencies", []) or pkg.get("requires_dist", []) or []
        version_dates = pkg.get("version_dates", {}) or {}

        downloads_html = (
            f"<p><strong>Trailing-week npm downloads:</strong> {int(downloads):,}</p>"
            if downloads is not None
            else ""
        )

        versions_html = ""
        if versions:
            recent = versions[-10:]
            rows = []
            for item in reversed(recent):
                date_value = version_dates.get(item, "N/A")
                date_text = date_value[:10] if isinstance(date_value, str) else "N/A"
                rows.append(f"<tr><td>{escape(str(item))}</td><td>{escape(date_text)}</td></tr>")
            versions_html = f"""
            <section class="info-section">
                <h2>Version History (Last {len(recent)})</h2>
                <table class="data-table"><thead><tr><th>Version</th><th>Released</th></tr></thead><tbody>{''.join(rows)}</tbody></table>
            </section>"""

        deps_html = ""
        clean_dependencies = []
        for dep in dependencies[:20]:
            dep_name = str(dep).split(">=")[0].split("<")[0].split("[")[0].strip()
            if dep_name:
                clean_dependencies.append(escape(dep_name))
        if clean_dependencies:
            deps_html = f"""
            <section class="info-section"><h2>Dependencies ({len(dependencies)})</h2>
            <div class="tag-list">{''.join(f'<span class="tag">{d}</span>' for d in clean_dependencies)}</div></section>"""

        keywords = pkg.get("keywords", []) or []
        if isinstance(keywords, str):
            keywords = [k.strip() for k in keywords.split(",") if k.strip()]
        clean_keywords = [escape(str(k)) for k in keywords if k]
        keywords_html = ""
        if clean_keywords:
            keywords_html = f"""
            <section class="info-section"><h2>Keywords</h2>
            <div class="tag-list">{''.join(f'<span class="tag">{k}</span>' for k in clean_keywords)}</div></section>"""

        homepage_row = ""
        homepage_link = ""
        if homepage:
            safe_home = escape(homepage, quote=True)
            home_label = escape(homepage[:60])
            homepage_row = f'<tr><td>Homepage</td><td><a href="{safe_home}" target="_blank" rel="noopener noreferrer">{home_label}</a></td></tr>'
            homepage_link = f'<li><a href="{safe_home}" target="_blank" rel="noopener noreferrer">Homepage</a></li>'

        trend_html = self._trend_panel(pkg, registry)
        registry_link = (
            f'<li><a href="https://www.npmjs.com/package/{escape(name_raw, quote=True)}" target="_blank" rel="noopener noreferrer">npm page</a></li>'
            if registry == "npm"
            else f'<li><a href="https://pypi.org/project/{escape(name_raw, quote=True)}/" target="_blank" rel="noopener noreferrer">PyPI page</a></li>'
        )

        return f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{name} — EcosystemPulse</title>
    <meta name="description" content="Package information and measured trends for {name}: {escape(description_raw[:140], quote=True)}">
    <link rel="canonical" href="{SITE_CONFIG['url']}/pages/{escape(name_raw, quote=True)}.html">
    <link rel="stylesheet" href="../css/style.css">
</head>
<body>
    <header class="site-header"><nav class="main-nav"><a href="../index.html" class="logo">EcosystemPulse</a><ul class="nav-links"><li><a href="../npm.html">npm</a></li><li><a href="../pypi.html">PyPI</a></li></ul></nav></header>
    <main class="container">
        <article class="package-detail">
            <header class="package-header">
                <h1>{name}</h1><p class="description">{description}</p>
                <div class="meta"><span class="badge registry">{registry}</span><span class="badge version">v{version}</span>{f'<span class="badge license">{license_info}</span>' if license_info else ''}</div>
            </header>
            {downloads_html}
            {trend_html}
            <section class="info-section"><h2>Quick Info</h2><table class="info-table">
                <tr><td>Registry</td><td>{registry}</td></tr><tr><td>Latest Version</td><td>{version}</td></tr><tr><td>Total Versions</td><td>{len(versions)}</td></tr>
                {f'<tr><td>Created</td><td>{escape(created[:10])}</td></tr>' if created else ''}
                {f'<tr><td>Last Modified</td><td>{escape(modified[:10])}</td></tr>' if modified else ''}
                {f'<tr><td>License</td><td>{license_info}</td></tr>' if license_info else ''}
                {homepage_row}
            </table></section>
            {versions_html}{deps_html}{keywords_html}
            <section class="links"><h2>Links</h2><ul>{registry_link}{homepage_link}</ul></section>
        </article>
    </main>
    <footer class="site-footer"><div class="footer-content"><p>&copy; {datetime.now().year} EcosystemPulse. Measured developer ecosystem data.</p></div></footer>
</body>
</html>"""

    def _generate_listing_page(self, packages: Dict[str, Dict], title: str, registry: str) -> str:
        rows = []
        sorted_packages = sorted(
            packages.items(),
            key=lambda item: item[1].get("weekly_downloads", 0) or 0,
            reverse=True,
        )
        for name, pkg in sorted_packages:
            downloads = pkg.get("weekly_downloads")
            downloads_str = f"{int(downloads):,}" if downloads is not None else "N/A"
            trend = self.trends.get(registry, {}).get(name, {})
            change = trend.get("change_7d_pct") if registry == "npm" else None
            change_cell = self._change_html(change) if registry == "npm" else "N/A"
            rows.append(
                f"<tr><td><a href=\"pages/{escape(name, quote=True)}.html\">{escape(name)}</a></td>"
                f"<td>{escape(str(pkg.get('latest_version', 'N/A')))}</td>"
                f"<td>{downloads_str}</td><td>{change_cell}</td>"
                f"<td>{escape(str(pkg.get('description', '') or '')[:80])}</td></tr>"
            )

        change_header = "<th>7d Change</th>" if registry == "npm" else "<th>Trend</th>"
        return f"""<!DOCTYPE html>
<html lang="en"><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{escape(title)} — EcosystemPulse</title><meta name="description" content="{escape(title, quote=True)} with registry data and measured activity trends">
<link rel="canonical" href="{SITE_CONFIG['url']}/{registry}.html"><link rel="stylesheet" href="css/style.css"></head>
<body><header class="site-header"><nav class="main-nav"><a href="index.html" class="logo">EcosystemPulse</a><ul class="nav-links"><li><a href="npm.html">npm</a></li><li><a href="pypi.html">PyPI</a></li></ul></nav></header>
<main class="container"><article class="listing"><header class="article-header"><h1>{escape(title)}</h1><p>Measured data from the {registry} registry. Updated {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}.</p></header>
<div class="table-wrapper"><table class="data-table"><thead><tr><th>Package</th><th>Version</th><th>Weekly Downloads</th>{change_header}<th>Description</th></tr></thead><tbody>{''.join(rows)}</tbody></table></div></article></main>
<footer class="site-footer"><div class="footer-content"><p>&copy; {datetime.now().year} EcosystemPulse. Measured developer ecosystem data.</p></div></footer></body></html>"""

    def _momentum_rows(self, npm_packages: Dict) -> str:
        movers = []
        for name in npm_packages:
            trend = self.trends.get("npm", {}).get(name, {})
            change = trend.get("change_7d_pct")
            if isinstance(change, (int, float)):
                movers.append((change, name, trend))
        movers.sort(reverse=True)
        rows = []
        for change, name, trend in movers[:5]:
            rows.append(
                f'<tr><td><a href="pages/{escape(name, quote=True)}.html">{escape(name)}</a></td>'
                f'<td>{self._change_html(change)}</td><td>{self._fmt_number(trend.get("downloads_7d"))}</td></tr>'
            )
        return "".join(rows)

    def _generate_index_page(self, npm_packages: Dict, pypi_packages: Dict) -> str:
        npm_count, pypi_count = len(npm_packages), len(pypi_packages)
        top_npm = sorted(
            [(name, pkg) for name, pkg in npm_packages.items() if pkg.get("weekly_downloads") is not None],
            key=lambda item: item[1]["weekly_downloads"],
            reverse=True,
        )[:5]
        top_rows = "".join(
            f'<tr><td><a href="pages/{escape(name, quote=True)}.html">{escape(name)}</a></td><td>{escape(str(pkg.get("latest_version", "N/A")))}</td><td>{int(pkg.get("weekly_downloads", 0)):,}</td></tr>'
            for name, pkg in top_npm
        )
        momentum_rows = self._momentum_rows(npm_packages)
        momentum_section = (
            f"""<section class="top-packages"><h2>Fastest-rising tracked npm packages</h2><p class="section-copy">Latest 7 complete download days compared with the previous 7.</p><div class="table-wrapper"><table class="data-table"><thead><tr><th>Package</th><th>7d Change</th><th>Downloads, 7d</th></tr></thead><tbody>{momentum_rows}</tbody></table></div></section>"""
            if momentum_rows
            else """<section class="top-packages"><h2>Download momentum is warming up</h2><p class="section-copy">EcosystemPulse is collecting enough complete npm download days to calculate reliable 7-day comparisons.</p></section>"""
        )

        return f"""<!DOCTYPE html>
<html lang="en"><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>EcosystemPulse — Developer Package Trends</title><meta name="description" content="Measured npm download momentum, package release activity, versions, and dependency data across npm and PyPI.">
<link rel="canonical" href="{SITE_CONFIG['url']}/"><link rel="stylesheet" href="css/style.css"><style>.search-hero{{max-width:500px;margin:0 auto 2rem}}.search-hero input{{width:100%;padding:.75rem 1rem;font-size:1rem;border:2px solid #333;border-radius:6px;background:#0a0a0a;color:#e0e0e0;font-family:'SF Mono','Fira Code',monospace}}.search-hero input:focus{{outline:none;border-color:#00ff88}}</style></head>
<body><header class="site-header"><nav class="main-nav"><a href="index.html" class="logo">EcosystemPulse</a><ul class="nav-links"><li><a href="npm.html">npm</a></li><li><a href="pypi.html">PyPI</a></li></ul></nav></header>
<main class="container"><section class="hero"><h1>Developer Ecosystem Data</h1><p>Measured package activity, downloads, releases, versions, and dependencies.</p><div class="search-hero"><form action="search.html" method="get"><input type="text" name="q" placeholder="Search for a package..." autocomplete="off"></form></div></section>
<section class="stats-grid"><div class="stat-card"><h3>{npm_count}</h3><p>npm Packages</p></div><div class="stat-card"><h3>{pypi_count}</h3><p>PyPI Packages</p></div><div class="stat-card"><h3>{npm_count + pypi_count}</h3><p>Total Tracked</p></div></section>
{momentum_section}
<section class="top-packages"><h2>Top tracked npm packages by downloads</h2><div class="table-wrapper"><table class="data-table"><thead><tr><th>Package</th><th>Version</th><th>Trailing-week Downloads</th></tr></thead><tbody>{top_rows}</tbody></table></div><p><a href="npm.html">View all npm packages →</a></p></section>
<section class="about-preview"><h2>What is EcosystemPulse?</h2><p>EcosystemPulse preserves public registry observations over time so changes can be measured instead of guessed.</p><ul><li>30-day npm download history and 7-day momentum</li><li>Release recency and recent release cadence</li><li>Current versions, dependencies, and registry metadata</li><li>No subjective “health score” hiding the underlying evidence</li></ul></section></main>
<footer class="site-footer"><div class="footer-content"><p>&copy; {datetime.now().year} EcosystemPulse. Measured developer ecosystem data.</p></div></footer></body></html>"""

    def generate_all_pages(self) -> Dict:
        data = self.load_data()
        npm_packages = data.get("npm", {})
        pypi_packages = data.get("pypi", {})
        generated = {"npm_pages": 0, "pypi_pages": 0, "listing_pages": 0, "index": False}

        for name, pkg in npm_packages.items():
            (self.pages_dir / f"{name}.html").write_text(self._generate_package_page(pkg, "npm"), encoding="utf-8")
            generated["npm_pages"] += 1
        for name, pkg in pypi_packages.items():
            (self.pages_dir / f"{name}.html").write_text(self._generate_package_page(pkg, "pypi"), encoding="utf-8")
            generated["pypi_pages"] += 1

        if npm_packages:
            (self.output_dir / "npm.html").write_text(self._generate_listing_page(npm_packages, "All Tracked npm Packages", "npm"), encoding="utf-8")
            generated["listing_pages"] += 1
        if pypi_packages:
            (self.output_dir / "pypi.html").write_text(self._generate_listing_page(pypi_packages, "All Tracked PyPI Packages", "pypi"), encoding="utf-8")
            generated["listing_pages"] += 1

        (self.output_dir / "index.html").write_text(self._generate_index_page(npm_packages, pypi_packages), encoding="utf-8")
        generated["index"] = True
        self._generate_sitemap(npm_packages, pypi_packages)
        self._generate_robots_txt()
        self._copy_static_assets()
        return generated

    def _generate_robots_txt(self) -> None:
        base_url = SITE_CONFIG["url"]
        (self.output_dir / "robots.txt").write_text(
            f"User-agent: *\nAllow: /\nSitemap: {base_url}/sitemap.xml\n",
            encoding="utf-8",
        )

    def _copy_static_assets(self) -> None:
        static_dir = Path(__file__).parent / "static"
        if not static_dir.exists():
            return
        for item in static_dir.rglob("*"):
            if item.is_file():
                rel = item.relative_to(static_dir)
                dest = self.output_dir / rel
                dest.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(item, dest)

    def _generate_sitemap(self, npm_packages: Dict, pypi_packages: Dict) -> None:
        base_url = SITE_CONFIG["url"]
        urls = [
            f"  <url><loc>{base_url}/</loc><changefreq>daily</changefreq><priority>1.0</priority></url>",
            f"  <url><loc>{base_url}/npm.html</loc><changefreq>daily</changefreq><priority>0.9</priority></url>",
            f"  <url><loc>{base_url}/pypi.html</loc><changefreq>daily</changefreq><priority>0.8</priority></url>",
        ]
        for name in npm_packages:
            urls.append(f"  <url><loc>{base_url}/pages/{escape(name)}.html</loc><changefreq>daily</changefreq><priority>0.8</priority></url>")
        for name in pypi_packages:
            urls.append(f"  <url><loc>{base_url}/pages/{escape(name)}.html</loc><changefreq>daily</changefreq><priority>0.8</priority></url>")
        sitemap = "<?xml version=\"1.0\" encoding=\"UTF-8\"?>\n<urlset xmlns=\"http://www.sitemaps.org/schemas/sitemap/0.9\">\n" + "\n".join(urls) + "\n</urlset>"
        (self.output_dir / "sitemap.xml").write_text(sitemap, encoding="utf-8")
