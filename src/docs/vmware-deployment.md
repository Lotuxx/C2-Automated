# VMware Deployment Guide — PA-C2

## Overview

This guide covers deploying the C2 server and agents in a VMware virtual
machine infrastructure (ESXi / vSphere / Fusion / Workstation), replacing the
default `127.0.0.1` loopback setup with real IP addresses.

## Prerequisites

- Python 3.10+ on both server VM and agent VMs
- OpenSSL CLI on the server VM
- `pip install rich` on the server VM
- Network connectivity between server and agent VMs (port 9443 by default)
- No internet access required (fully offline lab)

---

## Step 1 — Generate production TLS certificate

The server certificate must include the server VM's IP address and/or hostname
in the Subject Alternative Names:

```bash
# Replace 192.168.1.100 with your server VM's IP, lab-c2 with its hostname
SERVER_IP="192.168.1.100"
SERVER_HOST="lab-c2"

openssl req -x509 -newkey rsa:4096 -days 365 -nodes \
  -keyout certs/server.key -out certs/server.crt \
  -subj "/CN=${SERVER_HOST}" \
  -addext "subjectAltName=IP:${SERVER_IP},DNS:${SERVER_HOST},IP:127.0.0.1"

chmod 600 certs/server.key
```

Copy `certs/server.crt` (public, no private key) to each agent VM.

---

## Step 2 — Server configuration file (optional)

Create `config/server.yaml` for reproducible startup:

```yaml
# config/server.yaml — C2 server configuration
host: "0.0.0.0"        # listen on all interfaces
port: 9443
cert: "certs/server.crt"
key:  "certs/server.key"
db:   "data/c2.db"
log_file: "logs/server.log"
task_timeout: 120       # 2 minutes for VMware lab
playbooks_dir: "playbooks"
```

Start with:
```bash
python -m server.main \
  --host 0.0.0.0 \
  --port 9443 \
  --cert certs/server.crt \
  --key  certs/server.key \
  --db   data/c2.db \
  --log-file logs/server.log \
  --task-timeout 120 \
  --playbooks-dir playbooks
```

---

## Step 3 — Agent deployment on each VM

Copy to the agent VM:
```
agent/
shared/
certs/server.crt    ← server's public cert only
requirements-agent.txt
```

**`requirements-agent.txt`** (no rich needed on agents):
```
# No external dependencies for the agent
```

Start the agent:
```bash
python -m agent.main \
  --server 192.168.1.100 \
  --port   9443 \
  --ca     certs/server.crt \
  --agent-id vm-001 \
  --beacon-interval 30 \
  --beacon-jitter   5 \
  --reconnect-sessions 10 \
  --reconnect-attempts  5 \
  --reconnect-max-delay 30
```

---

## Step 4 — mTLS (optional, recommended for VMware)

Generate per-agent certificates:
```bash
python -m shared.mtls generate-lab-certs
# Creates: certs/agent-ca.crt, certs/agents/lab-agent-01.{crt,key}
```

Start server with mTLS:
```bash
python -m server.main --host 0.0.0.0 --port 9443 \
  --cert certs/server.crt --key certs/server.key \
  --agent-ca certs/agent-ca.crt
```

Start agent with certificate:
```bash
python -m agent.main \
  --server 192.168.1.100 --port 9443 \
  --ca certs/server.crt \
  --agent-cert certs/agents/lab-agent-01.crt \
  --agent-key  certs/agents/lab-agent-01.key \
  --agent-id   lab-agent-01
```

---

## Step 5 — OS startup persistence (auto-start agent on VM boot)

```bash
python -m agent.persistence install \
  --server 192.168.1.100 \
  --port 9443 \
  --ca /opt/c2-agent/certs/server.crt \
  --agent-id vm-001 \
  --beacon-interval 30

# Verify
python -m agent.persistence status
```

Or via the C2 CLI after the agent is connected:
```
[c2]> task vm-001 persist --server 192.168.1.100 --port 9443 --ca certs/server.crt
```

---

## Step 6 — Automation triggers for auto-inventory

Register a trigger so every new agent is automatically inventoried:
```
[c2]> trigger add agent_connected agent_inventory
[c2]> triggers    # verify registration
```

Now when `vm-002` connects for the first time, `agent_inventory` playbook
runs automatically: ping → get_info → sysinfo → whoami → uname.

---

## Network diagram (VMware lab)

```
┌─────────────────────────────────────────────────────┐
│                  VMware Host                         │
│                                                      │
│  ┌──────────────────┐      ┌──────────────────────┐ │
│  │   Server VM      │      │   Agent VM 1          │ │
│  │   192.168.1.100  │◄─TLS─│   192.168.1.101       │ │
│  │   port 9443      │      │   agent-id: vm-001    │ │
│  │   server/main.py │      │   agent/main.py       │ │
│  └────────┬─────────┘      └──────────────────────┘ │
│           │                                           │
│           │               ┌──────────────────────┐   │
│           └─────────TLS───│   Agent VM 2          │  │
│                           │   192.168.1.102       │  │
│                           │   agent-id: vm-002    │  │
│                           └──────────────────────┘   │
│                                                      │
│  VMnet: Host-Only or NAT (no internet required)     │
└─────────────────────────────────────────────────────┘
```

---

## Firewall / network

```bash
# On the server VM (Ubuntu/Debian):
sudo ufw allow 9443/tcp comment "C2 server TLS"

# Or with iptables:
sudo iptables -A INPUT -p tcp --dport 9443 -j ACCEPT
```

---

## Troubleshooting

| Symptom | Likely cause | Fix |
|---|---|---|
| Agent can't connect | Wrong server IP or port | Check `--server` and `--port` |
| TLS handshake fails | Server cert SAN doesn't include agent's target IP | Regenerate cert with correct SAN |
| 128 KiB upload CANCELLED | Old agent without `limit=4*1024*1024` | Update agent to v8+ |
| Agent disconnects on PING | Event loop blocked | Update to v8+ (asyncio.to_thread) |
| mTLS: cert CN mismatch | `--agent-id` doesn't match cert CN | Use `--agent-id lab-agent-01` |
