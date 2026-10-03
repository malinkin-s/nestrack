# Findings

Facts found while planning Nestrack. Each one changed or constrained a
decision in [ARCHITECTURE.md](ARCHITECTURE.md) and [ROADMAP.md](ROADMAP.md).

The code audit of finnpower-counter, which Nestrack grew out of, is in
[finnpower-counter's FINDINGS.md](https://github.com/malinkin-s/finnpower-counter/blob/main/docs/FINDINGS.md).

---

## Planning — 2026-09-29

| ID | Finding | Consequence |
|---|---|---|
| PLN-01 | SQLite's own documentation warns that file locking on network file systems is unreliable and concurrent writes from several machines can corrupt the database | No shared database file on a network drive. Led first to a log-of-files design, then to a server |
| PLN-02 | The Python standard library has no symmetric cipher. Current `cryptography` releases are built with Rust, and current Rust toolchains no longer target Windows 7; older releases that would run are unmaintained | Application-level encryption on the client is expensive. With a server, TLS from the standard library covers data in transit |
| PLN-03 | Python 3.8 bundles its own OpenSSL, so TLS does not depend on Windows 7's own TLS stack | The client can speak modern TLS on Windows 7 — to be confirmed on a real machine (S0-01) |
| PLN-04 | Python 3.8 has been end-of-life since October 2024, and the OpenSSL it bundles is end-of-life too. The client is pinned to it by Windows 7 | Keep the client's network surface minimal: it talks only to its own server, pinned by certificate fingerprint. The server is not bound by this and uses a current Python |
| PLN-05 | finnpower-counter's `app.spec` excludes `ssl`, `http`, `socket`, `email` and `urllib` — it was built to be fully offline | The Nestrack client has its own build with them included (S0-04) |
| PLN-06 | WebSocket is not in the standard library; Server-Sent Events are plain HTTP and can be read with `http.client` | Live updates use SSE |
| PLN-07 | Tk may only be used from the main thread | A background executor is required before any network I/O (S0-03) |
| PLN-08 | finnpower-counter's `gui.py` is a single ~790-line module that mixes layout and behaviour | The Nestrack client reuses the parser and views, not the window code; its UI is built as a package from the start (S0-02) |
| PLN-09 | finnpower-counter "keeps no history and should not" | Nestrack keeps history on the server; finnpower-counter stays history-free. Program files remain read-only in both |
| PLN-10 | Recording each operator's output is processing of personal data and may fall under labour and data-protection law | The project is open source and not tied to a shop: it provides retention and visibility settings (S1-09, S6-05), and compliance is the deployer's responsibility, stated in the documentation |
| PLN-11 | finnpower-counter's code comments and history are in Russian | Nestrack is English-first from the start; Russian versions of key documents are translations |
| PLN-12 | Infor SyteLine exposes a documented IDO REST API (load, update, invoke per IDO) and ION BODs, but has no public sandbox; cloud access goes through the ION API Gateway | The SyteLine connector is built against a mock (TB-04) and verified on a real instance later (R-01, Q-07) |
| PLN-13 | 1C:Enterprise can publish a standard OData v3 interface per infobase; 1C teams also commonly pull from external HTTP APIs with their own scheduled jobs | The integration hub supports both: an OData connector and a generic event feed (S8-04, S8-08) |
| PLN-14 | NC files carry no order or job number (`CUSTOMER` and `Order ID` are empty in the files analysed) | ERP integration needs mapping tables maintained by the administrator (S8-03) |
| PLN-15 | The system needs the same `.nc`/`.fms` parsing that finnpower-counter has verified against 30 real programs and 8,764 setup reports | Nestrack depends on finnpower-counter's parser as a pinned package instead of copying it (X-01) |

---

## Windows 7 probe (S0-01) — 2026-10-03

| ID | Finding | Consequence |
|---|---|---|
| PRB-01 | The probe `.exe` (Python 3.8.10 32-bit, PyInstaller 5.13.2) passes all five checks on the CI's Windows (10.0 build 26100): TLS 1.3 with a pinned certificate, a wrong certificate refused, SSE through three forced reconnects with no gaps, DPAPI in user and machine scope | The approach works in a frozen build. **Not yet confirmed on Windows 7** — S0-01 stays open until a report from a real Windows 7 32-bit PC is recorded here |
| PRB-02 | The OpenSSL bundled with Python 3.8.10 is 1.1.1k from March 2021 — long out of support, as PLN-04 expected | The client talks only to its own server with a pinned certificate; nothing else on the network is trusted. The server's TLS settings must keep TLS 1.2 available for such clients |

