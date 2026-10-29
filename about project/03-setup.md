# 3 · Setup Guide

[← Back to index](README.md)

There are two ways to install: the **one-click `setup.bat`** (recommended on Windows) or
the **manual steps**. Both end in the same place.

---

## Before you start

1. **Install Python 3.13 (64-bit)** from <https://www.python.org/downloads/windows/>.
   In the first installer screen tick **"Add python.exe to PATH"**.
   (Or in a terminal: `winget install -e --id Python.Python.3.13`.)
2. **Install PostgreSQL** from <https://www.postgresql.org/download/windows/> and
   remember the password you set for the `postgres` user. Skip this if the database
   runs on another server — you'll just need its address and a login.
3. **Copy the project folder** onto the PC, ideally to a short path such as
   `C:\Attendance` (long paths can break the install — see
   [Requirements](02-requirements.md#path-length-windows)). Don't copy the `venv` folder
   from another PC; setup creates a fresh one.

---

## Option A — One-click setup (`setup.bat`)

Double-click:

```
school_attendance\scripts\setup.bat
```

It runs seven steps and explains each one on screen:

| Step | What it does | If it's already done |
|------|--------------|----------------------|
| 1 · Python | Finds a 64-bit Python 3.11–3.14 (prefers python.org over the Store version); checks the folder path isn't too long | — |
| 2 · Virtual environment | Creates `school_attendance\venv` | Reuses it; recreates it if it was copied from another PC and doesn't work |
| 3 · Packages | Installs `requirements.txt` into the venv (a few minutes the first time) | Quick check, nothing re-downloaded |
| 4 · `.env` | Creates `.env` from `.env.example` with a random **API key**, then opens it in **Notepad** for you to fill in (see below). Then validates it | Keeps your `.env` untouched |
| 5 · Models | Downloads and SHA-256-verifies the face models (~300 MB) | Verifies the existing files |
| 6 · Database | Creates the database if missing and creates/updates the tables | Just checks the tables are up to date |
| 7 · Self-check | Loads the face models once to prove everything works | — |

Then it offers to put **Start / Stop / Status / Viewer shortcuts** on the desktop, and
prints how to start the server.

### What to fill in when Notepad opens

| Setting | Example | Required? |
|---------|---------|-----------|
| `DB_USER`, `DB_PASS` | `postgres` / your password | Yes |
| `DB_HOST` | `localhost` or the DB server's IP | If the DB is on another PC |
| `LMS_API_URL` | `https://lms.school.edu/api/attendance` | To send attendance to the LMS |
| `ATTENDANCE_TZ` | `Asia/Karachi` | Recommended (defines "today") |
| `CAMERA_URL` | `rtsp://admin:PASSWORD@192.168.18.234:554/Streaming/Channels/101` | If the server should read a camera |
| `API_KEY` | *(already generated)* | Give this value to the LMS team |

Save, **close Notepad**, and setup continues. All settings: [Configuration](05-configuration.md).

### Options

```bat
scripts\setup.bat --dev        :: also install test tools and run the test suite
scripts\setup.bat --no-prompt  :: unattended: no Notepad, no questions
```

### Running it again

`setup.bat` is safe to re-run at any time — after fixing a problem, after changing
`.env`, after copying in a new version of the code, or after moving the folder.

### If it stops with an error

| Message | Fix |
|---------|-----|
| `no 64-bit Python 3.11 - 3.14 found` | Install Python from python.org (tick *Add to PATH*) |
| `the project folder path is N characters long` | Move the project to e.g. `C:\Attendance`, or enable Windows long paths (command shown on screen) |
| `creating the virtual environment failed` | Usually the Microsoft Store Python — install the python.org one |
| `installing packages failed` | Check internet / proxy; re-run |
| `.env is invalid` | The message names the wrong setting; fix it in `.env` and re-run |
| `SETUP FINISHED WITH A WARNING` (database) | Start PostgreSQL, check `DB_USER`/`DB_PASS`, re-run |

More in [Troubleshooting](09-troubleshooting.md).

---

## Option B — Manual setup

Run these in a terminal (PowerShell or Command Prompt) inside `school_attendance`:

```powershell
# 1. virtual environment + packages
python -m venv venv
venv\Scripts\python.exe -m pip install --upgrade pip
venv\Scripts\python.exe -m pip install -r requirements.txt

# 2. settings
copy .env.example .env
notepad .env                       # fill in DB_USER, DB_PASS, LMS_API_URL, ...

# 3. face models (~300 MB, verified)
venv\Scripts\python.exe download_models.py

# 4. database (creates the database; tables are created when the server starts)
psql -U postgres -f schema.sql
```

Generate a strong `API_KEY` with:

```powershell
venv\Scripts\python.exe -c "import secrets; print(secrets.token_urlsafe(32))"
```

---

## After setup

### Start the server

```
school_attendance\scripts\start.bat
```

or `venv\Scripts\uvicorn main:app --host 0.0.0.0 --port 8000` (always **one** worker).
You should see lines like:

```
INFO attendance: HEAVY pipeline ready (w600k_r50)
INFO attendance: schema up to date (001_init.sql, 002_attendance.sql)
INFO attendance: 2026-10-24: 5 registered, 5 pending, 0 already marked
INFO:     Uvicorn running on http://0.0.0.0:8000
```

### Check it

- `scripts\status.bat`, or open <http://localhost:8000/api/status> — look for
  `"ready": true` and `"db_ok": true`.
- Interactive API docs: <http://localhost:8000/docs>.

### Let other PCs reach it

So the LMS server can call the API, open port 8000 once — in a terminal started with
**Run as administrator**:

```bat
netsh advfirewall firewall add rule name="School Attendance API" dir=in action=allow protocol=TCP localport=8000
```

Find this PC's address with `ipconfig` (IPv4 address); the LMS uses
`http://<that-ip>:8000`.

### Hand over to the LMS team

Give them: the server URL, the `API_KEY` value from `.env`, and the
[API reference](06-api-reference.md).

---

## Moving to another PC / updating

| Task | How |
|------|-----|
| Move to a new PC | Copy the folder **without** `venv`; copy `.env` across if you want the same settings; run `setup.bat` |
| Keep the data | The data is in PostgreSQL — back it up / restore it ([Operations](08-operations.md#backups)), or point `DB_HOST` at the same DB server |
| Update to a new version | Stop the server, replace the code (keep `.env`), run `setup.bat`, start again. Database changes are applied automatically at startup |
