"""Explainable trend calculations for EcosystemPulse V3."""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from statistics import median
from typing import Dict, Iterable, Optional


TREND_SCHEMA_VERSION = 1


def _parse_datetime(value: object) -> Optional[datetime]:
    if not isinstance(value, str) or not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)
    except ValueError:
        return None


def _release_datetimes(pkg: Dict) -> list[datetime]:
    dates = []
    for value in (pkg.get("version_dates") or {}).values():
        parsed = _parse_datetime(value)
        if parsed:
            dates.append(parsed)
    return sorted(set(dates))


def _release_metrics(pkg: Dict, now: datetime) -> Dict:
    dates = _release_datetimes(pkg)
    if not dates:
        return {
            "days_since_release": None,
            "releases_90d": 0,
            "median_release_interval_days": None,
        }

    latest = dates[-1]
    days_since = max(0, (now.date() - latest.date()).days)
    cutoff = now - timedelta(days=90)
    releases_90d = sum(1 for item in dates if item >= cutoff)

    recent = dates[-10:]
    intervals = [
        max(0, (recent[i] - recent[i - 1]).days)
        for i in range(1, len(recent))
        if recent[i] > recent[i - 1]
    ]
    interval = round(float(median(intervals)), 1) if intervals else None
    return {
        "days_since_release": days_since,
        "releases_90d": releases_90d,
        "median_release_interval_days": interval,
    }


def _momentum_label(change_pct: Optional[float]) -> str:
    if change_pct is None:
        return "insufficient data"
    if change_pct >= 5:
        return "rising"
    if change_pct <= -5:
        return "falling"
    return "steady"


class TrendAnalyzer:
    """Turn durable observations into transparent, non-mystery metrics."""

    def __init__(self, data_dir: Path):
        self.data_dir = data_dir
        self.history_dir = data_dir / "history"
        self.output_path = data_dir / "trends.json"

    def _load_history(self, registry: str) -> Dict:
        path = self.history_dir / f"{registry}.json"
        if not path.exists():
            return {"packages": {}}
        try:
            with path.open(encoding="utf-8") as f:
                data = json.load(f)
        except (OSError, json.JSONDecodeError):
            return {"packages": {}}
        if not isinstance(data.get("packages"), dict):
            data["packages"] = {}
        return data

    @staticmethod
    def _download_metrics(entry: Dict) -> Dict:
        points = [
            item
            for item in entry.get("daily_downloads", [])
            if isinstance(item, dict)
            and item.get("day")
            and isinstance(item.get("downloads"), (int, float))
        ]
        points = sorted(points, key=lambda item: item["day"])[-30:]
        values = [int(item["downloads"]) for item in points]

        last_7 = sum(values[-7:]) if len(values) >= 7 else None
        previous_7 = sum(values[-14:-7]) if len(values) >= 14 else None
        change_pct = None
        if last_7 is not None and previous_7 and previous_7 > 0:
            change_pct = round(((last_7 - previous_7) / previous_7) * 100, 1)

        return {
            "download_history_days": len(points),
            "download_points": points,
            "downloads_7d": last_7,
            "downloads_previous_7d": previous_7,
            "downloads_30d": sum(values) if values else None,
            "average_daily_downloads_30d": round(sum(values) / len(values)) if values else None,
            "change_7d_pct": change_pct,
            "momentum": _momentum_label(change_pct),
        }

    def analyze(self, collected_data: Dict) -> Dict:
        now = datetime.now(timezone.utc)
        npm_history = self._load_history("npm").get("packages", {})
        pypi_history = self._load_history("pypi").get("packages", {})

        result = {
            "schema_version": TREND_SCHEMA_VERSION,
            "generated_at": now.isoformat(),
            "methodology": {
                "momentum": "Trailing 7 complete npm download days versus the preceding 7; rising/falling thresholds are +/-5%.",
                "release_activity": "Calculated directly from registry release timestamps; no subjective health score is used.",
            },
            "npm": {},
            "pypi": {},
        }

        for name, pkg in collected_data.get("npm", {}).items():
            metrics = self._download_metrics(npm_history.get(name, {}))
            metrics.update(_release_metrics(pkg, now))
            metrics["current_version"] = pkg.get("latest_version") or None
            metrics["current_weekly_downloads"] = pkg.get("weekly_downloads")
            result["npm"][name] = metrics

        for name, pkg in collected_data.get("pypi", {}).items():
            metrics = _release_metrics(pkg, now)
            metrics["current_version"] = pkg.get("latest_version") or None
            metrics["history_snapshots"] = len(
                pypi_history.get(name, {}).get("snapshots", [])
            )
            result["pypi"][name] = metrics

        with self.output_path.open("w", encoding="utf-8") as f:
            json.dump(result, f, indent=2, sort_keys=True)
            f.write("\n")
        return result
