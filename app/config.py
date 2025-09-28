#### Fichier : app/config.py
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    """
    Gère les paramètres de l'application en les lisant
    depuis les variables d'environnement.
    """
    # Configuration pour charger depuis le fichier .env
    model_config = SettingsConfigDict(env_file='.env', env_file_encoding='utf-8', extra='ignore')

    # Paramètres de la base de données PostgreSQL
    POSTGRES_USER: str
    POSTGRES_PASSWORD: str
    POSTGRES_DB: str
    POSTGRES_HOST: str = "db"  # Nom du service dans docker-compose
    POSTGRES_PORT: int = 5432

    # Paramètres de la base de données ChromaDB
    CHROMA_HOST: str = "chromadb" # Nom du service dans docker-compose
    CHROMA_PORT: int = 8000

    # --- NOUVEAU PARAMÈTRE AJOUTÉ ---
    # Paramètres pour Redis (utilisé pour Celery et le cache de session de chat)
    REDIS_URL: str = "redis://redis:6379/0"

    @property
    def database_url(self) -> str:
        """
        Construit l'URL de connexion à la base de données à partir des paramètres.
        """
        return f"postgresql+psycopg://{self.POSTGRES_USER}:{self.POSTGRES_PASSWORD}@{self.POSTGRES_HOST}:{self.POSTGRES_PORT}/{self.POSTGRES_DB}"

# Instance unique des paramètres pour l'ensemble de l'application
settings = Settings()