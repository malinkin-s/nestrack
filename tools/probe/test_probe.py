"""Tests for the probe: run the client checks against a local probe server."""

import os
import shutil
import subprocess
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import probe_client  # noqa: E402
import probe_server  # noqa: E402


def _make_cert(directory):
    """OpenSSL if present (CI runners have it), otherwise `cryptography`."""
    cert = os.path.join(directory, "cert.pem")
    key = os.path.join(directory, "key.pem")
    openssl = shutil.which("openssl")
    if openssl:
        subprocess.run([openssl, "req", "-x509", "-newkey", "rsa:2048", "-nodes",
                        "-days", "1", "-keyout", key, "-out", cert,
                        "-subj", "/CN=nestrack-probe"],
                       check=True, capture_output=True)
        return cert, key
    try:
        import make_cert
        make_cert.make_cert(["127.0.0.1", "localhost"], cert, key, days=1)
    except ImportError:
        pytest.skip("neither openssl nor cryptography available")
    return cert, key


@pytest.fixture(scope="module")
def server(tmp_path_factory):
    cert, key = _make_cert(str(tmp_path_factory.mktemp("cert")))
    srv = probe_server.make_server("127.0.0.1", 0, cert, key, interval=0.05, quiet=True)
    probe_server.serve_in_thread(srv)
    yield "https://127.0.0.1:%d" % srv.server_address[1], probe_server.fingerprint_of_pem(cert)
    srv.shutdown()
    srv.server_close()


def _settings(url, fingerprint, seconds=1.5, report=None):
    args = ["--url", url, "--fingerprint", fingerprint,
            "--sse-seconds", str(seconds), "--interval", "0.05",
            "--config", os.devnull]
    if report:
        args += ["--report", report]
    return probe_client.load_settings(args)


def test_pinned_request_succeeds(server):
    status, detail = probe_client.check_tls_pinned(_settings(*server))
    assert status == probe_client.PASS, detail
    assert "TLSv1." in detail


def test_fingerprint_format_does_not_matter(server):
    url, fingerprint = server
    plain = fingerprint.replace(":", "").lower()
    status, detail = probe_client.check_tls_pinned(_settings(url, plain))
    assert status == probe_client.PASS, detail


def test_wrong_fingerprint_is_refused(server):
    url, _ = server
    with pytest.raises(probe_client.PinMismatch):
        probe_client.open_pinned(url, "11" * 32)
    status, _ = probe_client.check_tls_pin_rejects(_settings(*server))
    assert status == probe_client.PASS


def test_stream_reconnects_without_gaps(server):
    status, detail = probe_client.check_sse(_settings(*server, seconds=2.0))
    assert status == probe_client.PASS, detail
    reconnects = int(detail.split(" reconnects")[0].split()[-1])
    assert reconnects >= 1


@pytest.mark.skipif(not sys.platform.startswith("win"), reason="DPAPI is Windows-only")
@pytest.mark.parametrize("machine", [False, True])
def test_dpapi_round_trip(machine):
    status, detail = probe_client.check_dpapi(machine)
    assert status == probe_client.PASS, detail


def test_dpapi_skips_elsewhere():
    if sys.platform.startswith("win"):
        pytest.skip("Windows")
    assert probe_client.check_dpapi(False)[0] == probe_client.SKIP


def test_main_writes_report_and_exit_code(server, tmp_path):
    report = str(tmp_path / "report.txt")
    url, fingerprint = server
    code = probe_client.main(["--url", url, "--fingerprint", fingerprint,
                              "--sse-seconds", "1.5", "--interval", "0.05",
                              "--config", os.devnull, "--report", report])
    text = open(report, encoding="utf-8").read()
    assert code == 0, text
    assert "Result: OK" in text
    assert "openssl" in text


def test_without_server_settings_network_checks_skip(tmp_path):
    report = str(tmp_path / "report.txt")
    code = probe_client.main(["--config", os.devnull, "--report", report])
    text = open(report, encoding="utf-8").read()
    assert code == 0
    assert "tls_pinned       SKIP" in text
