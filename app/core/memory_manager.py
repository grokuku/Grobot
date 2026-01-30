import logging
from typing import Dict, Any, List, Optional
import os

# Mem0 Import
from mem0 import Memory

from app.config import settings
from app.database import sql_models
from app.core import llm_manager

logger = logging.getLogger("app.core.memory_manager")

class MemoryManager:
    """
    Wrapper autour de Mem0 pour gérer la mémoire à long terme (LTM).
    """

    @staticmethod
    def get_memory_client(bot: sql_models.Bot, global_settings: sql_models.GlobalSettings) -> Optional[Memory]:
        """
        Instancie un client Mem0 configuré avec les bons paramètres de fournisseur.
        """
        
        # 1. Résolution de la config LLM pour l'extraction de faits
        llm_config = llm_manager.resolve_llm_config(bot, global_settings, llm_manager.LLM_CATEGORY_TOOLS)
        
        # 2. Construction de la configuration Embedder
        # Mem0 est très sensible aux noms des clés selon le provider.
        embedder_config = {
            "provider": global_settings.embedding_provider or "openai",
            "config": {
                "model": global_settings.embedding_model or "text-embedding-3-small"
            }
        }
        
        if global_settings.embedding_api_key:
            embedder_config["config"]["api_key"] = global_settings.embedding_api_key
        
        if global_settings.embedding_base_url:
            # CORRECTION CRITIQUE : Pour Ollama, la clé est 'ollama_base_url'
            if global_settings.embedding_provider == "ollama":
                embedder_config["config"]["ollama_base_url"] = global_settings.embedding_base_url
            else:
                embedder_config["config"]["base_url"] = global_settings.embedding_base_url

        # 3. Construction de la configuration Mem0
        mem0_config = {
            "vector_store": {
                "provider": "chroma",
                "config": {
                    "collection_name": f"grobot_memory_{bot.id}",
                    "host": settings.CHROMA_HOST,
                    "port": settings.CHROMA_PORT,
                }
            },
            "embedder": embedder_config
        }

        # 4. Configuration du LLM (pour l'extraction des faits)
        provider_config = {}
        if llm_config.provider == llm_manager.LLMProvider.OLLAMA:
            provider_config = {
                "provider": "ollama",
                "config": {
                    "model": llm_config.model_name,
                    "base_url": llm_config.server_url
                }
            }
        elif llm_config.provider == llm_manager.LLMProvider.OPENAI:
            provider_config = {
                "provider": "openai",
                "config": {
                    "model": llm_config.model_name,
                    "api_key": llm_config.api_key
                }
            }
        elif llm_config.provider == llm_manager.LLMProvider.OPENAI_COMPATIBLE:
            provider_config = {
                "provider": "openai",
                "config": {
                    "model": llm_config.model_name,
                    "api_key": llm_config.api_key or "sk-placeholder",
                    "openai_base_url": llm_config.server_url
                }
            }
        
        mem0_config["llm"] = provider_config

        # 5. Instanciation
        try:
            return Memory.from_config(mem0_config)
        except Exception as e:
            logger.error(f"Failed to initialize Mem0 client with custom config: {e}")
            # Sécurité : On ne renvoie pas 'Memory()' car il crasherait sur l'absence de clé OpenAI
            return None

    @staticmethod
    def get_memories(memory_client: Optional[Memory], user_id: str, query: str = None) -> str:
        """
        Récupère les souvenirs pertinents. Gère le cas où le client est None.
        """
        if not memory_client:
            return ""
            
        try:
            if query:
                results = memory_client.search(query, user_id=user_id)
            else:
                results = memory_client.get_all(user_id=user_id)
            
            if not results:
                return ""
            
            formatted_memories = []
            for res in results:
                text = res.get('memory', res.get('text', ''))
                if text:
                    formatted_memories.append(f"- {text}")
            
            return "\n".join(formatted_memories)
            
        except Exception as e:
            logger.error(f"Error searching memories: {e}")
            return ""

    @staticmethod
    async def add_interaction(memory_client: Optional[Memory], user_id: str, user_message: str, bot_response: str):
        """
        Ajoute l'interaction à la mémoire. Gère le cas où le client est None.
        """
        if not memory_client:
            return
            
        try:
            # Mem0 effectue un appel LLM ici pour extraire les faits, c'est pourquoi c'est asynchrone dans notre orchestrateur
            memory_client.add(user_message, user_id=user_id, metadata={"role": "user"})
        except Exception as e:
            logger.error(f"Error adding interaction to memory: {e}")