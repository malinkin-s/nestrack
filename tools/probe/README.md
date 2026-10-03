# Windows 7 compatibility probe

Task **S0-01** in [docs/TASKS.md](../../docs/TASKS.md): before any server work,
prove that a client built like the real one — Python 3.8.10, 32-bit,
PyInstaller, standard library only — can do on a Windows 7 shop-floor PC what
the architecture relies on.

| Check | What it proves |
|---|---|
| `tls_pinned` | HTTPS with TLS 1.2 or newer to a server with a self-signed certificate, trusted by its pinned SHA-256 fingerprint |
| `tls_pin_rejects` | Any other certificate is refused before a request is sent |
| `sse` | A Server-Sent Events stream is read; after forced drops the client reconnects with `Last-Event-ID` and loses or repeats nothing |
| `dpapi_user`, `dpapi_machine` | Windows DPAPI protects and recovers a secret, user and machine scope |

The result is printed and written to `probe-report.txt` next to the program.

## Files

| File | Runs on | Purpose |
|---|---|---|
| `probe_server.py` | Any machine with Python 3.8+ — a VM, a laptop | HTTPS + SSE test server, standard library only |
| `make_cert.py` | Same machine | Self-signed certificate; needs `cryptography` (or use the OpenSSL one-liner inside) |
| `probe_client.py` | The shop-floor PC, as `nestrack-probe.exe` | The checks |
| `probe.spec` | Build machine | PyInstaller build of the client |
| `probe.ini.example` | Shop-floor PC | Settings template |
| `test_probe.py` | CI, developers | Runs every check against a local server |

## Running it

1. **Get the `.exe`.** Download the `nestrack-probe-win32` artifact from the
   latest **Probe** workflow run, or build it on a Windows machine with
   Python 3.8.10 32-bit:

   ```bash
   pip install "pyinstaller==5.13.2"
   pyinstaller probe.spec        # -> dist/nestrack-probe.exe
   ```

2. **Start the server** on a machine the shop-floor PC can reach, with the
   address the PC will use:

   ```bash
   python make_cert.py --name 192.168.56.10
   python probe_server.py --port 8443
   ```

   It prints the certificate fingerprint. Allow the port through the firewall.

3. **On the Windows 7 PC**, put `nestrack-probe.exe` and a `probe.ini` (from
   `probe.ini.example`, with the URL and fingerprint filled in) into one
   folder and run the `.exe`. No Python installation is needed.

4. **Record the result.** Attach `probe-report.txt` to the S0-01 pull request
   or issue and add the outcome to [docs/FINDINGS.md](../../docs/FINDINGS.md).
   Run it on a current Windows as well, for comparison.

## If something fails

| Failure | Likely cause | Next step |
|---|---|---|
| The `.exe` does not start at all | PyInstaller bootloader or Python runtime not supported on this Windows 7 build (missing updates such as KB2533623 / the Universal C Runtime) | Install the missing updates; try building with the same PyInstaller version that builds finnpower-counter |
| `tls_pinned` fails with a handshake error | TLS settings or a proxy between the PC and the server | Check the server's address and port from the PC; look for an intercepting proxy |
| `sse` shows gaps or no reconnects | Something buffers or cuts long-lived HTTP responses | Repeat without proxies; note it — it affects the live-update design |
| `dpapi_*` fails | DPAPI unavailable for this account | Note the account type (local, domain, kiosk); the client's local secrets depend on it |

Any failure means revisiting [docs/ARCHITECTURE.md](../../docs/ARCHITECTURE.md)
before stage 1 starts.

Set `NESTRACK_PROBE_TRACEBACK=1` to include Python tracebacks in the report.
