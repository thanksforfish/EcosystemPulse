"""Durable package-history storage for EcosystemPulse V4.1."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Optional, Tuple


SCHEMA_VERSION = 1
MAX_DAILY_POINTS = 400
MAX_SNAPSHOTS = 400
MAX_STATE_CHANGES = 200
MAX_VERSION_DOWNLOAD_SNAPSHOTS = 120
TOP_VERSION_DOWNLOADS = 25
MIN_GLOBAL_ZERO_SAMPLES = 10
GLOBAL_ZERO_FRACTION = 0.50


class HistoryCorruptionError(RuntimeError):
    """Raised when durable history exists but cannot be safely recovered."""


class HistoryStore:
    """Merge today's collection into Git-tracked history without silent data loss."""

    def __init__(self, data_dir: Path):
        self.data_dir = data_dir
        self.history_dir = data_dir / "history"
        self.backup_dir = self.history_dir / "backups"
        self.history_dir.mkdir(parents=True, exist_ok=True)
        self.backup_dir.mkdir(parents=True, exist_ok=True)
        self.npm_path = self.history_dir / "npm.json"
        self.pypi_path = self.history_dir / "pypi.json"

    def _empty(self, registry: str) -> Dict:
        return {
            "schema_version": SCHEMA_VERSION,
            "registry": registry,
            "updated_at": None,
            "packages": {},
        }

    def _backup_path(self, path: Path) -> Path:
        return self.backup_dir / path.name

    @staticmethod
    def _valid_store(data: object, registry: str) -> bool:
        return (
            isinstance(data, dict)
            and data.get("schema_version") == SCHEMA_VERSION
            and data.get("registry") == registry
            and isinstance(data.get("packages"), dict)
        )

    def _read_valid_store(self, path: Path, registry: str) -> Optional[Dict]:
        if not path.exists():
            return None
        try:
            with path.open(encoding="utf-8") as f:
                data = json.load(f)
        except (OSError, json.JSONDecodeError):
            return None
        return data if self._valid_store(data, registry) else None

    def _load(self, path: Path, registry: str) -> Dict:
        if not path.exists():
            return self._empty(registry)

        current = self._read_valid_store(path, registry)
        if current is not None:
            return current

        backup_path = self._backup_path(path)
        backup = self._read_valid_store(backup_path, registry)
        if backup is not None:
            print(f"WARNING: recovering invalid {path.name} from {backup_path}")
            return backup

        raise HistoryCorruptionError(
            f"Refusing to replace unreadable durable history: {path}. "
            f"No valid recovery copy exists at {backup_path}."
        )

    @staticmethod
    def _write_json(path: Path, data: Dict) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(path.suffix + ".tmp")
        with tmp.open("w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, sort_keys=True)
            f.write("\n")
        tmp.replace(path)

    def _write(self, path: Path, data: Dict) -> None:
        registry = str(data.get("registry") or path.stem)
        # Preserve the previous valid document before replacement. Never overwrite a
        # known-good backup with corrupt current content.
        previous = self._read_valid_store(path, registry)
        if previous is not None:
            self._write_json(self._backup_path(path), previous)
        self._write_json(path, data)

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
    def _state_record(pkg: Dict, registry: str, collected_at: str, observed_date: str) -> Dict:
        dependency_declarations = pkg.get("dependency_declarations", {})
        if not isinstance(dependency_declarations, dict):
            dependency_declarations = {}
        if registry == "npm":
            mutable = {
                "dist_tags": pkg.get("dist_tags", {}) or {},
                "deprecated": pkg.get("deprecated"),
                "engines": pkg.get("engines", {}) or {},
                "os": pkg.get("os", []) or [],
                "cpu": pkg.get("cpu", []) or [],
            }
        else:
            mutable = {
                "requires_python": pkg.get("requires_python") or None,
                "latest_yanked": bool(pkg.get("latest_yanked")),
                "latest_yanked_reasons": pkg.get("latest_yanked_reasons", []) or [],
                "classifiers": pkg.get("classifiers", []) or [],
            }
        payload = {
            "version": pkg.get("latest_version") or None,
            "dependency_declarations": dependency_declarations,
            "mutable_metadata": mutable,
        }
        canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
        return {
            "date": observed_date,
            "collected_at": collected_at,
            "state_hash": hashlib.sha256(canonical.encode("utf-8")).hexdigest(),
            **payload,
        }

    @staticmethod
    def _merge_state_history(existing: list, record: Dict) -> list:
        valid = [item for item in existing if isinstance(item, dict) and item.get("state_hash")]
        if valid and valid[-1].get("state_hash") == record.get("state_hash"):
            return valid[-MAX_STATE_CHANGES:]
        valid.append(record)
        return valid[-MAX_STATE_CHANGES:]

    @staticmethod
    def _version_download_snapshot(pkg: Dict, payload: Dict, collected_at: str, observed_date: str) -> Optional[Dict]:
        downloads = payload.get("downloads") if isinstance(payload, dict) else None
        if not isinstance(downloads, dict) or not downloads:
            return None
        clean: Dict[str, int] = {}
        for version, count in downloads.items():
            try:
                clean[str(version)] = max(0, int(count))
            except (TypeError, ValueError):
                continue
        if not clean:
            return None

        ranked = sorted(clean.items(), key=lambda item: (-item[1], item[0]))
        selected = dict(ranked[:TOP_VERSION_DOWNLOADS])
        latest = str(pkg.get("latest_version") or "")
        if latest and latest in clean:
            selected[latest] = clean[latest]
        archived_total = sum(selected.values())
        total = sum(clean.values())
        return {
            "date": observed_date,
            "collected_at": collected_at,
            "period": "last-week",
            "source": "npm per-version downloads endpoint",
            "reported_versions": len(clean),
            "archived_versions": len(selected),
            "total_downloads": total,
            "other_downloads": max(0, total - archived_total),
            "versions": dict(sorted(selected.items())),
        }

    @staticmethod
    def _merge_version_download_history(existing: list, snapshot: Dict) -> list:
        by_date = {
            item.get("date"): item
            for item in existing
            if isinstance(item, dict) and item.get("date")
        }
        by_date[snapshot["date"]] = snapshot
        return [by_date[key] for key in sorted(by_date)][-MAX_VERSION_DOWNLOAD_SNAPSHOTS:]

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

    @staticmethod
    def _find_suspect_zero_days(series_by_name: Dict[str, list]) -> Dict[str, Dict]:
        """Find coordinated zero days that look like an upstream registry gap."""
        day_stats: Dict[str, Dict[str, int]] = {}
        for daily in series_by_name.values():
            seen_for_package = set()
            for item in daily or []:
                if not isinstance(item, dict) or not item.get("day") or item.get("downloads") is None:
                    continue
                day = str(item["day"])
                if day in seen_for_package:
                    continue
                seen_for_package.add(day)
                try:
                    downloads = int(item["downloads"])
                except (TypeError, ValueError):
                    continue
                stats = day_stats.setdefault(day, {"packages_observed": 0, "zero_packages": 0})
                stats["packages_observed"] += 1
                if downloads == 0:
                    stats["zero_packages"] += 1

        suspect: Dict[str, Dict] = {}
        for day, stats in day_stats.items():
            observed = stats["packages_observed"]
            zeros = stats["zero_packages"]
            if observed < MIN_GLOBAL_ZERO_SAMPLES:
                continue
            zero_fraction = zeros / observed if observed else 0.0
            if zeros >= MIN_GLOBAL_ZERO_SAMPLES and zero_fraction >= GLOBAL_ZERO_FRACTION:
                suspect[day] = {
                    "reason": "registry-wide zero anomaly",
                    "packages_observed": observed,
                    "zero_packages": zeros,
                    "zero_fraction": round(zero_fraction, 3),
                }
        return suspect

    @staticmethod
    def _series_from_store(package_store: Dict[str, Dict]) -> Dict[str, list]:
        return {
            name: entry.get("daily_downloads", [])
            for name, entry in package_store.items()
            if isinstance(entry, dict)
        }

    @staticmethod
    def _series_from_ranges(download_ranges: Dict[str, Dict]) -> Dict[str, list]:
        return {
            name: (payload or {}).get("daily", [])
            for name, payload in download_ranges.items()
            if isinstance(payload, dict)
        }

    @staticmethod
    def _days_present(series_by_name: Dict[str, list]) -> set[str]:
        days: set[str] = set()
        for daily in series_by_name.values():
            for item in daily or []:
                if isinstance(item, dict) and item.get("day"):
                    days.add(str(item["day"]))
        return days

    @staticmethod
    def _remove_days(daily: list, excluded_days: set[str]) -> list:
        if not excluded_days:
            return list(daily or [])
        return [
            item for item in (daily or [])
            if not (isinstance(item, dict) and str(item.get("day", "")) in excluded_days)
        ]

    def _clean_npm_download_history(self, store: Dict, download_ranges: Dict[str, Dict], collected_at: str) -> Tuple[Dict[str, Dict], set[str]]:
        """Remove bad zero-days while allowing later corrected npm data to restore them."""
        package_store = store.setdefault("packages", {})
        existing_series = self._series_from_store(package_store)
        incoming_series = self._series_from_ranges(download_ranges)
        incoming_days = self._days_present(incoming_series)

        suspect_existing = self._find_suspect_zero_days(existing_series)
        suspect_incoming = self._find_suspect_zero_days(incoming_series)
        suspect_days = {
            day for day in suspect_existing
            if day not in incoming_days
        } | set(suspect_incoming)

        for entry in package_store.values():
            if isinstance(entry, dict):
                entry["daily_downloads"] = self._remove_days(
                    entry.get("daily_downloads", []), suspect_days
                )

        cleaned_ranges: Dict[str, Dict] = {}
        for name, payload in download_ranges.items():
            if not isinstance(payload, dict):
                continue
            cleaned = dict(payload)
            cleaned["daily"] = self._remove_days(payload.get("daily", []), suspect_days)
            cleaned["total"] = sum(
                int(item.get("downloads", 0))
                for item in cleaned["daily"]
                if isinstance(item, dict)
            )
            cleaned_ranges[name] = cleaned

        excluded = store.get("excluded_download_days")
        if not isinstance(excluded, dict):
            excluded = {}
        for day in incoming_days - set(suspect_incoming):
            excluded.pop(day, None)
        for day in sorted(suspect_days):
            details = suspect_incoming.get(day) or suspect_existing.get(day) or {}
            excluded[day] = {**details, "excluded_at": collected_at}
        store["excluded_download_days"] = excluded
        return cleaned_ranges, suspect_days

    def _update_registry(
        self,
        store: Dict,
        packages: Dict[str, Dict],
        registry: str,
        collected_at: str,
        observed_date: str,
        download_ranges: Dict[str, Dict] | None = None,
        version_downloads: Dict[str, Dict] | None = None,
    ) -> Tuple[int, int, int, int]:
        snapshot_count = 0
        download_series_count = 0
        state_change_count = 0
        version_download_count = 0
        package_store = store.setdefault("packages", {})
        download_ranges = download_ranges or {}
        version_downloads = version_downloads or {}

        for name, pkg in packages.items():
            entry = package_store.setdefault(
                name,
                {"first_seen": collected_at, "last_seen": collected_at, "snapshots": []},
            )
            entry.setdefault("first_seen", collected_at)
            entry["last_seen"] = collected_at
            entry["snapshots"] = self._merge_snapshots(
                entry.get("snapshots", []),
                self._snapshot(pkg, collected_at, observed_date),
            )
            snapshot_count += 1

            state_record = self._state_record(pkg, registry, collected_at, observed_date)
            old_state_len = len(entry.get("state_history", []))
            entry["state_history"] = self._merge_state_history(
                entry.get("state_history", []), state_record
            )
            if len(entry["state_history"]) > old_state_len:
                state_change_count += 1

            if registry == "npm":
                incoming = (download_ranges.get(name) or {}).get("daily", [])
                entry["daily_downloads"] = self._merge_daily(
                    entry.get("daily_downloads", []), incoming
                )
                if incoming:
                    download_series_count += 1

                version_snapshot = self._version_download_snapshot(
                    pkg, version_downloads.get(name, {}), collected_at, observed_date
                )
                if version_snapshot:
                    entry["version_download_history"] = self._merge_version_download_history(
                        entry.get("version_download_history", []), version_snapshot
                    )
                    version_download_count += 1

        store["updated_at"] = collected_at
        return snapshot_count, download_series_count, state_change_count, version_download_count

    def update(self, collected_data: Dict, collector) -> Dict:
        """Merge current collection and quality-checked npm history."""
        now = datetime.now(timezone.utc)
        collected_at = collected_data.get("collected_at") or now.isoformat()
        observed_date = now.date().isoformat()

        npm_store = self._load(self.npm_path, "npm")
        pypi_store = self._load(self.pypi_path, "pypi")

        npm_packages = collected_data.get("npm", {})
        npm_ranges = collector.get_npm_download_ranges(list(npm_packages), days=30)
        npm_ranges, suspect_days = self._clean_npm_download_history(
            npm_store, npm_ranges, collected_at
        )

        version_downloads: Dict[str, Dict] = {}
        if hasattr(collector, "get_npm_version_download_counts"):
            version_downloads = collector.get_npm_version_download_counts(list(npm_packages)) or {}

        npm_snapshots, npm_series, npm_state_changes, npm_version_downloads = self._update_registry(
            npm_store,
            npm_packages,
            "npm",
            collected_at,
            observed_date,
            download_ranges=npm_ranges,
            version_downloads=version_downloads,
        )
        pypi_snapshots, _, pypi_state_changes, _ = self._update_registry(
            pypi_store,
            collected_data.get("pypi", {}),
            "pypi",
            collected_at,
            observed_date,
        )

        self._write(self.npm_path, npm_store)
        self._write(self.pypi_path, pypi_store)

        return {
            "npm_snapshots": npm_snapshots,
            "pypi_snapshots": pypi_snapshots,
            "npm_download_series": npm_series,
            "npm_version_download_snapshots": npm_version_downloads,
            "npm_state_changes": npm_state_changes,
            "pypi_state_changes": pypi_state_changes,
            "npm_packages": len(npm_store.get("packages", {})),
            "pypi_packages": len(pypi_store.get("packages", {})),
            "npm_excluded_zero_days": len(suspect_days),
            "history_backups": str(self.backup_dir),
        }
