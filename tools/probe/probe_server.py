"""Throw-away HTTPS server for the Windows 7 compatibility probe (task S0-01).

Serves two endpoints over TLS with a self-signed certificate:

    GET /api/probe          JSON with the server time and version
    GET /api/probe/stream   Server-Sent Events, one event per interval

Query parameters of the stream, used to exercise reconnects:

    interval=SECONDS        time between events (default: --interval)
    drop_after=N            close the connection abruptly after N events
    limit=N                 end the stream cleanly after N events

The stream honours the Last-Event-ID header, so a reconnecting client
continues where it left off.

Standard library only. Not the Nestrack server — just enough to probe the
client side.
"""

import argparse
import hashlib
import json
import platform
import ssl
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Optional
from urllib.parse import parse_qs, urlparse

VERSION = "probe-server/1"


def fingerprint_of_pem(path: str) -> str:
    """SHA-256 fingerprint of a PEM certificate, as AA:BB:..."""
    with open(path, "r", encoding="ascii") as fh:
        der = ssl.PEM_cert_to_DER_cert(fh.read())
    digest = hashlib.sha256(der).hexdigest().upper()
    return ":".join(digest[i:i + 2] for i in range(0, len(digest), 2))


class ProbeHandler(BaseHTTPRequestHandler):
    # HTTP/1.0: the stream simply ends when the connection closes, which keeps
    # both sides trivial.
    protocol_version = "HTTP/1.0"
    server_version = VERSION
    default_interval = 1.0

    def log_message(self, fmt, *args):  # quieter than the default
        if not getattr(self.server, "quiet", False):
            sys.stderr.write("%s %s\n" % (self.address_string(), fmt % args))

    def do_GET(self):
        url = urlparse(self.path)
        if url.path == "/api/probe":
            self._send_json({
                "server": VERSION,
                "time": time.time(),
                "python": platform.python_version(),
            })
        elif url.path == "/api/probe/stream":
            self._stream(parse_qs(url.query))
        else:
            self.send_error(404)

    def _send_json(self, payload):
        body = json.dumps(payload).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _stream(self, query):
        interval = float(query.get("interval", [self.default_interval])[0])
        drop_after = _int_or_none(query.get("drop_after", [None])[0])
        limit = _int_or_none(query.get("limit", [None])[0])
        last_id = _int_or_none(self.headers.get("Last-Event-ID")) or 0

        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Cache-Control", "no-cache")
        self.end_headers()
        self.wfile.write(b"retry: 1000\n\n")
        self.wfile.flush()

        sent = 0
        event_id = last_id
        try:
            while limit is None or sent < limit:
                if drop_after is not None and sent >= drop_after:
                    # Abrupt close, as a network drop would look.
                    self.connection.shutdown(2)
                    return
                event_id += 1
                data = json.dumps({"n": event_id, "time": time.time()})
                self.wfile.write(
                    ("id: %d\ndata: %s\n\n" % (event_id, data)).encode("utf-8"))
                self.wfile.flush()
                sent += 1
                time.sleep(interval)
        except (BrokenPipeError, ConnectionResetError, ssl.SSLError, OSError):
            return


def _int_or_none(value) -> Optional[int]:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def make_server(host: str, port: int, cert: str, key: str,
                interval: float = 1.0, quiet: bool = False) -> ThreadingHTTPServer:
    handler = type("Handler", (ProbeHandler,), {"default_interval": interval})
    server = ThreadingHTTPServer((host, port), handler)
    server.daemon_threads = True
    server.quiet = quiet
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.minimum_version = ssl.TLSVersion.TLSv1_2
    context.load_cert_chain(cert, key)
    server.socket = context.wrap_socket(server.socket, server_side=True)
    return server


def serve_in_thread(server: ThreadingHTTPServer) -> threading.Thread:
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return thread


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=8443)
    parser.add_argument("--cert", default="probe-cert.pem")
    parser.add_argument("--key", default="probe-key.pem")
    parser.add_argument("--interval", type=float, default=1.0,
                        help="seconds between stream events (default 1)")
    args = parser.parse_args(argv)

    server = make_server(args.host, args.port, args.cert, args.key, args.interval)
    print("Probe server on https://%s:%d" % (args.host, server.server_address[1]))
    print("Certificate fingerprint (SHA-256): %s" % fingerprint_of_pem(args.cert))
    print("Put it into probe.ini next to the client. Ctrl+C to stop.")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
