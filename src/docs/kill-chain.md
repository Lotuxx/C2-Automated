# Analyse de la kill chain — PA-C2

> **Périmètre :** analyse pédagogique des phases d'attaque illustrées par le prototype dans un **laboratoire isolé et autorisé**. Ce document ne constitue pas un guide de déploiement malveillant.

---

## 1. Modèle de référence utilisé

L'analyse suit le modèle **MITRE ATT&CK** et le **Cyber Kill Chain** de Lockheed Martin. Chaque phase est mise en correspondance avec l'implémentation concrète du projet.

---

## 2. Kill chain — phase par phase

### Phase 1 — Reconnaissance

| Élément | Dans PA-C2 |
|---|---|
| Objectif attaquant | Identifier une cible, son OS, ses services exposés |
| Commande implémentée | `sysinfo` — collecte OS, CPU, mémoire, interfaces réseau, utilisateurs |
| Commande implémentée | `get_info` — hostname, platform, username, IP locale |
| Technique ATT&CK | T1082 (System Information Discovery), T1016 (Network Config Discovery) |

```
Opérateur → task <agent> sysinfo
          ← {"os": "Linux", "cpu": "...", "users": [...], "interfaces": [...]}
```

---

### Phase 2 — Établissement de la persistance

| Élément | Dans PA-C2 |
|---|---|
| Objectif attaquant | Survivre à un redémarrage de la machine |
| Commande implémentée | `persist install` — installe un service OS |
| Linux | Unité systemd `pa-agent-lab-<id>.service` dans `~/.config/systemd/user/` |
| macOS | LaunchAgent plist dans `~/Library/LaunchAgents/` |
| Windows | Tâche planifiée XML via Task Scheduler (`schtasks /Create`) |
| Technique ATT&CK | T1543.001 (Launch Agent), T1543.003 (Windows Service), T1053.005 (Scheduled Task) |

```
Opérateur → task <agent> persist --action install --server 127.0.0.1
          ← "service installed: pa-agent-lab-<id>"
```

---

### Phase 3 — Commande et contrôle (C2)

| Élément | Dans PA-C2 |
|---|---|
| Objectif attaquant | Maintenir un canal bidirectionnel chiffré avec l'agent |
| Canal | TCP/9443 avec TLS 1.2+ (JSON Lines) |
| Beaconing | Intervalle configurable + jitter (défaut : 30 s ± 5 s) |
| Évasion minimale | Intervalle variable, connexion sortante vers un port non standard |
| Technique ATT&CK | T1071.001 (Web Protocols), T1573.002 (Asymmetric Cryptography), T1102 (Beaconing) |

Le trafic de beaconing ressemble à :
```
Agent ──► BEACON {"status": "IDLE", "queue_depth": 0} ──► Serveur
Serveur ──► BEACON_ACK {} ──► Agent
(répété toutes les ~30 s)
```

---

### Phase 4 — Exécution de commandes

| Élément | Dans PA-C2 |
|---|---|
| Objectif attaquant | Exécuter du code arbitraire sur la cible |
| Commandes shell | `shell` — restreint à `pwd`, `whoami`, `uname` (allowlist stricte) |
| Exécution binaire | `shellcode` — binaire déposé dans `lab_dir`, header magic vérifié |
| Technique ATT&CK | T1059 (Command and Scripting Interpreter), T1106 (Native API) |

```
Opérateur → task <agent> shell --cmd whoami
          ← "user@machine"

Opérateur → task <agent> shellcode --name payload.bin
          ← (sortie de l'exécutable)
```

---

### Phase 5 — Collecte et exfiltration

| Élément | Dans PA-C2 |
|---|---|
| Objectif attaquant | Récupérer des fichiers depuis la cible |
| Commande implémentée | `download` — transfère un fichier de `lab_dir` vers le serveur |
| Commande implémentée | `upload` — dépose un fichier depuis le serveur vers `lab_dir` de l'agent |
| Limites | 128 Kio max, SHA-256 vérifié, confiné à `lab_dir` |
| Technique ATT&CK | T1041 (Exfiltration Over C2 Channel) |

```
Opérateur → task <agent> download --name rapport.pdf
          ← (contenu base64, SHA-256 vérifié)
```

---

### Phase 6 — Auto-suppression (Cleanup)

| Élément | Dans PA-C2 |
|---|---|
| Objectif attaquant | Effacer les traces et se retirer de la cible |
| Commande implémentée | `self_remove` — supprime les fichiers du manifeste d'installation |
| Contrôle | Seuls les fichiers listés dans le manifeste installé sont supprimés |
| Technique ATT&CK | T1070 (Indicator Removal), T1485 (Data Destruction — scope limité) |

```
Opérateur → task <agent> self_remove
          ← "removed 3 files: pa-agent-lab-<id>, service file, marker"
```

---

## 3. Tableau de synthèse MITRE ATT&CK

| Phase | Tactique | Technique | Commande PA-C2 |
|---|---|---|---|
| Reconnaissance | Discovery | T1082 — System Info | `sysinfo` |
| Reconnaissance | Discovery | T1016 — Network Config | `sysinfo`, `get_info` |
| Persistance | Persistence | T1543.001 — Launch Agent | `persist install` (macOS) |
| Persistance | Persistence | T1543.003 — Windows Service | `persist install` (Windows) |
| Persistance | Persistence | T1053.005 — Scheduled Task | `persist install` (Windows alt) |
| Persistance | Persistence | T1501 — systemd service | `persist install` (Linux) |
| C2 | Command and Control | T1573.002 — TLS | Canal TLS 1.2+ |
| C2 | Command and Control | T1571 — Non-standard Port | TCP/9443 |
| C2 | Command and Control | T1102 — Beaconing | `BEACON` périodique |
| Exécution | Execution | T1059 — Shell | `shell` (allowlist) |
| Exécution | Execution | T1106 — Native API | `shellcode` |
| Collecte | Collection | T1005 — Local Data | `download` |
| Exfiltration | Exfiltration | T1041 — Over C2 | `upload`/`download` |
| Effacement | Defense Evasion | T1070 — Indicator Removal | `self_remove` |

---

## 4. Limites du prototype (hors scope pédagogique)

Les techniques suivantes **ne sont pas implémentées** dans PA-C2 — délibérément, pour maintenir l'usage strictement pédagogique :

| Technique non implémentée | Raison de l'exclusion |
|---|---|
| Process injection (T1055) | Hors scope — nécessite des privilèges élevés et un OS cible spécifique |
| Obfuscation de trafic (domain fronting, DNS tunneling) | Bonus non implémenté — détaillé ci-dessous |
| Mouvement latéral (T1021) | Hors scope — un seul agent cible dans le lab |
| Exfiltration volumique (> 128 Kio) | Intentionnellement limité par l'architecture |
| Élévation de privilèges (T1548) | Hors scope sécurité |

---

## 5. Canaux de communication alternatifs (bonus non implémenté)

L'architecture prévoit les extensions suivantes (conçues, non codées) :

| Canal | Description | Détection typique |
|---|---|---|
| HTTP/HTTPS | Encapsuler JSON Lines dans POST avec user-agent légitime | Analyse comportementale HTTP, JA3 fingerprint |
| DNS | Données en sous-domaines, polling TXT records | Volume DNS anormal, domaines générés (DGA) |
| Raw TCP | Canal actuel — directement détectable | Inspection de port, DPI sur pattern JSON |

La structure modulaire de `shared/protocol.py` permet d'ajouter un transport sans modifier la logique de session.
