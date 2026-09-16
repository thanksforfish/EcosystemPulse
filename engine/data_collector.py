"""
EcosystemPulse V2 — Real Data Collector
Pulls package data from npm and PyPI public APIs
"""
import json
import urllib.request
import urllib.error
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional


class DataCollector:
    """Collects real package data from public APIs."""

    def __init__(self, data_dir: Path):
        self.data_dir = data_dir
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.cache_dir = data_dir / "cache"
        self.cache_dir.mkdir(exist_ok=True)

    def _fetch_json(self, url: str, cache_key: Optional[str] = None) -> Optional[Dict]:
        """Fetch JSON from URL with optional caching."""
        if cache_key:
            cache_path = self.cache_dir / f"{cache_key}.json"
            if cache_path.exists():
                # Use cache if less than 24 hours old
                age = datetime.now().timestamp() - cache_path.stat().st_mtime
                if age < 86400:  # 24 hours
                    with open(cache_path, "r") as f:
                        return json.load(f)

        try:
            req = urllib.request.Request(url, headers={"User-Agent": "EcosystemPulse/1.0"})
            with urllib.request.urlopen(req, timeout=15) as response:
                data = json.loads(response.read().decode())

                if cache_key:
                    with open(self.cache_dir / f"{cache_key}.json", "w") as f:
                        json.dump(data, f, indent=2)

                return data
        except Exception as e:
            print(f"Error fetching {url}: {e}")
            return None

    def _extract_pkg_name(self, dep_str: str) -> str:
        """Extract package name from a dependency string like 'package>=1.0'."""
        if not dep_str:
            return ""
        # Remove version specifiers
        name = dep_str.split(">=")[0].split("<=")[0].split("<")[0].split(">")[0].split("==")[0].split("!=")[0].split("[")[0].split(";")[0].strip()
        return name

    def get_npm_package(self, name: str) -> Optional[Dict]:
        """Get package info from npm registry (no auth needed)."""
        url = f"https://registry.npmjs.org/{name}"
        data = self._fetch_json(url, f"npm_{name}")
        if not data:
            return None

        # Extract latest version info
        latest_version = data.get("dist-tags", {}).get("latest", "")
        versions = list(data.get("versions", {}).keys())
        times = data.get("time", {})

        return {
            "name": name,
            "registry": "npm",
            "latest_version": latest_version,
            "all_versions": versions,
            "description": data.get("description", ""),
            "homepage": data.get("homepage", ""),
            "repository": data.get("repository", {}).get("url", "") if isinstance(data.get("repository"), dict) else "",
            "license": data.get("license", ""),
            "author": data.get("author", {}).get("name", "") if isinstance(data.get("author"), dict) else str(data.get("author", "")),
            "created": times.get("created", ""),
            "modified": times.get("modified", ""),
            "version_dates": {v: times.get(v, "") for v in versions[-10:]},  # Last 10 versions
            "keywords": data.get("keywords", [])[:10],
            "dependencies": list(data.get("versions", {}).get(latest_version, {}).get("dependencies", {}).keys()) if latest_version else [],
        }

    def get_npm_download_count(self, name: str) -> Optional[int]:
        """Get weekly download count from npm API."""
        url = f"https://api.npmjs.org/downloads/point/last-week/{name}"
        data = self._fetch_json(url, f"npm_downloads_{name}")
        if data:
            return data.get("downloads")
        return None

    def get_npm_download_range(self, name: str, days: int = 365) -> Optional[Dict]:
        """Get download data for date range."""
        url = f"https://api.npmjs.org/downloads/range/{days}d:{name}"
        data = self._fetch_json(url, f"npm_range_{name}_{days}")
        if data and "downloads" in data:
            total = sum(d.get("downloads", 0) for d in data["downloads"])
            return {"total": total, "daily": data["downloads"][-30:]}  # Last 30 days
        return None

    def get_pypi_package(self, name: str) -> Optional[Dict]:
        """Get package info from PyPI (no auth needed)."""
        url = f"https://pypi.org/pypi/{name}/json"
        data = self._fetch_json(url, f"pypi_{name}")
        if not data:
            return None

        info = data.get("info", {})
        releases = data.get("releases", {})

        # Extract version dates from release files
        version_dates = {}
        for ver, files in releases.items():
            if files and isinstance(files, list):
                upload_time = files[0].get("upload_time", "")
                if upload_time:
                    version_dates[ver] = upload_time

        # Get created/modified from earliest/latest uploads
        all_dates = sorted(version_dates.values()) if version_dates else []
        created = all_dates[0] if all_dates else ""
        modified = all_dates[-1] if all_dates else ""

        return {
            "name": name,
            "registry": "pypi",
            "latest_version": info.get("version", ""),
            "all_versions": list(releases.keys()),
            "version_dates": version_dates,
            "created": created,
            "modified": modified,
            "description": info.get("summary", ""),
            "home_page": info.get("home_page", ""),
            "project_urls": info.get("project_urls", {}),
            "license": (info.get("license", "") or "")[:50],
            "author": info.get("author", "") or info.get("author_email", ""),
            "requires_python": info.get("requires_python", ""),
            "keywords": info.get("keywords", ""),
            "classifiers": info.get("classifiers", [])[:10],
            "requires_dist": [self._extract_pkg_name(d) for d in (info.get("requires_dist", []) or [])[:20]],
        }

    def search_npm(self, query: str, size: int = 20) -> List[Dict]:
        """Search npm packages (no auth needed)."""
        url = f"https://registry.npmjs.org/-/v1/search?text={query}&size={size}"
        data = self._fetch_json(url, f"npm_search_{query.replace(' ', '_')}")
        if not data:
            return []

        results = []
        for obj in data.get("objects", []):
            pkg = obj.get("package", {})
            results.append({
                "name": pkg.get("name", ""),
                "description": pkg.get("description", ""),
                "version": pkg.get("version", ""),
                "score": obj.get("score", {}).get("final", 0),
            })
        return results

    def get_pypi_trending(self) -> List[Dict]:
        """Get recently updated PyPI packages."""
        url = "https://hugovk.github.io/top-pypi-packages/top-pypi-packages-30-days.min.json"
        data = self._fetch_json(url, "pypi_trending")
        if not data:
            return []

        rows = data.get("rows", [])[:50]
        return [
            {
                "name": row.get("project", ""),
                "downloads": row.get("download_count", 0),
            }
            for row in rows
        ]

    def collect_ecosystem_data(self, packages: Dict) -> Dict:
        """Collect data for a set of packages across ecosystems.
        
        packages format: {"npm": ["pkg1", "pkg2"], "pypi": ["pkg1", "pkg2"]}
        or: {"npm": {"packages": ["pkg1", "pkg2"]}, "pypi": {"packages": [...]}}
        """
        results = {"npm": {}, "pypi": {}, "collected_at": datetime.now().isoformat()}

        # Handle nested config format
        npm_list = packages.get("npm", [])
        if isinstance(npm_list, dict):
            npm_list = npm_list.get("packages", [])
        
        pypi_list = packages.get("pypi", [])
        if isinstance(pypi_list, dict):
            pypi_list = pypi_list.get("packages", [])

        # Collect npm packages
        for pkg_name in npm_list:
            print(f"Collecting npm: {pkg_name}")
            pkg_info = self.get_npm_package(pkg_name)
            if pkg_info:
                downloads = self.get_npm_download_count(pkg_name)
                pkg_info["weekly_downloads"] = downloads
                results["npm"][pkg_name] = pkg_info

        # Collect PyPI packages
        for pkg_name in pypi_list:
            print(f"Collecting pypi: {pkg_name}")
            pkg_info = self.get_pypi_package(pkg_name)
            if pkg_info:
                results["pypi"][pkg_name] = pkg_info

        # Save collected data
        output_path = self.data_dir / "collected_data.json"
        with open(output_path, "w") as f:
            json.dump(results, f, indent=2, default=str)

        print(f"\nCollected data for {len(results['npm'])} npm + {len(results['pypi'])} pypi packages")
        return results


# Default package sets for each ecosystem
DEFAULT_PACKAGES = {
    "npm": [
        "react", "vue", "angular", "svelte", "next", "nuxt", "express", "fastify",
        "typescript", "webpack", "vite", "esbuild", "tailwindcss", "prisma",
        "mongoose", "sequelize", "axios", "lodash", "date-fns", "zod",
    ],
    "pypi": [
        "django", "flask", "fastapi", "uvicorn", "pydantic", "sqlalchemy",
        "celery", "redis", "requests", "httpx", "pandas", "numpy",
        "scikit-learn", "torch", "transformers", "langchain", "openai",
        "pillow", "pytest", "black",
    ],
}


def main():
    """Run data collection for default packages."""
    collector = DataCollector(Path(__file__).parent.parent / "data")
    data = collector.collect_ecosystem_data(DEFAULT_PACKAGES)

    # Print summary
    print("\n=== Collection Summary ===")
    print(f"npm packages: {len(data['npm'])}")
    for name, info in list(data["npm"].items())[:5]:
        print(f"  {name}: v{info['latest_version']} ({info.get('weekly_downloads', 'N/A')} weekly downloads)")
    print(f"pypi packages: {len(data['pypi'])}")
    for name, info in list(data["pypi"].items())[:5]:
        print(f"  {name}: v{info['latest_version']}")


if __name__ == "__main__":
    main()
