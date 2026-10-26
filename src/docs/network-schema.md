# Schéma réseau — PA-C2

## 1. Topologie de laboratoire (configuration recommandée)

```
┌─────────────────────────────────────────────────────────────────────┐
│                    RÉSEAU HOST-ONLY / ISOLÉ                         │
│                    192.168.56.0/24  (exemple VMware)                │
│                                                                     │
│   ┌──────────────────────┐          ┌────────────────────────┐      │
│   │    VM Serveur C2      │          │     VM Agent(s)         │      │
│   │    Ubuntu 22.04       │          │     Ubuntu 22.04        │      │
│   │                       │          │                         │      │
│   │  192.168.56.10        │          │  192.168.56.20          │      │
│   │  (ou 127.0.0.1 si     │          │  192.168.56.21 ...      │      │
│   │   même VM)            │          │                         │      │
│   │                       │◄─────────┤  python -m agent.main   │      │
│   │  python -m server.main│  TLS 1.2+│  --server 192.168.56.10 │      │
│   │  --host 192.168.56.10 │  TCP 9443│  --port 9443            │      │
│   │  --port 9443          │          │  --ca certs/server.crt  │      │
│   │                       │          │                         │      │
│   │  SQLite: pa_c2.db     │          │  SQLite: local_state.db │      │
│   └──────────────────────┘          └────────────────────────┘      │
│                                                                     │
│   ┌──────────────────────┐                                          │
│   │   VM Opérateur        │                                          │
│   │   (optionnel/même VM) │                                          │
│   │                       │                                          │
│   │  CLI Rich             │                                          │
│   │  (local au serveur)   │                                          │
│   └──────────────────────┘                                          │
│                                                                     │
└─────────────────────────────────────────────────────────────────────┘
               │
               │  AUCUNE CONNEXION vers l'extérieur
               │  (pas de NAT, pas de bridge, pas de routage public)
               ▼
        ╔═══════════════╗
        ║   INTERNET    ║  ← hors scope, aucune connexion autorisée
        ╚═══════════════╝
```

---

## 2. Configuration réseau par défaut

| Paramètre | Valeur par défaut | Modifiable |
|---|---|---|
| Adresse d'écoute serveur | `127.0.0.1` | `--host` |
| Port TLS | `9443` | `--port` |
| Version TLS minimale | TLS 1.2 | non (sécurité) |
| Adresse agent | `127.0.0.1` | `--server` |

**Le serveur écoute sur `127.0.0.1` par défaut** — il faut explicitement passer `--host 0.0.0.0` ou une IP d'interface pour écouter sur le réseau. À ne faire que dans un réseau de laboratoire isolé.

---

## 3. Flux réseau détaillé

```
                          TCP 9443 (TLS 1.2+)
                    ┌────────────────────────────┐
                    │                            │
Agent               │                            │    Serveur C2
──────              │                            │    ──────────
                    │                            │
[1] TCP SYN ───────►│ ──────────────────────────►│
[2] TLS Handshake   │ ◄── ServerHello + Cert ────│
    vérification CA │ ──── ClientHello ──────────►│
[3] TLS établi      │ ◄──── Finished ─────────── │
                    │                            │
[4] REGISTER ───────►─────── JSON Lines ─────────►
[5] REGISTER_ACK   ◄─────── JSON Lines ──────────
[6] SYNC_STATE ─────►─────── JSON Lines ─────────►
[7] SYNC_COMPLETE  ◄─────── JSON Lines ──────────
                    │                            │
[8] BEACON (30s±jitter) ──────────────────────── ►
[9] BEACON_ACK     ◄───────────────────────────
                    │                            │
[10] TASK          ◄───────────────────────────
[11] TASK_ACK       ►──────────────────────────►
[12] TASK_STATUS    ►──────────────────────────►
[13] RESULT         ►──────────────────────────►
[14] RESULT_ACK    ◄───────────────────────────
```

---

## 4. Isolation du laboratoire VMware

### Configuration recommandée

```
VMware Workstation / Fusion / ESXi
│
├── Réseau : Host-Only (vmnet1 ou équivalent)
│   ├── Pas d'accès internet
│   ├── Pas de NAT
│   └── Pas de bridge vers interface physique
│
├── VM Serveur C2
│   ├── 1 interface : vmnet1
│   └── Firewall VM : autoriser TCP/9443 entrant uniquement
│
└── VM Agent(s)
    ├── 1 interface : vmnet1
    └── Firewall VM : autoriser TCP sortant vers IP serveur:9443 uniquement
```

### Règles iptables agent (exemple)

```bash
# Autoriser uniquement la connexion vers le C2
iptables -A OUTPUT -d 192.168.56.10 -p tcp --dport 9443 -j ACCEPT
iptables -A OUTPUT -j DROP
iptables -A INPUT -m state --state ESTABLISHED,RELATED -j ACCEPT
iptables -A INPUT -j DROP
```

### Règles iptables serveur (exemple)

```bash
# Autoriser uniquement le port C2 en entrée
iptables -A INPUT -p tcp --dport 9443 -s 192.168.56.0/24 -j ACCEPT
iptables -A INPUT -p tcp --dport 9443 -j DROP
```

---

## 5. Génération des certificats TLS

### Certificat serveur (lab)

```bash
# Depuis PA-MVP/
mkdir -p certs
openssl req -x509 -newkey rsa:2048 -days 365 -nodes \
  -keyout certs/server.key \
  -out    certs/server.crt \
  -subj   '/CN=127.0.0.1' \
  -addext 'subjectAltName=IP:127.0.0.1,IP:192.168.56.10,DNS:localhost'
chmod 600 certs/server.key
```

### mTLS — PKI agent (optionnel)

```bash
python -m shared.mtls generate-lab-certs
# Génère : certs/ca.crt, certs/agent.crt, certs/agent.key
```

Démarrer le serveur avec mTLS :
```bash
python -m server.main --host 192.168.56.10 --port 9443 \
  --cert certs/server.crt --key certs/server.key \
  --agent-ca certs/ca.crt
```

Démarrer l'agent avec mTLS :
```bash
python -m agent.main --server 192.168.56.10 --port 9443 \
  --ca certs/server.crt \
  --agent-cert certs/agent.crt --agent-key certs/agent.key
```

---

## 6. Points d'attention sécurité réseau

| Risque | Mesure |
|---|---|
| Exposition accidentelle du port 9443 | Écoute sur `127.0.0.1` par défaut |
| Agent se connectant à un faux serveur | Vérification du CA obligatoire côté agent |
| Sniffing du trafic C2 | TLS 1.2+ chiffre tout le contenu |
| Agent acceptant n'importe quel serveur avec le bon CA | mTLS optionnel — le serveur peut exiger un certificat agent signé |
| Débordement de buffer réseau | `StreamReader` limité à 4 Mio, messages limités à 1 Mio |
