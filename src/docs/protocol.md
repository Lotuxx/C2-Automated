# Protocole de communication — PA-C2

## 1. Transport

| Propriété | Valeur |
|---|---|
| Transport | TCP avec TLS 1.2+ obligatoire |
| Authentification serveur | Certificat X.509 validé côté agent (`--ca`) |
| mTLS optionnel | `--agent-ca` côté serveur + `--agent-cert/--agent-key` côté agent |
| Cadrage | JSON Lines — une ligne UTF-8 par message (`\n`) |
| Taille maximale d'un message | 1 Mio (newline incluse) |
| `StreamReader` interne | Limite 4 Mio (buffer TLS) |
| Version applicative | `version: 1` |

---

## 2. Enveloppe commune

Tous les messages partagent la même structure JSON :

```json
{
  "version": 1,
  "message_id": "<uuid>",
  "type": "TASK",
  "agent_id": "<agent-uuid-ou-null>",
  "session_id": "<session-uuid-ou-null>",
  "timestamp": "2026-10-26T20:00:00.000000Z",
  "payload": {}
}
```

**Identifiants — distinctions importantes :**

| Identifiant | Rôle |
|---|---|
| `message_id` | Identifie un message précis (déduplication par session, `deque(maxlen=256)`) |
| `task_id` | Identifie un travail à effectuer (stable à travers les reconnexions) |
| `result_id` | Identifie un résultat (détection des doublons de RESULT) |
| `session_id` | Identifie une connexion TLS active |

---

## 3. Catalogue des types de messages

| Type | Direction | Rôle |
|---|---|---|
| `REGISTER` | Agent → Serveur | Déclare `agent_id`, `hostname`, `platform` |
| `REGISTER_ACK` | Serveur → Agent | Confirme et attribue `session_id` |
| `SYNC_STATE` | Agent → Serveur | Liste les tâches en cours + résultats en attente de `RESULT_ACK` |
| `SYNC_STATE_RESPONSE` | Serveur → Agent | Accusé de synchronisation |
| `SYNC_COMPLETE` | Serveur → Agent | Autorise le traitement normal (tâches bloquées annulées côté serveur) |
| `BEACON` | Agent → Serveur | Heartbeat périodique + état `IDLE / BUSY / DEGRADED` |
| `BEACON_ACK` | Serveur → Agent | Accusé du beacon |
| `PING` | Bidirectionnel | Vérification de disponibilité (mesure RTT côté CLI) |
| `PONG` | Bidirectionnel | Réponse à `PING`, corrélé par `reply_to` |
| `TASK` | Serveur → Agent | `task_id`, `command`, `parameters` |
| `TASK_ACK` | Agent → Serveur | Confirmation de réception (PENDING → QUEUED) |
| `TASK_STATUS` | Agent → Serveur | Progression : `RUNNING` |
| `RESULT` | Agent → Serveur | `task_id`, `result_id`, statut terminal, sortie |
| `RESULT_ACK` | Serveur → Agent | Confirmation de persistance SQLite (permet purge du store local) |
| `TASK_STATUS_QUERY` | Serveur → Agent | Demande le statut courant d'une tâche |
| `TASK_STATUS_RESPONSE` | Agent → Serveur | Répond avec statut + liste des tâches en cours |
| `ERROR` | Bidirectionnel | Erreur non fatale de protocole ou de traitement |

---

## 4. Machine à états des tâches

```
PENDING
  │
  ▼
WAITING_ACK ──── timeout ───► TIMEOUT
  │
  ▼ (TASK_ACK reçu)
QUEUED
  │
  ▼ (TASK_STATUS RUNNING reçu)
RUNNING ─── failure ──────────► FAILED
  │           └── timeout ────► TIMEOUT
  │
  ▼ (RESULT reçu)
COMPLETED
```

Depuis **tout état non terminal** : `CANCELLED` (opérateur ou déconnexion agent).

13 transitions définies dans `server/task_manager.py::ALLOWED_TRANSITIONS`. `validate_transition()` est le seul point d'entrée — aucune transition n'est possible sans passer par lui.

---

## 5. Cycle nominal d'une session

```
Agent                          Serveur
  │── REGISTER ───────────────►│
  │◄── REGISTER_ACK ───────────│
  │── SYNC_STATE ──────────────►│  (serveur annule les tâches bloquées)
  │◄── SYNC_STATE_RESPONSE ────│
  │◄── SYNC_COMPLETE ──────────│
  │                             │
  │  [session active]           │
  │── BEACON ──────────────────►│  (toutes les beacon_interval ± jitter secondes)
  │◄── BEACON_ACK ─────────────│
  │                             │
  │◄── TASK ───────────────────│
  │── TASK_ACK ────────────────►│  (PENDING → QUEUED)
  │── TASK_STATUS(RUNNING) ────►│  (QUEUED → RUNNING)
  │── RESULT ──────────────────►│  (RUNNING → COMPLETED/FAILED)
  │◄── RESULT_ACK ─────────────│  (agent purge son store local)
```

---

## 6. Beaconing configurable

| Paramètre | Défaut | Rôle |
|---|---|---|
| `--beacon-interval` | 30 s | Intervalle nominal entre beacons |
| `--beacon-jitter` | 5 s | Variation aléatoire uniforme [-jitter, +jitter] |
| Payload `status` | `IDLE / BUSY / DEGRADED` | Charge de la file de tâches agent |

---

## 7. Sécurité du protocole

| Contrôle | Implémentation |
|---|---|
| Taille max message | `MAX_MESSAGE_BYTES = 1 MiB` dans `read_message()` |
| Rate limiting | 60 messages/s par connexion (fenêtre glissante) |
| Déduplication | `deque(maxlen=256)` par session — REGISTER/BEACON/PING exclus |
| Re-registration bloquée | Guard `agent_id is not None` avant traitement REGISTER |
| Replay borné | Uniquement les commandes `read_only` (echo, get_info, shell, sysinfo) |
| Exactement-une-livraison | `RESULT_ACK` + store SQLite local agent (`local_state.db`) |

---

## 8. Limites documentées (décisions architecturales)

| Limitation | Justification |
|---|---|
| Pas de reprise de transfert partiel | Nécessite un protocole de chunking dédié ; hors scope pédagogique |
| Pas d'exactly-once delivery distribuée | Nécessite un log distribué (Raft/Paxos) ; délibérément exclu |
| Aucune compression | Données de lab < 128 Kio, gain négligeable |
