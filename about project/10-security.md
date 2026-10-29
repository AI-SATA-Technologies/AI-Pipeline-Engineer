# 10 · Security

[← Back to index](README.md)

Face embeddings are **biometric data**. Treat this server like any system holding
personal data.

## Deployment checklist

- [ ] **`API_KEY` is set** (setup.bat generates a random one). Without it, anyone on the
      network can register faces, mark attendance and read the attendance log.
- [ ] The key is shared only with the LMS team, over a secure channel.
- [ ] **TLS:** the server speaks plain HTTP. Keep it on a trusted LAN, or put a reverse
      proxy with HTTPS in front (IIS, nginx, Caddy) — the API key and photos travel in
      every request.
- [ ] **Firewall:** only port 8000 is opened, and ideally only to the LMS server's IP:
      ```bat
      netsh advfirewall firewall add rule name="School Attendance API" dir=in action=allow protocol=TCP localport=8000 remoteip=<LMS-IP>
      ```
- [ ] **PostgreSQL** is not exposed to the network (or only to this server), uses a
      strong password, and the app uses its own DB user where possible.
- [ ] **`.env`** is readable only by the account running the server, never committed to
      git, never e-mailed.
- [ ] **Backups** are encrypted and access-controlled (they contain embeddings).
- [ ] `REVEAL_DUPLICATE_MATCH` stays `false` (otherwise a photo of anyone reveals their
      registration number).
- [ ] Students who leave are deleted (`DELETE /api/students/{reg}`).
- [ ] The camera's default password has been changed; the camera is on a separate VLAN
      if possible.

## What the system already does

| Protection | Detail |
|------------|--------|
| API key | Constant-time comparison; several keys allowed for rotation |
| Size limits | 10 MB per image, whole-request cap, max 40 MP decoded — blocks memory/CPU exhaustion and "decompression bomb" images |
| Concurrency cap | At most `INFERENCE_CONCURRENCY` face jobs at once |
| No photo storage | Images are processed in memory only |
| Privacy-safe errors | Duplicate-face replies don't name the other student |
| Model integrity | Model files checked against pinned SHA-256 hashes |
| Dependency audit | CI runs `pip-audit`; current pins have no known vulnerabilities |
| Secrets in logs | Camera credentials are masked; `/api/status` doesn't show the camera address |
| Container | Runs as a non-root user |
| Input validation | Settings validated at startup; registration numbers validated |

## Rotating the API key without downtime

1. Generate a new key:
   `venv\Scripts\python.exe -c "import secrets; print(secrets.token_urlsafe(32))"`
2. In `.env`: `API_KEY=<old-key>,<new-key>` → restart. Both work.
3. The LMS switches to the new key.
4. In `.env`: `API_KEY=<new-key>` → restart.

## Known gap: spoofing

There is **no liveness check yet**: a printed photo or a phone screen showing a
student's face can mark them present. Mitigations until anti-spoofing is added: place
the camera where staff can see it, review unusual patterns in `GET /api/attendance`.

## Reporting a problem

Report suspected vulnerabilities privately to the project maintainers rather than in a
public issue.
