# PA - C2 automatisé

> **Usage strictement pédagogique et local.** Exécuter uniquement dans une VM/WSL de test dédiée, sur des systèmes dont vous avez l'autorisation. Le serveur écoute par défaut sur `127.0.0.1`. Ne pas exposer le port sur un réseau public.

## 1. Objectif

Ce dépôt est un prototype client/serveur asynchrone en Python. Le serveur gère plusieurs connexions d'agents, conserve les agents/sessions/tâches/résultats dans SQLite, chiffre le transport avec TLS 1.2 ou supérieur et expose une CLI opérateur.

## 2. État fonctionnel réel

| Élément | État dans cette version |
|---|---|
| Architecture client/serveur asynchrone | Implémentée |
| Plusieurs agents et sessions | Implémenté côté serveur ; reconnexion d'une session établie avec nouvel ID de session |
| Transport TLS 1.2+ | Implémenté ; certificat de laboratoire à générer localement |
| Protocole JSON Lines versionné | Implémenté dans `shared/protocol.py` |
| Cycle de tâche avec ACK, états et résultats persistés | Implémenté |
| CLI (`agents`, `sessions`, `tasks`, `result`, `task`, `ping`, `interrupted`, `retry`, `disconnect`) | Implémentée |
| `echo`, `get_info` | Implémentés |
| `shell` | **Liste blanche en lecture seule uniquement** : `pwd`, `whoami`, `uname`. Pas de shell arbitraire, pas de métacaractères. |
| Beacon | Initial et périodique, intervalle et variation configurables, accusé de réception |
| Upload / download | **Réels via TASK / RESULT sur TLS** ; uniquement fichiers de laboratoire ≤128 Kio, vérification SHA-256 |
| Persistance OS de l'agent | Non implémentée dans ce prototype |
| Auto-retrait de l'agent | `task ... self_remove` : arrêt propre distant et nettoyage du marqueur temporaire. **Désinstallation complète du programme : commande locale explicite séparée** (`agent.local_install uninstall --execute`) pour les copies installées avec cet outil. Pas d'effacement distant du code. |
| Reprise durable après interruption | Journal SQLite + réconciliation après redémarrage + `retry` manuel en lecture seule. Aucune reprise automatique des opérations en cours. |
| Agent Windows | Non testé / non garanti |

Cette matrice est volontairement explicite : ne présentez pas les fonctionnalités marquées « non implémentées » comme terminées. Si le barème les exige, elles constituent encore des écarts à traiter ou à justifier à l'oral.

## 3. Prérequis

- Python 3.10+ (tests effectués avec Python 3.13 dans l'environnement de vérification)
- OpenSSL pour créer le certificat de test
- Aucun paquet Python externe requis par le code applicatif

## 4. Préparer le certificat TLS

Depuis le dossier `src/` :

```bash
mkdir -p certs data
openssl req -x509 -newkey rsa:2048 -days 365 -nodes \
  -keyout certs/server.key -out certs/server.crt \
  -subj '/CN=127.0.0.1' \
  -addext 'subjectAltName=IP:127.0.0.1,DNS:localhost'
chmod 600 certs/server.key
```

Le certificat est auto-signé et sert de point de confiance à l'agent dans ce laboratoire. **Ne réutilisez pas cette clé de démonstration en production.** Le dépôt n'inclut volontairement pas de clé privée.

## 5. Lancer une démonstration locale

Terminal 1 — serveur :

```bash
python -m server.main --host 127.0.0.1 --port 9443
```

Terminal 2 — agent :

```bash
python -m agent.main --server 127.0.0.1 --port 9443 --ca certs/server.crt
```

Pour **deux agents lancés depuis la même copie du projet**, donnez-leur des dossiers de fichiers distincts afin d'éviter que leurs démonstrations interfèrent :

```bash
python -m agent.main --agent-id lab-agent-a --lab-dir data/agent_a_files
python -m agent.main --agent-id lab-agent-b --lab-dir data/agent_b_files
```

Ouvrez ces commandes dans deux terminaux différents. Un `agent_id` stable explicite permet aussi de reconnaître le même agent lors d'un redémarrage du processus.

Dans la CLI du serveur, utiliser `help`, puis :

```text
agents
sessions
task <préfixe_agent> get_info
task <préfixe_agent> echo Bonjour-lab
task <préfixe_agent> shell whoami
task <préfixe_agent> shell uname
ping <préfixe_agent>
tasks
result <préfixe_tâche>
```

Les identifiants abrégés affichés par `agents` et `tasks` peuvent être utilisés tant qu'ils sont uniques. `quit` arrête proprement le serveur et ferme les connexions.

### Transferts distants et reconnexion

Depuis le dossier du projet, créez un fichier de test :

```bash
mkdir -p data/server_files
cp samples/sample.txt data/server_files/sample.txt
```

Avec le serveur et l'agent démarrés, saisissez dans `c2>` :

```text
task <préfixe_agent> upload sample.txt
tasks
result <préfixe_tâche_upload>
task <préfixe_agent> download sample.txt
tasks
result <préfixe_tâche_download>
```

`upload` dépose le fichier dans `data/agent_files/sample.txt`, côté agent. `download` récupère ce même fichier dans `data/server_downloads/sample.txt`, côté serveur. Les **chemins complets ne sont pas acceptés** et un fichier déjà existant ne sera pas écrasé. Si vous réessayez, utilisez un nouveau nom ou supprimez manuellement vos fichiers d'essai. Pour tester une coupure : laissez l'agent actif et saisissez `disconnect <préfixe_agent>` dans la CLI serveur. Après reconnexion, `sessions` montre l'ancienne session `DISCONNECTED` et une nouvelle session `ACTIVE` pour le même agent. Lancez ensuite `task <préfixe_agent> echo OK`. Vous pouvez aussi arrêter et relancer le serveur dans la fenêtre de reconnexion configurée.

Voir [documentation de transfert et reconnexion](docs/remote-transfers-and-reconnection.md) pour les paramètres, tests et limites.

### Installation et désinstallation locales de l'agent

Une copie minimale de l'agent peut être installée dans un dossier jetable dédié, puis **réellement retirée** après arrêt :

```bash
python -m agent.local_install install --target "$HOME/pa-agent-lab-demo"
python -m agent.local_install uninstall --target "$HOME/pa-agent-lab-demo"  # aperçu
python -m agent.local_install uninstall --target "$HOME/pa-agent-lab-demo" --execute
```

**Important :** ce désinstalleur nécessite une action **locale** sur la machine où l'agent est installé. `self_remove` envoyé depuis le C2 n'efface toujours pas le programme Python. Consulter [la procédure de désinstallation](docs/local-install-and-uninstall.md) pour le cycle complet avec un agent connecté et les garanties de sécurité.

## 6. Tests

Depuis le dossier `src/` :

```bash
python -m compileall -q .
python -m unittest discover -s tests -v
```

Plusieurs anciens tests de connexion utilisent des mocks ; le nouveau test d'intégration `tests.test_remote_transfer_reconnect` crée un certificat TLS temporaire et utilise une vraie connexion réseau sur `127.0.0.1` (il requiert `openssl`). Les avertissements `ResourceWarning` de certaines connexions SQLite en mémoire sont émis par des tests existants et ne correspondent pas à un échec fonctionnel, mais ils pourraient être nettoyés dans une passe ultérieure.

## 7. Documentation

- [Architecture et diagramme réseau](docs/architecture.md)
- [Protocole de communication](docs/protocol.md)
- [Analyse de chaîne d'attaque et contre-mesures](docs/kill-chain-and-countermeasures.md)
- [Scénario de démonstration / limites](docs/demo-and-limitations.md)
- [Transferts distants et reconnexion](docs/remote-transfers-and-reconnection.md)
- [Installation et désinstallation locales contrôlées](docs/local-install-and-uninstall.md)
- [Prompt pour audit externe indépendant](docs/claude-independent-audit-prompt.md)

## 8. Limites importantes

L'agent ne conserve pas son état de tâches localement. Après une déconnexion ou un redémarrage du serveur, l'état des tâches interrompues est conservé dans SQLite, avec une trace de l'incertitude. La CLI `interrupted` liste ces événements et `retry <id>` autorise une unique relance **manuelle en lecture seule** ; les tâches ne sont jamais rejouées automatiquement. Les commandes distantes sont volontairement limitées. Ce prototype n'est pas un outil opérationnel et ne doit pas être utilisé hors d'un laboratoire autorisé.

## Démonstrations locales complémentaires

`python -m lab_demo.demo` présente des transferts, une planification de beacons et un cycle de vie simulé, uniquement dans un dossier temporaire local. Voir `docs/local-feature-demonstrations.md`. Ce ne sont pas des commandes distantes du C2.

## Lab commands inside the C2 CLI (local simulations only)

At the `c2>` prompt: `lab help`, then `lab init`, `lab upload`, `lab download`, `lab beacon 10 2 5`, `lab persist`, `lab self_destruct`. These are local-only simulations and **are not dispatched to agents**. See `docs/local-feature-demonstrations.md`.

## Real agent heartbeat

The agent sends periodic BEACON messages after registration. Example: `python -m agent.main --beacon-interval 10 --beacon-jitter 2`. See `docs/heartbeat-implementation.md` for limitations.

## État pour l'audit extérieur

Les commandes `task ... upload` et `task ... download` opèrent réellement sur l'agent. Les commandes `lab ...` restent des **simulations locales distinctes**. La reconnexion est réelle mais plafonnée ; la nouvelle gestion durable conserve l'historique des interruptions **sans reprendre automatiquement leur exécution**. La commande distante `self_remove` arrête proprement l'agent et supprime seulement son marqueur temporaire, **pas son code**. `docs/audit-handoff.md` donne une synthèse concise.

## Journal de reprise et retrait contrôlé (nouveau)

```text
ping <préfixe_agent>
interrupted
retry <préfixe_tâche_interrompue>
task <préfixe_agent> self_remove
```

- `interrupted` affiche les anciennes tâches dont le résultat est inconnu ou dont l'envoi n'a pas commencé ; le journal résiste à un redémarrage du serveur.
- `retry` **ne s'applique qu'aux tâches en lecture seule** et ne peut être invoqué qu'une fois par tâche d'origine.
- `self_remove` clôt la session et arrête le processus agent après réception du résultat final ; seul un marqueur d'exécution temporaire, créé par l'agent, est supprimé. Les fichiers transférés et l'installation restent intacts.

Voir [reprise durable et retrait contrôlé](docs/durable-recovery-and-decommission.md). Pour les tests : `python -m unittest discover -s tests -v`.
