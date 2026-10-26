# Periodic agent check-ins

The network agent now sends periodic BEACON messages after SYNC_COMPLETE, in addition to its initial check-in. The server responds with BEACON_ACK.

Example: python -m agent.main --beacon-interval 10 --beacon-jitter 2

Interval range: 1–3600 seconds; jitter: 0–min(interval/2, 300) seconds.

Remote TLS file transfer and bounded reconnection after established connection loss have since been added and loopback TLS integration-tested; see `remote-transfers-and-reconnection.md`. OS persistence and self-removal remain unimplemented. The `lab` CLI remains local-only.

## Mise à jour — contrôles supplémentaires

Voir `docs/audit-handoff.md` pour la matrice de conformité complète et `docs/durable-recovery-and-decommission.md` pour le comportement détaillé de `self_remove` (suppression réelle des fichiers installés depuis v3), du journal d'interruptions SQLite, du watchdog de timeout, et du replay automatique des tâches lecture-seule. La persistance OS est désormais implémentée (systemd / launchd / Task Scheduler) via `agent/persistence.py`.
