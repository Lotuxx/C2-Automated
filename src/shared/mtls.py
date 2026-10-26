"""
shared/mtls.py — Mutual TLS helpers for the lab C2.

Role
----
This module provides the TLS context builders used by both the server and the
agent when mutual TLS (mTLS) is enabled.  In mTLS mode:

  * The SERVER presents certs/server.crt and is verified by the agent using
    a CA (certs/server-ca.crt, or the self-signed server cert itself).
  * The AGENT presents its own certificate (certs/agents/<agent_id>.crt +
    .key) signed by a dedicated agent CA (certs/agent-ca.crt).
  * The SERVER verifies the agent certificate against the agent CA.  The CN
    field of the agent certificate becomes the authoritative agent_id — the
    self-declared payload value in REGISTER is IGNORED in mTLS mode.

When mTLS is disabled (the default for backward compatibility), behaviour is
identical to the previous version: only the server is authenticated.

Certificate layout
------------------
  certs/
    server.crt / server.key   — server TLS certificate (existing)
    agent-ca.crt / agent-ca.key — CA that signs agent certificates
    agents/
      <agent_id>.crt          — per-agent certificate (CN = agent_id)
      <agent_id>.key          — private key for the agent certificate

Generation script
-----------------
Run ``python -m shared.mtls generate-lab-certs`` to create a complete
lab-grade PKI in the certs/ directory.  This generates:
  • A self-signed agent CA (certs/agent-ca.crt + agent-ca.key)
  • A sample agent certificate (certs/agents/lab-agent-01.crt + .key)
The existing server certificate is reused as-is.

Security note
-------------
mTLS proves that the connecting process holds the private key for a
certificate signed by the agent CA.  It does NOT prove physical identity of
the machine, user, or software.  For the lab this is sufficient to prevent
anonymous connections from claiming arbitrary agent IDs.
"""
from __future__ import annotations

import ssl
import subprocess
import sys
from pathlib import Path


def build_server_context(
    cert: str | Path,
    key: str | Path,
    *,
    agent_ca: str | Path | None = None,
) -> ssl.SSLContext:
    """Build a server-side TLS context, optionally requiring client certificates.

    Parameters
    ----------
    cert, key : path
        Server certificate and private key (PEM).
    agent_ca : path or None
        If provided, the server requires clients to present a certificate
        signed by this CA.  Connections without a valid client certificate
        are rejected at the TLS handshake level — no Python code runs for them.
        If None, client authentication is not required (backward-compatible mode).

    Returns
    -------
    ssl.SSLContext
        Ready to pass to ``asyncio.start_server(..., ssl=ctx)``.
    """
    ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    ctx.minimum_version = ssl.TLSVersion.TLSv1_2
    ctx.load_cert_chain(str(cert), str(key))

    if agent_ca is not None:
        # Require and verify a client certificate on every connection.
        ctx.verify_mode = ssl.CERT_REQUIRED
        ctx.load_verify_locations(cafile=str(agent_ca))

    return ctx


def build_agent_context(
    server_ca: str | Path,
    *,
    agent_cert: str | Path | None = None,
    agent_key: str | Path | None = None,
) -> ssl.SSLContext:
    """Build a client-side TLS context, optionally presenting a client certificate.

    Parameters
    ----------
    server_ca : path
        CA certificate used to verify the server (typically the server's own
        self-signed certificate in the lab).
    agent_cert, agent_key : path or None
        If both are provided, the agent presents this certificate to the server.
        Required when the server has ``agent_ca`` set (mTLS mode).

    Returns
    -------
    ssl.SSLContext
        Ready to pass to ``asyncio.open_connection(..., ssl=ctx)``.
    """
    ctx = ssl.create_default_context(ssl.Purpose.SERVER_AUTH, cafile=str(server_ca))
    ctx.minimum_version = ssl.TLSVersion.TLSv1_2

    if agent_cert is not None and agent_key is not None:
        ctx.load_cert_chain(str(agent_cert), str(agent_key))

    return ctx


def extract_agent_id_from_cert(writer) -> str | None:
    """Extract the CN from the peer certificate presented during the TLS handshake.

    Returns None if no client certificate is present (non-mTLS connection).
    Raises ValueError if the certificate has no CN or an empty one.

    Parameters
    ----------
    writer : asyncio.StreamWriter
        An open TLS stream whose SSL handshake has completed.
    """
    ssl_obj = writer.get_extra_info("ssl_object")
    if ssl_obj is None:
        return None
    cert = ssl_obj.getpeercert()
    if not cert:
        return None  # no client certificate presented
    # RFC 2253: subject is a list of RDN sets; each RDN is a list of (type, value) pairs.
    for rdn in cert.get("subject", ()):
        for attr_type, attr_value in rdn:
            if attr_type == "commonName":
                cn = attr_value.strip()
                if not cn:
                    raise ValueError("agent certificate has empty CN")
                return cn
    raise ValueError("agent certificate has no CN field")


def generate_lab_certs(certs_dir: str | Path = "certs") -> None:
    """Generate a minimal lab PKI suitable for demonstrating mTLS.

    Creates:
      certs/agent-ca.crt + certs/agent-ca.key
          Self-signed CA used to sign agent certificates.
      certs/agents/lab-agent-01.crt + certs/agents/lab-agent-01.key
          Sample agent certificate with CN=lab-agent-01.

    The server's own certificate (certs/server.crt) is NOT touched.

    Requires: OpenSSL CLI available on PATH.
    """
    root = Path(certs_dir)
    agents_dir = root / "agents"
    agents_dir.mkdir(parents=True, exist_ok=True)

    def run(cmd: list[str]) -> None:
        """Run an OpenSSL CLI command; raise RuntimeError on failure."""
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            print(result.stderr, file=sys.stderr)
            raise RuntimeError(f"OpenSSL command failed: {' '.join(cmd[:3])}")

    ca_key = root / "agent-ca.key"
    ca_crt = root / "agent-ca.crt"
    if not ca_key.exists():
        print("Generating agent CA key and self-signed certificate...")
        run([
            "openssl", "req", "-x509", "-newkey", "rsa:2048",
            "-days", "365", "-nodes",
            "-keyout", str(ca_key),
            "-out", str(ca_crt),
            "-subj", "/CN=lab-agent-ca",
        ])
        ca_key.chmod(0o600)
        print(f"  {ca_crt}\n  {ca_key}")
    else:
        print(f"Agent CA already exists at {ca_crt} — skipping.")

    sample_id = "lab-agent-01"
    agent_key = agents_dir / f"{sample_id}.key"
    agent_csr = agents_dir / f"{sample_id}.csr"
    agent_crt = agents_dir / f"{sample_id}.crt"

    if not agent_key.exists():
        print(f"Generating agent certificate for {sample_id!r}...")
        run([
            "openssl", "req", "-newkey", "rsa:2048", "-nodes",
            "-keyout", str(agent_key),
            "-out", str(agent_csr),
            "-subj", f"/CN={sample_id}",
        ])
        run([
            "openssl", "x509", "-req",
            "-in", str(agent_csr),
            "-CA", str(ca_crt),
            "-CAkey", str(ca_key),
            "-CAcreateserial",
            "-days", "365",
            "-out", str(agent_crt),
        ])
        agent_key.chmod(0o600)
        agent_csr.unlink(missing_ok=True)
        print(f"  {agent_crt}\n  {agent_key}")
    else:
        print(f"Agent cert already exists at {agent_crt} — skipping.")

    print(
        "\nTo use mTLS, start the server with:\n"
        f"  python -m server.main --agent-ca {ca_crt}\n"
        "\nAnd start the agent with:\n"
        f"  python -m agent.main --agent-cert {agent_crt} --agent-key {agent_key} "
        f"--agent-id {sample_id}\n"
        "\nThe agent_id is taken from the certificate CN; the --agent-id flag must "
        "match the CN exactly."
    )


if __name__ == "__main__":
    import argparse
    p = argparse.ArgumentParser(description="mTLS lab certificate utility")
    p.add_argument("command", choices=["generate-lab-certs"],
                   help="generate-lab-certs: create agent CA and a sample agent certificate")
    p.add_argument("--certs-dir", default="certs")
    args = p.parse_args()
    if args.command == "generate-lab-certs":
        generate_lab_certs(args.certs_dir)
