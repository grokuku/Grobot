# Project Context: GroBot

    ## 1. Vision et Objectifs du Projet

    Le projet "GroBot" vise à créer une plateforme d'hébergement et de gestion **pour une flotte de bots Discord entièrement indépendants**. Il ne s'agit pas d'un seul bot multi-personnalités, mais d'une infrastructure capable de faire tourner de multiples processus de bots en parallèle.

    L'objectif principal est une **administrabilité dynamique** via une **interface web moderne de type SPA (Single Page Application)**, permettant l'ajout, la configuration ou la désactivation d'un bot à chaud, **sans nécessiter le redémarrage des bots déjà en cours d'exécution**.

    ---

    ## 2. Principes d'Architecture Fondamentaux

    1.  **Architecture d'Application Combinée :** Pour simplifier le déploiement et éliminer les problèmes de CORS, le Frontend et le Backend sont servis par un **unique service conteneurisé**. Nginx agit comme reverse proxy : il sert les fichiers statiques du frontend et redirige les requêtes API vers le processus FastAPI tournant dans le même conteneur.
    2.  **Configuration Centralisée en Base de Données :** Toute la configuration spécifique à un bot est stockée **uniquement** dans PostgreSQL. Le fichier `.env` est réservé à la configuration de la plateforme.
    3.  **Isolation par Processus :** Chaque bot actif tourne dans son propre processus système, géré par le service `discord-bot-launcher`.
    4.  **Isolation des Données (Mémoire) :** La mémoire à long terme (LTM) est stockée dans ChromaDB au sein d'une **collection dédiée par bot**.
    5.  **Communication Conteneur-Hôte :** L'URL `http://host.docker.internal:[port]` est la valeur standard pour qu'un conteneur accède à un service sur l'hôte. Les services communiquent entre eux via leur nom de service (ex: `http://app:8000`, `http://ollama:11434`, `http://grobot_tools:8001`).
    6.  **Gestion du Schéma de Base de Données (Stratégie Blue/Green) :** Alembic a été **supprimé** (jugé trop lourd). La gestion du schéma est désormais assurée par un module personnalisé `app/database/migration.py` qui s'exécute au démarrage. Il compare la version du code (`CURRENT_APP_DB_VERSION`) avec celle de la base, et si nécessaire :
        *   Renomme les tables et index existants (Backup).
        *   Recrée les tables à neuf via `Base.metadata.create_all()`.
        *   Importe les données depuis les backups en mappant les colonnes communes.
        *   Réinitialise les séquences d'auto-incrémentation.
    7.  **Structure des Chemins dans le Conteneur `app` :** En raison de la configuration Docker, le répertoire `app` du projet est copié dans le répertoire `/app/app` du conteneur. Par conséquent, le chemin d'accès absolu pour les fichiers du projet (comme `alembic.ini` ou les playbooks) à l'intérieur du conteneur est systématiquement `/app/app/...`. Cette convention doit être respectée pour toutes les commandes `docker-compose exec`.
    8.  **Architecture de Prompt Hybride :** Le prompt système final envoyé au LLM est assemblé dynamiquement par la logique métier. Il combine des **directives fondamentales non-modifiables** (codées en dur pour tous les bots) avec le **contexte d'exécution dynamique** (serveur/salon Discord, fichiers joints, mémoire LTM) et la **personnalité spécifique au bot** (stockée en base de données).
    9.  **Orchestration Agentique Côté Serveur (Backend) :** Contrairement aux premières itérations, l'intelligence du bot est désormais centralisée dans le backend via `agent_orchestrator.py`. Le processus Discord (`bot_process.py`) agit comme un **client léger** ("dumb terminal") : il transmet les messages à l'API et affiche les réponses ou exécute les commandes WebSocket reçues. La "chaîne de montage" des agents (Gatekeeper, Tool Identifier, Planner, Synthesizer) réside entièrement dans le backend pour une meilleure maintenabilité et sécurité.
    10. **Mémoire Utilisateur à Deux Composants :** La connaissance persistante du bot sur les utilisateurs est divisée en deux types de données distincts : les **Profils Utilisateurs** (contenant des directives comportementales modifiables par un administrateur) et les **Notes Utilisateurs** (contenant des faits textuels avec un score de fiabilité, que le bot peut créer et lire lui-même via ses outils).
    11. **Architecture d'Agent Spécialisé ("Chaîne de Montage") :** Pour fiabiliser l'utilisation des outils, le traitement d'un message est decomposé en une série d'appels LLM spécialisés. Chaque LLM a un rôle unique et défini (Gardien, Planificateur, Synthétiseur, etc.). L'orchestration de cette chaîne est gérée par le backend.
    12. **Spécialisation des Modèles LLM par Catégorie de Tâche :** Pour optimiser les performances et les coûts, la configuration LLM est segmentée en trois catégories fonctionnelles, chacune pouvant être assignée à un serveur, un modèle et une fenêtre de contexte spécifiques. Ces catégories sont :
        *   **Décisionnel :** Modèles rapides pour des tâches de classification ou de filtrage (ex: `Gatekeeper`).
        *   **Outils :** Modèles fiables avec un bon raisonnement logique pour la génération de JSON et l'appel d'outils (ex: `Parameter Extractor`).
        *   **Output Client :** Modèles puissants et créatifs pour la génération des réponses finales à l'utilisateur (ex: `Synthesizer`).
    13. **Logique Context vs Output (DeepSeek Support) :** Le `llm_manager.py` sépare strictement la fenêtre de contexte (Input Context) de la limite de génération (Output Max Tokens).
        *   Si le contexte est immense (ex: 128k pour DeepSeek), l'application l'utilise pour l'historique mais plafonne la demande de génération (`max_tokens`) à une valeur sûre (ex: 4096 ou 8192) pour éviter les erreurs API.
        *   Si le contexte est petit (ex: 4096), l'application calcule une réserve pour le prompt afin de ne pas demander plus de tokens que le modèle ne peut en gérer au total.
    14. **Compatibilité DeepSeek JSON Strict :** Pour éviter les réponses vides avec DeepSeek V3 en mode JSON, le `llm_manager.py` injecte dynamiquement la directive *"IMPORTANT: Your output MUST be a valid JSON object"* dans le prompt système si le mode JSON est activé, satisfaisant ainsi les exigences strictes de l'API.
    15. **Streaming Robuste (Client Discord) :** Le client Discord (`api_client.py`) implémente un parser SSE (Server-Sent Events) basé sur un buffer. Il gère la fragmentation des paquets réseaux et les sauts de ligne multiples, garantissant que les réponses streamées ne sont jamais tronquées ou corrompues côté client.

    ---

    ## 3. Architecture et Technologies

    ### 3.1. Technologies Principales
    *   **Orchestration :** Docker, Docker Compose
    *   **Backend API :** FastAPI
    *   **Serveur Applicatif :** Nginx (agissant comme serveur web statique et reverse proxy) et Uvicorn (pour l'API FastAPI).
    *   **Gestion des processus Bots :** Python 3.11+, `subprocess`
    *   **Base de Données Relationnelle (Gestion) :** PostgreSQL (via SQLAlchemy). **Gestion des migrations custom (`migration.py`).**
    *   **Base de Données Vectorielle (Mémoire LTM Isolée) :** ChromaDB
    *   **Interaction LLM :**
        *   `ollama` (pour les modèles locaux).
        *   `litellm` >= 1.60.0 (pour le support Multi-Provider et OpenAI-Compatible récent).
        *   `openai` >= 1.60.0 (Requis par LiteLLM pour les types).
        *   `pydantic` >= 2.10.0 (Validation stricte).
    *   **Client Discord :** `discord.py`
    *   **Tâches Asynchrones :** Celery, Redis
    *   **Standard Outils (MCP) :** `mcp` (SDK), `mcp-use` (Client), `starlette` (Transport SSE)

    ### 3.2. Arborescence Complète du Projet et Rôle des Fichiers

    ```    📁 GroBot/
        ├─ 📄 .dockerignore                 # Ignore les fichiers non nécessaires lors de la construction de l'image Docker.
        ├─ 📄 .env.example                  # Fichier d'exemple pour les variables d'environnement.
        ├─ 📄 docker-compose.yml            # Définit et orchestre tous les services de l'application.
        ├─ 📄 Dockerfile                    # Recette multi-stage pour l'image 'app' (API+Frontend).
        ├─ 📄 features.md                   # Suivi de haut niveau des fonctionnalités.
        ├─ 📄 project_context.md            # Ce fichier, source de vérité du projet.
        ├─ 📄 requirements.txt              # Dépendances Python pour le service 'app'.
        │
        ├─ 📁 app/                           # Cœur du Backend : API et logique métier.
        │  ├─ 📄 __init__.py                 # Marque le dossier comme un package Python.
        │  ├─ 📄 config.py                   # Charge les variables d'environnement via Pydantic.
        │  ├─ 📄 main.py                     # Point d'entrée de l'API FastAPI, gère le cycle de vie et déclenche la MIGRATION.
        │  │
        │  ├─ 📁 api/                        # Contient les routeurs FastAPI (endpoints).
        │  │  ├─ 📄 __init__.py               # Marque le dossier comme un package Python.
        │  │  ├─ 📄 bots_api.py               # API pour la gestion des bots (CRUD).
        │  │  ├─ 📄 chat_api.py               # API pour l'orchestration des agents et le chat.
        │  │  ├─ 📄 files_api.py              # API pour la gestion des fichiers.
        │  │  ├─ 📄 llm_api.py                # API pour l'interaction avec les LLMs (ex: lister les modèles).
        │  │  ├─ 📄 mcp_api.py                # API pour la gestion des serveurs MCP.
        │  │  ├─ 📄 settings_api.py           # API pour les paramètres globaux.
        │  │  ├─ 📄 tools_api.py              # API proxy pour l'exécution des outils externes (MCP).
        │  │  ├─ 📄 user_profiles_api.py      # API pour la gestion des profils et notes utilisateurs.
        │  │  └─ 📄 workflows_api.py          # API pour la gestion des workflows (CRUD et exécution).
        │  │
        │  ├─ 📁 core/                       # Logique métier principale de l'application.
        │  │  ├─ 📄 __init__.py               # Marque le dossier comme un package Python.
        │  │  ├─ 📄 agent_orchestrator.py     # Orchestre la chaîne d'appels aux agents spécialisés.
        │  │  ├─ 📄 llm_manager.py            # Gère les instances de clients LLM (Ollama/LiteLLM/Async).
        │  │  ├─ 📄 websocket_manager.py      # Gère les connexions WebSocket persistantes avec les clients bot.
        │  │  └─ 📁 agents/                 # Contient la logique pour chaque agent LLM spécialisé.
        │  │     ├─ 📄 __init__.py           # Marque le dossier comme un package Python.
        │  │     ├─ 📄 acknowledger.py       # Agent pour générer les messages d'attente.
        │  │     ├─ 📄 archivist.py          # Agent pour archiver les informations en mémoire.
        │  │     ├─ 📄 clarifier.py          # Agent pour demander des informations manquantes.
        │  │     ├─ 📄 gatekeeper.py         # Agent pour décider si le bot doit répondre.
        │  │     ├─ 📄 parameter_extractor.py# Agent pour extraire les paramètres des outils.
        │  │     ├─ 📄 planner.py            # Agent pour créer le plan d'exécution des outils.
        │  │     ├─ 📄 prompts.py            # Centralise tous les prompts système des agents.
        │  │     ├─ 📄 synthesizer.py        # Agent pour formuler la réponse finale.
        │  │     └─ 📄 tool_identifier.py    # Agent pour identifier les outils nécessaires.
        │  │
        │  ├─ 📁 database/                   # Module pour l'accès aux bases de données.
        │  │  ├─ 📄 __init__.py               # Marque le dossier comme un package Python.
        │  │  ├─ 📄 base.py                   # Définit la base déclarative SQLAlchemy.
        │  │  ├─ 📄 chroma_manager.py         # Gère les interactions avec ChromaDB (mémoire vectorielle).
        │  │  ├─ 📄 migration.py              # NOUVEAU : Gestionnaire de migration (Backup/Recreate/Import).
        │  │  ├─ 📄 crud_bots.py              # Fonctions CRUD pour les bots.
        │  │  ├─ 📄 crud_channel_settings.py  # Fonctions CRUD pour les permissions par salon.
        │  │  ├─ 📄 crud_files.py             # Fonctions CRUD pour les fichiers.
        │  │  ├─ 📄 crud_mcp.py               # Fonctions CRUD pour les serveurs MCP.
        │  │  ├─ 📄 crud_settings.py          # Fonctions CRUD pour les paramètres globaux.
        │  │  ├─ 📄 crud_user_notes.py        # Fonctions CRUD pour les notes sur les utilisateurs.
        │  │  ├─ 📄 crud_user_profiles.py     # Fonctions CRUD pour les profils utilisateurs.
        │  │  ├─ 📄 crud_workflows.py         # Fonctions CRUD pour les workflows.
        │  │  ├─ 📄 redis_session.py          # Gère la connexion au client Redis.
        │  │  ├─ 📄 sql_models.py             # Définit les modèles de table SQLAlchemy.
        │  │  └─ 📄 sql_session.py            # Gère la session de base de données SQL.
        │  │
        │  ├─ 📁 schemas/                    # Contient les schémas Pydantic pour la validation des données API.
        │  │  ├─ 📄 __init__.py               # Marque le dossier comme un package Python.
        │  │  ├─ 📄 bot_schemas.py            # Schémas Pydantic pour les bots (API Keys ajoutées).
        │  │  ├─ 📄 chat_schemas.py           # Schémas Pydantic pour le chat et les agents.
        │  │  ├─ 📄 file_schemas.py           # Schémas Pydantic pour les fichiers.
        │  │  ├─ 📄 mcp_schemas.py            # Schémas Pydantic pour les serveurs MCP.
        │  │  ├─ 📄 settings_schema.py        # Schémas Pydantic pour les paramètres.
        │  │  ├─ 📄 user_note_schemas.py      # Schémas Pydantic pour les notes utilisateurs.
        │  │  ├─ 📄 user_profile_schemas.py   # Schémas Pydantic pour les profils utilisateurs.
        │  │  └─ 📄 workflow_schemas.py       # Schémas Pydantic pour les workflows.
        │  │
        │  └─ 📁 worker/                     # Configuration pour les tâches de fond (Celery).
        │     ├─ 📄 __init__.py               # Marque le dossier comme un package Python.
        │     ├─ 📄 celery_app.py             # Définit l'instance de l'application Celery.
        │     └─ 📄 tasks.py                  # Définit les tâches Celery (ex: archivage, exécution de workflows).
        │
        ├─ 📁 chromadb_overriden/
        │  └─ 📄 Dockerfile                  # Personnalise l'image ChromaDB (ex: ajout de 'curl').
        │
        ├─ 📁 discord_bot_launcher/         # Service isolé qui gère les processus des bots Discord.
        │  ├─ 📄 bot_process.py              # Point d'entrée du client Discord, initialise les handlers.
        │  ├─ 📄 Dockerfile                  # Image Docker pour le service launcher.
        │  ├─ 📄 launcher.py                 # Script qui surveille l'API et lance/arrête les bots.
        │  ├─ 📄 requirements.txt            # Dépendances Python pour le service launcher.
        │  └─ 📁 client/                     # Logique modulaire du client Discord.
        │     ├─ 📄 __init__.py               # Marque le dossier comme un package Python.
        │     ├─ 📄 api_client.py             # Centralise toutes les requêtes vers l'API backend.
        │     ├─ 📄 discord_ui.py             # Fonctions utilitaires pour l'UI de Discord (réactions, etc.).
        │     ├─ 📄 discord_message_helper.py # [NEW] Helper pour formatting et fichiers (déplacé ici).
        │     └─ 📄 event_handler.py          # Contient la logique principale `on_message` et Streaming State Machine.
        │
        ├─ 📁 frontend/                     # Application combinée (Nginx + SPA).
        │  ├─ 📄 entrypoint.sh               # Script de démarrage pour le conteneur 'app' (nginx + uvicorn).
        │  ├─ 📄 nginx.conf                  # Configuration Nginx (reverse proxy et fichiers statiques).
        │  └─ 📁 src/                        # Code source JavaScript pour l'interface utilisateur.
        │     ├─ 📄 api.js                    # Fonctions utilitaires pour l'UI de Discord (réactions, etc.).
        │     ├─ 📄 events.js                 # Gestionnaires d'événements (formulaires, WebSocket).
        │     ├─ 📄 index.html                # Structure HTML de l'application.
        │     ├─ 📄 main.js                   # Point d'entrée JavaScript, initialisation et routage.
        │     ├─ 📄 style.css                 # Styles CSS.
        │     ├─ 📄 ui.js                     # Fonctions pour manipuler le DOM et mettre à jour l'UI.
        │     └─ 📄 workflow_editor.js        # Module UI pour l'éditeur de workflows.
        │
        └─ 📁 grobot_tools/                 # Service MCP contenant les outils standards.
            ├─ 📄 Dockerfile                  # Dockerfile pour le service d'outils.
            ├─ 📄 requirements.txt            # Dépendances Python pour les outils.
            ├─ 📄 supervisord.conf            # Configuration Supervisor pour lancer les outils.
            ├─ 📁 file_tools/                 # Outils de gestion de fichiers.
            │  └─ 📄 server.py                 # Point d'entrée du serveur MCP pour les outils de fichiers.
            └─ 📁 time_tool/                  # Outils liés au temps.
            └─ 📄 server.py                 # Point d'entrée du serveur MCP pour l'outil de temps.
    ```

    ---

    ## 4. Vision de l'Interface Cible (Post-Refonte)

    *   **Disposition Générale :** Une application à deux colonnes principales.
        *   **Colonne de Gauche (Sidebar, redimensionnable) :**
            *   **Titre :** "GroBot".
            *   **Liste des Bots :** Affiche tous les bots configurés. Chaque élément montre le nom du bot et son état (en ligne/hors ligne).
            *   **Boutons d'Action Globale :**
                *   Un bouton pour "Add Bot".
                *   Un bouton "roue crantée" pour "Configuration Globale".
        *   **Colonne de Droite (Contenu Principal) :**
            *   **En-tête :** Affiche le nom du bot/de la vue actuellement sélectionné(e), et des contrôles (ex: boutons de thème).
            *   **Zone de Contenu :** Affiche la vue sélectionnée pour un bot via un système d'onglets. Les onglets principaux sont :
                *   **Test Chat :** Une interface pour interagir directement avec le bot.
                *   **Logs :** Un dashboard de logs en temps réel.
                *   **Settings :** Le formulaire de configuration du bot, incluant les nouveaux réglages LLM par catégorie et les **permissions par salon** (contrôle d'accès et écoute passive par canal).
                *   **Files :** Le gestionnaire de fichiers du bot.
                *   **Memory :** Une vue de la mémoire vectorielle du bot.
                *   **Knowledge Base :** Une interface pour gérer les connaissances du bot sur les utilisateurs (Recherche, Liste, Profils et Notes).
                *   **Workflows :** Une interface graphique pour créer et gérer des automatisations (Workflows) déclenchées par CRON, avec un éditeur d'étapes supportant le chaînage de paramètres et l'utilisation d'outils MCP.

    ---

    ## 6. Documentation : Le Standard Model Context Protocol (MCP)

    *   **Date d'Adoption Stricte :** 2025-12-19
    *   **Source de Vérité :** [Dépôt GitHub Officiel](https://github.com/modelcontextprotocol/modelcontextprotocol)
    *   **Architecture :** GroBot utilise strictement le SDK officiel `mcp` (pour les serveurs) et `mcp-use` (pour le client backend).

    ### 6.1. Principes Techniques

    1.  **Transport SSE et Starlette :** La communication utilise **Server-Sent Events (SSE)**.
        *   **Spécificité Starlette :** Lors de l'utilisation de Starlette avec `mcp`, l'endpoint recevant le `POST` des messages doit retourner un objet `Response` qui ne fait rien (NoOp), car le SDK `mcp` gère déjà l'envoi de la réponse ASGI. Sinon, une erreur "Double Response" se produit.
        *   **Routage :** Il est recommandé d'autoriser la méthode `POST` sur l'endpoint de handshake (ex: `/mcp`) en plus de l'endpoint dédié aux messages, pour une compatibilité maximale avec les clients.
    2.  **Bibliothèques Implémentées :**
        *   **Serveurs (Outils) :** `mcp` + `starlette` (Ex: `grobot_tools/time_tool/server.py`).
        *   **Client (Backend) :** `mcp-use` est utilisé par l'API (`tools_api.py`), l'orchestrateur (`agent_orchestrator.py`) et les workers (`tasks.py`).
    3.  **Découverte Robuste (Retry Pattern) :** 
        *   La découverte des outils (`tools/list`) est effectuée **serveur par serveur** de manière isolée pour éviter qu'un nœud défaillant ne bloque tout le système.
        *   **Retry Logic :** En raison de l'instabilité potentielle des connexions SSE (`httpx.RemoteProtocolError`), une logique de réessai (3 tentatives) est implémentée dans `agent_orchestrator.py` et `tools_api.py`.
    4.  **Problèmes Connus (SSE) :** Des erreurs de type `httpx.RemoteProtocolError: peer closed connection` surviennent occasionnellement. Le système les capture désormais et relance la connexion (Retry). Les logs peuvent afficher des erreurs MCP (connexion fermée), mais elles sont suivies d'une récupération réussie (`Successfully discovered ...`).

    ### 6.2. Format de Définition d'un Outil

    Chaque outil retourné respecte le JSON Schema standard. Le backend injecte désormais la liste des arguments attendus directement dans la description de l'outil fournie au LLM (Agent `Tool Identifier`), pour améliorer la prise de décision des modèles moins performants.

    ---

    ## 7. État Actuel et Plan d'Action

    ### 7.1. Bugs et Corrections Récents

    1.  **Authentification LLM (Erreur 401) [RÉSOLU] :** Correction de l'injection des clés API et de `crud_bots.py`.
    2.  **Crash LiteLLM (Async) [RÉSOLU] :** Passage à `acompletion` dans `llm_manager.py`.
    3.  **DeepSeek - Réponse Vide/Invalide [RÉSOLU] :**
        *   **Cause :** DeepSeek en mode `json_object` refuse de répondre si le prompt système ne contient pas le mot "JSON".
        *   **Fix :** Injection dynamique de la consigne "IMPORTANT: Your output MUST be a valid JSON object" dans `llm_manager.py`.
    4.  **Parsing JSON Fragile [RÉSOLU] :** Remplacement de la regex simpliste par une extraction robuste des blocs `{}` et `[]` imbriqués dans `_clean_json_response`.
    5.  **MCP SSE Instability [MITIGÉ] :** 
        *   **Symptôme :** Erreurs `httpx.RemoteProtocolError` récurrentes.
        *   **Fix :** Implémentation du pattern **Retry** (3 essais). Cela fonctionne (la découverte aboutit), mais les logs d'erreur restent visibles.
    6.  **"Tool Hallucination" [RÉSOLU] :** Le bot inventait des besoins d'outils (météo, image) sur des messages simples. Corrigé en durcissant le prompt du `Tool Identifier` et en ajoutant des règles d'exclusion pour les salutations.
    7.  **Parameter Extractor Crash [RÉSOLU] :** L'extracteur plantait ou inventait des paramètres manquants car il ne recevait pas le schéma des outils sélectionnés. Corrigé par injection dynamique des schémas (`tool_schemas`) dans le prompt système et filtrage de sécurité post-génération.
    8.  **"Goldfish Syndrome" (Context Loss) [RÉSOLU] :** Le bot ignorait le dernier message utilisateur et se présentait en boucle. Corrigé en fusionnant explicitement l'historique passé et le message courant (`full_history`) dans `agent_orchestrator.py` et `chat_api.py` avant appel aux LLMs.
    9.  **Crash LiteLLM Context Window (DeepSeek) [RÉSOLU] :** LiteLLM envoyait la taille totale du contexte (ex: 128k) comme limite de génération (`max_tokens`), provoquant une erreur `BadRequest`. Corrigé en découplant les paramètres : le contexte est libre, mais la sortie est plafonnée à une valeur sûre (ex: 4096 ou 8192).
    10. **Discord Stream Fragmentation [RÉSOLU] :** Le client Discord Python crashait lors de la lecture du flux SSE si les paquets étaient fragmentés. Corrigé par un parser robuste avec gestion de buffer dans `api_client.py`.
    11. **Settings Persistence (Frontend/Backend Sync) [RÉSOLU] :**
        *   **Symptôme :** Les clés API et choix de modèles ne s'enregistraient pas ou disparaissaient de l'UI.
        *   **Cause :** Manque d'écouteurs d'événements dans `ui.js`, désynchronisation des IDs (`tool` vs `tools`) dans `events.js`, et rejet silencieux par Pydantic.
        *   **Fix :** Ajout des `addEventListener` manquants, alignement des IDs Frontend/Backend, correction des noms de variables dans `events.js`, et ajout d'une logique de fallback pour l'affichage des modèles sauvegardés dans l'UI.
    12. **API Key Corruption [RÉSOLU] :** Identification de caractères parasites (ex: `:63`) dans les clés stockées, causés par des erreurs de saisie ou des bugs de parsing précédents.
    13. **Discord Streaming & Long Messages [RÉSOLU] :**
        *   **Symptôme :** Crash si message > 2000 chars ou découpage illisible des JSONs.
        *   **Fix :** Implémentation d'une machine à états dans `event_handler.py`.
        *   **Logique :** Mode TEXTE (streaming live) vs Mode CODE (bufferisation + animation "points").
        *   **Fichiers :** Conversion automatique des blocs de code en pièces jointes (`.json`, `.py`, etc.) avec détection de langage et nettoyage de la déclaration Markdown.
        *   **Architecture :** Déplacement de `discord_message_helper.py` dans le scope du launcher (`discord_bot_launcher/client/`) pour résoudre les problèmes d'import.

    ### 7.2. État des Fonctionnalités Clés

    1.  **Workflows (Automation) :** Le backend supporte désormais l'exécution de workflows complexes et le déclenchement via CRON (Celery Beat). L'intégration MCP-Use est active pour les étapes de workflow.
    2.  **Analyse de Fichiers :** L'endpoint `/files/{uuid}/analyze` est temporairement désactivé (renvoie 503) en attente d'une refonte du module d'analyse.

    ### 7.3. Plan d'Action

    1.  **Workflows (UI) :** Validation finale de l'interface utilisateur pour la création et l'édition des workflows.
    2.  **Logs UI :** Vérifier que les logs remontent bien via WebSocket (le code semble correct, à tester plus avant).

    ---

    ## 9. Dépendances Externes Majeures

    *   **Agentic Context Engine (ACE)**
        *   **Nom du Paquet PyPI :** `ace-framework`
        *   **Version lors de l'intégration :** 0.2.0

    *   **LiteLLM & OpenAI**
        *   **Versions Requises :** `litellm>=1.60.0`, `openai>=1.60.0`, `pydantic>=2.10.0`
        *   **Usage :** Abstraction multi-provider et typage strict des réponses.

    *   **Model Context Protocol (MCP)**
        *   **Paquets :** `mcp` (SDK Serveur), `mcp-use` (Client), `starlette` (Serveur Web ASGI).
        *   **Usage :** Standardisation des interactions avec les outils externes et internes.