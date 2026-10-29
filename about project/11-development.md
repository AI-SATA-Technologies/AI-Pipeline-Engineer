# 11 · Development

[← Back to index](README.md)

## Set up a development copy

```bat
school_attendance\scripts\setup.bat --dev
```

This installs `requirements-dev.txt` (pytest, ruff, pip-audit) and runs the tests.

## Everyday commands (inside `school_attendance`)

```bat
venv\Scripts\python.exe -m pytest              :: all tests (~5 s; no DB or models needed)
venv\Scripts\python.exe -m pytest -k register  :: only tests matching a name
venv\Scripts\ruff check .                      :: lint
venv\Scripts\ruff check . --fix                :: lint + auto-fix
venv\Scripts\pip-audit -r requirements.txt     :: known vulnerabilities in dependencies
venv\Scripts\uvicorn main:app --reload         :: dev server, restarts on code changes
```

The same lint + tests + audit run on GitHub for every push and pull request
(`.github/workflows/ci.yml`, Python 3.11 and 3.13).

## How the code fits together

| Layer | File(s) | Rule of thumb |
|-------|---------|---------------|
| HTTP | `main.py` | Thin: parse the request, call the service, map errors to status codes |
| Business logic | `attendance.py` | Registration rules, recognition → recording, day handling |
| Background work | `camera_worker.py`, `lms.py` | Camera thread; async LMS outbox |
| Data | `database.py` | All SQL; DB errors become `StorageError` (→ HTTP 503) |
| Face AI | `pipeline/` | No business rules; `engine.Pipeline` is the only entry point |
| Settings | `config.py` | Every setting is declared and validated here |

Important conventions:

- **Import `config` before `cv2`.** OpenCV reads its safety limits
  (`OPENCV_IO_MAX_IMAGE_PIXELS`, RTSP over TCP) from the environment when it loads.
  `pipeline/__init__.py`, `main.py`, `camera_worker.py` and `viewer.py` all import
  `config` first.
- **One process only.** The pending list, outbox and camera live in memory; never run
  multiple uvicorn workers.
- Blocking work (DB queries, model inference) in async endpoints goes through
  `asyncio.to_thread`.

## Tests

Tests use fakes so they run anywhere (CI has no PostgreSQL or models):

- `tests/fakes.py` → `FakeDB` (in-memory replacement for the `database` query
  functions) and `FakePipeline` (a fake "image" is JSON listing face ids; id *i* becomes
  a unit vector).
- `tests/conftest.py` pins environment variables so your own `.env` (camera, API key,
  LMS URL) never affects test runs.
- API tests reload `main` with the fakes and use FastAPI's `TestClient`.

When fixing a bug, add a test that fails without the fix.

## Adding a setting

1. Add the field (with type, default and limits) to `Settings` in `config.py`.
2. Export it as a module-level name at the bottom of `config.py`.
3. Add it, with a comment, to `.env.example` (blank = default).
4. Document it in `about project/05-configuration.md` and the root README.

`tests/test_hardening.py::test_env_example_is_a_valid_config` makes sure
`.env.example` always starts the server.

## Changing the database

Never edit an existing migration. Add a new file, e.g. `migrations/003_something.sql`,
written to be **safe to run repeatedly** (`CREATE TABLE IF NOT EXISTS`,
`ADD COLUMN IF NOT EXISTS`, …). All files run in name order at every startup
(`AUTO_MIGRATE=true`).

## Updating dependencies

1. Check the latest versions (`pip index versions <package>`), update the pins in
   `requirements.txt` / `requirements-dev.txt`.
2. `venv\Scripts\python.exe -m pip install -r requirements-dev.txt`
3. Run the tests and `pip-audit`.
4. Keep OpenCV on 4.x until OpenCV 5 has been tested.

## Git workflow

- Branches: `feature/<short-name>`, `fix/<short-name>`; open a pull request against
  `main`. CI must pass.
- Never commit `.env`, `venv/`, model files, or photos.
- `.bat` files must keep Windows (CRLF) line endings — enforced by `.gitattributes`.
