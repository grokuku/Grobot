# app/database/base.py

from sqlalchemy.orm import declarative_base

# Instance unique de Base pour toute l'application.
# Tous les modèles SQLAlchemy (sql_models) doivent l'importer et en hériter.
Base = declarative_base()