"""Repository hygiene checks; no client database or secret-file reads."""
from pathlib import Path
import subprocess

import pytest

ROOT = Path(__file__).resolve().parents[2]

IGNORED = [
    ".env", ".env.local", ".env.production", "backend/.env", "frontend/.env.local",
    "backend/production.env", ".envrc", ".direnv/cache", ".npmrc", ".pypirc", ".netrc",
    "secrets/session-secret", "credentials.json", "service-account-production.json",
    ".aws/credentials", ".ssh/id_ed25519", "certificates/server.key", "certificates/private.pem",
    "certificates/key.p12", "certificates/key.pfx", "certificates/key.p8", "certificates/key.jks",
    "backend/.venv/bin/python", "venv/bin/python", "__pycache__/module.pyc", "backend/.pytest_cache/results",
    "frontend/node_modules/package/index.js", "frontend/.next/cache/file", "frontend/out/index.html",
    "dist/bundle.js", "build/output", "frontend/tsconfig.tsbuildinfo", "coverage/report.json",
    "frontend/playwright-report/index.html", "frontend/test-results/screenshot.png", "blob-report/report.zip",
    "backend/.coverage.local", "frontend/.eslintcache", "debug.log", ".DS_Store", "file.py.swp",
    "backend/storage/invoices/invoice.pdf", "storage/invoices/invoice.pdf", "output/pdf/demo.pdf",
    "tmp/pdfs/preview.png", "temp/debug.txt", "local.txt", "backups/billing.sql", "exports/customers.csv",
    "billing.dump", "billing.sql.gz", "billing.sqlite3", "billing.sqlite3-wal", "billing.db-shm", "dump.rdb",
]

TRACKABLE = [
    ".gitignore", ".env.example", "backend/.env.example", "frontend/.env.example",
    "AGENTS.md", "README.md", "docs/PROJECT_STATUS.md", ".github/workflows/ci.yml",
    "docker-compose.yml", "docker-compose.prod.yml", "backend/Dockerfile.prod", "frontend/Dockerfile.prod",
    "backend/requirements.txt", "backend/requirements.lock", "frontend/package.json", "frontend/package-lock.json",
    "backend/alembic/versions/20261007_0024_seller_secondary_email.py",
    "backend/alembic/versions/source.sql", "backend/app/core/security.py", "frontend/app/lib/auth.ts",
    "backend/app/services/invoice_pdf.py", "backend/app/templates/invoice/v1/invoice.html",
    "backend/app/templates/invoice/v1/invoice.css", "backend/app/templates/invoice/v1/pb-logo.png",
    "backend/app/templates/invoice/v1/pb-logo-trimmed.png", "backend/tests/fixtures/reference.pdf",
    "frontend/public/logo.png", "frontend/next-env.d.ts", "backend/tests/test_gitignore.py",
]


def ignored_paths(paths):
    result = subprocess.run(
        ["git", "-c", "core.excludesFile=/dev/null", "check-ignore", "--no-index", "--stdin", "-z"],
        input="\0".join(paths) + "\0", text=True, capture_output=True, cwd=ROOT,
    )
    assert result.returncode in (0, 1), result.stderr
    return set(result.stdout.rstrip("\0").split("\0")) - {""}


@pytest.mark.parametrize("path", IGNORED)
def test_private_and_generated_paths_are_ignored(path):
    assert path in ignored_paths([path]), f"Private/generated path can be accidentally added: {path}"


def test_required_source_templates_and_lockfiles_remain_trackable():
    assert not ignored_paths(TRACKABLE)
