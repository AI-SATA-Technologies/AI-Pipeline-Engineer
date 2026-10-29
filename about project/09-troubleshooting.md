# 9 · Troubleshooting

[← Back to index](README.md)

## First checks

1. `scripts\status.bat` (or <http://localhost:8000/api/status>) — is it `ready`, `db_ok`?
2. Read the server window / log — errors and warnings name the problem.
3. Re-run `scripts\setup.bat` — it re-checks Python, packages, `.env`, models and the
   database and explains anything wrong.

## Setup problems

| Symptom | Cause | Fix |
|---------|-------|-----|
| `no 64-bit Python 3.11 - 3.14 found` | Python missing, 32-bit, or not on PATH | Install 64-bit Python 3.13 from python.org with *Add to PATH* |
| `creating the virtual environment failed` | Microsoft Store Python (sandboxed) | Install the python.org version, re-run setup |
| `project folder path is N characters long` / `filename or extension is too long` | Windows 260-character path limit | Move the project to `C:\Attendance`, or enable long paths (command shown by setup) |
| `installing packages failed` | No internet / proxy | Fix network; behind a proxy set `set HTTPS_PROXY=http://proxy:port` before running setup |
| `checksum mismatch` (models) | Corrupted / tampered download | Re-run setup; it deletes bad files and downloads again |
| Venv copied from another PC doesn't work | venvs are tied to one PC and folder | setup.bat detects and recreates it |

## Startup problems

| Symptom | Cause | Fix |
|---------|-------|-----|
| `Invalid configuration (.env)` | A setting has a wrong value | The message names it (e.g. `MODE` must be `lite` or `heavy`) |
| `Model not found at …` | Models not downloaded / wrong `MODEL_DIR` | `venv\Scripts\python.exe download_models.py` |
| `ready: false`, endpoints return `503` | PostgreSQL not reachable | Start the PostgreSQL service (`services.msc`), check `DB_*`. The server retries every 10 s |
| `password authentication failed` | Wrong `DB_USER` / `DB_PASS` | Fix `.env`, restart |
| `[Errno 10048] … address already in use` | Something already uses port 8000 | `scripts\restart.bat` (frees the port), or `stop.bat` first |
| `API_KEY is not set` warning | The API is open | Set `API_KEY` in `.env` |

## Recognition problems

| Symptom | Cause | Fix |
|---------|-------|-----|
| Registered student shows `unknown` | Poor light/angle, face too small, threshold too strict | Better lighting and camera position; try heavy mode; lower `SIMILARITY_THRESHOLD` slightly (e.g. 0.35) |
| Wrong person recognized | Threshold too loose | Raise `SIMILARITY_THRESHOLD` (e.g. 0.45–0.5) |
| Everyone `unknown` after a change | `MODE` changed | `/api/status` → `ignored_other_model`; re-register, or switch `MODE` back |
| `already_marked` | Seen earlier today | Expected — once per student per day |
| `error` status | Database write failed | Check DB; the student is marked on a later frame automatically |
| Slow / lagging | Heavy mode on a slow CPU with many faces | Use `MODE=lite`, lower `CAMERA_FPS`, use the camera sub-stream, or add a GPU |

## Registration problems

| Message | Fix |
|---------|-----|
| `Only N photo(s) had a detectable face` | Clear, well-lit photos; one face filling much of the frame; looking at the camera |
| `… consistently show the same person` | Make sure all 15 photos are of the same student (no group photos) |
| `already registered` | Delete the student first if you want to re-register |
| `face is already registered under another registration_number` | The person already has a number — check for a duplicate in the LMS |
| `413` | A photo is over 10 MB — resize it |

## Camera problems

| Symptom | Cause | Fix |
|---------|-------|-----|
| `camera …: cannot open` | Wrong URL/path, wrong login, camera offline | See [Camera setup](07-camera-setup.md); test the login at `http://<camera-ip>` |
| Hikvision rejects the login | Using the Hik-Connect app email/password | Use the camera's **local** `admin` account |
| Worked, then stopped accepting the login | Camera locked the account after failed attempts | Wait ~30 min or reboot the camera; the worker already slows to one try per 15 min |
| `404` / no stream | Wrong path | Hikvision: `/Streaming/Channels/101` |
| Picture lags behind | Not an issue in the server (it drops old frames); in the viewer, lower resolution or use the sub-stream | — |

Quick connectivity test from the server PC (PowerShell):

```powershell
Test-NetConnection 192.168.18.234 -Port 554
```

`TcpTestSucceeded : True` means the network path is fine — the problem is the URL or login.

## LMS problems

| Symptom | Cause | Fix |
|---------|-------|-----|
| LMS receives nothing | `LMS_API_URL` empty → events are `skipped` | Set `LMS_API_URL`, restart |
| `lms_status: pending` with `lms_last_error` | LMS down / returning errors / wrong URL / token | Fix the LMS side; delivery resumes automatically |
| `lms_status: failed` | 10 attempts failed | Fix, then re-queue ([Operations](08-operations.md#lms-delivery-problems)) |
| LMS gets `401` from us? | — | The LMS calling *us* must send `X-API-Key` |

## Getting more detail

```powershell
# what the server sees right now
Invoke-RestMethod http://localhost:8000/api/status | ConvertTo-Json -Depth 4

# today's attendance and delivery status
Invoke-RestMethod http://localhost:8000/api/attendance -Headers @{ 'X-API-Key' = '<key>' } | ConvertTo-Json -Depth 4
```
