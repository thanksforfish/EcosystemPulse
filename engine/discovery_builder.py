"""EcosystemPulse V4 discovery pages and search-facing site structure.

This layer deliberately builds on the evidence-first V3/V3.1 data model. It
creates useful search destinations without inventing scores or treating missing
momentum data as a ranking signal.
"""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from html import escape
from pathlib import Path
from typing import Dict, Iterable, List, Sequence, Tuple

from config import SITE_CONFIG


Comparison = Tuple[str, str, Sequence[str], str]


COMPARISONS: List[Comparison] = [
    (
        "react-vs-vue-vs-svelte",
        "React vs Vue vs Svelte",
        ("react", "vue", "svelte"),
        "Compare npm downloads, release activity, current versions, and measured download trends for React, Vue, and Svelte.",
    ),
    (
        "vite-vs-webpack-vs-esbuild",
        "Vite vs Webpack vs esbuild",
        ("vite", "webpack", "esbuild"),
        "Compare npm downloads, release cadence, versions, and measured trends for Vite, Webpack, and esbuild.",
    ),
    (
        "express-vs-fastify-vs-hono",
        "Express vs Fastify vs Hono",
        ("express", "fastify", "hono"),
        "Compare npm downloads, release activity, versions, and measured trends for Express, Fastify, and Hono.",
    ),
    (
        "zod-vs-joi-vs-yup",
        "Zod vs Joi vs Yup",
        ("zod", "joi", "yup"),
        "Compare npm downloads, release activity, versions, and measured trends for Zod, Joi, and Yup.",
    ),
    (
        "jest-vs-vitest-vs-mocha",
        "Jest vs Vitest vs Mocha",
        ("jest", "vitest", "mocha"),
        "Compare npm downloads, release activity, versions, and measured trends for Jest, Vitest, and Mocha.",
    ),
    (
        "date-fns-vs-dayjs",
        "date-fns vs Day.js",
        ("date-fns", "dayjs"),
        "Compare npm downloads, release activity, versions, and measured trends for date-fns and Day.js.",
    ),
    (
        "next-vs-nuxt",
        "Next.js vs Nuxt",
        ("next", "nuxt"),
        "Compare npm downloads, release activity, versions, and measured trends for Next.js and Nuxt.",
    ),
]


class DiscoveryBuilder:
    """Generate V4 discovery/SEO pages and connect them to the existing site."""

    def __init__(self, data_dir: Path, output_dir: Path):
        self.data_dir = data_dir
        self.output_dir = output_dir
        self.pages_dir = output_dir / "pages"
        self.compare_dir = output_dir / "comparisons"
        self.compare_dir.mkdir(parents=True, exist_ok=True)
        self.data = self._load_json(data_dir / "collected_data.json", {"npm": {}, "pypi": {}})
        self.trends = self._load_json(data_dir / "trends.json", {"npm": {}, "pypi": {}})

    @staticmethod
    def _load_json(path: Path, default: Dict) -> Dict:
        if not path.exists():
            return default
        try:
            with path.open(encoding="utf-8") as f:
                value = json.load(f)
            return value if isinstance(value, dict) else default
        except (OSError, json.JSONDecodeError):
            return default

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
    def _change_html(change) -> str:
        if not isinstance(change, (int, float)):
            return '<span class="trend-neutral">Not yet available</span>'
        css = "trend-up" if change > 0 else "trend-down" if change < 0 else "trend-neutral"
        sign = "+" if change > 0 else ""
        return f'<span class="{css}">{sign}{change:.1f}%</span>'

    @staticmethod
    def _sparkline_svg(points: Iterable[Dict], label: str) -> str:
        values = []
        for point in points:
            if not isinstance(point, dict):
                continue
            value = point.get("downloads")
            if isinstance(value, (int, float)):
                values.append(int(value))
        if len(values) < 2:
            return ""
        width, height, pad = 360, 90, 8
        low, high = min(values), max(values)
        span = max(1, high - low)
        usable_w = width - pad * 2
        usable_h = height - pad * 2
        coords = []
        for idx, value in enumerate(values):
            x = pad + usable_w * idx / max(1, len(values) - 1)
            y = pad + usable_h - ((value - low) / span * usable_h)
            coords.append(f"{x:.1f},{y:.1f}")
        return (
            f'<svg class="mini-sparkline" viewBox="0 0 {width} {height}" role="img" '
            f'aria-label="{escape(label, quote=True)}">'
            f'<polyline points="{" ".join(coords)}" fill="none" stroke="currentColor" '
            'stroke-width="3" vector-effect="non-scaling-stroke" /></svg>'
        )

    @staticmethod
    def _json_ld(payload: Dict) -> str:
        raw = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")
        return f'<script type="application/ld+json">{raw}</script>'

    @staticmethod
    def _nav(prefix: str = "") -> str:
        return (
            '<ul class="nav-links">'
            f'<li><a href="{prefix}npm.html">npm</a></li>'
            f'<li><a href="{prefix}pypi.html">PyPI</a></li>'
            f'<li><a href="{prefix}movers.html">Movers</a></li>'
            f'<li><a href="{prefix}comparisons.html">Compare</a></li>'
            '</ul>'
        )

    def _head(self, title: str, description: str, canonical_path: str, css_prefix: str = "") -> str:
        canonical = f"{SITE_CONFIG['url']}/{canonical_path.lstrip('/')}" if canonical_path else f"{SITE_CONFIG['url']}/"
        return f"""<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{escape(title)}</title>
    <meta name="description" content="{escape(description, quote=True)}">
    <link rel="canonical" href="{escape(canonical, quote=True)}">
    <meta property="og:title" content="{escape(title, quote=True)}">
    <meta property="og:description" content="{escape(description, quote=True)}">
    <meta property="og:url" content="{escape(canonical, quote=True)}">
    <meta property="og:type" content="website">
    <link rel="stylesheet" href="{css_prefix}css/style.css">
</head>"""

    def _breadcrumb_schema(self, items: Sequence[Tuple[str, str]]) -> str:
        payload = {
            "@context": "https://schema.org",
            "@type": "BreadcrumbList",
            "itemListElement": [
                {
                    "@type": "ListItem",
                    "position": idx,
                    "name": name,
                    "item": f"{SITE_CONFIG['url']}/{path.lstrip('/')}" if path else f"{SITE_CONFIG['url']}/",
                }
                for idx, (name, path) in enumerate(items, start=1)
            ],
        }
        return self._json_ld(payload)

    def _mover_entries(self) -> Tuple[List[Tuple[float, str, Dict]], List[Tuple[float, str, Dict]]]:
        entries = []
        npm = self.data.get("npm", {})
        for name in npm:
            trend = self.trends.get("npm", {}).get(name, {})
            change = trend.get("change_7d_pct")
            if trend.get("momentum_available") and isinstance(change, (int, float)):
                entries.append((float(change), name, trend))
        rising = sorted(entries, key=lambda item: item[0], reverse=True)
        falling = sorted(entries, key=lambda item: item[0])
        return rising, falling

    def _mover_table(self, entries: Sequence[Tuple[float, str, Dict]], limit: int = 10) -> str:
        rows = []
        for change, name, trend in entries[:limit]:
            pkg = self.data.get("npm", {}).get(name, {})
            rows.append(
                '<tr>'
                f'<td><a href="pages/{escape(name, quote=True)}.html">{escape(name)}</a></td>'
                f'<td>{self._change_html(change)}</td>'
                f'<td>{self._fmt_number(trend.get("downloads_7d"))}</td>'
                f'<td>{self._fmt_number(pkg.get("weekly_downloads"))}</td>'
                f'<td>{escape(str(pkg.get("latest_version", "N/A")))}</td>'
                '</tr>'
            )
        return "".join(rows)

    def _current_activity_table(self) -> str:
        npm = self.data.get("npm", {})
        ranked = sorted(
            npm.items(),
            key=lambda item: item[1].get("weekly_downloads", 0) or 0,
            reverse=True,
        )[:15]
        rows = []
        for name, pkg in ranked:
            trend = self.trends.get("npm", {}).get(name, {})
            rows.append(
                '<tr>'
                f'<td><a href="pages/{escape(name, quote=True)}.html">{escape(name)}</a></td>'
                f'<td>{self._fmt_number(pkg.get("weekly_downloads"))}</td>'
                f'<td>{trend.get("days_since_release") if trend.get("days_since_release") is not None else "N/A"}</td>'
                f'<td>{escape(str(pkg.get("latest_version", "N/A")))}</td>'
                '</tr>'
            )
        return "".join(rows)

    def _generate_movers_page(self) -> str:
        rising, falling = self._mover_entries()
        title = "npm Package Download Trends & Movers | EcosystemPulse"
        description = (
            "Track measured npm package download trends, 7-day momentum, weekly downloads, and release activity. "
            "EcosystemPulse withholds mover rankings when registry data is incomplete."
        )
        schema = self._breadcrumb_schema((("EcosystemPulse", ""), ("npm Package Movers", "movers.html")))
        if rising:
            mover_content = f"""
            <section class="discovery-section">
                <h2>Fastest-rising tracked npm packages</h2>
                <p class="section-copy">Latest 7 consecutive reliable download days compared with the preceding 7.</p>
                <div class="table-wrapper"><table class="data-table"><thead><tr><th>Package</th><th>7d change</th><th>Downloads, 7d</th><th>Trailing week</th><th>Version</th></tr></thead><tbody>{self._mover_table(rising)}</tbody></table></div>
            </section>
            <section class="discovery-section">
                <h2>Fastest-falling tracked npm packages</h2>
                <p class="section-copy">Declines use the same consecutive-day requirement. They are measurements, not judgments about package quality.</p>
                <div class="table-wrapper"><table class="data-table"><thead><tr><th>Package</th><th>7d change</th><th>Downloads, 7d</th><th>Trailing week</th><th>Version</th></tr></thead><tbody>{self._mover_table(falling)}</tbody></table></div>
            </section>"""
        else:
            mover_content = f"""
            <section class="status-panel">
                <h2>Reliable mover rankings are warming up</h2>
                <p>EcosystemPulse will not rank packages from broken or gapped npm download windows. The site needs 14 consecutive reliable calendar days before comparing one 7-day period with the previous 7.</p>
                <p>This page will turn into a live risers-and-fallers table automatically when the evidence is complete.</p>
            </section>
            <section class="discovery-section">
                <h2>Current tracked npm activity</h2>
                <p class="section-copy">These are current registry observations, not momentum rankings.</p>
                <div class="table-wrapper"><table class="data-table"><thead><tr><th>Package</th><th>Trailing-week downloads</th><th>Days since release</th><th>Version</th></tr></thead><tbody>{self._current_activity_table()}</tbody></table></div>
            </section>"""

        return f"""<!DOCTYPE html>
<html lang="en">
{self._head(title, description, "movers.html")}
<body>
<header class="site-header"><nav class="main-nav"><a href="index.html" class="logo">EcosystemPulse</a>{self._nav()}</nav></header>
<main class="container">
    <article class="discovery-page">
        <header class="article-header"><p class="eyebrow">npm download trends</p><h1>npm Package Movers</h1>
        <p>See which tracked npm packages are gaining or losing download momentum using explainable 7-day comparisons. Missing registry days are excluded instead of silently counted as zero.</p></header>
        {mover_content}
        <section class="methodology-box"><h2>How the ranking works</h2><p>Momentum compares the latest seven consecutive reliable npm download days with the previous seven. EcosystemPulse detects coordinated zero-download anomalies across tracked packages, removes those dates, and waits for complete calendar windows before publishing a percentage.</p></section>
        <p class="discovery-links"><a href="comparisons.html">Compare related packages →</a> <a href="npm.html">Browse all tracked npm packages →</a></p>
    </article>
</main>
{schema}
<footer class="site-footer"><div class="footer-content"><p>&copy; {datetime.now().year} EcosystemPulse. Measured developer ecosystem data.</p></div></footer>
</body></html>"""

    def _comparison_metrics(self, name: str) -> Dict:
        pkg = self.data.get("npm", {}).get(name, {})
        trend = self.trends.get("npm", {}).get(name, {})
        dependencies = pkg.get("dependencies", []) or []
        return {
            "name": name,
            "pkg": pkg,
            "trend": trend,
            "weekly_downloads": pkg.get("weekly_downloads"),
            "version": pkg.get("latest_version", "N/A"),
            "dependencies": len(dependencies),
            "days_since_release": trend.get("days_since_release"),
            "releases_90d": trend.get("releases_90d"),
            "change": trend.get("change_7d_pct") if trend.get("momentum_available") else None,
        }

    def _comparison_table(self, names: Sequence[str]) -> str:
        metrics = [self._comparison_metrics(name) for name in names]
        header = "".join(
            f'<th><a href="../pages/{escape(item["name"], quote=True)}.html">{escape(item["name"])}</a></th>'
            for item in metrics
        )
        rows = [
            ("Latest version", [escape(str(item["version"])) for item in metrics]),
            ("Trailing-week npm downloads", [self._fmt_number(item["weekly_downloads"]) for item in metrics]),
            ("7d vs previous 7d", [self._change_html(item["change"]) for item in metrics]),
            ("Days since latest release", [str(item["days_since_release"]) if item["days_since_release"] is not None else "N/A" for item in metrics]),
            ("Releases in 90 days", [str(item["releases_90d"]) if item["releases_90d"] is not None else "N/A" for item in metrics]),
            ("Direct dependencies", [str(item["dependencies"]) for item in metrics]),
        ]
        body = "".join(
            f'<tr><th>{escape(label)}</th>{"".join(f"<td>{value}</td>" for value in values)}</tr>'
            for label, values in rows
        )
        return f'<div class="table-wrapper"><table class="comparison-table"><thead><tr><th>Metric</th>{header}</tr></thead><tbody>{body}</tbody></table></div>'

    def _comparison_charts(self, names: Sequence[str]) -> str:
        cards = []
        for name in names:
            trend = self.trends.get("npm", {}).get(name, {})
            sparkline = self._sparkline_svg(trend.get("download_points", []), f"Daily npm downloads for {name}")
            if not sparkline:
                continue
            cards.append(
                f'<div class="comparison-chart"><h3><a href="../pages/{escape(name, quote=True)}.html">{escape(name)}</a></h3>'
                f'{sparkline}<p>{self._fmt_number(trend.get("downloads_30d"))} downloads across stored reliable days in the current 30-day window.</p></div>'
            )
        return f'<div class="comparison-chart-grid">{"".join(cards)}</div>' if cards else ""

    def _generate_comparison_page(self, slug: str, label: str, names: Sequence[str], description: str) -> str:
        title = f"{label}: npm Downloads, Releases & Trends | EcosystemPulse"
        available = [name for name in names if name in self.data.get("npm", {})]
        schema = self._breadcrumb_schema(
            (("EcosystemPulse", ""), ("Package Comparisons", "comparisons.html"), (label, f"comparisons/{slug}.html"))
        )
        item_schema = self._json_ld({
            "@context": "https://schema.org",
            "@type": "ItemList",
            "name": label,
            "itemListElement": [
                {
                    "@type": "ListItem",
                    "position": idx,
                    "name": name,
                    "url": f"{SITE_CONFIG['url']}/pages/{name}.html",
                }
                for idx, name in enumerate(available, start=1)
            ],
        })
        availability_note = ""
        if any(self._comparison_metrics(name)["change"] is None for name in available):
            availability_note = (
                '<p class="data-note"><strong>Momentum note:</strong> A 7-day change is shown only when 14 consecutive reliable npm download days are available. '
                '“Not yet available” means the evidence window is incomplete, not that the package has zero growth.</p>'
            )
        package_links = "".join(
            f'<li><a href="../pages/{escape(name, quote=True)}.html">{escape(name)} package data</a></li>' for name in available
        )
        return f"""<!DOCTYPE html>
<html lang="en">
{self._head(title, description, f"comparisons/{slug}.html", "../")}
<body>
<header class="site-header"><nav class="main-nav"><a href="../index.html" class="logo">EcosystemPulse</a>{self._nav('../')}</nav></header>
<main class="container">
<article class="comparison-page">
    <header class="article-header"><p class="eyebrow">npm package comparison</p><h1>{escape(label)}</h1><p>{escape(description)}</p></header>
    <section class="discovery-section"><h2>Side-by-side package data</h2>{self._comparison_table(available)}{availability_note}</section>
    <section class="discovery-section"><h2>Download history</h2><p class="section-copy">Sparklines use stored reliable npm daily-download observations. Gaps are not converted to zero.</p>{self._comparison_charts(available)}</section>
    <section class="methodology-box"><h2>What this comparison does and does not say</h2><p>Download counts and release timestamps are observable signals, not a verdict about which library is “best.” EcosystemPulse shows the underlying measurements so you can weigh adoption, maintenance activity, dependencies, API fit, bundle size, documentation, and project requirements separately.</p></section>
    <section class="related-links"><h2>Package detail pages</h2><ul>{package_links}</ul><p><a href="../comparisons.html">Browse all comparisons →</a></p></section>
</article>
</main>
{schema}{item_schema}
<footer class="site-footer"><div class="footer-content"><p>&copy; {datetime.now().year} EcosystemPulse. Measured developer ecosystem data.</p></div></footer>
</body></html>"""

    def _generate_comparison_hub(self) -> str:
        title = "Developer Package Comparisons: npm Downloads & Releases | EcosystemPulse"
        description = "Compare related npm packages using measured weekly downloads, release activity, current versions, dependencies, and reliable download trends."
        cards = []
        for slug, label, names, summary in COMPARISONS:
            if not all(name in self.data.get("npm", {}) for name in names):
                continue
            current = [self._comparison_metrics(name) for name in names]
            stats = " · ".join(
                f'{escape(item["name"])} {self._fmt_number(item["weekly_downloads"])} / week'
                for item in current
            )
            cards.append(
                f'<article class="comparison-card"><h2><a href="comparisons/{slug}.html">{escape(label)}</a></h2>'
                f'<p>{escape(summary)}</p><p class="comparison-card-stats">{stats}</p>'
                f'<a href="comparisons/{slug}.html">View comparison →</a></article>'
            )
        schema = self._breadcrumb_schema((("EcosystemPulse", ""), ("Package Comparisons", "comparisons.html")))
        return f"""<!DOCTYPE html>
<html lang="en">
{self._head(title, description, "comparisons.html")}
<body>
<header class="site-header"><nav class="main-nav"><a href="index.html" class="logo">EcosystemPulse</a>{self._nav()}</nav></header>
<main class="container">
<article class="discovery-page"><header class="article-header"><p class="eyebrow">side-by-side evidence</p><h1>Developer Package Comparisons</h1><p>Compare related npm packages using the same measured signals on each side: trailing-week downloads, release activity, current versions, dependencies, and download momentum when the data window is complete.</p></header>
<div class="comparison-card-grid">{"".join(cards)}</div>
<section class="methodology-box"><h2>Why these comparisons exist</h2><p>People routinely search for package-versus-package choices. EcosystemPulse does not manufacture a winner. These pages make the underlying public measurements easier to compare while leaving the engineering decision to you.</p></section>
<p class="discovery-links"><a href="movers.html">See npm download movers →</a> <a href="npm.html">Browse all tracked npm packages →</a></p></article>
</main>
{schema}
<footer class="site-footer"><div class="footer-content"><p>&copy; {datetime.now().year} EcosystemPulse. Measured developer ecosystem data.</p></div></footer>
</body></html>"""

    @staticmethod
    def _replace_nav(html: str, prefix: str) -> str:
        replacement = DiscoveryBuilder._nav(prefix)
        return re.sub(r'<ul class="nav-links">.*?</ul>', replacement, html, count=1, flags=re.DOTALL)

    def _comparison_links_for_package(self, name: str) -> List[Tuple[str, str]]:
        links = []
        for slug, label, names, _summary in COMPARISONS:
            if name in names and all(item in self.data.get("npm", {}) for item in names):
                links.append((label, f"../comparisons/{slug}.html"))
        return links

    def _enhance_package_pages(self) -> int:
        updated = 0
        for registry in ("npm", "pypi"):
            for name, pkg in self.data.get(registry, {}).items():
                path = self.pages_dir / f"{name}.html"
                if not path.exists():
                    continue
                html = path.read_text(encoding="utf-8")
                if registry == "npm":
                    title = f"{name} npm Downloads, Trends, Releases & Versions | EcosystemPulse"
                    description = f"Track {name} npm downloads, reliable download trends, release activity, current version, dependencies, and version history with measured registry data."
                else:
                    title = f"{name} PyPI Releases, Versions & Package Activity | EcosystemPulse"
                    description = f"Track {name} on PyPI: current version, release activity, recent release cadence, dependencies, and version history from measured registry data."
                html = re.sub(r'<title>.*?</title>', f'<title>{escape(title)}</title>', html, count=1, flags=re.DOTALL)
                html = re.sub(
                    r'<meta name="description" content="[^"]*">',
                    f'<meta name="description" content="{escape(description, quote=True)}">',
                    html,
                    count=1,
                )
                html = self._replace_nav(html, "../")

                breadcrumb = self._breadcrumb_schema(
                    (("EcosystemPulse", ""), ("npm" if registry == "npm" else "PyPI", f"{registry}.html"), (name, f"pages/{name}.html"))
                )
                if "BreadcrumbList" not in html:
                    html = html.replace("</body>", f"{breadcrumb}\n</body>", 1)

                links = self._comparison_links_for_package(name) if registry == "npm" else []
                if links and "Related comparisons" not in html:
                    link_html = "".join(
                        f'<li><a href="{escape(url, quote=True)}">{escape(label)}</a></li>' for label, url in links
                    )
                    section = f'<section class="related-links"><h2>Related comparisons</h2><ul>{link_html}</ul></section>'
                    html = html.replace("</article>", f"{section}</article>", 1)
                path.write_text(html, encoding="utf-8")
                updated += 1
        return updated

    def _enhance_root_navigation(self) -> int:
        updated = 0
        for path in self.output_dir.glob("*.html"):
            if path.name in {"movers.html", "comparisons.html"}:
                continue
            html = path.read_text(encoding="utf-8")
            enhanced = self._replace_nav(html, "")
            if enhanced != html:
                path.write_text(enhanced, encoding="utf-8")
                updated += 1
        return updated

    def _enhance_homepage(self) -> bool:
        path = self.output_dir / "index.html"
        if not path.exists():
            return False
        html = path.read_text(encoding="utf-8")
        if "Explore package trends and comparisons" in html:
            return False
        section = """
<section class="discovery-section home-discovery">
<h2>Explore package trends and comparisons</h2>
<p>Follow measured npm download movement or compare related libraries side by side. EcosystemPulse uses public registry observations and withholds momentum when the evidence window is incomplete.</p>
<div class="home-discovery-grid">
<a class="discovery-tile" href="movers.html"><strong>npm Package Movers</strong><span>Reliable 7-day download momentum and current activity</span></a>
<a class="discovery-tile" href="comparisons.html"><strong>Package Comparisons</strong><span>React vs Vue vs Svelte, Vite vs Webpack vs esbuild, and more</span></a>
</div>
</section>
"""
        marker = '<section class="about-preview">'
        if marker in html:
            html = html.replace(marker, section + marker, 1)
        else:
            html = html.replace("</main>", section + "</main>", 1)
        path.write_text(html, encoding="utf-8")
        return True

    def _extend_sitemap(self, comparison_slugs: Sequence[str]) -> int:
        path = self.output_dir / "sitemap.xml"
        if not path.exists():
            return 0
        xml = path.read_text(encoding="utf-8")
        base = SITE_CONFIG["url"]
        additions = [
            f"  <url><loc>{base}/movers.html</loc><changefreq>daily</changefreq><priority>0.9</priority></url>",
            f"  <url><loc>{base}/comparisons.html</loc><changefreq>weekly</changefreq><priority>0.9</priority></url>",
        ]
        additions.extend(
            f"  <url><loc>{base}/comparisons/{slug}.html</loc><changefreq>daily</changefreq><priority>0.85</priority></url>"
            for slug in comparison_slugs
        )
        new_lines = [line for line in additions if line.split("<loc>", 1)[1].split("</loc>", 1)[0] not in xml]
        if new_lines:
            xml = xml.replace("</urlset>", "\n" + "\n".join(new_lines) + "\n</urlset>")
            path.write_text(xml, encoding="utf-8")
        return len(new_lines)

    def build(self) -> Dict:
        """Build discovery destinations and improve crawl/search context site-wide."""
        (self.output_dir / "movers.html").write_text(self._generate_movers_page(), encoding="utf-8")
        (self.output_dir / "comparisons.html").write_text(self._generate_comparison_hub(), encoding="utf-8")

        generated_slugs = []
        for slug, label, names, summary in COMPARISONS:
            if not all(name in self.data.get("npm", {}) for name in names):
                continue
            (self.compare_dir / f"{slug}.html").write_text(
                self._generate_comparison_page(slug, label, names, summary),
                encoding="utf-8",
            )
            generated_slugs.append(slug)

        package_pages = self._enhance_package_pages()
        root_pages = self._enhance_root_navigation()
        homepage = self._enhance_homepage()
        sitemap_urls = self._extend_sitemap(generated_slugs)
        return {
            "movers": True,
            "comparison_hub": True,
            "comparison_pages": len(generated_slugs),
            "package_pages_enhanced": package_pages,
            "root_pages_enhanced": root_pages,
            "homepage_enhanced": homepage,
            "sitemap_urls_added": sitemap_urls,
        }
