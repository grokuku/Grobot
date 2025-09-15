# app/database/sql_session.py

from sqlalchemy import create_engine
 
from sqlalchemy.orm import sessionmaker

from app.config import settings

# Création du moteur SQLAlchemy en utilisant l'URL de la base de données
# pool_pre_ping=True vérifie la validité d'une connexion avant son utilisation
engine = create_engine(
    settings.database_url,
    pool_pre_ping=True,
    pool_size=10,  # Increased pool size from default 5
    max_overflow=20  # Increased max overflow from default 10
)

# Création d'une classe SessionLocal configurée. Chaque instance de cette
# classe sera une session de base de données indépendante.
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def get_db():
    """
    Dépendance FastAPI qui fournit une session de base de données SQLAlchemy.
    
    Cette fonction est un générateur qui va :
    1. Créer et fournir une nouvelle session de base de données.
    2. S'assurer que la session est TOUJOURS fermée après la fin de la requête,
       même en cas d'erreur, grâce au bloc `finally`.
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()