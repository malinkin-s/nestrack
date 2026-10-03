# Nestrack

**English** · [Русский](README.ru.md)

Open-source production tracking for sheet-metal shops: which positions of a
shift task are complete, who made what and when, live for the supervisor and
connected to the ERP.

> **Status: planning.** The architecture, roadmap and task breakdown are
> written; no code yet. Start with [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md).

---

## Where it comes from

Nestrack started as **[finnpower-counter](https://github.com/malinkin-s/finnpower-counter)**,
a standalone utility written for one specific machine: a Prima Power /
Finn-Power punching machine whose programs come from the NCeXpress FMS
postprocessor.

The problem it solved is common to any shop that nests parts on shared
sheets. One shift task holds many parts in different quantities; to save
metal, CAM spreads each part across many programs. A position of 20 pieces
may come out 2 here, 4 there and close only on the 28th program out of 30.
The operator needs to know what is fully done — and at shift handover that
knowledge used to live on sticky notes.

finnpower-counter reads the NC programs and setup reports, works out how many
pieces of each part the shift produces and tracks completion on one
workstation. It stays a separate, standalone project. Nestrack takes the same
idea to the whole shop and reuses its file parsing — verified against real
shift tasks and thousands of real setup reports — as a dependency.

## What it will do

| For | What |
|---|---|
| **Operator** | Opens the shift folder in a desktop client, ticks programs as they are cut, sees which positions are complete; signs in by name and PIN; keeps working when the network drops |
| **Supervisor** | Watches production live in a browser — per operator, day, shift and task; exports CSV |
| **Administrator** | Configures shifts, operators, workstations, retention, Active Directory and ERP connections in a web panel |
| **ERP** | Receives completed quantities per job operation (Infor SyteLine, 1C, webhook, files), or reads them from Nestrack's API |

## How it is built

```
Operator client (Windows 7+, Python 3.8, single .exe)
        │  HTTPS + Server-Sent Events
        ▼
Server (FastAPI · SQLite · Docker or Windows service)
        ├── supervisor and admin web pages
        ├── Active Directory (LDAPS)
        └── integration hub → ERP connectors
```

Diagrams, decisions and the reasons behind them are in
[docs/ARCHITECTURE.md](docs/ARCHITECTURE.md).

## Roadmap

| Stage | What it brings |
|---|---|
| 0 | Windows 7 compatibility probe (gate), client skeleton on finnpower-counter's parser |
| 1 | Server: users, roles, workstations, settings, admin panel, Docker deployment |
| 2 | Client connects: workstation registration, name + PIN sign-in, offline sign-in |
| 3 | Production log: every mark on the server, offline outbox, live updates |
| 4 | Supervisor page, CSV export |
| 5 | Saved sessions: named bookmarks with date and time |
| 6 | Operations: backups, installation guide, retention |
| 7 | Active Directory sign-in, roles from groups |
| 8 | Integration hub: SyteLine, 1C, webhook and file connectors; integration API |

## Documents

- [docs/ROADMAP.md](docs/ROADMAP.md) — stages and decisions
- [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) — client–server design, diagrams
- [docs/INTEGRATIONS.md](docs/INTEGRATIONS.md) — ERP and Active Directory research, integration hub
- [docs/TEST_BENCH.md](docs/TEST_BENCH.md) — test bench nodes, configurations, scenarios
- [docs/TASKS.md](docs/TASKS.md) — task breakdown with acceptance criteria
- [docs/FINDINGS.md](docs/FINDINGS.md) — facts that shaped the plan

The repository is maintained in English; Russian versions (`*.ru.md`) are
translations and may lag behind.

---

## License

[MIT](LICENSE).

The software is provided as is, without warranty of any kind. Whoever deploys
it is responsible for the correctness of accounting at their plant and for
complying with local law on recording employees' work.

## Disclaimer

This project is unofficial and not affiliated with Prima Power, Finn-Power,
the developers of NCeXpress, Infor, 1C or Microsoft. Product names are used
solely to describe file formats and integration targets and belong to their
respective owners.
