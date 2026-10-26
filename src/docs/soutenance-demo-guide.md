# Guide de démonstration — Soutenance PA-C2

## Prérequis

```bash
pip install -r requirements.txt
openssl req -x509 -newkey rsa:2048 -days 365 -nodes \
  -keyout certs/server.key -out certs/server.crt \
  -subj '/CN=127.0.0.1' -addext 'subjectAltName=IP:127.0.0.1,DNS:localhost'
mkdir -p data/server_files data/server_downloads data/agent_files
cp samples/sample.txt data/server_files/
```

## Séquence de démonstration (15-20 minutes)

### Étape 1 — Lancer le serveur (terminal 1)

```bash
python -m server.main --host 127.0.0.1 --port 9443 --log-file server.log
```

La CLI affiche la bannière Rich. Taper `help` pour voir toutes les commandes.

### Étape 2 — Lancer l'agent A (terminal 2)

```bash
python -m agent.main --server 127.0.0.1 --port 9443 \
  --ca certs/server.crt --beacon-interval 10
```

### Étape 3 — Lancer l'agent B (terminal 3)

```bash
python -m agent.main --server 127.0.0.1 --port 9443 \
  --ca certs/server.crt --beacon-interval 10 \
  --agent-id lab-agent-b
```

### Étape 4 — Vérifications de base (CLI serveur)

```
[c2]> agents           # Montrer 2 agents connectés (● vert)
[c2]> sessions         # Montrer 2 sessions distinctes
[c2]> tasks            # Tableau vide pour l'instant
```

### Étape 5 — Tâches individuelles

```
[c2]> task <prefix-A> echo "hello C2"
[c2]> result <task-prefix>      # Voir le résultat avec panel vert
[c2]> task <prefix-A> get_info  # Identification de l'agent
[c2]> task <prefix-A> shell whoami
[c2]> ping <prefix-A>           # PONG avec latence RTT
```

### Étape 6 — Collecte d'informations système

```
[c2]> task <prefix-A> sysinfo
[c2]> result <task-prefix>      # JSON pretty-print: hostname, CPU, mémoire, réseau
```

### Étape 7 — Transfert de fichiers (128 KiB)

```
[c2]> task <prefix-A> upload sample.txt
[c2]> result <task-prefix>
[c2]> task <prefix-A> download sample.txt
[c2]> result <task-prefix>      # SHA-256 vérifié
```

**Point à expliquer :** Avant v7, le transfert de 128 KiB échouait en raison de la limite 64 KiB de `asyncio.StreamReader`. Le fix : `limit=4*1024*1024` sur `start_server` et `open_connection`.

### Étape 8 — Isolation des agents

```
[c2]> task <prefix-B> echo "agent B only"
[c2]> tasks           # Montrer que les tâches sont attribuées aux bons agents
```

### Étape 9 — Automation (playbook)

```
[c2]> playbooks                               # 3 playbooks intégrés
[c2]> playbook show agent_inventory           # Inspecter les étapes
[c2]> playbook validate agent_inventory       # ✓ Valid
[c2]> playbook run agent_inventory <prefix-A> # Lancer
[c2]> runs                                    # Suivre l'exécution
[c2]> run <run-prefix>                        # Détail step-by-step avec résultats
```

**Point à expliquer :** Le playbook `agent_inventory` exécute automatiquement : ping_check → get_id → sysinfo → whoami → hostname. Chaque étape attend le résultat de la précédente.

### Étape 10 — Déconnexion et reconnexion

```
[c2]> disconnect <prefix-A>   # Déconnexion forcée
# Observer l'agent reconnecter automatiquement dans les logs
[c2]> sessions                # Nouvelle session visible
[c2]> task <prefix-A> echo "after reconnect"
[c2]> result <task-prefix>    # Fonctionne toujours
```

### Étape 11 — Journal des interruptions

```
[c2]> interrupted    # Tâches interrompues (ex: tâche pendant déconnexion)
[c2]> result <interrupted-task-prefix>   # Montre la raison + hint retry
```

### Étape 12 — Historique durable SQLite

```
[c2]> tasks          # Toutes les tâches avec statuts colorés
[c2]> sessions       # Historique complet des sessions
```

## Fonctionnalités à NE PAS présenter comme complètes

- **Validation Windows complète** : code cross-platform présent, non testé sur hardware
- **mTLS en production** : fonctionnel mais requiert génération de certificats agents
- **Exactly-once delivery** : délibérément absent (risque de double exécution)
- **Transfer resume** : à re-émettre depuis le début si interrompu

## Réponses aux questions prévisibles

**"Comment gérez-vous le timeout d'une tâche ?"**
→ Un watchdog asyncio démarre après dispatch. Si aucun RESULT n'arrive avant `--task-timeout` (défaut 60s), `timeout_task()` marque atomiquement la tâche TIMEOUT dans SQLite et insère un enregistrement dans `task_interruptions`. Le watchdog se cancelle automatiquement si un RESULT arrive d'abord.

**"Que se passe-t-il si le serveur crashe ?"**
→ Au redémarrage, `reconcile_process_restart()` : ferme les sessions orphelines, marque les tâches RUNNING→FAILED, et nettoie les réservations `__pending_` laissées par des replays interrompus.

**"Comment garantissez-vous l'intégrité des fichiers transférés ?"**
→ SHA-256 calculé côté serveur avant envoi. L'agent recalcule SHA-256 après réception et rejette le fichier si les empreintes diffèrent. `O_EXCL` empêche l'écrasement accidentel.

**"Comment le playbook sait-il quand passer à l'étape suivante ?"**
→ `AutomationManager._execute_step()` dispatch la tâche via `dispatch_task()`, puis poll `db.get_task(task_id)` toutes les 200ms jusqu'à ce que le statut soit terminal (COMPLETED/FAILED/TIMEOUT/CANCELLED).

**"Pourquoi l'exécution n'est-elle plus bloquante depuis v7 ?"**
→ `execute_allowed()` est maintenant appelé via `asyncio.to_thread()` qui délègue au thread pool OS. L'event loop asyncio reste libre pour traiter PING, BEACON, et les signaux de shutdown pendant qu'une tâche s'exécute.
