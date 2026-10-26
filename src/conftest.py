"""
tests/conftest.py — Pytest session fixtures.

Generates a self-signed TLS certificate in ``certs/`` at the start of the
test session so that the three mTLS tests (TestMTLSHelpers) can run without
requiring the operator to generate certs manually beforehand.

The certificate is written once per session and reused across test files.
It is intentionally placed in the project's certs/ directory (not a tmpdir)
so that the same path used by the production code is exercised.
"""
import subprocess
from pathlib import Path

import pytest


@pytest.fixture(scope="session", autouse=True)
def ensure_test_certs():
    """Generate certs/server.crt and certs/server.key if they do not exist.

    Uses ``openssl req`` with a 1-day validity and the same SAN extensions
    as the README recommends, so the certificate is accepted by the TLS
    stack in integration tests.

    Skips silently when OpenSSL is not on PATH (e.g. minimal CI containers);
    the three mTLS unit tests handle the missing cert gracefully with
    ``self.skipTest()``.
    """
    root  = Path(__file__).parent.parent
    cert  = root / "certs" / "server.crt"
    key   = root / "certs" / "server.key"

    if cert.is_file() and key.is_file():
        return  # already present

    try:
        (root / "certs").mkdir(parents=True, exist_ok=True)
        subprocess.run(
            [
                "openssl", "req", "-x509", "-newkey", "rsa:2048",
                "-days", "1", "-nodes",
                "-keyout", str(key),
                "-out",    str(cert),
                "-subj",   "/CN=127.0.0.1",
                "-addext", "subjectAltName=IP:127.0.0.1,DNS:localhost",
            ],
            capture_output=True, check=True, timeout=30,
        )
    except (FileNotFoundError, subprocess.CalledProcessError):
        # OpenSSL not available — the mTLS tests will skip themselves
        pass
