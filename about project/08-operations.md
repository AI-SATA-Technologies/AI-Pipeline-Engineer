# 8 · Operations (day-to-day running)

[← Back to index](README.md)

## Scripts (`school_attendance\scripts\`)

| Script | Does |
|--------|------|
| `setup.bat` | Install / repair / update the installation (safe to re-run) |
| `start.bat` | Start the server on port 8000 (window stays open; close it or press Ctrl+C to stop) |
| `stop.bat` | Stop the server and the viewer |
| `restart.bat` | Free port 8000, then start again |
| `status.bat` | Show readiness, counts, LMS backlog, camera state and the LAN address |
| `viewer.bat` | Open the live camera view |

## A normal day

Nothing to do. The server:

- rebuilds the pending list at midnight (`ATTENDANCE_TZ`) — everyone can be marked again;
- records each student once per day;
- keeps retrying LMS delivery in the background.

Check `status.bat` occasionally: `ready: True`, `lms_pending` near 0, camera `running`.

## Start automatically when the PC starts

**Task Scheduler** (simplest) — in a terminal opened *as Administrator*:

```bat
schtasks /create /tn "School Attendance API" /sc onlogon /rl highest ^
  /tr "\"C:\Attendance\school_attendance\scripts\start.bat\""
```

(Adjust the path. Remove with `schtasks /delete /tn "School Attendance API" /f`.)

For a true Windows service that runs without anyone logged in, wrap the same command
with a service manager such as [NSSM](https://nssm.cc/). Always run **one** server
process — never several workers or copies on the same database.

## Logs

The server prints its log to the console window. To keep a log file instead:

```bat
cd C:\Attendance\school_attendance
venv\Scripts\uvicorn main:app --host 0.0.0.0 --port 8000 >> server.log 2>&1
```

Useful lines to look for:

| Log line | Meaning |
|----------|---------|
| `… N registered, N pending, N already marked` | Students loaded (startup / new day) |
| `attendance: 2026-CS-001 via main-gate (score 0.63)` | A student was marked |
| `LMS notified: 2026-CS-001` | Delivered to the LMS |
| `LMS delivery failed … retry in 10s` | LMS problem — will retry |
| `camera main-gate: cannot open …` | Camera URL / login / network problem |
| `API_KEY is not set` | The API is open — set `API_KEY` |

## Managing students

| Task | How |
|------|-----|
| Register | The LMS calls `POST /api/register/lms` |
| Remove (left school, erasure request) | `DELETE /api/students/{registration_number}` |
| Re-register (new photos) | Delete, then register again |
| See who was marked today | `GET /api/attendance` |

## LMS delivery problems

`GET /api/attendance` shows each event's `lms_status`, `lms_attempts` and
`lms_last_error`. Events that failed 10 times are `failed` and are not retried.
After fixing the LMS (or `LMS_API_URL`), queue them again — in `psql`:

```sql
UPDATE attendance_events
SET lms_status = 'pending', lms_attempts = 0, next_attempt_at = NOW()
WHERE lms_status = 'failed';
```

They are delivered within about 30 seconds (no restart needed).

## Backups

All data is in PostgreSQL. Back up daily, e.g. with a Task Scheduler job running this
PowerShell (adjust the PostgreSQL version folder and the backup folder):

```powershell
$env:PGPASSWORD = '<db password>'
& "C:\Program Files\PostgreSQL\17\bin\pg_dump.exe" -U postgres -Fc `
  -f "D:\backups\attendance_$(Get-Date -Format yyyy-MM-dd).dump" school_attendance
```

Restore onto a new server:

```bat
createdb -U postgres school_attendance
pg_restore -U postgres -d school_attendance attendance_20261024.dump
```

The backup contains **biometric data** (face embeddings) — store it encrypted and with
restricted access.

## Changing `MODE` (lite ↔ heavy)

Embeddings from the two modes are incompatible:

1. Set `MODE` in `.env` and restart.
2. `/api/status` → `registered_total` drops and `ignored_other_model` shows how many
   students must re-register.
3. Re-register them (delete + register).

## Updating to a new version

1. `scripts\stop.bat`
2. Replace the code (keep `.env`; don't copy `venv` from elsewhere).
3. `scripts\setup.bat` — installs new packages, verifies models and database.
4. `scripts\start.bat` — database changes in `migrations/` are applied automatically.

## Testing: clearing today's attendance

To re-run a test the same day (this deletes today's records!):

```sql
DELETE FROM attendance_events WHERE attendance_date = CURRENT_DATE;
```

then `POST /api/cache/reload`.
