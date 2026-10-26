# Analyse de chaîne d'attaque et contre-mesures

Cette analyse décrit les phases que l'architecture d'un outil de commande et contrôle pourrait traverser dans un **laboratoire autorisé**. Elle ne constitue pas un guide de déploiement malveillant. La persistance OS est implémentée (systemd/launchd/Task Scheduler via `agent/persistence.py`). L'auto-suppression distante est implémentée (`self_remove` supprime les fichiers installés depuis une copie `pa-agent-lab-*`, avec vérification de manifeste). Les transferts limités à des fichiers du laboratoire sont opérationnels.

| Phase conceptuelle | Illustration dans le prototype | Risque principal | Contre-mesures / traces |
|---|---|---|---|
| Préparation | Création manuelle d'un agent et d'un certificat de laboratoire | Binaire ou script non approuvé | Contrôle de provenance, signature des artefacts, inventaire des fichiers |
| Exécution | Lancement manuel de `python -m agent.main` | Exécution de code non autorisé | Allowlisting applicatif, journalisation des processus, moindre privilège |
| Commande et contrôle | Connexion TLS vers le serveur de laboratoire | Canal sortant abusif ou serveur usurpé | Egress filtering, validation stricte du certificat, surveillance DNS/IP/ports |
| Tâches | `TASK` suivi de `TASK_ACK`, `TASK_STATUS`, `RESULT` | Abus de commandes distantes | Liste blanche, contrôle des paramètres, logs horodatés, approbation humaine |
| Collecte / transfert | Upload/download réels, limités aux dossiers de laboratoire et à 128 Kio | Exfiltration de données | DLP, surveillance des volumes sortants, accès minimal aux fichiers, contrôle des chemins |
| Persistance | Pas de persistance OS implémentée | Maintien après redémarrage | Audit des services/tâches planifiées/entrées de démarrage et détection des changements |
| Effacement | Pas d'auto-suppression implémentée | Destruction de preuves ou de données | Sauvegardes, immutabilité des journaux, contrôle d'intégrité, séparation des privilèges |

## Défense en profondeur

1. **Isolation** : VM ou réseau host-only dédié, snapshots avant les tests, aucun routage vers les réseaux de production.
2. **Privilèges** : lancer l'agent et le serveur avec un compte non privilégié ; ne pas utiliser `sudo`.
3. **Réseau** : écoute loopback par défaut, pare-feu restrictif, règles sortantes explicites.
4. **TLS** : vérifier le certificat côté agent ; protéger la clé privée du serveur et la renouveler après les tests.
5. **Journalisation** : conserver les logs serveur, les états de tâches et les résultats ; horloges synchronisées.
6. **Réponse à incident** : isoler l'hôte, préserver les journaux et snapshots avant de supprimer des artefacts.
7. **Validation** : tester uniquement avec des agents et des fichiers de test créés pour l'exercice.

## Conclusion

Les mêmes mécanismes de session, de tâches et de canal chiffré sont pertinents pour comprendre et détecter un C2. Les contrôles les plus importants sont l'isolation du laboratoire, les privilèges minimaux, une liste blanche stricte et la traçabilité des tâches.
