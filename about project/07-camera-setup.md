# 7 · Camera Setup

[← Back to index](README.md)

There are two ways frames reach the system — use either or both:

| Way | How | Use for |
|-----|-----|---------|
| **Server reads the camera** | Set `CAMERA_URL` in `.env` | Normal operation (one camera per server) |
| **Clients post frames** | Any program POSTs images to `/api/camera/process-frame` | Extra cameras, the viewer, testing |

A student is recorded once per day no matter how many cameras see them.

## `CAMERA_URL` formats

| Value | Opens |
|-------|-------|
| *(empty)* | No camera worker |
| `0`, `1`, … | Local USB webcam with that index |
| `rtsp://USER:PASS@IP:554/PATH` | IP camera over RTSP (always over TCP — more reliable than UDP) |
| `C:\videos\test.mp4` | A video file, played at `CAMERA_FPS` and looped — handy for testing |

Related settings: `CAMERA_ID` (label stored with each event, e.g. `main-gate`) and
`CAMERA_FPS` (frames analysed per second, default 2).

## Hikvision cameras / NVRs

```
CAMERA_URL=rtsp://admin:YOUR_PASSWORD@192.168.18.234:554/Streaming/Channels/101
```

| Part | Value |
|------|-------|
| User / password | The camera's **local** account — usually `admin` and the password set when the camera was *activated*. **Not** your Hik-Connect / Hik-Partner app email and password (those are cloud accounts and RTSP rejects them) |
| Port | `554` (default RTSP port) |
| Main stream (full quality) | `/Streaming/Channels/101` |
| Sub stream (lower quality, faster) | `/Streaming/Channels/102` |
| NVR channel *N* | `/Streaming/Channels/N01` (main) or `/Streaming/Channels/N02` (sub) — e.g. channel 3 = `301` |

Check the login first in a browser: open `http://<camera-ip>` and sign in with the same
user and password. If the web login fails, RTSP will fail too.

> ⚠️ **Lockout:** Hikvision devices lock the account (often for ~30 minutes) after
> several wrong passwords. The camera worker protects you: after **5 failed
> connections** it waits **15 minutes** between attempts. If you're locked out, reboot
> the camera or wait, fix `.env`, then restart the server.

### Other brands

| Brand | Typical main-stream URL |
|-------|-------------------------|
| Dahua / Amcrest | `rtsp://admin:PASS@IP:554/cam/realmonitor?channel=1&subtype=0` |
| Reolink | `rtsp://admin:PASS@IP:554/h264Preview_01_main` |
| Generic ONVIF | Check the camera's manual or the ONVIF Device Manager tool |

### Special characters in the password or username

Write them as they are — the server percent-encodes them automatically (an email-style
username like `name@mail.com` or a password containing `@ ! : #` works). If you prefer
encoding them yourself (e.g. `@` → `%40`), the server leaves already-encoded values
alone.

Common mistakes the server also corrects: stray characters before `rtsp://` (e.g.
`0rtsp://…`).

## Camera placement tips

- Faces should be **at least ~64 pixels wide** in the image; heavy mode handles smaller
  faces better than lite.
- Mount at head height, facing the walking direction; avoid strong backlight (windows
  or doors behind students).
- Use the **main stream** for distance shots, the **sub stream** if the CPU is busy.

## Watching what the camera sees

```
school_attendance\scripts\viewer.bat
```

or `venv\Scripts\python.exe viewer.py [source]`. The viewer sends frames to the
running server and draws the boxes and names it returns (green = recognized, red =
unknown). Press **Q** to quit. Source order: command-line argument → `CAMERA_URL` →
webcam 0.

If the server already reads the same camera (`CAMERA_URL`), the viewer only adds a
display — attendance is still recorded once.

## Checking the camera worker

`scripts\status.bat` or `/api/status` → `camera`:

| `state` | Meaning |
|---------|---------|
| `running` | Receiving frames; `frames_processed` increases |
| `connecting` | Opening the stream |
| `reconnecting` | Couldn't open / stream dropped; see `last_error` and the server log |

The server log shows `camera main-gate: streaming from rtsp://***:***@…` (credentials
are always hidden in logs and never shown in `/api/status`).

## Testing without a camera

```env
CAMERA_URL=C:\videos\sample.mp4
```

Any video with faces works; registered students in it will be marked.
