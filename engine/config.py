"""
EcosystemPulse V2 Configuration
"""
import os
from pathlib import Path

# Paths
BASE_DIR = Path(__file__).parent.parent
DATA_DIR = BASE_DIR / "data"
OUTPUT_DIR = BASE_DIR / "output"
PAGES_DIR = OUTPUT_DIR / "pages"

# Site configuration
SITE_CONFIG = {
    "name": "EcosystemPulse",
    "description": "Real-time developer ecosystem data. Track package health, downloads, versions, and trends across npm and PyPI.",
    "url": os.environ.get("SITE_URL", "https://thanksforfish.github.io/EcosystemPulse").rstrip("/"),
    "tagline": "No fluff. Just data.",
}

# Package tracking configuration
TRACKED_ECOSYSTEMS = {
    "npm": {
        "packages": [
            "react", "vue", "angular", "svelte", "next", "nuxt",
            "express", "fastify", "hono",
            "typescript", "webpack", "vite", "esbuild", "rollup",
            "tailwindcss", "prisma", "drizzle-orm",
            "mongoose", "sequelize", "typeorm",
            "axios", "node-fetch", "got",
            "lodash", "date-fns", "dayjs",
            "zod", "joi", "yup",
            "vitest", "jest", "mocha",
            "eslint", "prettier",
        ],
    },
    "pypi": {
        "packages": [
            "django", "flask", "fastapi", "litestar",
            "uvicorn", "gunicorn",
            "pydantic", "marshmallow",
            "sqlalchemy", "peewee",
            "celery", "huey",
            "redis", "requests", "httpx",
            "pandas", "numpy", "polars",
            "scikit-learn", "torch", "tensorflow",
            "transformers", "langchain", "openai",
            "pillow", "opencv-python",
            "pytest", "black", "ruff",
            "mypy", "pyright",
        ],
    },
}

# Content generation
CONTENT_CONFIG = {
    "max_description_length": 160,
    "packages_per_listing_page": 50,
}
