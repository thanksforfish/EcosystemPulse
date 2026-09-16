# EcosystemPulse

EcosystemPulse is an early-stage developer ecosystem data tool. It collects public npm and PyPI package metadata, preserves selected observations over time, generates a static site, validates the build, and refreshes automatically through GitHub Actions.

## Current capabilities

- Tracks a curated set of npm and PyPI packages.
- Displays current package metadata and npm download counts.
- Preserves durable package observations across daily runs.
- Backfills 30 days of complete npm daily download data.
- Calculates transparent 7-day vs previous-7-day npm momentum.
- Shows release recency and recent release cadence from registry timestamps.
- Renders lightweight inline sparklines without a client-side chart dependency.
- Provides live npm search and an outbound PyPI search link.
- Generates package pages, listing pages, sitemap, robots.txt, and canonical custom-domain URLs.
- Includes privacy-first Cloudflare Web Analytics.
- Runs a 29-check smoke suite before deployment.

EcosystemPulse avoids subjective package health scores in favor of showing the underlying measurements. Its usefulness and usage patterns are still being evaluated.

## Run locally

```bash
python run.py
python smoke_test.py
python -m http.server 8000 -d output
```

Then open `http://localhost:8000/`.

## Deployment

The included workflow validates pull requests, refreshes the data daily on `main`, persists durable history, and deploys the generated `output/` directory to GitHub Pages.

Deployment target: `https://ecosystempulse.dev/`
