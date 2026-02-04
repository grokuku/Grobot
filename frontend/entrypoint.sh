#!/bin/sh

# entrypoint.sh: gère le démarrage des services dans le conteneur.
set -e

echo "Correction des permissions..."
# On force l'appartenance des dossiers montés à l'utilisateur interne (souvent app_user)
# C'est ÇA qui règle ton erreur Permission Denied sur llm_interactions.md
mkdir -p /app/logs /app/files /app/data
chown -R app_user:app_group /app/files /app/logs /app/data

echo "Démarrage d'Uvicorn en tâche de fond (worker unique)..."
# On utilise gosu pour lancer l'appli Python en tant qu'utilisateur sécurisé
gosu app_user uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 1 &

echo "Démarrage de Nginx au premier plan..."
# Nginx se lance en root (il a besoin du port 80)
nginx -g 'daemon off;'