# Étape 1: Builder l'application Python sur une base Debian "slim"
# CHANGEMENT: Passage à 'slim-bullseye' pour une meilleure compatibilité des paquets
FROM python:3.11-slim-bullseye AS builder

# Empêcher Python de mettre en mémoire tampon les sorties stdout et stderr
ENV PYTHONUNBUFFERED=1

# Installer les dépendances système nécessaires pour la compilation sur Debian
# CHANGEMENT: Utilisation de apt-get et des noms de paquets Debian
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libpq-dev \
    libffi-dev \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Définir le répertoire de travail
WORKDIR /app

# Copier les dépendances et les installer
COPY requirements.txt .
# L'installation de onnxruntime fonctionnera maintenant car des wheels pré-compilées existent pour cette base
RUN pip install --no-cache-dir -r requirements.txt

# Copier le code de l'application Backend
COPY ./app /app/app
# Copier les fichiers statiques du frontend
COPY ./frontend/src /app/frontend_static

# --- Fin de l'Étape 1 (builder) ---

# Étape 2: Créer l'image finale avec Nginx sur une base Debian
# CHANGEMENT: Utilisation de 'nginx:stable-bullseye' pour garder la cohérence
FROM nginx:stable-bullseye AS final

# Installer 'gosu' (équivalent de 'su-exec' sur Debian) et la dépendance d'exécution libffi
# CHANGEMENT: Utilisation de apt-get et installation de gosu
# --- AJOUT ---: Ajout de 'libmagic1' pour la bibliothèque python-magic
RUN apt-get update && apt-get install -y --no-install-recommends gosu libffi7 libmagic1 \
    && rm -rf /var/lib/apt/lists/*

# Copier l'ENSEMBLE de l'installation Python (librairies, exécutables, etc.)
COPY --from=builder /usr/local/ /usr/local/

# Copier notre code d'application
COPY --from=builder /app/app /app

# Copier les fichiers statiques du frontend dans le répertoire racine de Nginx
COPY --from=builder /app/frontend_static /usr/share/nginx/html/
# Copier la configuration Nginx personnalisée
COPY frontend/nginx.conf /etc/nginx/conf.d/default.conf

# Créer un groupe et un utilisateur système pour notre application
RUN addgroup --system app_group && adduser --system --ingroup app_group app_user
# Donner la propriété du code de notre application à cet utilisateur
RUN chown -R app_user:app_group /app

# Copier et préparer le script de démarrage
COPY frontend/entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh && sed -i 's/\r$//' /entrypoint.sh

# Exposer le port 80 pour Nginx
EXPOSE 80

# Définir le script de démarrage comme commande principale.
CMD ["/entrypoint.sh"]