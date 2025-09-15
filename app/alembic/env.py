# alembic/env.py

import os
from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config
from sqlalchemy import pool

# --- DÉBUT DE LA CONFIGURATION SPÉCIFIQUE AU PROJET ---

# 1. Importer la Base de nos modèles SQLAlchemy
# Nous devons ajouter le chemin de notre application au sys.path
# pour que le script puisse trouver 'app.database.base'.
import sys
# On ajoute le répertoire parent (/app) au path pour que l'import 'from app...' fonctionne.
sys.path.insert(0, os.path.realpath(os.path.join(os.path.dirname(__file__), '..', '..')))

from app.database.sql_models import Base

# 2. Importer notre configuration d'application pour récupérer les variables d'environnement
from app.config import settings as app_settings

# --- FIN DE LA CONFIGURATION SPÉCIFIQUE AU PROJET ---


# Ceci est la configuration Alembic, qui a accès aux valeurs
# du fichier .ini via l'objet 'context'.
config = context.config

# Interprète le fichier de configuration pour le logging Python.
# Cette ligne configure principalement les loggers.
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# --- DÉBUT DE LA MODIFICATION DE LA CONNEXION ---

# 3. Définir la cible des métadonnées pour la détection automatique des migrations.
# Alembic comparera la base de données à l'état défini par ces métadonnées.
target_metadata = Base.metadata

# 4. Surcharger l'URL de la base de données à partir de notre configuration d'application
# au lieu de la lire directement depuis alembic.ini.
# C'est la méthode la plus robuste pour s'assurer que l'application et la migration
# utilisent exactement la même configuration.
config.set_main_option('sqlalchemy.url', app_settings.database_url)

# --- FIN DE LA MODIFICATION DE LA CONNEXION ---


def run_migrations_offline() -> None:
    """Exécute les migrations en mode 'offline'.
    Ceci génère des instructions SQL dans un script.
    """
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Exécute les migrations en mode 'online'.
    Dans ce mode, nous avons besoin de créer un Engine
    et d'associer une connexion avec le contexte.
    """
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection, target_metadata=target_metadata
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()