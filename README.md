# EcosystemPulse

**Live site:** https://ecosystempulse.dev/

EcosystemPulse is an early-stage developer ecosystem data tool. It collects public npm and PyPI package metadata, preserves selected observations over time, generates a static site, validates the build, and refreshes automatically through GitHub Actions.

## Current capabilities

- Tracks a curated set of npm and PyPI packages.
- Displays current package metadata and npm download counts.
- Preserves durable package observations across daily runs.
- Backfills 30 days of complete npm daily download data.
- Calculates transparent 7-day vs previous-7-day npm momentum only when the data-quality window is complete.
- Detects and excludes coordinated npm zero-day anomalies instead of treating them as real download collapses.
- Shows release recency and recent release cadence from registry timestamps.
- Renders lightweight inline sparklines without a client-side chart dependency.
- Provides live npm search and an outbound PyPI search link.
- Publishes npm Movers and package-comparison pages designed around common developer search intent.
- Generates package pages, listing pages, sitemap, robots.txt, canonical custom-domain URLs, and structured breadcrumb/list data.
- Includes privacy-first Cloudflare Web Analytics.
- Runs 33 core integrity/build checks plus 11 V4 discovery/SEO checks before deployment.

EcosystemPulse avoids subjective package health scores in favor of showing the underlying measurements. Its usefulness and usage patterns are still being evaluated.

## Run locally

```bash
python run.py
python smoke_test.py
python v4_smoke_test.py
python -m http.server 8000 -d output
```

Then open `http://localhost:8000/`.

## Deployment

The included workflow validates pull requests, refreshes the data daily on `main`, persists durable history, and deploys the generated `output/` directory to GitHub Pages.

Deployment target: https://ecosystempulse.dev/
