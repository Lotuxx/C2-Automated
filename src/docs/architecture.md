# Architecture — PA-C2

## 1. Vue d'ensemble

PA-C2 est un serveur de commande et contrôle entièrement asynchrone (Python `asyncio`). Il gère plusieurs agents simultanés via TLS, stocke toutes les données dans SQLite, et expose une CLI opérateur Rich.

```
┌─────────────────────────────────────────────────────────────┐
│                        OPÉRATEUR                            │
│              CLI Rich interactive (asyncio.to_thread)       │
└────────────────────────────┬────────────────────────────────┘
                             │
┌────────────────────────────▼────────────────────────────────┐
│                         SERVEUR C2                          │
│                                                             │
│  ┌─────────────────┐   ┌──────────────────┐                │
│  │  ConnectionMgr  │   │  AutomationMgr   │                │
│  │  TLS 1.2+       │   │  Playbooks/Steps │                │
│  └────────┬────────┘   └────────┬─────────┘                │
│           │                     │                           │
│  ┌────────▼─────────────────────▼─────────────────────┐    │
│  │                    C2Server core                    │    │
│  │  handle_client()  dispatch_task()  ping_agent()     │    │
│  │  _start_task_watchdog()  reconcile_process_restart()│    │
│  └────────────────────────┬────────────────────────────┘    │
│                           │                                  │
│  ┌────────────────────────▼────────────────────────────┐    │
│  │              Database (SQLite + asyncio.Lock)        │    │
│  │  agents  sessions  tasks  results                    │    │
│  │  task_interruptions  playbook_runs  playbook_steps   │    │
│  └─────────────────────────────────────────────────────┘    │
└────────────────────────────┬────────────────────────────────┘
                             │ TLS 1.2+ (JSON Lines)
              ┌──────────────┴──────────────┐
              │                             │
   ┌──────────▼──────────┐     ┌────────────▼─────────┐
   │       AGENT A        │     │       AGENT B         │
   │   agent/main.py      │     │   agent/main.py       │
   │                      │     │                       │
   │  Session TLS         │     │  Session TLS          │
   │  asyncio.Queue(8)    │     │  asyncio.Queue(8)     │
   │  Beacon loop         │     │  Beacon loop          │
   │  execute_allowed()   │     │  execute_allowed()    │
   │  lab_dir/ sandbox    │     │  lab_dir/ sandbox     │
   │  local_state.db      │     │  local_state.db       │
   └──────────────────────┘     └──────────────────────┘
```

---

## 2. Responsabilités des composants

### 2.1 Serveur

| Fichier | Composant | Responsabilité |
|---|---|---|
| `server/main.py` | `C2Server` | Connexions TLS, dispatch des tâches, CLI opérateur, shutdown propre |
| `server/main.py` | `cli()` | REPL Rich — toutes les commandes opérateur |
| `server/task_manager.py` | `TaskManager` | Machine à états — unique point d'autorisation des transitions |
| `server/storage/database.py` | `Database` | Façade SQLite avec `asyncio.Lock` — toute la persistance |
| `server/automation.py` | `AutomationManager` | Exécution des playbooks YAML, retry, triggers, historique |

### 2.2 Agent

| Fichier | Composant | Responsabilité |
|---|---|---|
| `agent/main.py` | `_run_session()` | Session TLS complète — boucle de réception, queue de tâches |
| `agent/main.py` | `execute_allowed()` | Dispatcher des commandes — liste blanche stricte |
| `agent/main.py` | Beacon loop | Heartbeat périodique configurable (interval + jitter) |
| `agent/local_state.py` | `AgentLocalState` | Store SQLite local — résultats en attente de `RESULT_ACK` |
| `agent/persistence.py` | `install/remove` | Démarrage OS — systemd / launchd / Windows Task Scheduler |
| `agent/local_install.py` | `LocalInstall` | Manifeste d'installation — contrôle `self_remove` |

### 2.3 Partagé

| Fichier | Responsabilité |
|---|---|
| `shared/protocol.py` | Framing JSON Lines, validation, constantes (`MAX_MESSAGE_BYTES`, `ALLOWED_TYPES`) |
| `shared/lab_transfer.py` | I/O de fichiers confiné à `lab_dir` (O_NOFOLLOW, O_EXCL, SHA-256) |
| `shared/mtls.py` | Contextes TLS serveur et client — `minimum_version = TLSv1_2` |
| `shared/platform_compat.py` | Abstraction plateforme (Linux / macOS / Windows) |

---

## 3. Flux de données

### 3.1 Dispatch d'une tâche

```
CLI opérateur                 C2Server              Database              Agent
     │                           │                      │                    │
     │── task <agent> <cmd> ────►│                      │                    │
     │                           │── create_task() ────►│                    │
     │                           │                      │ PENDING             │
     │                           │── send TASK ─────────────────────────────►│
     │                           │── update WAITING_ACK►│                    │
     │                           │                      │            ◄── TASK_ACK
     │                           │── update QUEUED ────►│                    │
     │                           │                      │        ◄── TASK_STATUS(RUNNING)
     │                           │── update RUNNING ───►│                    │
     │                           │                      │              ◄── RESULT
     │                           │── complete_task() ──►│                    │
     │                           │── send RESULT_ACK ───────────────────────►│
     │                           │                      │      (purge store local)
```

### 3.2 Reconnexion d'un agent

```
Agent (redémarre)              Serveur
  │── REGISTER ──────────────►│  (même agent_id → session récupérée)
  │── SYNC_STATE ─────────────►│  (signale résultats non confirmés)
  │                            │── interrupt_task() sur tâches bloquées
  │◄── SYNC_COMPLETE ──────────│  (session opérationnelle)
  │── RESULT (pending) ───────►│  (résultats stockés dans local_state.db)
  │◄── RESULT_ACK ─────────────│
```

---

## 4. Persistance SQLite

### Schéma (tables principales)

| Table | Colonnes clés | Rôle |
|---|---|---|
| `agents` | `agent_id`, `hostname`, `platform`, `last_seen` | Registre des agents connus |
| `sessions` | `session_id`, `agent_id`, `connected_at`, `disconnected_at` | Historique des connexions |
| `tasks` | `task_id`, `agent_id`, `command`, `status`, `created_at` | État de chaque tâche |
| `results` | `result_id`, `task_id`, `output`, `created_at` | Sorties des tâches |
| `task_interruptions` | `task_id`, `interrupted_at`, `reason` | Journal de récupération |
| `playbook_runs` | `run_id`, `playbook_name`, `agent_id`, `status` | Runs d'automatisation |
| `playbook_steps` | `step_id`, `run_id`, `task_id`, `retry_count` | Steps et retries |

---

## 5. Sécurité de l'architecture

| Propriété | Implémentation |
|---|---|
| Pas de blocage de l'event loop | Toutes les opérations bloquantes via `asyncio.to_thread()` |
| Isolation des sessions | Chaque `handle_client()` est une coroutine indépendante |
| Liste blanche des commandes | `ALLOWED_COMMANDS` frozenset, vérifié avant toute exécution |
| Sandbox fichiers | `validate_name()` + `workspace_file()` confinés à `lab_dir` |
| `shell=False` partout | Aucun `subprocess.run(..., shell=True)` dans le code de production |
| Isolation DB | `asyncio.Lock` sur toutes les écritures — pas de race condition |

---

## 6. Métriques du code (v10)

| Métrique | Valeur |
|---|---|
| Lignes de code (production) | 7 013 |
| Fichiers Python | 16 |
| Classes | 16 |
| Tests | 390 passés / 1 ignoré / 0 échoués |
| `bare except:` | 0 |
| `shell=True` effectif | 0 |
| `eval` / `exec` / `pickle` | 0 |
| `ResourceWarning` | 0 |
