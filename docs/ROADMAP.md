# Roadmap

**English** · [Русский](ROADMAP.ru.md)

Nestrack is a production tracking system for sheet-metal shops: a server
with a database, a client at the operator's workstation, a web page for the
shift supervisor, directory and ERP integration.

It grew out of [finnpower-counter](https://github.com/malinkin-s/finnpower-counter), a standalone utility built for a
Prima Power / Finn-Power punching machine with the NCeXpress FMS
postprocessor. finnpower-counter stays a separate project and keeps its own
roadmap — including more data from the machine files (material, time,
weight, order), which Nestrack picks up through the shared parser.

Architecture in [ARCHITECTURE.md](ARCHITECTURE.md); integrations in
[INTEGRATIONS.md](INTEGRATIONS.md); test benches in
[TEST_BENCH.md](TEST_BENCH.md); task breakdown in [TASKS.md](TASKS.md);
findings in [FINDINGS.md](FINDINGS.md).

Status: **planned, not implemented.**

The project is open source and not tied to a particular shop. Everything
site-specific — shifts, operators, retention, directory, ERP — is configured
by the administrator.

---


## Scope

| # | Feature | Where | Stage |
|---|---|---|---|
| 1 | Save a session: user-given name plus save date and time | client + server | 5 |
| 2 | Production log: sheets, programs, parts, operator name | server | 3 |
| 3 | Operator identifies at start-up: name from a list plus PIN | client | 2 |
| 4 | Secure sign-in and user registration | server | 1, 2 |
| 5 | Data stored where the administrator decides | server | 1 |
| 6 | Roles: operator in the client, supervisor and admin in a browser | client + server | 1, 2 |
| 7 | Supervisor views production and writes nothing | web | 4 |
| 8 | Production export to CSV | web | 4 |
| 9 | Clients work concurrently, changes show up immediately | server + client | 3, 4 |
| 10 | Administrator settings: shifts, time format, retention, visibility | server | 1 |
| 11 | Sign-in with Active Directory accounts, roles from groups | server | 7 |
| 12 | Integration hub: pluggable, configurable ERP connectors (SyteLine, 1C, webhook, files) and an API for ERPs to read from | server | 8 |

## Decisions

- **Client and server**, not a shared network folder. The shared folder is
  the fallback if a server turns out to be impossible.
- **Server: Linux in Docker** as the primary platform, OS-agnostic code,
  tests on Windows too.
- **Supervisor and administrator use a browser**; only the operator runs the
  client.
- **Operator sign-in: name from a list plus PIN**, only from a registered
  workstation; the server limits attempts.
- **Protection**: TLS in transit, the server sets the author and time of each
  event, server disk encrypted by the OS, client-local files protected with
  DPAPI.
- **Offline, the client keeps working** and sends queued marks later.
- **A session is a named bookmark**; the production log is the single source
  of truth about marks.
- **Standalone use stays with finnpower-counter**, which remains a separate
  project; Nestrack depends on its file parsing.
- **Site-specific settings belong to the administrator**: shift boundaries,
  time format, operators per workstation, retention, visibility.
- **Integrations are plugins** configured in the admin panel, never
  hard-wired; mapping between our data and the ERP's is data, not code.

## Stage 0. Checks and client groundwork

Nothing visible changes.

- On a shop-floor Windows 7 32-bit PC, in a PyInstaller build, check: HTTPS
  to a test server (`http.client` + `ssl`, TLS 1.2, self-signed certificate
  pinned by fingerprint), reading an SSE stream, DPAPI via ctypes. **If any
  of it fails, the client architecture is revisited before anything else.**
- Client skeleton on top of finnpower-counter's parser, installed as a
  pinned package.
- Background executor: all I/O off the main thread.
- Client build with the network modules included.

## Stage 1. Server skeleton

- FastAPI, SQLite, migrations; `docker compose up` brings everything up on a
  VM.
- Users and roles, password sign-in to the web panel, first-run setup (the
  first administrator).
- Workstations: creation, one-time registration code.
- Audit log of sign-ins and administrator actions.
- System settings: shift boundaries, time format, retention, visibility.
- CI: server tests on Linux and Windows.

## Stage 2. The client connects

- Client setup: server address and workstation registration code.
- Sign-in window: name from a list plus PIN. Offline sign-in for those who
  have signed in on this PC before.
- The operator window — the same views as finnpower-counter, with the
  signed-in name and a connection indicator.

## Stage 3. Production log

- Every mark and unmark is an event on the server; the server sets the author
  and receive time.
- Outbox for connection drops, resending without duplicates.
- Content-based task ID; marks are restored when the task is opened on any
  workstation.
- Event stream: a mark on one workstation shows up on the others at once.

## Stage 4. Supervisor page

- Production per operator, day, shift, task: sheets, programs, positions,
  pieces.
- Live updates without clicking.
- CSV export (`;`, UTF-8 with BOM — like finnpower-counter's positions export).

## Stage 5. Sessions

- "Save session" in the client: the user types a name, the save date and time
  are added; stored on the server.
- Session list: open and continue; compare with the moment of saving.

## Stage 6. Operations

- PIN reset, blocking and unblocking users and workstations.
- Scheduled backups and restore checks.
- Server installation guide for IT; running as a Windows service.
- Client notification about a new version.
- Data retention job.

## Stage 7. Directory

- Supervisor and administrator sign-in with Active Directory accounts
  (LDAPS); roles from domain groups.
- Operators may be linked to domain accounts; sign-in at the machine stays
  name + PIN.
- Optional browser single sign-on (Kerberos).

## Stage 8. Integration hub

- Connector plugins configured in the admin panel: connection profiles,
  secrets, test button, routing of event types.
- Integration outbox: retries, idempotency, dead letters, delivery log.
- Mapping tables: parts to items, tasks to jobs, operators to employees.
- Integration API: tokens, event feed by cursor, reference-data upload.
- Built-in connectors: webhook, file drop, Infor SyteLine (IDO REST),
  1C (OData). Research first, against a mock ERP until a real one is
  available.
