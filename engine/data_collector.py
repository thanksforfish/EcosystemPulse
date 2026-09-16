"""EcosystemPulse V4.1 real-data collector.

Collects current npm/PyPI facts plus a few deliberately preserved fields whose
historical state is difficult to reconstruct later.
"""

from __future__ import annotations

import json
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Dict, List, Optional


class DataCollector:
    """Collect real package data from public registry APIs."""

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
            .replace(",", "_")
        )

    def _fetch_json(self, url: str, cache_key: Optional[str] = None) -> Optional[Dict]:
        """Fetch JSON with a 24-hour local cache and bounded retry."""
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

        for attempt in range(3):
            try:
                req = urllib.request.Request(
                    url,
                    headers={"User-Agent": "EcosystemPulse/4.1 (+https://ecosystempulse.dev)"},
                )
                with urllib.request.urlopen(req, timeout=20) as response:
                    data = json.loads(response.read().decode())
                    if cache_path:
                        with cache_path.open("w", encoding="utf-8") as f:
                            json.dump(data, f, indent=2)
                    return data
            except urllib.error.HTTPError as e:
                if e.code == 429 and attempt < 2:
                    retry_after = e.headers.get("Retry-After") if e.headers else None
                    try:
                        delay = max(1.0, float(retry_after)) if retry_after else 2.0 * (attempt + 1)
                    except (TypeError, ValueError):
                        delay = 2.0 * (attempt + 1)
                    print(f"Rate limited by {url}; retrying in {delay:.1f}s")
                    time.sleep(delay)
                    continue
                print(f"Error fetching {url}: HTTP {e.code}")
                return None
            except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, OSError) as e:
                if attempt < 2:
                    time.sleep(1.0 * (attempt + 1))
                    continue
                print(f"Error fetching {url}: {e}")
                return None
        return None

    @staticmethod
    def _extract_pkg_name(dep_str: str) -> str:
        if not dep_str:
            return ""
        return (
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

    @staticmethod
    def _looks_prerelease(version: str) -> bool:
        value = str(version or "").lower()
        if "-" in value.split("+", 1)[0]:
            return True
        return bool(re.search(r"(?:a|b|rc|alpha|beta|preview|pre|dev)\d*", value))

    @staticmethod
    def _versions_by_date(versions: List[str], dates: Dict[str, str]) -> List[str]:
        return sorted(
            versions,
            key=lambda version: (dates.get(version, ""), str(version)),
        )

    def get_npm_package(self, name: str) -> Optional[Dict]:
        encoded = urllib.parse.quote(name, safe="@/")
        data = self._fetch_json(f"https://registry.npmjs.org/{encoded}", f"npm_{name}")
        if not data:
            return None

        latest_version = data.get("dist-tags", {}).get("latest", "")
        raw_versions = data.get("versions", {}) or {}
        times = data.get("time", {}) or {}
        version_dates = {
            version: times.get(version, "")
            for version in raw_versions
            if times.get(version)
        }
        versions = self._versions_by_date(list(raw_versions.keys()), version_dates)
        stable_version_dates = {
            version: date
            for version, date in version_dates.items()
            if not self._looks_prerelease(version)
        }
        latest_data = raw_versions.get(latest_version, {}) if latest_version else {}
        repository = data.get("repository", {})
        author = data.get("author", {})

        dependency_declarations = {
            "dependencies": dict(latest_data.get("dependencies", {}) or {}),
            "optional_dependencies": dict(latest_data.get("optionalDependencies", {}) or {}),
            "peer_dependencies": dict(latest_data.get("peerDependencies", {}) or {}),
            "dev_dependencies": dict(latest_data.get("devDependencies", {}) or {}),
            "bundled_dependencies": list(
                latest_data.get("bundledDependencies", latest_data.get("bundleDependencies", [])) or []
            ),
        }

        return {
            "name": name,
            "registry": "npm",
            "latest_version": latest_version,
            "all_versions": versions,
            "description": data.get("description", ""),
            "homepage": data.get("homepage", ""),
            "repository": repository.get("url", "") if isinstance(repository, dict) else "",
            "license": data.get("license", ""),
            "author": author.get("name", "") if isinstance(author, dict) else str(author or ""),
            "created": times.get("created", ""),
            "modified": times.get("modified", ""),
            # Preserve every known release timestamp. The prior last-20 truncation made
            # 90-day release metrics materially wrong for fast-moving packages.
            "version_dates": version_dates,
            "stable_version_dates": stable_version_dates,
            "keywords": (data.get("keywords", []) or [])[:10],
            "dependencies": list((latest_data.get("dependencies", {}) or {}).keys()),
            "dependency_declarations": dependency_declarations,
            "dist_tags": dict(data.get("dist-tags", {}) or {}),
            "deprecated": latest_data.get("deprecated") or None,
            "engines": dict(latest_data.get("engines", {}) or {}),
            "os": list(latest_data.get("os", []) or []),
            "cpu": list(latest_data.get("cpu", []) or []),
        }

    @staticmethod
    def _split_bulk_names(names: List[str]) -> tuple[List[str], List[str]]:
        bulk = [name for name in names if not name.startswith("@")]
        scoped = [name for name in names if name.startswith("@")]
        return bulk, scoped

    def get_npm_download_counts(self, names: List[str], period: str = "last-week") -> Dict[str, int]:
        """Fetch download totals with one npm bulk request where possible."""
        names = list(dict.fromkeys(names))
        if not names:
            return {}
        bulk, scoped = self._split_bulk_names(names)
        result: Dict[str, int] = {}

        if bulk:
            joined = ",".join(bulk)
            encoded = urllib.parse.quote(joined, safe=",")
            data = self._fetch_json(
                f"https://api.npmjs.org/downloads/point/{period}/{encoded}",
                f"npm_point_bulk_{period}_{len(bulk)}",
            )
            if isinstance(data, dict):
                if len(bulk) == 1 and data.get("downloads") is not None:
                    result[bulk[0]] = int(data["downloads"])
                else:
                    for name in bulk:
                        item = data.get(name)
                        if isinstance(item, dict) and item.get("downloads") is not None:
                            result[name] = int(item["downloads"])

        for name in scoped:
            encoded = urllib.parse.quote(name, safe="@/")
            data = self._fetch_json(
                f"https://api.npmjs.org/downloads/point/{period}/{encoded}",
                f"npm_point_{period}_{name}",
            )
            if data and data.get("downloads") is not None:
                result[name] = int(data["downloads"])
            time.sleep(0.15)
        return result

    def get_npm_download_count(self, name: str) -> Optional[int]:
        return self.get_npm_download_counts([name]).get(name)

    @staticmethod
    def _normalize_daily(items) -> List[Dict]:
        daily = []
        for item in items or []:
            if not isinstance(item, dict) or not item.get("day"):
                continue
            try:
                downloads = int(item.get("downloads", 0))
            except (TypeError, ValueError):
                downloads = 0
            daily.append({"day": item["day"], "downloads": downloads})
        return daily

    def get_npm_download_ranges(self, names: List[str], days: int = 30) -> Dict[str, Dict]:
        """Fetch complete daily download series using npm's bulk range endpoint."""
        names = list(dict.fromkeys(names))
        if not names:
            return {}
        days = max(1, min(int(days), 365))
        end = datetime.now(timezone.utc).date() - timedelta(days=1)
        start = end - timedelta(days=days - 1)
        period = f"{start.isoformat()}:{end.isoformat()}"
        bulk, scoped = self._split_bulk_names(names)
        result: Dict[str, Dict] = {}

        if bulk:
            joined = ",".join(bulk)
            encoded = urllib.parse.quote(joined, safe=",")
            data = self._fetch_json(
                f"https://api.npmjs.org/downloads/range/{period}/{encoded}",
                f"npm_range_bulk_{period}_{len(bulk)}",
            )
            if isinstance(data, dict):
                if len(bulk) == 1 and isinstance(data.get("downloads"), list):
                    daily = self._normalize_daily(data.get("downloads"))
                    result[bulk[0]] = {"start": start.isoformat(), "end": end.isoformat(), "total": sum(x["downloads"] for x in daily), "daily": daily}
                else:
                    for name in bulk:
                        item = data.get(name)
                        if isinstance(item, dict) and isinstance(item.get("downloads"), list):
                            daily = self._normalize_daily(item.get("downloads"))
                            result[name] = {"start": item.get("start", start.isoformat()), "end": item.get("end", end.isoformat()), "total": sum(x["downloads"] for x in daily), "daily": daily}

        for name in scoped:
            encoded = urllib.parse.quote(name, safe="@/")
            data = self._fetch_json(
                f"https://api.npmjs.org/downloads/range/{period}/{encoded}",
                f"npm_range_{name}_{period}",
            )
            if data and isinstance(data.get("downloads"), list):
                daily = self._normalize_daily(data.get("downloads"))
                result[name] = {"start": start.isoformat(), "end": end.isoformat(), "total": sum(x["downloads"] for x in daily), "daily": daily}
            time.sleep(0.15)
        return result

    def get_npm_download_range(self, name: str, days: int = 30) -> Optional[Dict]:
        return self.get_npm_download_ranges([name], days=days).get(name)

    def get_npm_version_download_counts(self, names: List[str]) -> Dict[str, Dict]:
        """Capture npm's per-version previous-seven-day distribution.

        npm does not expose arbitrary historical queries for this endpoint, so these
        observations are intentionally archived while they are available.
        """
        result: Dict[str, Dict] = {}
        for name in list(dict.fromkeys(names)):
            # npm's per-version endpoint requires the slash in scoped names to be encoded.
            encoded = urllib.parse.quote(name, safe="@")
            data = self._fetch_json(
                f"https://api.npmjs.org/versions/{encoded}/last-week",
                f"npm_versions_last_week_{name}",
            )
            downloads = data.get("downloads") if isinstance(data, dict) else None
            if isinstance(downloads, dict):
                clean = {}
                for version, count in downloads.items():
                    try:
                        clean[str(version)] = int(count)
                    except (TypeError, ValueError):
                        continue
                result[name] = {
                    "package": data.get("package", name),
                    "period": "last-week",
                    "downloads": clean,
                }
            time.sleep(0.10)
        return result

    def get_pypi_package(self, name: str) -> Optional[Dict]:
        encoded = urllib.parse.quote(name, safe="")
        data = self._fetch_json(f"https://pypi.org/pypi/{encoded}/json", f"pypi_{name}")
        if not data:
            return None

        info = data.get("info", {})
        releases = data.get("releases", {}) or {}
        version_dates = {}
        for ver, files in releases.items():
            if files and isinstance(files, list):
                times = [
                    str(file.get("upload_time_iso_8601") or file.get("upload_time") or "")
                    for file in files
                    if isinstance(file, dict)
                ]
                times = [value for value in times if value]
                if times:
                    version_dates[ver] = min(times)
        versions = self._versions_by_date(list(releases.keys()), version_dates)
        stable_version_dates = {
            version: date
            for version, date in version_dates.items()
            if not self._looks_prerelease(version)
        }
        all_dates = sorted(version_dates.values()) if version_dates else []
        latest_version = info.get("version", "")
        latest_files = releases.get(latest_version, []) if latest_version else []
        yanked_reasons = sorted({
            str(file.get("yanked_reason") or "").strip()
            for file in latest_files
            if isinstance(file, dict) and file.get("yanked") and str(file.get("yanked_reason") or "").strip()
        })
        requires_dist_full = [str(item) for item in (info.get("requires_dist", []) or [])]

        return {
            "name": name,
            "registry": "pypi",
            "latest_version": latest_version,
            "all_versions": versions,
            "version_dates": version_dates,
            "stable_version_dates": stable_version_dates,
            "created": all_dates[0] if all_dates else "",
            "modified": all_dates[-1] if all_dates else "",
            "description": info.get("summary", ""),
            "home_page": info.get("home_page", ""),
            "project_urls": info.get("project_urls", {}),
            "license": (info.get("license", "") or "")[:50],
            "author": info.get("author", "") or info.get("author_email", ""),
            "requires_python": info.get("requires_python", ""),
            "keywords": info.get("keywords", ""),
            "classifiers": (info.get("classifiers", []) or [])[:20],
            "requires_dist": [self._extract_pkg_name(d) for d in requires_dist_full[:20]],
            "requires_dist_full": requires_dist_full,
            "dependency_declarations": {"requires_dist": requires_dist_full},
            "latest_yanked": any(bool(file.get("yanked")) for file in latest_files if isinstance(file, dict)),
            "latest_yanked_reasons": yanked_reasons,
        }

    def search_npm(self, query: str, size: int = 20) -> List[Dict]:
        encoded = urllib.parse.quote(query, safe="")
        data = self._fetch_json(
            f"https://registry.npmjs.org/-/v1/search?text={encoded}&size={size}",
            f"npm_search_{query.replace(' ', '_')}",
        )
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
        url = "https://hugovk.github.io/top-pypi-packages/top-pypi-packages-30-days.min.json"
        data = self._fetch_json(url, "pypi_trending")
        if not data:
            return []
        return [
            {"name": row.get("project", ""), "downloads": row.get("download_count", 0)}
            for row in data.get("rows", [])[:50]
        ]

    def collect_ecosystem_data(self, packages: Dict) -> Dict:
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
                results["npm"][pkg_name] = pkg_info

        download_counts = self.get_npm_download_counts(list(results["npm"]))
        for pkg_name, pkg_info in results["npm"].items():
            pkg_info["weekly_downloads"] = download_counts.get(pkg_name)

        for pkg_name in pypi_list:
            print(f"Collecting pypi: {pkg_name}")
            pkg_info = self.get_pypi_package(pkg_name)
            if pkg_info:
                results["pypi"][pkg_name] = pkg_info

        with (self.data_dir / "collected_data.json").open("w", encoding="utf-8") as f:
            json.dump(results, f, indent=2, default=str)
            f.write("\n")

        print(f"\nCollected data for {len(results['npm'])} npm + {len(results['pypi'])} pypi packages")
        return results


DEFAULT_PACKAGES = {
    "npm": [
        "react", "vue", "svelte", "next", "nuxt", "express", "fastify",
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
    DataCollector(Path(__file__).parent.parent / "data").collect_ecosystem_data(DEFAULT_PACKAGES)


if __name__ == "__main__":
    main()
