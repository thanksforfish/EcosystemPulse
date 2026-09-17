"""Focused V4.1 trust, recovery, and future-data regression checks."""

import json
import sys
import tempfile
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

BASE = Path(__file__).resolve().parent
DATA = BASE / "data"
OUTPUT = BASE / "output"
sys.path.insert(0, str(BASE / "engine"))

from config import TRACKED_ECOSYSTEMS
from history_store import HistoryCorruptionError, HistoryStore, TOP_VERSION_DOWNLOADS
from trend_analyzer import MOMENTUM_MAX_AGE_DAYS, TrendAnalyzer

errors = []


def record(condition, label, detail=""):
    status = "PASS" if condition else "FAIL"
    print(f"{label} {status}" + (f": {detail}" if detail else ""))
    if not condition:
        errors.append(f"{label} FAIL" + (f": {detail}" if detail else ""))


def load_json(path, default):
    try:
        with Path(path).open(encoding="utf-8") as f:
            value = json.load(f)
        return value
    except (OSError, json.JSONDecodeError):
        return default


collected = load_json(DATA / "collected_data.json", {})
npm = collected.get("npm", {})
pypi = collected.get("pypi", {})
expected_npm = TRACKED_ECOSYSTEMS["npm"]["packages"]
expected_pypi = TRACKED_ECOSYSTEMS["pypi"]["packages"]
record(
    len(npm) >= int(len(expected_npm) * 0.9) and len(pypi) >= int(len(expected_pypi) * 0.9),
    "V4.1 CHECK 1",
    f"fresh collection coverage npm={len(npm)}/{len(expected_npm)} pypi={len(pypi)}/{len(expected_pypi)}",
)

try:
    collected_at = datetime.fromisoformat(str(collected.get("collected_at", "")).replace("Z", "+00:00"))
    if collected_at.tzinfo is None:
        collected_at = collected_at.replace(tzinfo=timezone.utc)
    age_hours = (datetime.now(timezone.utc) - collected_at.astimezone(timezone.utc)).total_seconds() / 3600
except (TypeError, ValueError):
    age_hours = 999
record(0 <= age_hours <= 6, "V4.1 CHECK 2", f"collection age={age_hours:.2f}h")

react = npm.get("react", {})
react_dates = react.get("version_dates", {}) if isinstance(react, dict) else {}
record(
    isinstance(react_dates, dict) and len(react_dates) > 20,
    "V4.1 CHECK 3",
    f"React release timestamps preserved={len(react_dates)} (> old 20-version cap)",
)

requests_pkg = pypi.get("requests", {})
requests_versions = requests_pkg.get("all_versions", []) if isinstance(requests_pkg, dict) else []
requests_dates = requests_pkg.get("version_dates", {}) if isinstance(requests_pkg, dict) else {}
dated_versions = [version for version in requests_versions if requests_dates.get(version)]
dated_values = [requests_dates[version] for version in dated_versions]
record(
    bool(dated_values) and dated_values == sorted(dated_values),
    "V4.1 CHECK 4",
    "PyPI version history is chronological before page rendering",
)

start = date(2026, 1, 1)
old_points = [
    {"day": (start + timedelta(days=i)).isoformat(), "downloads": 100 if i < 7 else 120}
    for i in range(14)
]
old_metrics = TrendAnalyzer._download_metrics(
    {"daily_downloads": old_points}, as_of_date=date(2026, 9, 16)
)
record(
    not old_metrics.get("momentum_available")
    and not old_metrics.get("download_data_fresh")
    and old_metrics.get("change_7d_pct") is None,
    "V4.1 CHECK 5",
    f"stale 14-day window cannot qualify as current momentum (max age={MOMENTUM_MAX_AGE_DAYS}d)",
)

fresh_end = date(2026, 9, 15)
fresh_start = fresh_end - timedelta(days=13)
fresh_points = [
    {"day": (fresh_start + timedelta(days=i)).isoformat(), "downloads": 100 if i < 7 else 120}
    for i in range(14)
]
fresh_metrics = TrendAnalyzer._download_metrics(
    {"daily_downloads": fresh_points}, as_of_date=date(2026, 9, 16)
)
record(
    fresh_metrics.get("momentum_available") and fresh_metrics.get("change_7d_pct") == 20.0,
    "V4.1 CHECK 6",
    "fresh consecutive data still produces momentum",
)

gapped = [
    {"day": "2026-09-10", "downloads": 100},
    {"day": "2026-09-12", "downloads": 110},
    {"day": "2026-09-13", "downloads": 111},
    {"day": "2026-09-14", "downloads": 112},
    {"day": "2026-09-15", "downloads": 113},
]
gap_metrics = TrendAnalyzer._download_metrics(
    {"daily_downloads": gapped}, as_of_date=date(2026, 9, 16)
)
chart_days = [point["day"] for point in gap_metrics.get("download_points", [])]
record(
    chart_days == ["2026-09-12", "2026-09-13", "2026-09-14", "2026-09-15"]
    and gap_metrics.get("download_had_gap"),
    "V4.1 CHECK 7",
    "chart input stops at the newest gap instead of visually compressing missing dates",
)

npm_history = load_json(DATA / "history" / "npm.json", {})
pypi_history = load_json(DATA / "history" / "pypi.json", {})
backup_npm = load_json(DATA / "history" / "backups" / "npm.json", {})
backup_pypi = load_json(DATA / "history" / "backups" / "pypi.json", {})
record(
    backup_npm.get("schema_version") == 1 and backup_pypi.get("schema_version") == 1,
    "V4.1 CHECK 8",
    "valid rolling history recovery copies exist",
)

recovery_ok = False
fail_closed_ok = False
with tempfile.TemporaryDirectory() as tmp:
    data_dir = Path(tmp)
    store = HistoryStore(data_dir)
    valid = {"schema_version": 1, "registry": "npm", "updated_at": None, "packages": {"demo": {}}}
    store._write_json(store._backup_path(store.npm_path), valid)
    store.npm_path.write_text("{broken", encoding="utf-8")
    recovered = store._load(store.npm_path, "npm")
    recovery_ok = recovered.get("packages", {}).get("demo") == {}
    store._backup_path(store.npm_path).unlink()
    try:
        store._load(store.npm_path, "npm")
    except HistoryCorruptionError:
        fail_closed_ok = True
record(recovery_ok, "V4.1 CHECK 9", "corrupt history recovers from known-good copy")
record(fail_closed_ok, "V4.1 CHECK 10", "corrupt history without recovery copy fails closed")

npm_hist_packages = npm_history.get("packages", {})
pypi_hist_packages = pypi_history.get("packages", {})
npm_state = sum(1 for name in npm if npm_hist_packages.get(name, {}).get("state_history"))
pypi_state = sum(1 for name in pypi if pypi_hist_packages.get(name, {}).get("state_history"))
record(
    npm_state >= int(len(npm) * 0.9) and pypi_state >= int(len(pypi) * 0.9),
    "V4.1 CHECK 11",
    f"change-aware package state archived npm={npm_state}/{len(npm)} pypi={pypi_state}/{len(pypi)}",
)

version_archives = [
    entry.get("version_download_history", [])[-1]
    for name, entry in npm_hist_packages.items()
    if name in npm and entry.get("version_download_history")
]
well_shaped = [
    item for item in version_archives
    if isinstance(item.get("versions"), dict)
    and item.get("reported_versions", 0) >= item.get("archived_versions", 0) > 0
    and item.get("archived_versions", 0) <= TOP_VERSION_DOWNLOADS + 1
]
record(
    len(well_shaped) >= max(10, int(len(npm) * 0.7)),
    "V4.1 CHECK 12",
    f"bounded per-version npm windows archived for {len(well_shaped)}/{len(npm)} current packages",
)

search_html = (OUTPUT / "search.html").read_text(encoding="utf-8", errors="ignore") if (OUTPUT / "search.html").exists() else ""
record(
    "View EcosystemPulse history" in search_html and "trackedNpm" in search_html and "trackedPypi" in search_html,
    "V4.1 CHECK 13",
    "tracked search results route to local history before external registry fallback",
)

record(
    "angular" not in expected_npm and not (OUTPUT / "pages" / "angular.html").exists(),
    "V4.1 CHECK 14",
    "legacy unscoped AngularJS package is no longer presented as modern Angular",
)

workflow = (BASE / ".github" / "workflows" / "deploy.yml").read_text(encoding="utf-8")
record(
    "cron: '17 2 * * *'" in workflow and "python v4_1_smoke_test.py" in workflow,
    "V4.1 CHECK 15",
    "scheduled collection runs after midnight UTC and V4.1 gates CI",
)

print("\n=== V4.1 RESULT ===")
if errors:
    for error in errors:
        print("  " + error)
    raise SystemExit(1)
print("ALL 15 V4.1 CHECKS PASSED")
