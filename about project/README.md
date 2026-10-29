# About the Project — Documentation

Everything you need to understand, install, run and maintain the **School Face
Attendance API**. Start with the overview, then follow the setup guide.

| # | Document | Read it when you want to… |
|---|----------|---------------------------|
| 1 | [Overview](01-overview.md) | understand what the system does and how it works |
| 2 | [Requirements](02-requirements.md) | know what hardware, software and network access a PC needs |
| 3 | [Setup guide](03-setup.md) | install it on a new PC (one-click `setup.bat`, or by hand) |
| 4 | [Folder structure](04-folder-structure.md) | find your way around the code and files |
| 5 | [Configuration](05-configuration.md) | understand every setting in `.env` |
| 6 | [API reference](06-api-reference.md) | integrate the LMS or call the API yourself |
| 7 | [Camera setup](07-camera-setup.md) | connect an IP camera (RTSP / Hikvision) or a webcam |
| 8 | [Operations](08-operations.md) | run it day to day: start/stop, monitoring, backups, maintenance |
| 9 | [Troubleshooting](09-troubleshooting.md) | fix an error or something that isn't working |
| 10 | [Security](10-security.md) | deploy it safely (checklist) |
| 11 | [Development](11-development.md) | change the code, run tests, release |

## Quick start (new PC)

1. Install **Python 3.13** (python.org, tick *Add python.exe to PATH*) and **PostgreSQL**.
2. Copy the project folder to the PC — ideally a short path such as `C:\Attendance`.
3. Double-click **`school_attendance\scripts\setup.bat`** and follow the prompts.
4. Start the server with **`school_attendance\scripts\start.bat`**, then open
   <http://localhost:8000/docs>.

Details: [Setup guide](03-setup.md).

## One-paragraph summary

A headless (no UI) FastAPI service that plugs into the school's **LMS**. The LMS
registers each student once with 15 photos; the service stores only a 512-number face
"fingerprint" (embedding). It then watches an IP camera (or accepts frames from
clients), recognizes students, records each one **once per day**, and reliably reports
`{registration_number, detected_at}` to the LMS — retrying until the LMS accepts it.
Face detection and recognition run locally on the CPU with ONNX models; data lives in
PostgreSQL.
