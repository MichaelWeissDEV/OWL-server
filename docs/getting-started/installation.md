# Installation

## Docker (recommended)

You need Docker with Compose v2. The database runs on an internal network and is never published.

```console
$ git clone https://github.com/MichaelWeissDEV/OWL-server.git && cd OWL-server
$ cp .env.example .env        # set POSTGRES_PASSWORD (see the comments in the file)
$ docker compose up -d --build
$ curl http://127.0.0.1:8765/api/v1/ready
```

Add the web dashboard with the `dashboard` profile (served on <http://127.0.0.1:8080>):

```console
$ docker compose --profile dashboard up -d --build
```

The API container runs as a non-root user with a read-only file system and all capabilities dropped.
Details and the production checklist: {doc}`/operations/deployment`.

## From source

Python 3.13+ and PostgreSQL (or SQLite for tests). OWL Server uses the OWL core package for the data
model, hashing and validation; during development it is taken from the sibling checkout.

```console
$ git clone https://github.com/MichaelWeissDEV/OWL.git
$ git clone https://github.com/MichaelWeissDEV/OWL-server.git
$ cd OWL-server && uv sync
$ OWL_SERVER_DATABASE_URL=sqlite:///owl.db uv run owl-server serve
```

```{note}
OWL Server is not on PyPI. Install it from source or use the Docker image built from this repository.
```
