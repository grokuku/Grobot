# app/database/chroma_manager.py

import chromadb
import logging
from chromadb.types import Collection
from typing import Dict, Any

from app.config import settings

# --- Setup ---
logging.basicConfig(level=logging.INFO, format='%(asctime)s - [%(levelname)s] - (CHROMA_MANAGER) - %(message)s')

class ChromaManager:
    """
    Gère toutes les interactions avec la base de données vectorielle ChromaDB.
    Assure une connexion centralisée et fournit des méthodes pour interagir
    avec les collections de mémoire des bots.
    """
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(ChromaManager, cls).__new__(cls)
            try:
                # Initialise le client HTTP pour se connecter au service ChromaDB
                cls._instance.client = chromadb.HttpClient(
                    host=settings.CHROMA_HOST,
                    port=settings.CHROMA_PORT
                )
                logging.info("ChromaDB client initialized. Connection will be established on first use.")
            except Exception as e:
                logging.error(f"Failed to initialize ChromaDB client: {e}")
                cls._instance.client = None
        return cls._instance

    def get_or_create_bot_collection(self, bot_id: int) -> Collection | None:
        """
        Récupère ou crée une collection dédiée pour un bot spécifique.
        Le nom de la collection est standardisé pour garantir l'isolation.

        Args:
            bot_id: L'identifiant unique du bot.

        Returns:
            L'objet Collection de ChromaDB, ou None si le client n'est pas disponible.
        """
        if not self.client:
            return None
        
        try:
            collection_name = f"bot_memory_{bot_id}"
            return self.client.get_or_create_collection(name=collection_name)
        except Exception as e:
            logging.error(f"Failed to get_or_create_collection for bot {bot_id}: {e}", exc_info=True)
            return None

    def get_bot_memory(self, bot_id: int) -> Dict[str, Any] | None:
        """
        Retrieves all documents and their metadata from a bot's collection.

        Args:
            bot_id: The unique ID of the bot.

        Returns:
            A dictionary containing the count and a list of memory items,
            or None if an error occurs.
        """
        collection = self.get_or_create_bot_collection(bot_id)
        if not collection:
            return None

        try:
            # Retrieve all entries from the collection
            memory_data = collection.get()

            # Process the raw data into a structured list of items
            items = []
            if memory_data and memory_data.get('ids'):
                for i in range(len(memory_data['ids'])):
                    items.append({
                        "id": memory_data['ids'][i],
                        "document": memory_data['documents'][i],
                        "metadata": memory_data['metadatas'][i]
                    })
            
            return {
                "count": len(items),
                "items": items
            }

        except Exception as e:
            logging.error(f"Failed to retrieve memory for bot {bot_id}: {e}", exc_info=True)
            return None

    def delete_memory_entry(self, bot_id: int, memory_id: str) -> bool:
        """
        Deletes a single memory entry from a bot's collection.

        Args:
            bot_id: The unique ID of the bot.
            memory_id: The unique ID of the memory entry to delete.

        Returns:
            True if deletion was successful, False otherwise.
        """
        collection = self.get_or_create_bot_collection(bot_id)
        if not collection:
            return False
        
        try:
            collection.delete(ids=[memory_id])
            logging.info(f"Successfully deleted memory entry '{memory_id}' for bot {bot_id}.")
            return True
        except Exception as e:
            logging.error(f"Failed to delete memory entry '{memory_id}' for bot {bot_id}: {e}", exc_info=True)
            return False


# Instance unique du manager pour être utilisée dans toute l'application
chroma_manager = ChromaManager()