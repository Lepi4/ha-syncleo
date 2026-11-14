# Contributing

This is the Lepi4 fork of [DeKaN/ha-syncleo](https://github.com/DeKaN/ha-syncleo).
Keep upstream attribution and the MIT license, including the vendored pysyncleo notice.
Report fork problems at <https://github.com/Lepi4/ha-syncleo/issues>.
Redact device tokens, share URLs, keys, MAC addresses and private network details from logs.

## Checks

Use Python 3.14.2 or newer and [uv](https://docs.astral.sh/uv/):

```sh
uv sync --locked
uv run ruff check
uv run ruff format --check
uv run mypy custom_components/syncleo/ --check-untyped-defs
uv run python -m unittest discover -s tests -v
uv run python scripts/build_release.py --version 0.7.1
```

Tests use synthetic keys and fake UDP traffic; no devices are contacted.
Hassfest and HACS validation also run in GitHub Actions.

## Release

1. Update `custom_components/syncleo/manifest.json` and `pyproject.toml` to the same version.
2. Run `uv lock` and commit `uv.lock` with the change.
3. Add `docs/releases/<version>.md` and update `CHANGELOG.md`.
4. Run the checks above and wait for Lint and Validate on `main` to pass.
5. Tag that tested commit as `v<version>` and push the tag.

The Release workflow repeats the checks, creates `dist/syncleo.zip` with integration
files at its root, includes both license notices and publishes the release only
after its ZIP and `SHA256SUMS` have been attached. It rejects a tag/version mismatch.
Never retag a published release; fix a failed release with a new version as needed.

To retry before any release was created, dispatch the Release workflow with the
existing tag. If a draft already exists, inspect it before changing or publishing it.
