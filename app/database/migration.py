####
# FICHIER: app/database/migration.py
####
import logging
import datetime
from sqlalchemy import inspect, text
from app.database.base import Base
from app.database import sql_models # Important pour charger tous les modèles

logger = logging.getLogger(__name__)

# --- CONFIGURATION ---
# Version 3 : Ajout des colonnes de configuration des Embeddings (Mémoire Mem0)
CURRENT_APP_DB_VERSION = 3

def get_current_db_version(connection):
    """Récupère la version stockée en base, ou 0 si la table n'existe pas."""
    inspector = inspect(connection)
    if not inspector.has_table("db_version"):
        return 0
    
    try:
        result = connection.execute(text("SELECT version_number FROM db_version LIMIT 1"))
        row = result.fetchone()
        return row[0] if row else 0
    except Exception:
        return 0

def set_db_version(connection, version):
    """Met à jour ou crée la version en base."""
    connection.execute(text("""
        CREATE TABLE IF NOT EXISTS db_version (
            version_number INTEGER PRIMARY KEY,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """))
    connection.execute(text("DELETE FROM db_version"))
    connection.execute(text(
        "INSERT INTO db_version (version_number) VALUES (:v)"
    ), {"v": version})

def migrate_if_needed(engine):
    """
    Orchestre la migration 'Blue/Green' :
    1. Vérifie la version.
    2. Si obsolète : Renomme les tables et INDEX (Backup), Recrée tout, Importe les données, Corrige les séquences.
    """
    # Utilisation d'une transaction unique pour tout le processus
    with engine.begin() as connection:
        db_version = get_current_db_version(connection)
        logger.info(f"MIGRATION CHECK: Version DB actuelle = {db_version}, Version Code Cible = {CURRENT_APP_DB_VERSION}")

        if db_version >= CURRENT_APP_DB_VERSION:
            logger.info("Base de données à jour. Aucune action requise.")
            return

        logger.warning(f"!!! MIGRATION REQUISE ({db_version} -> {CURRENT_APP_DB_VERSION}) !!!")
        logger.info("Démarrage de la stratégie : Backup (Tables+Index) -> Re-Create -> Import -> Reset Sequences")

        target_tables = Base.metadata.sorted_tables
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_suffix = f"_bak_{timestamp}" # Suffixe raccourci pour éviter de dépasser 63 chars
        
        inspector = inspect(connection)
        existing_table_names = inspector.get_table_names()
        backup_map = {}

        # ---------------------------------------------------------
        # 1. RENOMMER LES TABLES ET LEURS INDEX (BACKUP)
        # ---------------------------------------------------------
        for table in reversed(target_tables):
            table_name = table.name
            if table_name in existing_table_names:
                backup_name = f"{table_name}{backup_suffix}"
                logger.info(f"-> Renommage de '{table_name}' en '{backup_name}'")
                
                # A. Récupérer les noms des index AVANT de renommer la table
                try:
                    query_indexes = text("SELECT indexname FROM pg_indexes WHERE tablename = :t")
                    res_indexes = connection.execute(query_indexes, {"t": table_name})
                    indexes_to_rename = [row[0] for row in res_indexes]
                except Exception as e:
                    logger.warning(f"   Impossible de lister les index pour {table_name}: {e}")
                    indexes_to_rename = []

                # B. Renommer la table
                connection.execute(text(f'ALTER TABLE "{table_name}" RENAME TO "{backup_name}"'))
                backup_map[table_name] = backup_name

                # C. Renommer les index associés
                for idx_name in indexes_to_rename:
                    new_idx_name = f"{idx_name}{backup_suffix}"
                    if len(new_idx_name) > 63:
                        new_idx_name = new_idx_name[:40] + backup_suffix
                    
                    try:
                        if not idx_name.endswith(backup_suffix):
                            connection.execute(text(f'ALTER INDEX "{idx_name}" RENAME TO "{new_idx_name}"'))
                    except Exception as e:
                        logger.warning(f"   Echec renommage index '{idx_name}': {e}")
        
        # Renommage table version si elle existe
        if "db_version" in existing_table_names:
                connection.execute(text(f'ALTER TABLE "db_version" RENAME TO "db_version{backup_suffix}"'))

        # ---------------------------------------------------------
        # 2. CRÉATION DU NOUVEAU SCHÉMA
        # ---------------------------------------------------------
        logger.info("-> Création des nouvelles tables...")
        Base.metadata.create_all(bind=connection)

        # ---------------------------------------------------------
        # 3. IMPORTATION DES DONNÉES
        # ---------------------------------------------------------
        logger.info("-> Importation des données...")
        for table in target_tables:
            table_name = table.name
            if table_name not in backup_map:
                continue
            
            backup_name = backup_map[table_name]
            
            try:
                res_col = connection.execute(text(f'SELECT * FROM "{backup_name}" LIMIT 0'))
                backup_cols = list(res_col.keys())
            except Exception:
                logger.error(f"   Impossible de lire les colonnes de {backup_name}")
                continue

            target_cols = [c.name for c in table.columns]
            common_cols = set(backup_cols).intersection(target_cols)
            
            if not common_cols:
                continue

            cols_list = ", ".join([f'"{c}"' for c in common_cols])
            query = f'INSERT INTO "{table_name}" ({cols_list}) SELECT {cols_list} FROM "{backup_name}"'
            
            connection.execute(text(query))
            logger.info(f"   Données migrées pour '{table_name}'.")

        # ---------------------------------------------------------
        # 4. RESET DES SÉQUENCES (AUTO-INCREMENT)
        # ---------------------------------------------------------
        logger.info("-> Réinitialisation des séquences (IDs)...")
        for table in target_tables:
            table_name = table.name
            if 'id' in table.columns and table.columns['id'].primary_key:
                try:
                    reset_seq_sql = text(f"""
                        SELECT setval(
                            pg_get_serial_sequence(:t, 'id'), 
                            COALESCE((SELECT MAX(id) FROM "{table_name}"), 0) + 1, 
                            false
                        )
                    """)
                    connection.execute(reset_seq_sql, {"t": table_name})
                except Exception:
                    pass

        # ---------------------------------------------------------
        # 5. FINALISATION
        # ---------------------------------------------------------
        set_db_version(connection, CURRENT_APP_DB_VERSION)
        logger.info(f"Migration terminée avec succès. Version {CURRENT_APP_DB_VERSION} active.")