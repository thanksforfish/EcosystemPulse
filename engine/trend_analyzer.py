"""Explainable trend calculations for EcosystemPulse V4.1."""

from __future__ import annotations

import json
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from statistics import median
from typing import Dict, Optional


TREND_SCHEMA_VERSION = 1
MOMENTUM_MAX_AGE_DAYS = 2


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
    # Prefer stable release timestamps when the collector can distinguish them.
    source = pkg.get("stable_version_dates") or pkg.get("version_dates") or {}
    dates = []
    for value in source.values():
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
            "release_scope": "stable when identifiable",
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
        "release_scope": "stable when identifiable",
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
        except (OSError, json.JSONDecodeError) as exc:
            raise RuntimeError(f"Unreadable durable trend history: {path}") from exc
        if not isinstance(data, dict) or not isinstance(data.get("packages"), dict):
            raise RuntimeError(f"Invalid durable trend history structure: {path}")
        return data

    @staticmethod
    def _consecutive_suffix(points: list[Dict]) -> list[Dict]:
        """Return the newest uninterrupted calendar-day suffix of a download series."""
        if not points:
            return []
        parsed = []
        for item in points:
            try:
                day_value = datetime.strptime(str(item["day"]), "%Y-%m-%d").date()
                downloads = int(item["downloads"])
            except (KeyError, TypeError, ValueError):
                continue
            parsed.append((day_value, {"day": day_value.isoformat(), "downloads": downloads}))
        parsed.sort(key=lambda pair: pair[0])
        if not parsed:
            return []

        suffix = [parsed[-1]]
        for pair in reversed(parsed[:-1]):
            newer_day = suffix[-1][0]
            if newer_day - pair[0] != timedelta(days=1):
                break
            suffix.append(pair)
        suffix.reverse()
        return [item for _, item in suffix]

    @staticmethod
    def _download_metrics(entry: Dict, as_of_date: Optional[date] = None) -> Dict:
        points = [
            item
            for item in entry.get("daily_downloads", [])
            if isinstance(item, dict)
            and item.get("day")
            and isinstance(item.get("downloads"), (int, float))
        ]
        points = sorted(points, key=lambda item: item["day"])[-30:]
        contiguous = TrendAnalyzer._consecutive_suffix(points)
        contiguous_days = len(contiguous)

        latest_day = None
        if contiguous:
            try:
                latest_day = datetime.strptime(contiguous[-1]["day"], "%Y-%m-%d").date()
            except (KeyError, TypeError, ValueError):
                latest_day = None

        data_fresh = True
        freshness_age_days = None
        if as_of_date is not None:
            if latest_day is None:
                data_fresh = False
            else:
                freshness_age_days = (as_of_date - latest_day).days
                data_fresh = 0 <= freshness_age_days <= MOMENTUM_MAX_AGE_DAYS

        last_7 = None
        previous_7 = None
        change_pct = None
        if contiguous_days >= 14 and data_fresh:
            comparison = contiguous[-14:]
            previous_7 = sum(int(item["downloads"]) for item in comparison[:7])
            last_7 = sum(int(item["downloads"]) for item in comparison[7:])
            if previous_7 > 0:
                change_pct = round(((last_7 - previous_7) / previous_7) * 100, 1)

        downloads_30d = None
        average_30d = None
        if contiguous_days >= 30 and data_fresh:
            values_30 = [int(item["downloads"]) for item in contiguous[-30:]]
            downloads_30d = sum(values_30)
            average_30d = round(downloads_30d / 30)

        # Charts use only the newest uninterrupted suffix. This avoids drawing a
        # continuous line across excluded/missing calendar dates.
        chart_points = contiguous[-30:]
        return {
            "download_history_days": contiguous_days,
            "download_observation_days": len(points),
            "download_points": chart_points,
            "download_had_gap": len(chart_points) < len(points),
            "download_latest_day": latest_day.isoformat() if latest_day else None,
            "download_data_fresh": data_fresh,
            "download_freshness_age_days": freshness_age_days,
            "download_freshness_limit_days": MOMENTUM_MAX_AGE_DAYS,
            "downloads_7d": last_7,
            "downloads_previous_7d": previous_7,
            "downloads_30d": downloads_30d,
            "average_daily_downloads_30d": average_30d,
            "change_7d_pct": change_pct,
            "momentum": _momentum_label(change_pct),
            "momentum_available": change_pct is not None,
            "comparison_requires_consecutive_days": True,
            "comparison_requires_fresh_data": True,
        }

    def analyze(self, collected_data: Dict) -> Dict:
        now = datetime.now(timezone.utc)
        npm_history_doc = self._load_history("npm")
        pypi_history_doc = self._load_history("pypi")
        npm_history = npm_history_doc.get("packages", {})
        pypi_history = pypi_history_doc.get("packages", {})
        excluded_days = npm_history_doc.get("excluded_download_days", {})
        if not isinstance(excluded_days, dict):
            excluded_days = {}

        result = {
            "schema_version": TREND_SCHEMA_VERSION,
            "generated_at": now.isoformat(),
            "methodology": {
                "momentum": (
                    "Trailing 7 consecutive reliable npm download days versus the preceding 7 consecutive reliable days; "
                    "the newest download day must be no more than 2 calendar days old. Rising/falling thresholds are +/-5%. "
                    "Registry-wide zero anomalies are excluded."
                ),
                "release_activity": (
                    "Calculated from the full registry release-timestamp set available at collection time; prereleases are excluded "
                    "when they can be identified. No subjective health score is used."
                ),
                "charts": "Download charts use only the newest uninterrupted reliable calendar-day segment; missing dates are not visually compressed together.",
            },
            "npm_data_quality": {
                "excluded_registry_days": sorted(excluded_days),
                "excluded_registry_day_count": len(excluded_days),
            },
            "npm": {},
            "pypi": {},
        }

        for name, pkg in collected_data.get("npm", {}).items():
            metrics = self._download_metrics(npm_history.get(name, {}), as_of_date=now.date())
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
