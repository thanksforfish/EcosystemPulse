"""
EcosystemPulse V2 — Page Generator
Generates useful pages from real collected data
"""
import json
import shutil
from datetime import datetime
from pathlib import Path
from typing import Dict

from config import SITE_CONFIG


class PageGenerator:
    """Generates pages from real package data."""

    def __init__(self, data_dir: Path, output_dir: Path):
        self.data_dir = data_dir
        self.output_dir = output_dir
        self.pages_dir = output_dir / "pages"
        self.pages_dir.mkdir(parents=True, exist_ok=True)

    def load_data(self) -> Dict:
        """Load collected data."""
        data_path = self.data_dir / "collected_data.json"
        if data_path.exists():
            with open(data_path) as f:
                return json.load(f)
        return {"npm": {}, "pypi": {}}

    def _generate_package_page(self, pkg: Dict, registry: str) -> str:
        """Generate a detailed page for a single package."""
        name = pkg["name"]
        version = pkg.get("latest_version", "N/A")
        description = pkg.get("description", "")
        downloads = pkg.get("weekly_downloads")
        versions = pkg.get("all_versions", [])
        created = pkg.get("created", "")
        modified = pkg.get("modified", "")
        license_info = pkg.get("license", "")
        homepage = pkg.get("homepage", "") or pkg.get("home_page", "")
        dependencies = pkg.get("dependencies", []) or pkg.get("requires_dist", [])
        version_dates = pkg.get("version_dates", {})

        downloads_html = f"<p><strong>Weekly Downloads:</strong> {downloads:,}</p>" if downloads else ""

        versions_html = ""
        if versions:
            recent = versions[-10:]
            versions_html = f"""
            <h2>Version History (Last {len(recent)})</h2>
            <table class="data-table">
                <thead><tr><th>Version</th><th>Released</th></tr></thead>
                <tbody>
                    {"".join(f'<tr><td>{v}</td><td>{version_dates.get(v, "N/A")[:10] if isinstance(version_dates.get(v), str) else "N/A"}</td></tr>' for v in reversed(recent))}
                </tbody>
            </table>"""

        deps_html = ""
        if dependencies:
            deps_html = f"""
            <h2>Dependencies ({len(dependencies)})</h2>
            <div class="tag-list">
                {"".join(f'<span class="tag">{d.split(">=")[0].split("<")[0].split("[")[0].strip()}</span>' for d in dependencies[:20])}
            </div>"""

        keywords = pkg.get("keywords", [])
        if isinstance(keywords, str):
            keywords = [k.strip() for k in keywords.split(",") if k.strip()]
        keywords_html = ""
        if keywords:
            keywords_html = f"""
            <h2>Keywords</h2>
            <div class="tag-list">
                {"".join(f'<span class="tag">{k}</span>' for k in keywords if k)}
            </div>"""

        return f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{name} — EcosystemPulse</title>
    <meta name="description" content="Package information for {name}: {description[:150]}">
    <link rel="stylesheet" href="../css/style.css">
</head>
<body>
    <header class="site-header">
        <nav class="main-nav">
            <a href="../index.html" class="logo">EcosystemPulse</a>
            <ul class="nav-links">
                <li><a href="../npm.html">npm</a></li>
                <li><a href="../pypi.html">PyPI</a></li>
            </ul>
        </nav>
    </header>
    <main class="container">
        <article class="package-detail">
            <header class="package-header">
                <h1>{name}</h1>
                <p class="description">{description}</p>
                <div class="meta">
                    <span class="badge registry">{registry}</span>
                    <span class="badge version">v{version}</span>
                    {f'<span class="badge license">{license_info}</span>' if license_info else ""}
                </div>
            </header>

            {downloads_html}

            <section class="info-section">
                <h2>Quick Info</h2>
                <table class="info-table">
                    <tr><td>Registry</td><td>{registry}</td></tr>
                    <tr><td>Latest Version</td><td>{version}</td></tr>
                    <tr><td>Total Versions</td><td>{len(versions)}</td></tr>
                    {f'<tr><td>Created</td><td>{created[:10]}</td></tr>' if created else ""}
                    {f'<tr><td>Last Modified</td><td>{modified[:10]}</td></tr>' if modified else ""}
                    {f'<tr><td>License</td><td>{license_info}</td></tr>' if license_info else ""}
                    {f'<tr><td>Homepage</td><td><a href="{homepage}" target="_blank">{homepage[:60]}...</a></td></tr>' if homepage else ""}
                </table>
            </section>

            {versions_html}
            {deps_html}
            {keywords_html}

            <section class="links">
                <h2>Links</h2>
                <ul>
                    {f'<li><a href="https://www.npmjs.com/package/{name}" target="_blank">npm page</a></li>' if registry == "npm" else ""}
                    {f'<li><a href="https://pypi.org/project/{name}/" target="_blank">PyPI page</a></li>' if registry == "pypi" else ""}
                    {f'<li><a href="{homepage}" target="_blank">Homepage</a></li>' if homepage else ""}
                </ul>
            </section>
        </article>
    </main>
    <footer class="site-footer">
        <div class="footer-content">
            <p>&copy; {datetime.now().year} EcosystemPulse. Real-time developer ecosystem data.</p>
        </div>
    </footer>
</body>
</html>"""

    def _generate_listing_page(self, packages: Dict[str, Dict], title: str, registry: str) -> str:
        """Generate a listing page for multiple packages."""
        rows = ""
        for name, pkg in sorted(packages.items(), key=lambda x: x[1].get("weekly_downloads", 0) or 0, reverse=True):
            downloads = pkg.get("weekly_downloads")
            downloads_str = f"{downloads:,}" if downloads else "N/A"
            rows += f"""
            <tr>
                <td><a href="pages/{name}.html">{name}</a></td>
                <td>{pkg.get('latest_version', 'N/A')}</td>
                <td>{downloads_str}</td>
                <td>{pkg.get('description', '')[:80]}</td>
            </tr>"""

        return f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{title} — EcosystemPulse</title>
    <meta name="description" content="{title} with real-time download stats and version data">
    <link rel="stylesheet" href="css/style.css">
</head>
<body>
    <header class="site-header">
        <nav class="main-nav">
            <a href="index.html" class="logo">EcosystemPulse</a>
            <ul class="nav-links">
                <li><a href="npm.html">npm</a></li>
                <li><a href="pypi.html">PyPI</a></li>
            </ul>
        </nav>
    </header>
    <main class="container">
        <article class="listing">
            <header class="article-header">
                <h1>{title}</h1>
                <p>Real-time data from {registry} registry. Last updated: {datetime.now().strftime("%Y-%m-%d %H:%M UTC")}</p>
            </header>
            <div class="table-wrapper">
                <table class="data-table">
                    <thead>
                        <tr>
                            <th>Package</th>
                            <th>Version</th>
                            <th>Weekly Downloads</th>
                            <th>Description</th>
                        </tr>
                    </thead>
                    <tbody>
                        {rows}
                    </tbody>
                </table>
            </div>
        </article>
    </main>
    <footer class="site-footer">
        <div class="footer-content">
            <p>&copy; {datetime.now().year} EcosystemPulse. Real-time developer ecosystem data.</p>
        </div>
    </footer>
</body>
</html>"""

    def _generate_index_page(self, npm_packages: Dict, pypi_packages: Dict) -> str:
        """Generate the homepage."""
        npm_count = len(npm_packages)
        pypi_count = len(pypi_packages)

        top_npm = sorted(
            [(n, p) for n, p in npm_packages.items() if p.get("weekly_downloads")],
            key=lambda x: x[1]["weekly_downloads"],
            reverse=True
        )[:5]

        top_npm_rows = ""
        for name, pkg in top_npm:
            top_npm_rows += f"""
            <tr>
                <td><a href="pages/{name}.html">{name}</a></td>
                <td>{pkg.get('latest_version', 'N/A')}</td>
                <td>{pkg.get('weekly_downloads', 0):,}</td>
            </tr>"""

        return f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>EcosystemPulse — Real-Time Developer Ecosystem Data</title>
    <meta name="description" content="Search npm packages and browse PyPI data. Real-time download stats, version history, and dependency data.">
    <link rel="stylesheet" href="css/style.css">
    <style>
        .search-hero {{
            max-width: 500px;
            margin: 0 auto 2rem;
        }}
        .search-hero input {{
            width: 100%;
            padding: 0.75rem 1rem;
            font-size: 1rem;
            border: 2px solid #333;
            border-radius: 6px;
            background: #0a0a0a;
            color: #e0e0e0;
            font-family: 'SF Mono', 'Fira Code', monospace;
            box-sizing: border-box;
        }}
        .search-hero input:focus {{
            outline: none;
            border-color: #00ff88;
        }}
        .search-hero input::placeholder {{
            color: #666;
        }}
    </style>
</head>
<body>
    <header class="site-header">
        <nav class="main-nav">
            <a href="index.html" class="logo">EcosystemPulse</a>
            <ul class="nav-links">
                <li><a href="npm.html">npm</a></li>
                <li><a href="pypi.html">PyPI</a></li>
            </ul>
        </nav>
    </header>
    <main class="container">
        <section class="hero">
            <h1>Developer Ecosystem Data</h1>
            <p>Search npm packages. Browse PyPI data. Real-time stats. No fluff.</p>
            <div class="search-hero">
                <form action="search.html" method="get">
                    <input type="text" name="q" placeholder="Search for a package..." autocomplete="off">
                </form>
            </div>
        </section>

        <section class="stats-grid">
            <div class="stat-card">
                <h3>{npm_count}</h3>
                <p>npm Packages</p>
            </div>
            <div class="stat-card">
                <h3>{pypi_count}</h3>
                <p>PyPI Packages</p>
            </div>
            <div class="stat-card">
                <h3>{npm_count + pypi_count}</h3>
                <p>Total Tracked</p>
            </div>
        </section>

        <section class="top-packages">
            <h2>Top npm by Downloads</h2>
            <div class="table-wrapper">
                <table class="data-table">
                    <thead>
                        <tr><th>Package</th><th>Version</th><th>Weekly Downloads</th></tr>
                    </thead>
                    <tbody>
                        {top_npm_rows}
                    </tbody>
                </table>
            </div>
            <p><a href="npm.html">View all npm packages →</a></p>
        </section>

        <section class="about-preview">
            <h2>What is EcosystemPulse?</h2>
            <p>Real data from npm and PyPI. No opinions. No affiliate links. No SEO spam.</p>
            <ul>
                <li>Search npm packages by name or description</li>
                <li>Browse PyPI package data and versions</li>
                <li>Real download statistics from npm</li>
                <li>Version history and release frequency</li>
                <li>Dependency tracking</li>
            </ul>
        </section>
    </main>
    <footer class="site-footer">
        <div class="footer-content">
            <p>&copy; {datetime.now().year} EcosystemPulse. Real-time developer ecosystem data.</p>
        </div>
    </footer>
    <script>
        document.querySelector('.search-hero input').addEventListener('keydown', function(e) {{
            if (e.key === 'Enter' && this.value.trim()) {{
                window.location.href = 'search.html?q=' + encodeURIComponent(this.value.trim());
            }}
        }});
    </script>
</body>
</html>"""

    def generate_all_pages(self) -> Dict:
        """Generate all pages from collected data."""
        data = self.load_data()
        npm_packages = data.get("npm", {})
        pypi_packages = data.get("pypi", {})

        generated = {"npm_pages": 0, "pypi_pages": 0, "listing_pages": 0, "index": False}

        for name, pkg in npm_packages.items():
            html = self._generate_package_page(pkg, "npm")
            output_path = self.pages_dir / f"{name}.html"
            with open(output_path, "w", encoding="utf-8") as f:
                f.write(html)
            generated["npm_pages"] += 1

        for name, pkg in pypi_packages.items():
            html = self._generate_package_page(pkg, "pypi")
            output_path = self.pages_dir / f"{name}.html"
            with open(output_path, "w", encoding="utf-8") as f:
                f.write(html)
            generated["pypi_pages"] += 1

        if npm_packages:
            html = self._generate_listing_page(npm_packages, "All Tracked npm Packages", "npm")
            output_path = self.output_dir / "npm.html"
            with open(output_path, "w", encoding="utf-8") as f:
                f.write(html)
            generated["listing_pages"] += 1

        if pypi_packages:
            html = self._generate_listing_page(pypi_packages, "All Tracked PyPI Packages", "pypi")
            output_path = self.output_dir / "pypi.html"
            with open(output_path, "w", encoding="utf-8") as f:
                f.write(html)
            generated["listing_pages"] += 1

        html = self._generate_index_page(npm_packages, pypi_packages)
        output_path = self.output_dir / "index.html"
        with open(output_path, "w", encoding="utf-8") as f:
            f.write(html)
        generated["index"] = True

        self._generate_sitemap(npm_packages, pypi_packages)
        self._generate_robots_txt()
        self._copy_static_assets()
        return generated

    def _generate_robots_txt(self):
        """Generate robots.txt."""
        base_url = SITE_CONFIG["url"]
        content = f"User-agent: *\nAllow: /\nSitemap: {base_url}/sitemap.xml\n"
        robots_path = self.output_dir / "robots.txt"
        with open(robots_path, "w") as f:
            f.write(content)

    def _copy_static_assets(self):
        """Copy static assets from engine/static/ to output/."""
        static_dir = Path(__file__).parent / "static"
        if static_dir.exists():
            for item in static_dir.rglob("*"):
                if item.is_file():
                    rel = item.relative_to(static_dir)
                    dest = self.output_dir / rel
                    dest.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(item, dest)

    def _generate_sitemap(self, npm_packages: Dict, pypi_packages: Dict):
        """Generate sitemap.xml from collected data."""
        base_url = SITE_CONFIG["url"]
        urls = [f'  <url><loc>{base_url}/</loc><changefreq>daily</changefreq><priority>1.0</priority></url>']

        for name in npm_packages:
            urls.append(f'  <url><loc>{base_url}/pages/{name}.html</loc><changefreq>weekly</changefreq><priority>0.8</priority></url>')

        for name in pypi_packages:
            urls.append(f'  <url><loc>{base_url}/pages/{name}.html</loc><changefreq>weekly</changefreq><priority>0.8</priority></url>')

        sitemap = f"""<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
{chr(10).join(urls)}
</urlset>"""

        sitemap_path = self.output_dir / "sitemap.xml"
        with open(sitemap_path, "w", encoding="utf-8") as f:
            f.write(sitemap)
