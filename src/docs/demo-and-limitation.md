# Démonstration orale et limites connues

## Scénario conseillé (3–5 minutes)

1. Montrer le schéma d'architecture et rappeler que le serveur est lié à `127.0.0.1`.
2. Démarrer le serveur et un ou deux agents dans le laboratoire.
3. Afficher `agents` et `sessions` pour démontrer l'enregistrement.
4. Exécuter `task <agent> get_info`, puis `task <agent> echo test-lab`.
5. Exécuter `task <agent> shell whoami` pour montrer la liste blanche ; essayer `task <agent> shell whoami;cat /etc/passwd` et montrer que la CLI refuse l'entrée.
6. Afficher `tasks` et `result <préfixe>` pour montrer le suivi d'état et la persistance SQLite.
7. Démontrer `task <agent> upload sample.txt` et `task <agent> download sample.txt`, puis comparer les fichiers du dossier de labo de chaque côté.
8. Exécuter `disconnect <agent>` dans la CLI (en laissant l'agent tourner) et vérifier via `sessions` qu'un nouveau `session_id` apparaît pour le même `agent_id` ; refaire `task <agent> echo OK`.
9. Terminer avec `quit` et présenter les tests automatisés et les limites.

## Critères à expliquer à l'oral

- TLS protège la confidentialité et l'intégrité du canal ; le certificat de démonstration est auto-signé.
- Le serveur ne confond pas envoi, réception et exécution : `WAITING_ACK`, `QUEUED`, `RUNNING`, puis un état terminal.
- Le stockage des états et résultats utilise SQLite ; les transitions illégales et certains doublons sont rejetés.
- Les tâches **lecture-seule** (`echo`, `get_info`, `shell` allowlisté) sont automatiquement rejouées après reconnexion via `get_auto_replayable_interruptions`. Les transferts de fichiers et commandes de cycle de vie ne sont **pas** rejouées automatiquement (risque d'exécution double documenté).
- La commande `shell` n'est pas un shell général : elle exécute uniquement trois commandes exactes, en lecture seule, sans interpréteur shell.

## Limites à ne pas masquer

Le projet intègre désormais : transferts de fichiers TLS (upload/download), beacon périodique, reconnexion bornée, journal d'interruptions SQLite, watchdog de timeout de tâche, replay automatique des tâches lecture-seule, persistance OS (systemd/launchd/Task Scheduler), mTLS, `sysinfo` complet, exécution de binaire sandboxée (`shellcode`), `self_remove` avec suppression réelle des fichiers installés, et une CLI Rich interactive. 295 tests passent dont plusieurs sur vraie connexion TLS loopback. Une démonstration manuelle en WSL2 avec deux agents distincts reste recommandée pour la soutenance.

## Après la démonstration

Arrêter le serveur et les agents, conserver le dossier de code et les logs nécessaires au rapport, puis supprimer les données de test manuellement. Ne pas installer l'agent comme service persistant sur une machine personnelle ou de production.

## Mise à jour du 25/10/2026 — contrôles supplémentaires

Voir `docs/durable-recovery-and-decommission.md` depuis la racine du projet pour le détail actualisé : journal d'interruption SQLite, reprise après redémarrage du serveur sans rediffusion automatique, `ping`/`PONG` réel, `interrupted` et `retry` en lecture seule, et commande distante `self_remove` **supprimant les fichiers installés** quand l'agent tourne depuis une copie `pa-agent-lab-*` (vérification de manifeste incluse), ou limitée au marqueur temporaire depuis l'arbre source. La persistance OS est implémentée via `agent/persistence.py` (systemd, launchd, Task Scheduler). Le replay automatique des tâches lecture-seule est actif depuis le handler SYNC_COMPLETE.
