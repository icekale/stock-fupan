# Daily Report Command Design

## Goal

Add a stable local command for generating a real daily close report with one line:

```bash
make report DATE=2026-05-26
```

The command is for the local MVP workflow. It must reuse the existing report pipeline and keep the generated HTML as the primary artifact.

## Architecture

Add a thin backend CLI module under `apps/api/app/cli/` that loads existing settings, builds the existing provider bundle, runs `ReportGenerator.generate_close_report()`, and prints paths plus provider diagnostics. The CLI must not duplicate market/news/report logic and must not print API keys.

Add a root `Makefile` target that calls the CLI from `apps/api` with `PYTHONPATH=.` and the project virtualenv Python when available. The default command reads `.env`/environment configuration exactly like the API.

## Behavior

- Required input: `--date YYYY-MM-DD`, exposed as `make report DATE=YYYY-MM-DD`.
- Optional input: `--reports-root PATH`, for temporary or custom output roots.
- Successful output includes `report.html`, `snapshot.json`, validation status, and provider status summary.
- Invalid report validation exits non-zero.
- Provider fallback or fake status is shown clearly, but does not fail the command by default because local development may intentionally allow fallback.
- No production fake override is added; existing `APP_ENV=production` validation still protects production-grade reports.

## Testing

Add CLI tests that monkeypatch provider creation and PNG export so behavior is deterministic and fast. Verify that the command writes a report, returns exit code 0 for valid reports, and returns non-zero when validation fails.
