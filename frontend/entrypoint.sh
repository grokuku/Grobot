#!/bin/sh

# entrypoint.sh: gère le démarrage des services dans le conteneur.

# La commande 'set -e' arrête le script immédiatement si une commande échoue.
set -e

# Donner la propriété du répertoire des fichiers à l'utilisateur de l'application
chown -R app_user:app_group /app/files

# NOTE: La gestion de la base de données (création des tables) est désormais gérée
# directement par l'application (main.py) au démarrage via SQLAlchemy natif.
# L'étape explicite 'alembic upgrade' a été supprimée.

# Démarre le serveur Uvicorn en arrière-plan avec UN SEUL WORKER.
# C'est crucial pour que le gestionnaire de logs en mémoire (LogManager) soit partagé
# entre la connexion WebSocket et les requêtes POST qui soumettent les logs.
echo "Démarrage d'Uvicorn en tâche de fond (worker unique)..."
gosu app_user uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 1 &

# Démarre Nginx au premier plan.
# Nginx est lancé par 'root', ce qui lui permet de s'initialiser correctement.
echo "Démarrage de Nginx au premier plan..."
nginx -g 'daemon off;'