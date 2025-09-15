# Utiliser une image Python légère
FROM python:3.11-slim

# Définir le répertoire de travail dans le conteneur
WORKDIR /app

# CORRECTION : Installer curl, qui sera utilisé par le healthcheck de Docker Compose.
# On met à jour les listes de paquets, on installe, puis on nettoie le cache pour garder l'image légère.
RUN apt-get update && apt-get install -y curl && rm -rf /var/lib/apt/lists/*

# Copier le fichier des dépendances et les installer
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copier le reste du code de l'application
COPY . .

# La commande à exécuter sera spécifiée dans docker-compose.yml