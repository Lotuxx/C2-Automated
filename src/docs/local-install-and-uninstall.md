# Installation et désinstallation réelles de l'agent (laboratoire local)

Cette fonctionnalité **désinstalle réellement les fichiers du programme** d'une installation jetable préparée par `agent.local_install`. Elle n'est **pas** une commande distante du C2 et ne permet pas l'effacement autonome du code de l'agent. Le contrôle à distance `self_remove` continue uniquement à terminer proprement son processus et à nettoyer son marqueur temporaire.

## Pourquoi deux étapes ?

Le processus est volontairement explicite :

1. L'opérateur installe une copie distincte de l'agent dans un dossier dédié.
2. L'agent fonctionne depuis ce dossier avec des fichiers d'essai conservés **à l'extérieur de l'installation**.
3. Depuis le C2, `task <agent> self_remove` provoque l'arrêt propre de l'agent (pas la désinstallation).
4. Sur le système qui héberge l'agent, l'opérateur prévisualise la désinstallation puis autorise localement la suppression du **programme installé**.

Aucune tâche réseau, aucun redémarrage automatique, aucun service système et aucun script détaché n'est utilisé pour déclencher la suppression du code.

## Instructions à reproduire depuis la racine du projet (WSL2 / Linux)

Dans le terminal de l'agent, depuis le dépôt `PA-MVP/` :

```bash
# Installer seulement les modules nécessaires à l'agent (pas le serveur).
python -m agent.local_install install --target "$HOME/pa-agent-lab-demo"

# Chemin absolu pour le certificat généré à la section TLS du README.
CERT="$(pwd)/certs/server.crt"

# Créer un dossier de données distinct, qui ne sera jamais effacé
# automatiquement par le désinstalleur du programme.
mkdir -p "$HOME/pa-agent-test-data"

cd "$HOME/pa-agent-lab-demo"
python -m agent.main --server 127.0.0.1 --port 9443 \
  --ca "$CERT" --lab-dir "$HOME/pa-agent-test-data" \
  --agent-id pa-lab-demo
```

Dans le terminal serveur C2 :

```text
agents
task <agent_id> get_info
task <agent_id> self_remove
tasks
result <task_id>
```

Après la fin du processus agent, revenir dans un répertoire **extérieur à l'installation**, par exemple depuis un troisième terminal ouvert sur le dépôt d'origine :

```bash
# Prévisualisation, aucune suppression :
python -m agent.local_install uninstall --target "$HOME/pa-agent-lab-demo"

# Confirmation explicite, suppression des fichiers du programme,
# des caches Python et du dossier d'installation :
python -m agent.local_install uninstall --target "$HOME/pa-agent-lab-demo" --execute

test ! -e "$HOME/pa-agent-lab-demo" && echo 'Installation supprimée'
```

Le programme `agent.local_install` est également copié dans le dossier installé. L'exécuter depuis un **dossier extérieur à l'installation** si le dépôt original est absent. L'absence de l'agent installé ne signifie **pas** que les données de laboratoire extérieures, le serveur, l'historique SQLite ou le dépôt source ont été effacés.

## Protection des fichiers

- Dossier d'installation inexistant à l'installation et nommé `pa-agent-lab-...`.
- Manifeste local contenant une liste fixe de fichiers Python copiés lors de l'installation.
- Vérification du nom, de l'emplacement et de l'identifiant du manifeste avant désinstallation.
- Refus si un lien symbolique, un fichier inconnu, un sous-dossier non attendu ou un manifeste modifié est rencontré.
- Aucun chemin issu du manifeste ne sert directement de cible de suppression : la liste des modules est définie dans le code.
- Mode aperçu par défaut ; `--execute` est requis pour réellement retirer le programme.
- Aucun nettoyage des fichiers déposés dans `--lab-dir`, qui doit rester distinct de l'installation.
- Pas d'élévation de privilèges, de mécanisme caché ni d'inscription au démarrage du système.

**Limite :** ce désinstalleur gère uniquement les installations créées par l'outil. Il ne tente pas de supprimer des agents copiés manuellement ailleurs, ni des fichiers d'utilisateurs, ni les artefacts gérés par des gestionnaires de paquets. Ne pas présenter ceci comme une commande distante d'effacement intégral ni comme une preuve d'effacement sécurisé du disque.

## Tests

```bash
python -m unittest tests.test_local_agent_uninstall -v
python -m unittest discover -s tests -q
```

Les tests incluent : exécution de la copie installée, contrôle de l'aperçu, suppression réelle, caches Python, chemins non conformes, fichier utilisateur, lien symbolique et manifeste modifié.
