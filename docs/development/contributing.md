# Contributing

Bug reports and pull requests are welcome. For larger changes please open an issue first.

```console
$ uv sync
$ uv run ruff check . && uv run ruff format --check . && uv run mypy src && uv run pytest
$ cd dashboard && npm ci && npm run lint && npm test
```

Rules of thumb: keep secure behaviour as the default, give every weakening switch a long
`ALLOW_INSECURE_…` name, add tests with each change and update the documentation in `docs/`.

Build the documentation locally:

```console
$ uv sync --group docs
$ uv run sphinx-build -W --keep-going -b html docs docs/_build/html
```
