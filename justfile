set shell := ["bash", "-eu", "-o", "pipefail", "-c"]
set dotenv-load := false

python := "uv run python"
pnpm := "pnpm"
cargo := "cargo"

default:
    @just --list

# Install language workspaces and Git hooks. LaTeX is detected, never skipped.
setup:
    @if command -v mise >/dev/null; then mise install; fi
    uv sync --all-packages --group dev
    pnpm install
    {{ cargo }} fetch
    lefthook install
    @echo "Checking LaTeX toolchain (not optional)..."
    @if ! command -v lualatex >/dev/null || ! command -v latexmk >/dev/null; then \
      echo "LaTeX is a first-class dependency and was not found."; \
      echo "Install TeX Live 2026 or MacTeX, then run: just doctor"; \
      exit 1; \
    fi
    @echo "setup complete"

# Language workspaces only. Used by CI jobs that install TeX separately.
setup-ci:
    uv sync --all-packages --group dev
    pnpm install
    {{ cargo }} fetch

doctor:
    {{ python }} scripts/doctor.py

dev: dev-web

dev-web:
    pnpm --filter @paper/web dev

dev-api:
    {{ python }} -m paper_api

dev-worker:
    {{ python }} -m paper_worker

fmt:
    uv run ruff format apps packages/python scripts
    pnpm exec biome check --write .
    {{ cargo }} fmt --all
    {{ python }} scripts/latex_check.py fmt
    @if command -v taplo >/dev/null; then taplo format; fi
    @if command -v shfmt >/dev/null; then shfmt -w scripts; fi

fmt-check:
    uv run ruff format --check apps packages/python scripts
    pnpm exec biome ci .
    {{ cargo }} fmt --all -- --check
    {{ python }} scripts/latex_check.py check
    @if command -v taplo >/dev/null; then taplo format --check; fi
    @if command -v shfmt >/dev/null; then shfmt -d scripts; fi

lint: lint-python lint-ts lint-rust lint-latex

lint-python:
    uv run ruff check apps packages/python scripts

lint-ts:
    pnpm exec biome lint .

lint-rust:
    {{ cargo }} clippy --workspace --all-targets --all-features -- -D warnings

lint-latex:
    {{ python }} scripts/latex_check.py check

typecheck: typecheck-python typecheck-ts

typecheck-python:
    uv run pyright

typecheck-ts:
    pnpm exec tsc --build

test: test-python test-ts test-rust

test-python:
    uv run pytest -m "not e2e and not slow" --cov --cov-report=term-missing

test-ts:
    pnpm exec vitest run

test-rust:
    {{ cargo }} test --workspace --all-features

test-unit:
    uv run pytest -m unit
    pnpm exec vitest run
    {{ cargo }} test --workspace --all-features --lib

test-integration:
    {{ python }} scripts/pytest_category.py integration uv run pytest -m integration

test-golden:
    {{ python }} scripts/pytest_category.py golden uv run pytest -m golden

test-e2e:
    pnpm exec playwright test

test-update-golden:
    @echo "Never update golden output merely to silence a failing test."
    @echo "Confirm the expected contract changed, then replace only the affected golden files."
    @echo "No golden updater is registered yet."
    {{ python }} scripts/pytest_category.py golden uv run pytest -m golden

latex: latex-smoke
    {{ python }} scripts/latex_run.py compile templates

latex-check:
    {{ python }} scripts/latex_check.py check

latex-smoke:
    {{ python }} scripts/latex_run.py compile smoke
    {{ python }} scripts/latex_run.py compile templates

latex-clean:
    {{ python }} scripts/latex_run.py clean smoke
    {{ python }} scripts/latex_run.py clean templates

generate:
    {{ python }} scripts/generate.py

generate-check:
    {{ python }} scripts/generate.py
    git diff --exit-code

schema:
    {{ python }} scripts/verify_schemas.py

docs-bilingual:
    {{ python }} scripts/verify_bilingual_docs.py

docs-fast: docs-bilingual
    {{ python }} scripts/verify_agent_notes.py
    {{ python }} scripts/verify_agent_skills.py
    @if command -v markdownlint-cli2 >/dev/null; then markdownlint-cli2; else pnpm exec markdownlint-cli2; fi

docs: docs-fast
    @if command -v typos >/dev/null; then typos; fi
    @if command -v vale >/dev/null; then vale README.en.md AGENTS.en.md CONTRIBUTING.md SECURITY.md CHANGELOG.md docs .agents; fi
    @if command -v lychee >/dev/null; then lychee --offline --no-progress README.md README.en.md AGENTS.md AGENTS.en.md docs .agents; else echo "lychee not installed; skipping live link check"; fi
    @if command -v yamllint >/dev/null; then yamllint -c .yamllint.yaml .; fi

security:
    @if command -v gitleaks >/dev/null; then gitleaks detect --no-git --source .; else echo "gitleaks not installed"; exit 1; fi
    {{ cargo }} deny check
    @if command -v zizmor >/dev/null; then zizmor .github/workflows; else echo "zizmor not on PATH; CI runs zizmor-action"; fi
    @if command -v actionlint >/dev/null; then actionlint; fi

check-fast: fmt-check lint typecheck test-unit schema docs-fast latex-check

check: fmt-check lint typecheck test test-golden test-integration latex-check latex-smoke schema docs

ci: check security generate-check
    @echo "ci complete"

clean:
    rm -rf .venv/.ruff_cache .ruff_cache .pytest_cache .mypy_cache htmlcov coverage.xml .coverage
    rm -rf apps/web/dist packages/typescript/*/dist
    {{ python }} scripts/latex_run.py clean smoke || true
    {{ python }} scripts/latex_run.py clean templates || true
    @echo "Refusing to delete lockfiles, fixture sources, tracked PDFs, or Cargo target automatically."
    @echo "Use 'cargo clean' only when you intend to drop the Rust build cache."
