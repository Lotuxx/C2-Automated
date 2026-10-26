# Contre-mesures — PA-C2

> Ce document décrit les mécanismes de détection et de défense applicables à un C2 ayant les capacités de PA-C2. Il est destiné à former à la défense, pas à l'attaque.

---

## 1. Détection réseau

### 1.1 Détection du beaconing

Le beaconing périodique de PA-C2 (défaut : 30 s ± 5 s) crée un pattern statistiquement détectable.

| Indicateur | Outil / Méthode |
|---|---|
| Connexions TCP sortantes périodiques vers un port non standard | SIEM — règle sur `dst_port=9443` avec régularité temporelle |
| Intervalles réguliers (même avec jitter) | Analyse de fréquence sur les flows NetFlow/sFlow |
| Volume faible et constant (keepalive) | Détection d'anomalie de volume par ML (Zeek, Darktrace) |
| Certificat TLS auto-signé | Inspection du champ `issuer` dans le handshake TLS |

**Règle Sigma (exemple) :**
```yaml
title: Suspicious periodic outbound TCP connection
detection:
  selection:
    dst_port: 9443
    direction: outbound
  condition: selection | count() by src_ip > 5 within 5m
```

### 1.2 Détection du trafic C2

| Indicateur | Description |
|---|---|
| Port 9443 non standard | Les services légitimes utilisent rarement ce port |
| SNI absent ou IP directe | Connexion TLS vers une IP sans hostname (CN=127.0.0.1) |
| Faible entropie du payload | JSON lisible si capturé avant TLS (mitm sur la VM) |
| Certificat de courte durée | Certs de lab expirés en 1 jour — flags dans les SIEM |

---

## 2. Détection système (endpoint)

### 2.1 Persistance OS

| Mécanisme PA-C2 | Indicateur détectable | Outil |
|---|---|---|
| Unité systemd user | Nouveau fichier dans `~/.config/systemd/user/*.service` | auditd, OSSEC, Falco |
| LaunchAgent macOS | Nouveau fichier dans `~/Library/LaunchAgents/*.plist` | EDR, File Integrity Monitoring |
| Tâche planifiée Windows | Création via `schtasks /Create` | Windows Event Log ID 4698 |

**Règle auditd (Linux) :**
```
-w /home -p w -k persistence_write
-a always,exit -F arch=b64 -S execve -F exe=/usr/bin/systemctl -k systemctl_enable
```

**Event Log Windows :**
```
EventID 4698 : A scheduled task was created
EventID 4702 : A scheduled task was updated
```

### 2.2 Exécution suspecte

| Indicateur | Description |
|---|---|
| `python -m agent.main` lancé depuis un répertoire inhabituel | Processus Python avec args C2 |
| Connexion réseau sortante depuis un interpréteur Python | `python3` ouvre une socket TCP — inhabituel |
| Fichiers exécutables dans `lab_dir/` | Binaires dans des répertoires données utilisateur |
| `subprocess.run(["whoami"])` depuis Python | Appel système depuis un processus Python |

### 2.3 Indicateurs de compromission (IoC)

| Type | Valeur exemple | Description |
|---|---|---|
| Fichier | `pa-agent-lab-*.py` | Script agent installé |
| Fichier | `pa-agent-lab-*.service` | Unité systemd |
| Fichier | `com.pa-c2.agent.*.plist` | LaunchAgent macOS |
| Fichier | `local_state.db` | Store SQLite local agent |
| Port | TCP/9443 | Port par défaut du C2 |
| Processus | `python.*agent\.main` | Agent en cours d'exécution |
| Répertoire | `data/agent_files/` | Sandbox de fichiers agent |

---

## 3. Contre-mesures défensives

### 3.1 Isolation réseau (prévention principale)

```
Principe : zero-trust sortant — aucune connexion non explicitement autorisée

Règles recommandées :
  - Allowlist des destinations autorisées (IP + port)
  - Inspection TLS (SSL bump) sur les connexions sortantes
  - Blocage des connexions vers des IP sans hostname SNI valide
  - DNS filtering — bloquer les domaines nouvellement créés
```

### 3.2 Durcissement des endpoints

| Mesure | Impact sur PA-C2 |
|---|---|
| Application allowlisting (AppLocker, Wazuh) | Bloque `python -m agent.main` si Python n'est pas dans la whitelist |
| Monitoring de l'intégrité des fichiers (FIM) | Détecte la création du service systemd / plist / tâche planifiée |
| EDR (Endpoint Detection & Response) | Détecte les connexions réseau depuis Python, les appels subprocess |
| Moindre privilège | L'agent ne peut écrire que dans `lab_dir` — limite la collecte |
| Désactiver les services utilisateur systemd | Empêche `systemctl --user enable` |

### 3.3 Détection comportementale

| Comportement | Baseline | Anomalie |
|---|---|---|
| Connexions TCP sortantes | ~10/heure pour une workstation | 2/minute vers un port non standard |
| Appels `whoami`/`uname` | 0-1/jour | Plusieurs fois en quelques secondes |
| Écriture dans `~/.config/systemd/` | Rare | Nouveau fichier `.service` |
| Volume réseau sortant | Variable | Faible et parfaitement régulier |

---

## 4. Réponse à incident

### 4.1 Identification

```bash
# Trouver les processus Python suspects
ps aux | grep "agent.main"

# Trouver les connexions vers le port C2
ss -tnp | grep 9443

# Chercher les unités systemd installées
find ~/.config/systemd/user/ -name "pa-agent-*"

# Chercher les fichiers agent
find /home -name "pa-agent-lab-*" 2>/dev/null
find /home -name "local_state.db" 2>/dev/null
```

### 4.2 Confinement

```bash
# Tuer l'agent
pkill -f "agent.main"

# Bloquer le port réseau
iptables -A OUTPUT -p tcp --dport 9443 -j DROP

# Désactiver le service systemd
systemctl --user disable pa-agent-lab-<id>.service
systemctl --user stop pa-agent-lab-<id>.service
```

### 4.3 Éradication (équivalent de `self_remove` côté défenseur)

```bash
# Supprimer le service systemd
rm ~/.config/systemd/user/pa-agent-lab-*.service
systemctl --user daemon-reload

# Supprimer les fichiers agent
rm -f pa-agent-lab-*.py local_state.db

# Supprimer le sandbox
rm -rf data/agent_files/
```

### 4.4 Préservation des preuves

Avant de supprimer :
```bash
# Copier les logs serveur
cp server.log /mnt/forensics/
cp pa_c2.db   /mnt/forensics/

# Dump mémoire du processus (si disponible)
gcore $(pgrep -f agent.main)

# Capture réseau
tcpdump -i any -w /mnt/forensics/capture.pcap port 9443
```

---

## 5. Défense en profondeur — synthèse

```
┌─────────────────────────────────────────────────────────┐
│                    DÉFENSE EN PROFONDEUR                │
│                                                         │
│  PRÉVENTION          DÉTECTION          RÉPONSE         │
│  ──────────          ─────────          ────────        │
│  Isolation réseau    SIEM (beaconing)   Isolation host  │
│  Application AL      EDR (processus)    Kill processus  │
│  Moindre privilège   FIM (persistance)  Suppression IoC │
│  mTLS (authentif.)   NetFlow (C2)       Forensics       │
│  Firewall sortant    auditd (syscalls)  Patch           │
└─────────────────────────────────────────────────────────┘
```

---

## 6. Ce que PA-C2 illustre pour la formation défensive

| Capacité C2 | Ce qu'elle apprend à détecter |
|---|---|
| Beaconing avec jitter | Analyse de fréquence des connexions réseau |
| TLS vers un port non standard | Inspection du SNI, blocage des IP directes |
| Persistance systemd | FIM sur `~/.config/systemd/`, auditd |
| `sysinfo` / `get_info` | Surveillance des appels système de discovery |
| `shellcode` + `lab_dir` | Détection d'exécutables dans des répertoires données |
| `self_remove` | Importance de la préservation des preuves AVANT suppression |
| Machine à états des tâches | Reconstruction de la timeline d'attaque depuis les logs C2 |
