"""Windows 7 compatibility probe for the Nestrack client (task S0-01).

Checks, with the standard library of Python 3.8 only, everything the real
client will rely on:

1. tls_pinned       HTTPS to the probe server with TLS 1.2+, the server
                    certificate pinned by its SHA-256 fingerprint
2. tls_pin_rejects  the same connection with a wrong fingerprint is refused
3. sse              a Server-Sent Events stream is read, survives forced
                    drops, reconnects with Last-Event-ID, loses nothing
4. dpapi_user       Windows DPAPI round-trip, user scope
5. dpapi_machine    Windows DPAPI round-trip, machine scope

Settings come from probe.ini next to the program (or the script), and can be
overridden on the command line:

    [probe]
    url = https://192.168.56.10:8443
    fingerprint = AA:BB:...
    sse_seconds = 30

The result goes to the console and to probe-report.txt next to the program.
Exit code 0 when nothing failed.
"""

import argparse
import configparser
import ctypes
import datetime
import hashlib
import http.client
import json
import os
import platform
import socket
import ssl
import struct
import sys
import tempfile
import time
import traceback
from typing import Dict, List, Optional, Tuple
from urllib.parse import urlparse

PROBE_VERSION = "1"

PASS = "PASS"
FAIL = "FAIL"
SKIP = "SKIP"


# --- settings -------------------------------------------------------------

def program_dir() -> str:
    """Folder of the .exe when frozen by PyInstaller, of the script otherwise."""
    if getattr(sys, "frozen", False):
        return os.path.dirname(os.path.abspath(sys.executable))
    return os.path.dirname(os.path.abspath(__file__))


def load_settings(argv: Optional[List[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Nestrack Windows 7 probe")
    parser.add_argument("--url", help="probe server, e.g. https://192.168.56.10:8443")
    parser.add_argument("--fingerprint", help="server certificate SHA-256, AA:BB:...")
    parser.add_argument("--sse-seconds", type=float, help="how long to read the stream")
    parser.add_argument("--interval", type=float, default=None,
                        help="seconds between stream events (server default if omitted)")
    parser.add_argument("--report", help="where to write the report")
    parser.add_argument("--config", help="settings file (default: probe.ini next to the program)")
    args = parser.parse_args(argv)

    config = configparser.ConfigParser()
    config.read(args.config or os.path.join(program_dir(), "probe.ini"), encoding="utf-8")
    section = config["probe"] if config.has_section("probe") else {}

    args.url = args.url or section.get("url")
    args.fingerprint = args.fingerprint or section.get("fingerprint")
    if args.sse_seconds is None:
        args.sse_seconds = float(section.get("sse_seconds", "30"))
    if args.interval is None and section.get("interval"):
        args.interval = float(section.get("interval"))
    return args


def normalise_fingerprint(value: str) -> str:
    return value.replace(":", "").replace(" ", "").strip().upper()


# --- TLS with certificate pinning -------------------------------------------

class PinMismatch(Exception):
    """The server presented a certificate other than the pinned one."""


def pinned_context() -> ssl.SSLContext:
    """TLS 1.2+, no CA validation: trust comes from the pinned fingerprint."""
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    context.check_hostname = False
    context.verify_mode = ssl.CERT_NONE
    context.minimum_version = ssl.TLSVersion.TLSv1_2
    return context


def open_pinned(url: str, fingerprint: str, timeout: float = 10.0
                ) -> Tuple[http.client.HTTPSConnection, Dict[str, str]]:
    """Connect and check the pin before a single byte of the request is sent."""
    parts = urlparse(url)
    conn = http.client.HTTPSConnection(parts.hostname, parts.port or 443,
                                       context=pinned_context(), timeout=timeout)
    conn.connect()
    der = conn.sock.getpeercert(binary_form=True)
    actual = hashlib.sha256(der).hexdigest().upper()
    if actual != normalise_fingerprint(fingerprint):
        conn.close()
        raise PinMismatch("expected %s, got %s" % (normalise_fingerprint(fingerprint), actual))
    cipher = conn.sock.cipher()
    info = {
        "tls_version": conn.sock.version() or "?",
        "cipher": cipher[0] if cipher else "?",
        "fingerprint": actual,
    }
    return conn, info


def check_tls_pinned(settings) -> Tuple[str, str]:
    conn, info = open_pinned(settings.url, settings.fingerprint)
    try:
        conn.request("GET", "/api/probe")
        response = conn.getresponse()
        body = json.loads(response.read().decode("utf-8"))
    finally:
        conn.close()
    if response.status != 200 or "server" not in body:
        return FAIL, "HTTP %s, body %r" % (response.status, body)
    return PASS, "%s, %s, server %s" % (info["tls_version"], info["cipher"], body["server"])


def check_tls_pin_rejects(settings) -> Tuple[str, str]:
    wrong = "00" * 32
    try:
        conn, _ = open_pinned(settings.url, wrong)
    except PinMismatch:
        return PASS, "a different certificate was refused"
    conn.close()
    return FAIL, "connection accepted with a wrong fingerprint"


# --- Server-Sent Events -----------------------------------------------------

def read_events(conn: http.client.HTTPSConnection, path: str, last_id: Optional[str],
                deadline: float):
    """Yield (event_id, data) until the stream ends, drops or the deadline passes."""
    headers = {"Accept": "text/event-stream", "Cache-Control": "no-cache"}
    if last_id:
        headers["Last-Event-ID"] = last_id
    conn.request("GET", path, headers=headers)
    response = conn.getresponse()
    if response.status != 200:
        raise IOError("HTTP %s" % response.status)
    event_id, data = None, []
    while time.time() < deadline:
        raw = response.readline()
        if not raw:
            return  # stream closed
        line = raw.decode("utf-8").rstrip("\r\n")
        if not line:
            if data:
                yield event_id, "\n".join(data)
            event_id, data = None, []
        elif line.startswith(":"):
            continue
        else:
            field, _, value = line.partition(":")
            value = value[1:] if value.startswith(" ") else value
            if field == "id":
                event_id = value
            elif field == "data":
                data.append(value)


def check_sse(settings) -> Tuple[str, str]:
    drop_after = 5
    query = "drop_after=%d" % drop_after
    if settings.interval:
        query += "&interval=%s" % settings.interval
    path = "/api/probe/stream?" + query
    deadline = time.time() + settings.sse_seconds

    received: List[int] = []
    reconnects = 0
    errors: List[str] = []
    last_id: Optional[str] = None
    while time.time() < deadline:
        try:
            conn, _ = open_pinned(settings.url, settings.fingerprint)
            try:
                for event_id, data in read_events(conn, path, last_id, deadline):
                    received.append(json.loads(data)["n"])
                    last_id = event_id
            finally:
                conn.close()
        except (OSError, http.client.HTTPException, ssl.SSLError) as exc:
            errors.append(type(exc).__name__)
        if time.time() < deadline:
            reconnects += 1
            time.sleep(0.5)

    expected = list(range(received[0], received[0] + len(received))) if received else []
    detail = "%d events, %d reconnects, ids %s" % (
        len(received), reconnects,
        "%d..%d" % (received[0], received[-1]) if received else "none")
    if errors:
        detail += ", errors: %s" % ", ".join(sorted(set(errors)))
    if not received:
        return FAIL, detail
    if received != expected:
        return FAIL, detail + " — gaps or duplicates"
    if len(received) > drop_after and reconnects == 0:
        return FAIL, detail + " — no reconnect happened"
    return PASS, detail


# --- DPAPI ------------------------------------------------------------------

CRYPTPROTECT_UI_FORBIDDEN = 0x1
CRYPTPROTECT_LOCAL_MACHINE = 0x4


def _dpapi():
    from ctypes import wintypes

    class DataBlob(ctypes.Structure):
        _fields_ = [("cbData", wintypes.DWORD),
                    ("pbData", ctypes.POINTER(ctypes.c_char))]

    crypt32 = ctypes.WinDLL("crypt32", use_last_error=True)
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    return DataBlob, crypt32, kernel32


def _blob(DataBlob, data: bytes):
    buffer = ctypes.create_string_buffer(data, len(data))
    return DataBlob(len(data), ctypes.cast(buffer, ctypes.POINTER(ctypes.c_char))), buffer


def dpapi_protect(data: bytes, entropy: bytes, machine: bool) -> bytes:
    DataBlob, crypt32, kernel32 = _dpapi()
    blob_in, keep_in = _blob(DataBlob, data)
    blob_entropy, keep_entropy = _blob(DataBlob, entropy)
    blob_out = DataBlob()
    flags = CRYPTPROTECT_UI_FORBIDDEN | (CRYPTPROTECT_LOCAL_MACHINE if machine else 0)
    if not crypt32.CryptProtectData(ctypes.byref(blob_in), "nestrack-probe",
                                    ctypes.byref(blob_entropy), None, None, flags,
                                    ctypes.byref(blob_out)):
        raise ctypes.WinError(ctypes.get_last_error())
    try:
        return ctypes.string_at(blob_out.pbData, blob_out.cbData)
    finally:
        kernel32.LocalFree(blob_out.pbData)


def dpapi_unprotect(data: bytes, entropy: bytes) -> bytes:
    DataBlob, crypt32, kernel32 = _dpapi()
    blob_in, keep_in = _blob(DataBlob, data)
    blob_entropy, keep_entropy = _blob(DataBlob, entropy)
    blob_out = DataBlob()
    if not crypt32.CryptUnprotectData(ctypes.byref(blob_in), None,
                                      ctypes.byref(blob_entropy), None, None,
                                      CRYPTPROTECT_UI_FORBIDDEN, ctypes.byref(blob_out)):
        raise ctypes.WinError(ctypes.get_last_error())
    try:
        return ctypes.string_at(blob_out.pbData, blob_out.cbData)
    finally:
        kernel32.LocalFree(blob_out.pbData)


def check_dpapi(machine: bool) -> Tuple[str, str]:
    if not sys.platform.startswith("win"):
        return SKIP, "not Windows"
    secret = os.urandom(32)
    entropy = b"nestrack-probe-entropy"
    protected = dpapi_protect(secret, entropy, machine)
    if secret in protected:
        return FAIL, "protected blob contains the plaintext"
    if dpapi_unprotect(protected, entropy) != secret:
        return FAIL, "round-trip returned different bytes"
    return PASS, "%d-byte secret -> %d-byte blob and back" % (len(secret), len(protected))


# --- report -----------------------------------------------------------------

def environment() -> List[Tuple[str, str]]:
    rows = [
        ("probe", PROBE_VERSION),
        ("time", datetime.datetime.now().isoformat(timespec="seconds")),
        ("platform", platform.platform()),
        ("python", "%s (%d-bit)" % (platform.python_version(), struct.calcsize("P") * 8)),
        ("openssl", ssl.OPENSSL_VERSION),
        ("frozen", "yes (PyInstaller)" if getattr(sys, "frozen", False) else "no"),
    ]
    if hasattr(sys, "getwindowsversion"):
        version = sys.getwindowsversion()
        rows.insert(3, ("windows", "%d.%d build %d %s" % (
            version.major, version.minor, version.build, version.service_pack)))
    return rows


def run_checks(settings) -> List[Tuple[str, str, str]]:
    checks = [
        ("tls_pinned", lambda: check_tls_pinned(settings)),
        ("tls_pin_rejects", lambda: check_tls_pin_rejects(settings)),
        ("sse", lambda: check_sse(settings)),
        ("dpapi_user", lambda: check_dpapi(machine=False)),
        ("dpapi_machine", lambda: check_dpapi(machine=True)),
    ]
    needs_server = {"tls_pinned", "tls_pin_rejects", "sse"}
    results = []
    for name, check in checks:
        if name in needs_server and not (settings.url and settings.fingerprint):
            results.append((name, SKIP, "no url or fingerprint in probe.ini"))
            continue
        try:
            status, detail = check()
        except Exception as exc:  # the report must be written whatever happens
            status = FAIL
            detail = "%s: %s" % (type(exc).__name__, exc)
            if os.environ.get("NESTRACK_PROBE_TRACEBACK"):
                detail += "\n" + traceback.format_exc()
        results.append((name, status, detail))
        print("%-16s %s  %s" % (name, status, detail))
        sys.stdout.flush()
    return results


def format_report(env, results) -> str:
    lines = ["Nestrack Windows 7 probe report", "=" * 31, ""]
    lines += ["%-10s %s" % (key, value) for key, value in env]
    lines += ["", "Checks", "------"]
    lines += ["%-16s %-4s  %s" % row for row in results]
    failed = [name for name, status, _ in results if status == FAIL]
    lines += ["", "Result: %s" % ("FAILED: " + ", ".join(failed) if failed else "OK"), ""]
    return "\n".join(lines)


def write_report(text: str, path: Optional[str]) -> str:
    candidates = [path] if path else [
        os.path.join(program_dir(), "probe-report.txt"),
        os.path.join(os.getcwd(), "probe-report.txt"),
        os.path.join(tempfile.gettempdir(), "probe-report.txt"),
    ]
    for candidate in candidates:
        try:
            with open(candidate, "w", encoding="utf-8") as fh:
                fh.write(text)
            return candidate
        except OSError:
            continue
    return ""


def main(argv: Optional[List[str]] = None) -> int:
    settings = load_settings(argv)
    socket.setdefaulttimeout(15)
    env = environment()
    for key, value in env:
        print("%-10s %s" % (key, value))
    print()
    results = run_checks(settings)
    text = format_report(env, results)
    where = write_report(text, settings.report)
    print()
    print(text.splitlines()[-1])
    print("Report: %s" % (where or "could not be written"))
    if getattr(sys, "frozen", False) and sys.stdin and sys.stdin.isatty():
        try:
            input("Press Enter to close...")
        except EOFError:
            pass
    return 1 if any(status == FAIL for _, status, _ in results) else 0


if __name__ == "__main__":
    sys.exit(main())
