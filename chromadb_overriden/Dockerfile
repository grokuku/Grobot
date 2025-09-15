# Utiliser l'image de base officielle de ChromaDB
FROM chromadb/chroma:latest

# Installer curl pour le healthcheck et nettoyer le cache
RUN apt-get update && apt-get install -y curl && rm -rf /var/lib/apt/lists/*