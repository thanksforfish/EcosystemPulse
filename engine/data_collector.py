"""
EcosystemPulse V3 — Real Data Collector
Pulls package data from npm and PyPI public APIs.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Dict, List, Optional


class DataCollector:
    """Collects real package data from public APIs."""

    def __init__(self, data_dir: Path):
        self.data_dir = data_dir
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.cache_dir = data_dir / "cache"
        self.cache_dir.mkdir(exist_ok=True)

    @staticmethod
    def _safe_cache_key(cache_key: str) -> str:
        return (
            cache_key.replace("/", "__")
            .replace("\\", "__")
            .replace("@", "at_")
            .replace(":", "_")
        )

    def _fetch_json(self, url: str, cache_key: Optional[str] = None) -> Optional[Dict]:
        """Fetch JSON from URL with optional 24-hour local caching."""
        cache_path = None
        if cache_key:
            cache_path = self.cache_dir / f"{self._safe_cache_key(cache_key)}.json"
            if cache_path.exists():
                age = datetime.now().timestamp() - cache_path.stat().st_mtime
                if age < 86400:
                    try:
                        with cache_path.open("r", encoding="utf-8") as f:
                            return json.load(f)
                    except (OSError, json.JSONDecodeError):
                        pass

        try:
            req = urllib.request.Request(
                url,
                headers={"User-Agent": "EcosystemPulse/3.0 (+https://ecosystempulse.dev)"},
            )
            with urllib.request.urlopen(req, timeout=20) as response:
                data = json.loads(response.read().decode())
                if cache_path:
                    with cache_path.open("w", encoding="utf-8") as f:
                        json.dump(data, f, indent=2)
                return data
        except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, json.JSONDecodeError, OSError) as e:
            print(f"Error fetching {url}: {e}")
            return None

    def _extract_pkg_name(self, dep_str: str) -> str:
        """Extract package name from a dependency string like 'package>=1.0'."""
        if not dep_str:
            return ""
        name = (
            dep_str.split(">=")[0]
            .split("<=")[0]
            .split("<")[0]
            .split(">")[0]
            .split("==")[0]
            .split("!=")[0]
            .split("[")[0]
            .split(";")[0]
            .strip()
        )
        return name

    def get_npm_package(self, name: str) -> Optional[Dict]:
        """Get package metadata from the public npm registry."""
        encoded = urllib.parse.quote(name, safe="@/")
        url = f"https://registry.npmjs.org/{encoded}"
        data = self._fetch_json(url, f"npm_{name}")
        if not data:
            return None

        latest_version = data.get("dist-tags", {}).get("latest", "")
        versions = list(data.get("versions", {}).keys())
        times = data.get("time", {})
        latest_data = data.get("versions", {}).get(latest_version, {}) if latest_version else {}

        repository = data.get("repository", {})
        repository_url = repository.get("url", "") if isinstance(repository, dict) else ""
        author = data.get("author", {})
        author_name = author.get("name", "") if isinstance(author, dict) else str(author or "")

        return {
            "name": name,
            "registry": "npm",
            "latest_version": latest_version,
            "all_versions": versions,
            "description": data.get("description", ""),
            "homepage": data.get("homepage", ""),
            "repository": repository_url,
            "license": data.get("license", ""),
            "author": author_name,
            "created": times.get("created", ""),
            "modified": times.get("modified", ""),
            "version_dates": {v: times.get(v, "") for v in versions[-20:]},
            "keywords": (data.get("keywords", []) or [])[:10],
            "dependencies": list((latest_data.get("dependencies", {}) or {}).keys()),
        }

    def get_npm_download_count(self, name: str) -> Optional[int]:
        """Get npm's public trailing-week download count."""
        encoded = urllib.parse.quote(name, safe="@/")
        url = f"https://api.npmjs.org/downloads/point/last-week/{encoded}"
        data = self._fetch_json(url, f"npm_downloads_{name}")
        if data and data.get("downloads") is not None:
            return int(data["downloads"])
        return None

    def get_npm_download_range(self, name: str, days: int = 30) -> Optional[Dict]:
        """Get complete daily npm download counts for the previous N days.

        npm's range endpoint expects an explicit date range. We end at yesterday so
        trend comparisons never mix a partial current day with complete past days.
        """
        days = max(1, min(int(days), 365))
        end = datetime.now(timezone.utc).date() - timedelta(days=1)
        start = end - timedelta(days=days - 1)
        encoded = urllib.parse.quote(name, safe="@/")
        url = f"https://api.npmjs.org/downloads/range/{start.isoformat()}:{end.isoformat()}/{encoded}"
        cache_key = f"npm_range_{name}_{start.isoformat()}_{end.isoformat()}"
        data = self._fetch_json(url, cache_key)
        if not data or "downloads" not in data:
            return None

        daily = []
        for item in data.get("downloads", []):
            if not isinstance(item, dict) or not item.get("day"):
                continue
            try:
                downloads = int(item.get("downloads", 0))
            except (TypeError, ValueError):
                downloads = 0
            daily.append({"day": item["day"], "downloads": downloads})

        return {
            "start": start.isoformat(),
            "end": end.isoformat(),
            "total": sum(item["downloads"] for item in daily),
            "daily": daily,
        }

    def get_pypi_package(self, name: str) -> Optional[Dict]:
        """Get package metadata from the public PyPI JSON API."""
        encoded = urllib.parse.quote(name, safe="")
        url = f"https://pypi.org/pypi/{encoded}/json"
        data = self._fetch_json(url, f"pypi_{name}")
        if not data:
            return None

        info = data.get("info", {})
        releases = data.get("releases", {})

        version_dates = {}
        for ver, files in releases.items():
            if files and isinstance(files, list):
                upload_time = files[0].get("upload_time", "")
                if upload_time:
                    version_dates[ver] = upload_time

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
            "classifiers": (info.get("classifiers", []) or [])[:10],
            "requires_dist": [
                self._extract_pkg_name(d)
                for d in (info.get("requires_dist", []) or [])[:20]
            ],
        }

    def search_npm(self, query: str, size: int = 20) -> List[Dict]:
        """Search npm packages using the public registry search endpoint."""
        encoded = urllib.parse.quote(query, safe="")
        url = f"https://registry.npmjs.org/-/v1/search?text={encoded}&size={size}"
        data = self._fetch_json(url, f"npm_search_{query.replace(' ', '_')}")
        if not data:
            return []

        results = []
        for obj in data.get("objects", []):
            pkg = obj.get("package", {})
            results.append(
                {
                    "name": pkg.get("name", ""),
                    "description": pkg.get("description", ""),
                    "version": pkg.get("version", ""),
                    "score": obj.get("score", {}).get("final", 0),
                }
            )
        return results

    def get_pypi_trending(self) -> List[Dict]:
        """Fetch the optional third-party top-PyPI snapshot used for research only."""
        url = "https://hugovk.github.io/top-pypi-packages/top-pypi-packages-30-days.min.json"
        data = self._fetch_json(url, "pypi_trending")
        if not data:
            return []
        rows = data.get("rows", [])[:50]
        return [
            {"name": row.get("project", ""), "downloads": row.get("download_count", 0)}
            for row in rows
        ]

    def collect_ecosystem_data(self, packages: Dict) -> Dict:
        """Collect the configured npm and PyPI package sets."""
        results = {
            "npm": {},
            "pypi": {},
            "collected_at": datetime.now(timezone.utc).isoformat(),
        }

        npm_list = packages.get("npm", [])
        if isinstance(npm_list, dict):
            npm_list = npm_list.get("packages", [])
        pypi_list = packages.get("pypi", [])
        if isinstance(pypi_list, dict):
            pypi_list = pypi_list.get("packages", [])

        for pkg_name in npm_list:
            print(f"Collecting npm: {pkg_name}")
            pkg_info = self.get_npm_package(pkg_name)
            if pkg_info:
                pkg_info["weekly_downloads"] = self.get_npm_download_count(pkg_name)
                results["npm"][pkg_name] = pkg_info

        for pkg_name in pypi_list:
            print(f"Collecting pypi: {pkg_name}")
            pkg_info = self.get_pypi_package(pkg_name)
            if pkg_info:
                results["pypi"][pkg_name] = pkg_info

        output_path = self.data_dir / "collected_data.json"
        with output_path.open("w", encoding="utf-8") as f:
            json.dump(results, f, indent=2, default=str)
            f.write("\n")

        print(
            f"\nCollected data for {len(results['npm'])} npm + "
            f"{len(results['pypi'])} pypi packages"
        )
        return results


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
    collector = DataCollector(Path(__file__).parent.parent / "data")
    collector.collect_ecosystem_data(DEFAULT_PACKAGES)


if __name__ == "__main__":
    main()
