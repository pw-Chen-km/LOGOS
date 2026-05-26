# LOGOS 2.0 Open-Source Checklist

Use this checklist before publishing LOGOS 2.0 or opening a release branch.

## Must Not Be Committed

- `.env` or provider credentials
- `runs/`, `logs/`, `artifacts/`, `paper_skills/`, `paper_library/`
- `graph_index.sqlite` or any local database file
- local `skills/` installs or downloaded paper content
- `__pycache__/`, `.pytest_cache/`, `.ruff_cache/`, `.mypy_cache/`

## Expected Public Surface

- `src/logos2/` contains the package source.
- `pyproject.toml` defines the `logos2` package and `logos2` CLI.
- `configs/logos2.yaml` is safe for offline/direct development.
- `configs/logos2.survey-agent.yaml` enables the full EvoScientist survey integration.
- `tests/fixtures/` and `examples/fixtures/` contain only small synthetic data.

## Integration Policy

- LOGOS core must import without EvoScientist installed.
- EvoScientist survey is a supported optional integration, enabled by config and optional dependencies.
- Tests that require real external services, API keys, or a live EvoScientist agent should be marked as integration tests.

## Release Smoke Checks

```bash
pip install -e .[dev]
pytest tests/
logos2 status
```
