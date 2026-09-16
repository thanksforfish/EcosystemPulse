"""Durable package-history storage for EcosystemPulse V3."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Tuple


SCHEMA_VERSION = 1
MAX_DAILY_POINTS = 400
MAX_SNAPSHOTS = 400


class HistoryStore:
    """Merge today's collection into small Git-tracked history files."""

    def __init__(self, data_dir: Path):
        self.data_dir = data_dir
        self.history_dir = data_dir / "history"
        self.history_dir.mkdir(parents=True, exist_ok=True)
        self.npm_path = self.history_dir / "npm.json"
        self.pypi_path = self.history_dir / "pypi.json"

    def _empty(self, registry: str) -> Dict:
        return {
            "schema_version": SCHEMA_VERSION,
            "registry": registry,
            "updated_at": None,
            "packages": {},
        }

    def _load(self, path: Path, registry: str) -> Dict:
        if not path.exists():
            return self._empty(registry)
        try:
            with path.open(encoding="utf-8") as f:
                data = json.load(f)
        except (OSError, json.JSONDecodeError):
            return self._empty(registry)
        if not isinstance(data, dict) or data.get("schema_version") != SCHEMA_VERSION:
            return self._empty(registry)
        if not isinstance(data.get("packages"), dict):
            data["packages"] = {}
        return data

    def _write(self, path: Path, data: Dict) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(path.suffix + ".tmp")
        with tmp.open("w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, sort_keys=True)
            f.write("\n")
        tmp.replace(path)

    @staticmethod
    def _snapshot(pkg: Dict, collected_at: str, observed_date: str) -> Dict:
        dependencies = pkg.get("dependencies", []) or pkg.get("requires_dist", []) or []
        versions = pkg.get("all_versions", []) or []
        snapshot = {
            "date": observed_date,
            "collected_at": collected_at,
            "version": pkg.get("latest_version") or None,
            "dependency_count": len(dependencies),
            "total_versions": len(versions),
            "modified": pkg.get("modified") or None,
        }
        if pkg.get("weekly_downloads") is not None:
            snapshot["weekly_downloads"] = int(pkg["weekly_downloads"])
        return snapshot

    @staticmethod
    def _merge_snapshots(existing: list, snapshot: Dict) -> list:
        by_date = {
            item.get("date"): item
            for item in existing
            if isinstance(item, dict) and item.get("date")
        }
        by_date[snapshot["date"]] = snapshot
        return [by_date[key] for key in sorted(by_date)][-MAX_SNAPSHOTS:]

    @staticmethod
    def _merge_daily(existing: list, incoming: list) -> list:
        by_day = {}
        for item in existing:
            if isinstance(item, dict) and item.get("day") and item.get("downloads") is not None:
                by_day[item["day"]] = {
                    "day": item["day"],
                    "downloads": int(item["downloads"]),
                }
        for item in incoming:
            if isinstance(item, dict) and item.get("day") and item.get("downloads") is not None:
                by_day[item["day"]] = {
                    "day": item["day"],
                    "downloads": int(item["downloads"]),
                }
        return [by_day[key] for key in sorted(by_day)][-MAX_DAILY_POINTS:]

    def _update_registry(
        self,
        store: Dict,
        packages: Dict[str, Dict],
        registry: str,
        collector,
        collected_at: str,
        observed_date: str,
    ) -> Tuple[int, int]:
        snapshot_count = 0
        download_series_count = 0
        package_store = store.setdefault("packages", {})

        for name, pkg in packages.items():
            entry = package_store.setdefault(
                name,
                {
                    "first_seen": collected_at,
                    "last_seen": collected_at,
                    "snapshots": [],
                },
            )
            entry.setdefault("first_seen", collected_at)
            entry["last_seen"] = collected_at
            entry["snapshots"] = self._merge_snapshots(
                entry.get("snapshots", []),
                self._snapshot(pkg, collected_at, observed_date),
            )
            snapshot_count += 1

            if registry == "npm":
                range_data = collector.get_npm_download_range(name, days=30)
                incoming = (range_data or {}).get("daily", [])
                entry["daily_downloads"] = self._merge_daily(
                    entry.get("daily_downloads", []), incoming
                )
                if incoming:
                    download_series_count += 1

        store["updated_at"] = collected_at
        return snapshot_count, download_series_count

    def update(self, collected_data: Dict, collector) -> Dict:
        """Merge current collection and npm download history into tracked history."""
        now = datetime.now(timezone.utc)
        collected_at = collected_data.get("collected_at") or now.isoformat()
        observed_date = now.date().isoformat()

        npm_store = self._load(self.npm_path, "npm")
        pypi_store = self._load(self.pypi_path, "pypi")

        npm_snapshots, npm_series = self._update_registry(
            npm_store,
            collected_data.get("npm", {}),
            "npm",
            collector,
            collected_at,
            observed_date,
        )
        pypi_snapshots, _ = self._update_registry(
            pypi_store,
            collected_data.get("pypi", {}),
            "pypi",
            collector,
            collected_at,
            observed_date,
        )

        self._write(self.npm_path, npm_store)
        self._write(self.pypi_path, pypi_store)

        return {
            "npm_snapshots": npm_snapshots,
            "pypi_snapshots": pypi_snapshots,
            "npm_download_series": npm_series,
            "npm_packages": len(npm_store.get("packages", {})),
            "pypi_packages": len(pypi_store.get("packages", {})),
        }
