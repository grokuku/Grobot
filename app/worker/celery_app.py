import os
from celery import Celery

# Récupérer l'URL du broker depuis les variables d'environnement
CELERY_BROKER_URL = os.getenv("CELERY_BROKER_URL")

# Vérifier que la variable est bien définie pour éviter les erreurs silencieuses
if not CELERY_BROKER_URL:
    raise ValueError("La variable d'environnement CELERY_BROKER_URL n'est pas définie.")

# Créer l'instance de l'application Celery.
# Le nom de la variable 'celery' est important car c'est ce que la commande
# `celery -A app.worker.celery_app worker` cherche par défaut.
celery = Celery(
    'grobot_tasks',           # Nom de l'application Celery
    broker=CELERY_BROKER_URL,
    backend=CELERY_BROKER_URL # On utilise aussi Redis pour stocker les résultats des tâches
)

# Cette ligne permet à Celery de découvrir automatiquement les tâches
# que nous définirons plus tard dans `app/worker/tasks.py`.
celery.autodiscover_tasks(['app.worker'])