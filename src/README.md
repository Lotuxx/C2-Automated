# PA-C2 — Serveur de commande et contrôle (laboratoire pédagogique)

> **Usage strictement pédagogique et local.**  
> Exécuter uniquement dans une VM ou un réseau de laboratoire isolé, sur des systèmes dont vous avez l'autorisation écrite.  
> Le serveur écoute sur `127.0.0.1` par défaut. **Ne jamais exposer le port sur un réseau public.**

---

## Vue d'ensemble

PA-C2 est un serveur de commande et contrôle (C2) asynchrone Python complet, développé dans le cadre d'un Projet Annuel à l'ESGI. Il illustre l'architecture et les mécanismes d'un outil C2 dans un cadre pédagogique caontrôlé.

**Fonctionnalités principales :**
- Architecture client/serveur asynchrone (`asyncio`) — multi-agents simultanés
- Transport TLS 1.2+ avec mTLS optionnel
- Protocole JSON Lines documenté avec 17 types de messages
- Machine à états des tâches à 8 états, watchdog de timeout
- 8 commandes agent implémentées : `echo`, `get_info`, `shell`, `sysinfo`, `shellcode`, `upload`, `download`, `persist`, `self_remove`
- CLI opérateur Rich interactive
- Beaconing configurable (intervalle + jitter)
- Moteur d'automatisation par playbooks YAML
- Persistance SQLite côté serveur et côté agent
- Livraison confirmée (`RESULT_ACK`) avec store local agent
- Persistance OS cross-platform : systemd / launchd / Windows Task Scheduler

---

## Démarrage rapide

### Prérequis

- Python 3.10+
- OpenSSL (pour les certificats de lab)

```bash
pip install -r requirements.txt
```

### 1. Générer les certificats TLS

```bash
mkdir -p certs
openssl req -x509 -newkey rsa:2048 -days 365 -nodes \
  -keyout certs/server.key -out certs/server.crt \
  -subj '/CN=127.0.0.1' \
  -addext 'subjectAltName=IP:127.0.0.1,DNS:localhost'
chmod 600 certs/server.key
```

Pour le mTLS (optionnel) :
```bash
python -m shared.mtls generate-lab-certs
```

### 2. Démarrer le serveur

```bash
python -m server.main
```

Options complètes :
```
--host            Adresse d'écoute        (défaut : 127.0.0.1)
--port            Port TLS                (défaut : 9443)
--cert            Certificat serveur      (défaut : certs/server.crt)
--key             Clé privée serveur      (défaut : certs/server.key)
--task-timeout    Timeout tâches (s)      (défaut : 60)
--playbooks-dir   Dossier playbooks       (défaut : playbooks/)
--agent-ca        CA agent pour mTLS      (optionnel)
--log-file        Fichier de log          (optionnel)
```

### 3. Démarrer un agent

```bash
python -m agent.main --server 127.0.0.1 --port 9443 --ca certs/server.crt
```

Options complètes :
```
--server              Adresse du serveur C2
--port                Port TLS
--ca                  Certificat CA du serveur
--agent-id            ID fixe de l'agent (UUID aléatoire sinon)
--beacon-interval     Intervalle heartbeat (s)     (défaut : 30)
--beacon-jitter       Variation aléatoire (s)      (défaut : 5)
--reconnect-sessions  Nombre max de reconnexions   (0 = illimité)
--agent-cert          Certificat mTLS agent        (optionnel)
--agent-key           Clé privée mTLS agent        (optionnel)
```

---

## Commandes opérateur (CLI)

### Gestion des agents et sessions

| Commande | Description |
|---|---|
| `agents` | Liste les agents connectés |
| `sessions` | Historique de toutes les sessions |
| `ping <agent>` | PING avec mesure RTT |
| `disconnect <agent>` | Déconnecte un agent |

### Gestion des tâches

| Commande | Description |
|---|---|
| `tasks` | Liste toutes les tâches |
| `task <agent> <cmd> [args]` | Dispatch une tâche sur un agent |
| `result <task>` | Affiche la sortie d'une tâche |
| `interrupted` | Journal des tâches interrompues |
| `retry <task>` | Relance une tâche (lecture seule uniquement) |

### Commandes agent disponibles

| Commande | Description |
|---|---|
| `echo --text <msg>` | Renvoie le message |
| `get_info` | Hostname, OS, IP, username |
| `sysinfo` | Inventaire complet : CPU, RAM, réseau, processus |
| `shell --cmd <cmd>` | Exécute une commande shell (allowlist : `pwd`, `whoami`, `uname`) |
| `shellcode --name <file>` | Exécute un binaire depuis `lab_dir` |
| `upload --name <file>` | Envoie un fichier au serveur |
| `download --name <file>` | Dépose un fichier sur l'agent |
| `persist --action install\|remove --server <ip>` | Persistance OS |
| `self_remove` | Auto-suppression de l'agent |

### Automatisation (playbooks)

| Commande | Description |
|---|---|
| `playbooks` | Liste les playbooks disponibles |
| `playbook show <name>` | Inspecte un playbook |
| `playbook validate <name>` | Valide avant exécution |
| `playbook run <name> <agent>` | Exécute un playbook |
| `playbook cancel <run>` | Annule un run en cours |
| `runs` | Historique des runs |
| `run <run>` | Détail step-by-step d'un run |
| `triggers` | Liste les déclencheurs actifs |
| `trigger add <event> <playbook>` | Enregistre un déclencheur |

### Playbooks intégrés

| Nom | Description |
|---|---|
| `agent_inventory` | Ping → get_info → sysinfo → whoami → uname |
| `connectivity` | 3× echo → whoami → get_info (test de fiabilité) |
| `file_integrity` | Upload → download → vérification SHA-256 |

---

## Exemple de session complète

```
# Terminal 1 — serveur
$ python -m server.main --log-file server.log
[C2] Listening on 127.0.0.1:9443
c2> agents
  (aucun agent connecté)

# Terminal 2 — agent
$ python -m agent.main --server 127.0.0.1 --ca certs/server.crt
[AGENT] Connected, session a1b2c3d4

# Terminal 1 — opérateur
c2> agents
  ID        Hostname    Platform  Status
  a1b2c3d4  mybox       Linux     IDLE

c2> task a1b2 sysinfo
  [task dispatched: task-uuid]

c2> result task-uuid
  {"os": "Linux", "cpu": "...", "interfaces": [...]}

c2> task a1b2 persist --action install --server 127.0.0.1
  [task dispatched]

c2> trigger add agent_connected agent_inventory
  [trigger registered]
```

---

## Tests

```bash
python -m pytest tests/ -v
# 390 passés / 1 ignoré (macOS uniquement) / 0 échoués / 0 warnings
```

Le test ignoré (`test_macos_ifconfig_method`) nécessite le format ABI natif d'`ifconfig` Darwin — il ne peut pas être mocké sans réimplémenter le parser. Tous les autres chemins macOS et Windows sont couverts par des tests unitaires avec mocking.

---

## Structure du projet

```
PA-MVP/
├── server/
│   ├── main.py              # Serveur C2, CLI Rich, dispatch
│   ├── task_manager.py      # Machine à états des tâches
│   ├── automation.py        # Moteur de playbooks
│   └── storage/
│       └── database.py      # Persistance SQLite
├── agent/
│   ├── main.py              # Session TLS, queue de tâches, execute_allowed()
│   ├── local_state.py       # Store SQLite local (résultats en attente)
│   ├── persistence.py       # systemd / launchd / Task Scheduler
│   └── local_install.py     # Manifeste d'installation
├── shared/
│   ├── protocol.py          # Framing JSON Lines, types, constantes
│   ├── lab_transfer.py      # I/O fichiers sandbox (O_NOFOLLOW, SHA-256)
│   ├── mtls.py              # Contextes TLS serveur et client
│   └── platform_compat.py  # Abstraction plateforme
├── tests/                   # 390 tests
├── playbooks/               # Playbooks YAML
├── docs/                    # Documentation technique
│   ├── protocol.md          # Protocole de communication
│   ├── architecture.md      # Architecture système
│   ├── network-schema.md    # Schéma réseau et configuration lab
│   ├── kill-chain.md        # Analyse de la kill chain (MITRE ATT&CK)
│   └── countermeasures.md   # Contre-mesures et détection
├── certs/                   # Certificats TLS (générés localement)
├── data/                    # Lab dir agent + SQLite serveur
├── requirements.txt
└── README.md
```

---

## Sécurité et périmètre

- **Liste blanche stricte** : toutes les commandes passent par `ALLOWED_COMMANDS` — aucune commande arbitraire n'est possible.
- **`shell` restreint** : uniquement `pwd`, `whoami`, `uname` — sans métacaractères, sans expansion de shell.
- **`shell=False` partout** : aucun `subprocess.run(..., shell=True)` dans le code de production.
- **Sandbox fichiers** : tous les transferts confinés à `lab_dir` avec `O_NOFOLLOW`, `O_EXCL`, validation du nom, SHA-256.
- **TLS 1.2+ forcé** : `ctx.minimum_version = ssl.TLSVersion.TLSv1_2`.
- **127.0.0.1 par défaut** : le serveur n'écoute pas sur le réseau sans configuration explicite.

---

## Documentation

| Document | Description |
|---|---|
| [`docs/protocol.md`](docs/protocol.md) | Protocole de communication — types de messages, machine à états, sécurité |
| [`docs/architecture.md`](docs/architecture.md) | Architecture système — composants, flux de données, schéma |
| [`docs/network-schema.md`](docs/network-schema.md) | Schéma réseau — topologie lab, VMware, génération certificats |
| [`docs/kill-chain.md`](docs/kill-chain.md) | Analyse de la kill chain — phases d'attaque, MITRE ATT&CK |
| [`docs/countermeasures.md`](docs/countermeasures.md) | Contre-mesures — détection, réponse à incident, défense en profondeur |
