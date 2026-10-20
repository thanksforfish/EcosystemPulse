"""A small, evidence-first weekly changelog from durable npm/PyPI observations.

Completed Monday-Sunday (UTC) editions are frozen to data/history/weekly_reports.
They remain available even after bounded raw history rotates out.  Never infer a
security issue, a release date, or a breaking change from a registry snapshot.
"""

from __future__ import annotations

import json
from datetime import date, datetime, timedelta, timezone
from html import escape
from pathlib import Path
from urllib.parse import quote

from config import SITE_CONFIG, TRACKED_ECOSYSTEMS


CATEGORIES = ("compatibility", "dependencies", "releases")
TITLES = {
    "compatibility": "Compatibility and deprecation signals",
    "dependencies": "Dependency requirement changes",
    "releases": "Version changes observed",
}
LIMITS = {"compatibility": 8, "dependencies": 10, "releases": 12}


def completed_week(as_of: date) -> tuple[date, date]:
    """Last *completed* Monday-Sunday UTC week (never include an ongoing Sunday)."""
    end = as_of - timedelta(days=as_of.weekday() + 1)
    return end - timedelta(days=6), end


def _read_json(path: Path) -> dict:
    with path.open(encoding="utf-8") as stream:
        value = json.load(stream)
    if not isinstance(value, dict):
        raise ValueError(f"Invalid historical document: {path}")
    return value


def _short(value: object, limit: int = 110) -> str:
    value = str(value)
    return value if len(value) <= limit else value[: limit - 1] + "…"


def _change_map(previous: object, current: object) -> str | None:
    """Summarize changed *requirements*, not just changes in dependency names."""
    a = previous if isinstance(previous, dict) else {}
    b = current if isinstance(current, dict) else {}
    added = sorted(b.keys() - a.keys())
    removed = sorted(a.keys() - b.keys())
    modified = sorted(name for name in a.keys() & b.keys() if a[name] != b[name])
    if not (added or removed or modified):
        return None
    examples = (
        [f"added {name}" for name in added[:2]]
        + [f"removed {name}" for name in removed[:2]]
        + [f"{name}: {_short(a[name], 25)} → {_short(b[name], 25)}" for name in modified[:2]]
    )
    totals = f"{len(added)} added, {len(removed)} removed, {len(modified)} updated"
    return totals + (". Examples: " + "; ".join(examples) if examples else "")


def _change_python_deps(previous: object, current: object) -> str | None:
    a = set(previous or []) if isinstance(previous, list) else set()
    b = set(current or []) if isinstance(current, list) else set()
    added, removed = sorted(b - a), sorted(a - b)
    if not (added or removed):
        return None
    examples = [f"added {_short(x, 65)}" for x in added[:2]]
    examples += [f"removed {_short(x, 65)}" for x in removed[:2]]
    return f"{len(added)} added and {len(removed)} removed requirement declarations. " + "; ".join(examples)


def _registry_url(registry: str, package: str) -> str:
    if registry == "npm":
        return "https://www.npmjs.com/package/" + quote(package, safe="@/")
    return "https://pypi.org/project/" + quote(package, safe="") + "/"


def extract_week_events(npm_history: dict, pypi_history: dict, start: date, end: date) -> list[dict]:
    """Compare consecutive captured states; never treat first observation as a change."""
    latest_by_package_category = {}
    for registry, archive in (("npm", npm_history), ("pypi", pypi_history)):
        tracked = set(TRACKED_ECOSYSTEMS[registry]["packages"])
        for name, package in (archive.get("packages") or {}).items():
            if name not in tracked or not isinstance(package, dict):
                continue
            states = sorted(
                (x for x in package.get("state_history", []) if isinstance(x, dict) and x.get("date")),
                key=lambda x: (x["date"], x.get("collected_at", "")),
            )
            for before, after in zip(states, states[1:]):
                observed = str(after["date"])
                if observed < start.isoformat() or observed > end.isoformat():
                    continue
                findings = []
                old_meta = before.get("mutable_metadata") or {}
                new_meta = after.get("mutable_metadata") or {}
                old_deps = before.get("dependency_declarations") or {}
                new_deps = after.get("dependency_declarations") or {}

                if registry == "pypi":
                    a, b = old_meta.get("requires_python"), new_meta.get("requires_python")
                    if a != b:
                        findings.append(("compatibility", "Python version requirement changed",
                                         f"Recorded requirement: {a or 'unspecified'} → {b or 'unspecified'}."))
                    if old_meta.get("latest_yanked") != new_meta.get("latest_yanked"):
                        findings.append(("compatibility", "PyPI yanked status changed",
                                         f"Latest-version yanked status: {old_meta.get('latest_yanked')} → {new_meta.get('latest_yanked')}."))
                    diff = _change_python_deps(old_deps.get("requires_dist"), new_deps.get("requires_dist"))
                    if diff:
                        findings.append(("dependencies", "PyPI requirements changed", diff))
                else:
                    a, b = old_meta.get("engines") or {}, new_meta.get("engines") or {}
                    if a != b:
                        findings.append(("compatibility", "Runtime engine requirement changed",
                                         f"Recorded engines: {_short(json.dumps(a, sort_keys=True))} → {_short(json.dumps(b, sort_keys=True))}."))
                    if old_meta.get("deprecated") != new_meta.get("deprecated"):
                        findings.append(("compatibility", "Deprecation notice changed",
                                         f"Recorded notice: {_short(old_meta.get('deprecated') or 'none')} → {_short(new_meta.get('deprecated') or 'none')}."))
                    diffs = []
                    for key, label in (("dependencies", "Runtime"),
                                       ("optional_dependencies", "Optional"),
                                       ("peer_dependencies", "Peer")):
                        diff = _change_map(old_deps.get(key), new_deps.get(key))
                        if diff:
                            diffs.append(f"{label}: {diff}")
                    if diffs:
                        findings.append(("dependencies", "npm dependency requirements changed",
                                         " ".join(diffs)))

                if before.get("version") != after.get("version") and before.get("version") and after.get("version"):
                    findings.append(("releases", "Version change observed",
                                     f"Latest registry version: {_short(before['version'])} → {_short(after['version'])}."))
                for category, headline, detail in findings:
                    event = {
                        "category": category,
                        "registry": registry,
                        "package": name,
                        "observed": observed,
                        "headline": headline,
                        "detail": _short(detail, 420),
                    }
                    # Keep the most recent change of each class for a package
                    # within this edition rather than repeat every nightly prerelease.
                    latest_by_package_category[(registry, name, category)] = event
    return sorted(
        latest_by_package_category.values(),
        key=lambda x: (CATEGORIES.index(x["category"]), -date.fromisoformat(x["observed"]).toordinal(),
                       x["registry"], x["package"]),
    )


class WeeklyBrief:
    def __init__(self, data_dir: Path, output_dir: Path):
        self.data_dir = data_dir
        self.output_dir = output_dir
        self.store_dir = data_dir / "history" / "weekly_reports"
        self.public_dir = output_dir / "weekly"

    def _create_frozen_edition(self, start: date, end: date) -> None:
        path = self.store_dir / f"{end.isoformat()}.json"
        if path.exists():
            return  # Once published, an edition cannot silently change.
        npm = _read_json(self.data_dir / "history" / "npm.json")
        pypi = _read_json(self.data_dir / "history" / "pypi.json")
        edition = {
            "schema_version": 1,
            "start": start.isoformat(),
            "end": end.isoformat(),
            "created_utc": datetime.now(timezone.utc).isoformat(),
            "scope": "Observed changes across 33 npm and 31 PyPI packages, not the full registries.",
            "events": extract_week_events(npm, pypi, start, end),
        }
        # Exclusive write ensures an archive never gets overwritten by a rerun.
        with path.open("x", encoding="utf-8") as stream:
            json.dump(edition, stream, indent=2, ensure_ascii=False, sort_keys=True)
            stream.write("\n")

    def _load_editions(self) -> list[dict]:
        result = []
        for file in sorted(self.store_dir.glob("*.json"), reverse=True):
            edition = _read_json(file)
            if (
                edition.get("schema_version") != 1
                or edition.get("end") != file.stem
                or not isinstance(edition.get("events"), list)
                or not isinstance(edition.get("start"), str)
                or date.fromisoformat(edition["end"]) - date.fromisoformat(edition["start"]) != timedelta(days=6)
            ):
                raise ValueError(f"Invalid frozen report: {file}")
            result.append(edition)
        return result

    @staticmethod
    def _navigation(prefix: str) -> str:
        links = (
            ("Weekly changes", "weekly.html"),
            ("npm", "npm.html"), ("PyPI", "pypi.html"),
            ("Movers", "movers.html"), ("Compare", "comparisons.html"),
            ("Search", "search.html"),
        )
        return '<ul class="nav-links">' + "".join(
            f'<li><a href="{prefix}{url}">{escape(label)}</a></li>' for label, url in links
        ) + "</ul>"

    def _frame(self, *, title: str, description: str, canonical: str, body: str, prefix: str) -> str:
        base = SITE_CONFIG["url"]
        return f"""<!DOCTYPE html>
<html lang="en"><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{escape(title)}</title><meta name="description" content="{escape(description, quote=True)}">
<link rel="canonical" href="{base}/{canonical}"><link rel="stylesheet" href="{prefix}css/style.css"></head>
<body><a class="skip-link" href="#main-content">Skip to content</a>
<header class="site-header"><nav class="main-nav"><a class="logo" href="{prefix}index.html">EcosystemPulse</a>{self._navigation(prefix)}</nav></header>
<main class="container" id="main-content" tabindex="-1">{body}</main>
<footer class="site-footer"><div class="footer-content"><p>© {datetime.now(timezone.utc).year} EcosystemPulse. Evidence from public package registries.</p></div></footer>
</body></html>"""

    @staticmethod
    def _event_markup(event: dict, prefix: str) -> str:
        name = escape(str(event["package"]))
        registry = escape(str(event["registry"]).upper())
        headline = escape(str(event["headline"]))
        observed = escape(str(event["observed"]))
        detail = escape(str(event["detail"]))
        internal = f'{prefix}pages/{quote(event["package"], safe="")}.html'
        source = escape(_registry_url(event["registry"], event["package"]), quote=True)
        return f"""<article class="brief-event"><div class="brief-event-meta">{registry} · Observed {observed}</div>
<h3>{name}: {headline}</h3><p>{detail}</p>
<p class="brief-event-links"><a href="{internal}">Package overview</a> · <a href="{source}" rel="noopener noreferrer" target="_blank">Official registry ↗</a></p></article>"""

    def _edition_markup(self, edition: dict, prefix: str) -> str:
        groups = []
        for category in CATEGORIES:
            events = [x for x in edition["events"] if x["category"] == category]
            shown = events[:LIMITS[category]]
            entries = "".join(self._event_markup(x, prefix) for x in shown)
            if not entries:
                entries = '<p class="data-note">No changes of this type were recorded among the tracked packages.</p>'
            if len(events) > len(shown):
                entries += f'<p class="method-note">Showing {len(shown)} of {len(events)} observed changes in this category.</p>'
            groups.append(f'<section class="discovery-section"><h2>{TITLES[category]} ({len(events)})</h2>'
                          f'<div class="brief-event-grid">{entries}</div></section>')
        start, end = escape(edition["start"]), escape(edition["end"])
        return f"""<header class="article-header"><p class="eyebrow">Weekly package change intelligence</p>
<h1>What changed this week?</h1>
<p>Registry changes observed from {start} through {end} (UTC). Highlights from 33 npm and 31 PyPI packages, not a comprehensive security or release audit.</p></header>
<div class="methodology-box"><h2>How to interpret these signals</h2>
<p>We compare successive snapshots of registry metadata. An observation date is not necessarily the actual release date. A changed requirement does not by itself establish a breaking change, vulnerability, or impact on your project. Always check the official package's details before upgrading. We never fill missing npm download dates with invented figures.</p></div>
{''.join(groups)}"""

    def build(self, as_of: date | None = None) -> dict:
        today = as_of or datetime.now(timezone.utc).date()
        start, end = completed_week(today)
        self.store_dir.mkdir(parents=True, exist_ok=True)
        self.public_dir.mkdir(parents=True, exist_ok=True)
        # Reconstruct missed complete weekly editions if the collector was offline.
        existing = sorted(self.store_dir.glob("*.json"))
        if existing:
            last = date.fromisoformat(existing[-1].stem)
            if last > end:
                raise ValueError("Future weekly archive date found")
            pending = [last + timedelta(days=7 * i) for i in range(1, 1 + (end - last).days // 7)]
        else:
            pending = [end]
        for week_end in pending:
            self._create_frozen_edition(week_end - timedelta(days=6), week_end)
        editions = self._load_editions()
        if not editions:
            raise RuntimeError("No completed weekly edition")
        latest = editions[0]
        for edition in editions:
            body = self._edition_markup(edition, "../")
            self._write(
                self.public_dir / f"{edition['end']}.html",
                self._frame(title=f"Package changes, week ending {edition['end']} | EcosystemPulse",
                            description=f"Observed npm and PyPI package changes for the week ending {edition['end']}.",
                            canonical=f"weekly/{edition['end']}.html", body=body, prefix="../"),
            )
        archive_links = "".join(
            f'<li><a href="weekly/{escape(item["end"], quote=True)}.html">Week ending {escape(item["end"])}</a>'
            f' · {len(item["events"])} tracked change categories</li>' for item in editions
        )
        index_body = (self._edition_markup(latest, "") +
                      '<section class="related-links"><h2>Previous editions</h2>'
                      f'<ul>{archive_links}</ul></section>')
        self._write(
            self.output_dir / "weekly.html",
            self._frame(title="What changed this week? | EcosystemPulse",
                        description="Observed compatibility changes, dependency updates and package versions across tracked npm and PyPI projects.",
                        canonical="weekly.html", body=index_body, prefix=""),
        )
        home = self.output_dir / "index.html"
        html = home.read_text(encoding="utf-8")
        highlights = [x for x in latest["events"] if x["category"] == "compatibility"][:2]
        if not highlights:
            highlights = [x for x in latest["events"] if x["category"] == "dependencies"][:2]
        if not highlights:
            highlights = [x for x in latest["events"] if x["category"] == "releases"][:2]
        examples = "".join(
            f'<li><strong>{escape(x["package"])}</strong>: {escape(x["headline"])}</li>'
            for x in highlights
        ) or '<li>No qualifying changes were observed this week.</li>'
        teaser = f"""<section class="brief-home" aria-labelledby="brief-home-title">
<p class="eyebrow">Week ending {escape(latest['end'])}</p><h2 id="brief-home-title">What changed in developer packages this week?</h2>
<p>See observed compatibility requirements, dependency changes and releases, with dated evidence instead of invented health scores.</p>
<ul>{examples}</ul><p><a href="weekly.html">Read the weekly package changes →</a></p>
</section>"""
        marker = '<dl class="stats-grid">'
        if marker not in html:
            raise RuntimeError("Homepage brief insertion point missing")
        if 'id="brief-home-title"' not in html:
            self._write(home, html.replace(marker, teaser + "\n" + marker, 1))
        sitemap = self.output_dir / "sitemap.xml"
        xml = sitemap.read_text(encoding="utf-8")
        paths = ["weekly.html"] + [f"weekly/{x['end']}.html" for x in editions]
        lines = [
            f'  <url><loc>{SITE_CONFIG["url"]}/{path}</loc><changefreq>weekly</changefreq><priority>0.8</priority></url>'
            for path in paths if f"<loc>{SITE_CONFIG['url']}/{path}</loc>" not in xml
        ]
        if lines:
            self._write(sitemap, xml.replace("</urlset>", "\n" + "\n".join(lines) + "\n</urlset>"))
        return {"week_end": latest["end"], "events": len(latest["events"]), "archives": len(editions)}

    @staticmethod
    def _write(path: Path, content: str) -> None:
        path.write_text(content, encoding="utf-8")
