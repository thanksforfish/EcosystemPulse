# EcosystemPulse

EcosystemPulse is a small autonomous developer-ecosystem experiment. It collects public npm and PyPI package metadata, generates a static site, validates the build, and is designed to refresh and redeploy daily through GitHub Actions.

## Current experiment

- Tracks a curated set of npm and PyPI packages.
- Displays real package metadata and npm weekly download counts.
- Provides live npm search and an honest outbound PyPI search link.
- Generates package pages, listing pages, sitemap, and robots.txt.
- Runs an 18-check smoke suite before deployment.

EcosystemPulse is an early-stage public data tool. Its usefulness and usage patterns are still being evaluated.

## Run locally

```bash
python run.py
python smoke_test.py
python -m http.server 8000 -d output
```

Then open `http://localhost:8000/`.

## Deployment

The included workflow builds and validates the site on pushes to `main`, refreshes the data daily, and deploys `output/` to GitHub Pages.

Deployment target: `https://thanksforfish.github.io/EcosystemPulse/`
