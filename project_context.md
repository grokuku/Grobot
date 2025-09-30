#### project_context.md
    ---
    ### AXIOMES FONDAMENTAUX DE LA SESSION ###
    ---

    **AXIOME COMPORTEMENTAL : Tu es un expert en développement logiciel, méticuleux et proactif.**
    *   Tu anticipes les erreurs et suggères des points de vérification après chaque modification.
    *   Tu respectes le principe de moindre intervention : tu ne modifies que ce qui est nécessaire et tu ne fais aucune optimisation non demandée.
    *   Tu agis comme un partenaire de développement, pas seulement comme un exécutant.

    **AXIOME D'ANALYSE ET DE SÉCURITÉ : Aucune action aveugle.**
    *   Avant TOUTE modification de fichier, si tu ne disposes de son contenu intégral et à jour dans notre session actuelle, tu dois impératif me le demander.
    *   Tu ne proposeras jamais de code de modification (`sed` ou autre) sans avoir analysé le contenu du fichier concerné au préalable.

    **AXIOME DE RESTITUTION DU CODE : La clarté et la fiabilité priment.**
    1.  **Modification par `sed` :**
        *   Tu fournis les modifications via une commande `sed` pour Git Bash, sur **une seule ligne**, avec l'argument encapsulé dans des guillemets simples (`'`).
        *   **CONDITION STRICTE :** Uniquement si la commande est basique et sans risque d'erreur. Dans ce cas, tu ne montres pas le code, seulement la commande.
        *   Tu n'utiliseras **jamais** un autre outil (`patch`, `awk`, `tee`, etc.).
    2.  **Modification par Fichier Complet :**
        *   Si une commande `sed` en une seule ligne est impossible ou risquée, tu abandonnes `sed`.
        *   À la place, tu fournis le **contenu intégral et mis à jour** du fichier.
    3.  **Formatage des Fichiers et Blocs de Code :**
        *   **Pour les fichiers Markdown (`.md`) :** L'intégralité du contenu du fichier que tu fournis **doit systématiquement être indenté de quatre espaces.**
        *   **Pour les fichiers de code (`.py`, etc.) et de configuration :** Tu utiliseras un bloc de code standard (```) formaté comme suit :
            *   Les balises d'ouverture et de fermeture (```) ne sont **jamais** indentées.
            *   L'intégralité du code contenu à l'intérieur **doit systématiquement être indenté de quatre espaces.**

    **AXIOME DE WORKFLOW : Un pas après l'autre.**
    1.  **Validation Explicite :** Après chaque proposition de modification (commande `sed` ou fichier complet), tu t'arrêtes et attends mon accord explicite avant de continuer sur une autre tâche ou un autre fichier.
    2.  **Mise à Jour de la Documentation :** À la fin du développement d'une fonctionnalité majeure et après ma validation, tu proposeras de manière proactive la mise à jour des fichiers `project_context.md` et `features.md`.

    **AXIOME LINGUISTIQUE : Bilinguisme strict.**
    *   **Nos Interactions :** Toutes tes réponses et nos discussions se feront en **français**.
    *   **Le Produit Final :** Absolument tout le code, les commentaires, les docstrings, les variables et les textes destinés à l'utilisateur (logs, UI, API) doivent être rédigés exclusively en **anglais**, à l'exception du contenu de la configuration métier (prompts, exemples) qui peut être en français si le besoin l'exige.

    ---
    ### FIN DES AXIOMES FONDAMENTAUX ###
    ---
    
    ## 1. Vision et Objectifs du Projet

    Le projet "GroBot" vise à créer une plateforme d'hébergement et de gestion **pour une flotte de bots Discord entièrement indépendants**. Il ne s'agit pas d'un seul bot multi-personnalités, mais d'une infrastructure capable de faire tourner de multiples processus de bots en parallèle.

    L'objectif principal est une **administrabilité dynamique** via une **interface web moderne de type SPA (Single Page Application)**, permettant l'ajout, la configuration ou la désactivation d'un bot à chaud, **sans nécessiter le redémarrage des bots déjà en cours d'exécution**.

    ---

    ## 2. Principes d'Architecture Fondamentaux

    1.  **Architecture d'Application Combinée :** Pour simplifier le déploiement et éliminer les problèmes de CORS, le Frontend et le Backend sont servis par un **unique service conteneurisé**. Nginx agit comme reverse proxy : il sert les fichiers statiques du frontend et redirige les requêtes API vers le processus FastAPI tournant dans le même conteneur.
    2.  **Configuration Centralisée en Base de Données :** Toute la configuration spécifique à un bot est stockée **uniquement** dans PostgreSQL. Le fichier `.env` est réservé à la configuration de la plateforme.
    3.  **Isolation par Processus :** Chaque bot actif tourne dans son propre processus système, géré par le service `discord-bot-launcher`.
    4.  **Isolation des Données (Mémoire) :** La mémoire à long terme (LTM) est stockée dans ChromaDB au sein d'une **collection dédiée par bot**.
    5.  **Communication Conteneur-Hôte :** L'URL `http://host.docker.internal:[port]` est la valeur standard pour qu'un conteneur accède à un service sur l'hôte. Les services communiquent entre eux via leur nom de service (ex: `http://app:8000`, `http://ollama:11434`).
    6.  **Gestion du Schéma de Base de Données :** Alembic est la **seule autorité** pour la gestion du schéma de la base de données. L'appel `Base.metadata.create_all()` n'est pas utilisé en production pour éviter tout conflit. Pour les relations "plusieurs-à-plusieurs" avec des données additionnelles (ex: la configuration d'un outil pour un bot), le patron de conception **Association Object** de SQLAlchemy est utilisé.
    7.  **Structure des Chemins dans le Conteneur `app` :** En raison de la configuration Docker, le répertoire `app` du projet est copié dans le répertoire `/app` du conteneur. Par conséquent, le chemin d'accès absolu pour les fichiers du projet (comme `alembic.ini`) à l'intérieur du conteneur est systématiquement `/app/app/...`. Cette convention doit être respectée pour toutes les commandes `docker-compose exec`.
    8.  **Architecture de Prompt Hybride :** Le prompt système final envoyé au LLM est assemblé dynamiquement par la logique métier. Il combine des **directives fondamentales non-modifiables** (codées en dur pour tous les bots) avec le **contexte d'exécution dynamique** (serveur/salon Discord, fichiers joints, mémoire LTM) et la **personnalité spécifique au bot** (stockée en base de données).
    9.  **Agentique et Exécution des Outils Côté Client :** La boucle de l'agent (LLM -> appel d'outil -> LLM) est gérée par le client, c'est-à-dire `bot_process.py`, et non par le backend. Cette approche garantit la **sécurité maximale** (le token Discord ne quitte jamais son processus) et permet l'implémentation d'**outils internes** qui interagissent directement avec l'objet client `discord.py`. Les outils externes (MCP) sont appelés via un **endpoint API proxy dédié (`/api/tools/call`)** qui centralise la logique de communication.
    10. **Mémoire Utilisateur à Deux Composants :** La connaissance persistante du bot sur les utilisateurs est divisée en deux types de données distincts : les **Profils Utilisateurs** (contenant des directives comportementales modifiables par un administrateur) et les **Notes Utilisateurs** (contenant des faits textuels avec un score de fiabilité, que le bot peut créer et lire lui-même via ses outils).
    11. **Architecture d'Agent Spécialisé ("Chaîne de Montage") :** Pour fiabiliser l'utilisation des outils, le traitement d'un message est décomposé en une série d'appels LLM spécialisés. Chaque LLM a un rôle unique et défini (Gardien, Planificateur, Synthétiseur, etc.). L'orchestration de cette chaîne est gérée par le backend.
    12. **Spécialisation des Modèles LLM par Catégorie de Tâche :** Pour optimiser les performances et les coûts, la configuration LLM est segmentée en trois catégories fonctionnelles, chacune pouvant être assignée à un serveur, un modèle et une fenêtre de contexte spécifiques. Ces catégories sont :
        *   **Décisionnel :** Modèles rapides pour des tâches de classification ou de filtrage (ex: `Gatekeeper`).
        *   **Outils :** Modèles fiables avec un bon raisonnement logique pour la génération de JSON et l'appel d'outils (ex: `Parameter Extractor`).
        *   **Output Client :** Modèles puissants et créatifs pour la génération des réponses finales à l'utilisateur (ex: `Synthesizer`).

    ---

    ## 3. Architecture et Technologies

    ### 3.1. Technologies Principales
    *   **Orchestration :** Docker, Docker Compose
    *   **Backend API :** FastAPI
    *   **Serveur Applicatif :** Nginx (agissant comme serveur web statique et reverse proxy) et Uvicorn (pour l'API FastAPI).
    *   **Gestion des processus Bots :** Python 3.11+, `subprocess`
    *   **Base de Données Relationnelle (Gestion) :** PostgreSQL (via SQLAlchemy)
    *   **Migration de Base de Données :** Alembic (pour les mises à jour de schéma non-destructives)
    *   **Base de Données Vectorielle (Mémoire LTM Isolée) :** ChromaDB
    *   **Interaction LLM :** `requests`, `httpx`, `ollama-python`
    *   **Client Discord :** `discord.py`
    *   **Tâches Asynchrones :** Celery, Redis

    ### 3.2. Arborescence Complète du Projet et Rôle des Fichiers

    ```
    📁 GroBot/
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
      │  ├─ 📄 alembic.ini                 # Fichier de configuration pour Alembic.
      │  ├─ 📄 config.py                   # Charge les variables d'environnement via Pydantic.
      │  ├─ 📄 main.py                     # Point d'entrée de l'API FastAPI, gère le cycle de vie et les routeurs.
      │  │
      │  ├─ 📁 alembic/                    # Dossier pour la gestion des migrations de base de données.
      │  │  ├─ 📄 README                    # Instructions pour Alembic.
      │  │  ├─ 📄 env.py                    # Script de configuration d'environnement pour Alembic.
      │  │  ├─ 📄 script.py.mako            # Template pour les nouveaux scripts de migration.
      │  │  └─ 📁 versions/               # Contient tous les scripts de migration générés.
      │  │     └─ ... (fichiers de migration auto-générés)
      │  │
      │  ├─ 📁 api/                        # Contient les routeurs FastAPI (endpoints).
      │  │  ├─ 📄 __init__.py               # Marque le dossier comme un package Python.
      │  │  ├─ 📄 bots_api.py               # API pour la gestion des bots (CRUD).
      │  │  ├─ 📄 bots_api.py.bak           # Fichier de sauvegarde, non utilisé.
      │  │  ├─ 📄 chat_api.py               # API pour l'orchestration des agents et le chat.
      │  │  ├─ 📄 files_api.py              # API pour la gestion des fichiers.
      │  │  ├─ 📄 llm_api.py                # API pour l'interaction avec les LLMs (ex: lister les modèles).
      │  │  ├─ 📄 mcp_api.py                # API pour la gestion des serveurs MCP.
      │  │  ├─ 📄 settings_api.py           # API pour les paramètres globaux.
      │  │  ├─ 📄 tools_api.py              # API proxy pour l'exécution des outils externes (MCP).
      │  │  └─ 📄 user_profiles_api.py      # API pour la gestion des profils et notes utilisateurs.
      │  │
      │  ├─ 📁 core/                       # Logique métier principale de l'application.
      │  │  ├─ 📄 __init__.py               # Marque le dossier comme un package Python.
      │  │  ├─ 📄 agent_logic.py.old        # Fichier de sauvegarde, non utilisé.
      │  │  ├─ 📄 agent_orchestrator.py     # Orchestre la chaîne d'appels aux agents spécialisés.
      │  │  ├─ 📄 llm_manager.py            # Gère les instances de clients LLM et les interactions.
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
      │  │  ├─ 📄 crud_bots.py              # Fonctions CRUD pour les bots.
      │  │  ├─ 📄 crud_files.py             # Fonctions CRUD pour les fichiers.
      │  │  ├─ 📄 crud_mcp.py               # Fonctions CRUD pour les serveurs MCP.
      │  │  ├─ 📄 crud_settings.py          # Fonctions CRUD pour les paramètres globaux.
      │  │  ├─ 📄 crud_user_notes.py        # Fonctions CRUD pour les notes sur les utilisateurs.
      │  │  ├─ 📄 crud_user_profiles.py     # Fonctions CRUD pour les profils utilisateurs.
      │  │  ├─ 📄 redis_session.py          # Gère la connexion au client Redis.
      │  │  ├─ 📄 sql_models.py             # Définit les modèles de table SQLAlchemy.
      │  │  └─ 📄 sql_session.py            # Gère la session de base de données SQL.
      │  │
      │  ├─ 📁 schemas/                    # Contient les schémas Pydantic pour la validation des données API.
      │  │  ├─ 📄 __init__.py               # Marque le dossier comme un package Python.
      │  │  ├─ 📄 bot_schemas.py            # Schémas Pydantic pour les bots.
      │  │  ├─ 📄 chat_schemas.py           # Schémas Pydantic pour le chat et les agents.
      │  │  ├─ 📄 file_schemas.py           # Schémas Pydantic pour les fichiers.
      │  │  ├─ 📄 mcp_schemas.py            # Schémas Pydantic pour les serveurs MCP.
      │  │  ├─ 📄 settings_schema.py        # Schémas Pydantic pour les paramètres.
      │  │  ├─ 📄 user_note_schemas.py      # Schémas Pydantic pour les notes utilisateurs.
      │  │  └─ 📄 user_profile_schemas.py   # Schémas Pydantic pour les profils utilisateurs.
      │  │
      │  └─ 📁 worker/                     # Configuration pour les tâches de fond (Celery).
      │     ├─ 📄 __init__.py               # Marque le dossier comme un package Python.
      │     ├─ 📄 celery_app.py             # Définit l'instance de l'application Celery.
      │     └─ 📄 tasks.py                  # Définit les tâches Celery (ex: archivage asynchrone).
      │
      ├─ 📁 chromadb_overriden/
      │  └─ 📄 Dockerfile                  # Personnalise l'image ChromaDB (ex: ajout de 'curl').
      │
      ├─ 📁 discord_bot_launcher/         # Service isolé qui gère les processus des bots Discord.
      │  ├─ 📄 bot_process.py              # Point d'entrée du client Discord, initialise les handlers.
      │  ├─ 📄 bot_process.py.old          # Fichier de sauvegarde, non utilisé.
      │  ├─ 📄 Dockerfile                  # Image Docker pour le service launcher.
      │  ├─ 📄 launcher.py                 # Script qui surveille l'API et lance/arrête les bots.
      │  ├─ 📄 requirements.txt            # Dépendances Python pour le service launcher.
      │  └─ 📁 client/                     # Logique modulaire du client Discord.
      │     ├─ 📄 __init__.py               # Marque le dossier comme un package Python.
      │     ├─ 📄 api_client.py             # Centralise toutes les requêtes vers l'API backend.
      │     ├─ 📄 discord_ui.py             # Fonctions utilitaires pour l'UI de Discord (réactions, etc.).
      │     └─ 📄 event_handler.py          # Contient la logique principale `on_message`.
      │
      ├─ 📁 frontend/                     # Application combinée (Nginx + SPA).
      │  ├─ 📄 entrypoint.sh               # Script de démarrage pour le conteneur 'app' (nginx + uvicorn).
      │  ├─ 📄 nginx.conf                  # Configuration Nginx (reverse proxy et fichiers statiques).
      │  └─ 📁 src/                        # Code source JavaScript pour l'interface utilisateur.
      │     ├─ 📄 api.js                    # Fonctions utilitaires pour les appels API.
      │     ├─ 📄 events.js                 # Gestionnaires d'événements (formulaires, WebSocket).
      │     ├─ 📄 index.html                # Structure HTML de l'application.
      │     ├─ 📄 main.js                   # Point d'entrée JavaScript, initialisation et routage.
      │     ├─ 📄 style.css                 # Styles CSS.
      │     └─ 📄 ui.js                     # Fonctions pour manipuler le DOM et mettre à jour l'UI.
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
                *   **Settings :** Le formulaire de configuration du bot, incluant les nouveaux réglages LLM par catégorie (serveur, modèle, contexte).
                *   **Files :** Le gestionnaire de fichiers du bot.
                *   **Memory :** Une vue de la mémoire vectorielle du bot.
                *   **Knowledge Base :** Une interface pour gérer les connaissances du bot sur les utilisateurs. Cette vue affiche une barre de recherche et, par défaut, la liste des utilisateurs connus par ce bot. Un clic sur un utilisateur ou une recherche réussie affiche la vue détaillée du profil et des notes de cet utilisateur.

    ---

    ## 6. Documentation : Le Standard Model Context Protocol (MCP)

    *   **Date d'Adoption :** 2025-08-15
    *   **Source de Vérité :** [Dépôt GitHub Officiel](https://github.com/modelcontextprotocol/modelcontextprotocol) et [Documentation](https://modelcontextprotocol.info/docs/)

    Cette section annule et remplace toute implémentation précédente d'outils. Le projet adopte le standard ouvert et officiel MCP pour l'intégration des outils.

    ### 6.1. Principes Fondamentaux

    1.  **Communication Standardisée :** Toutes les interactions entre un client (notre `bot_process`) et un serveur d'outils (ex: `mcp_time_tool`) **DOIVENT** utiliser le protocole **JSON-RPC 2.0**.
    2.  **Méthodes RPC Spécifiées :** Le standard définit des noms de méthodes précis que les serveurs doivent implémenter et que les clients doivent appeler. Les deux méthodes fondamentales pour les outils sont `tools/list` et `tools/call`.
    3.  **Définition via JSON Schema :** La "signature" d'un outil (son nom, sa description, ses paramètres et leurs types) est décrite de manière structurée via une JSON Schema. C'est ce qui permet une découverte véritablement automatique et fiable.

    ### 6.2. Méthodes RPC Standard

    #### 6.2.1. `tools/list`

    *   **Rôle :** Permet à client de découvrir les outils disponibles sur un serveur.
    *   **Requête du Client :**
        ```json
        {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/list",
            "params": {}
        }
        ```    *   **Réponse du Serveur :**
        ```json
        {
            "jsonrpc": "2.0",
            "id": 1,
            "result": {
                "tools": [
                    // ... liste des définitions d'outils ...
                ]
            }
        }
        ```

    #### 6.2.2. `tools/call`

    *   **Rôle :** Permet à client d'exécuter un outil spécifique avec des arguments.
    *   **Requête du Client :**
        ```json
        {
            "jsonrpc": "2.0",
            "id": 2,
            "method": "tools/call",
            "params": {
                "name": "tool_name_to_call",
                "arguments": {
                    "param1_name": "value1",
                    "param2_name": 123
                }
            }
        }
        ```    *   **Réponse du Serveur :**
        ```json
        {
            "jsonrpc": "2.0",
            "id": 2,
            "result": {
                "content": [
                    {
                        "type": "text",
                        "text": "The result of the tool execution."
                    }
                ]
            }
        }
        ```    
    ### 6.3. Format de Définition d'un Outil

    Chaque outil retourné par `tools/list` **DOIT** suivre le format JSON Schema suivant, avec la clé `inputSchema` pour les paramètres.

    **Exemple pour `get_current_time` :**
    ```json
    {
        "name": "get_current_time",
        "title": "Get Current Time",
        "description": "Returns the current server date and time. Use this for any questions about the current time, date, or day of the week.",
        "inputSchema": {
            "type": "object",
            "properties": {}
        }
    }
    ```

    ### 6.4. Implémentations MCP Connues

    Pour garantir l'interopérabilité, GroBot s'appuie sur des serveurs d'outils qui respectent le standard MCP. La documentation de référence pour ces serveurs est essentielle pour comprendre les outils disponibles.

    *   **MCP_GenImage:** Service avancé de génération d'images.
        *   *[Lien vers le project_context.md de MCP_GenImage à insérer ici]*

    ---

    ## 7. État Actuel et Plan d'Action

    ### 7.1. Bugs Connus et Régression (Issues Actuellement Ouvertes)

    *   **Erreur de Parsing de l'Agent `Parameter Extractor`**
        *   **Description :** La chaîne d'agents s'interrompt après que le `Tool Identifier` a correctement identifié un outil. Le `Parameter Extractor` reçoit une réponse JSON valide du LLM, mais le code Python qui valide cette réponse échoue.
        *   **Analyse Technique :** Le log d'erreur `name 'ParameterExtractionResult' is not defined` indique une `NameError` en Python. Cela signifie que la classe (probablement un schéma Pydantic) `ParameterExtractionResult` est utilisée dans le code de l'orchestrateur sans avoir été importée au préalable.
        *   **Impact :** CRITIQUE. L'utilisation d'outils est complètement bloquée.
        *   **Statut :** NON RÉSOLU.

    *   **Erreurs de Communication avec Certains Serveurs MCP**
        *   **Description :** Lors de la découverte des outils, les requêtes vers certains serveurs MCP (ex: `mtp-sd-swarm00:8001`, `mtp-sd-swarm00:8002`) génèrent une erreur `MCP server ... returned an error: None` dans les logs, bien que la requête HTTP sous-jacente reçoive un statut `200 OK`.
        *   **Analyse Technique :** L'échec se produit probablement lors de l'analyse de la réponse. La cause la plus probable est que ces serveurs renvoient une réponse qui n'est pas un JSON valide ou qui ne respecte pas le format JSON-RPC 2.0 attendu (ex: une page HTML d'erreur, une chaîne de caractères, etc.).
        *   **Impact :** Les outils hébergés sur les serveurs défaillants ne peuvent pas être découverts ni utilisés par les bots.
        *   **Statut :** NON RÉSOLU.

    *   **Problème d'Interface Utilisateur dans l'Onglet "Memory" (`frontend/src/ui.js`, `app/api/chat_api.py`)**
        *   **Description :** L'onglet "Memory" dans l'interface utilisateur ne fonctionne pas. Le code de `frontend/src/ui.js` contient une section commentée ou une référence à `fetchBotMemory` qui ne semble pas être correctement appelée ou rendue.
        *   **Impact :** L'utilisateur ne peut pas consulter la mémoire conversationnelle du bot.
        *   **Statut :** NON RÉSOLU.

    *   **Outils non Fonctionnels dans l'Interface de Test (`frontend/src/ui.js`)**
        *   **Description :** Les outils (comme `generate_image` ou `describe_image`) ne fonctionnent pas lorsqu'ils sont appelés depuis l'interface de test chat dans le frontend. Le code dans `handleTestChatSubmit` ne semble pas gérer l'exécution des outils directement.
        *   **Impact :** L'utilisateur ne peut pas tester les fonctionnalités des outils via l'interface web.
        *   **Statut :** NON RÉSOLU.

    *   **Suppression de Bot Impossible (`frontend/src/ui.js`, `app/api/bots_api.py`)**
        *   **Description :** La fonctionnalité de suppression d'un bot n'est pas implémentée dans l'interface utilisateur (pas de bouton ou de logique de gestion pour la suppression) ni dans l'API backend (`bots_api.py`). Bien que le `crud_bots.delete_bot` existe, il n'est pas appelé par une route API.
        *   **Impact :** Les utilisateurs ne peuvent pas supprimer des bots via l'interface web.
        *   **Statut :** NON RÉSOLU.

    ### 7.2. Bugs Récemment Résolus

    *   **Dysfonctionnement du Chargement des Paramètres Globaux LLM (`frontend/src/ui.js`)**
        *   **Analyse :** Après sauvegarde et rechargement, les listes déroulantes des modèles LLM restaient vides. Le problème provenait d'un bug de timing dans le rendu du DOM : le code tentait de trouver l'élément `<select>` par son ID (`document.getElementById`) alors que celui-ci n'existait qu'en mémoire et n'était pas encore attaché à la page.
        *   **Résolution :** La fonction `populateModelDropdown` a été modifiée pour accepter un objet élément DOM directement, au lieu d'un ID. Le code de rendu (`createLlmConfigBlock`) a été mis à jour pour trouver l'élément `<select>` dans le fragment de DOM en mémoire et passer l'objet directement à la fonction, garantissant que la cible existe toujours au moment du peuplement.
        *   **Statut :** RÉSOLU.

    *   **Crash du Streaming de Réponse (`app/api/chat_api.py`)**
        *   **Analyse :** Le serveur crashait avec une `TypeError: object async_generator can't be used in 'await' expression` lors de la génération d'une réponse. La fonction `synthesizer.run_synthesizer` avait été refactorisée pour être un générateur asynchrone (utilisant `yield`), mais le code appelant dans `chat_api.py` essayait encore de l'`attendre` (`await`) comme une fonction normale.
        *   **Résolution :** L'appel `await synthesizer.run_synthesizer(...)` a été remplacé par une boucle `async for chunk in synthesizer.run_synthesizer(...)`, qui est la syntaxe correcte pour consommer un générateur asynchrone.
        *   **Statut :** RÉSOLU.

    ### 7.3. Points d'Amélioration Potentiels (Code/Architecture)

    *   **Backend Implementation for Categorized LLM Configuration (`app/database/sql_models.py`, `app/schemas/*`, `app/api/*`)**
        *   **Description :** Le frontend a été mis à jour pour permettre la configuration de modèles LLM par catégorie (Décisionnel, Outils, Output). Le backend doit maintenant être adapté pour supporter cette nouvelle structure (migration de base de données, mise à jour des schémas Pydantic et des endpoints, refactorisation de l'orchestrateur).
        *   **Impact :** La nouvelle configuration LLM n'est pas pleinement fonctionnelle tant que le backend n'est pas mis à jour.

    *   **Gestion des Exceptions dans les Outils MCP (`grobot_tools/file_tools/server.py`, `grobot_tools/time_tool/server.py`) :**
        *   **Description :** Les gestionnaires d'outils retournent des chaînes de caractères simples en cas d'erreur. Il serait préférable de retourner des réponses JSON-RPC standard avec des codes d'erreur appropriés.
        *   **Impact :** Le client pourrait avoir du mal à interpréter les erreurs des outils externes.

    *   **Cohérence des Chemins d'API dans le Frontend (`frontend/src/api.js`) :**
        *   **Description :** Le code frontend utilise parfois `/api/...` et parfois des chemins directs. Il serait plus robuste d'utiliser systématiquement une constante `API_BASE_URL`.
        *   **Impact :** Potentiel de 404 si la configuration Nginx change.

    *   **Détail des Outils dans le Prompt (`app/core/agents/tool_identifier.py`) :**
        *   **Description :** Le formatage des outils pour le prompt n'inclut que le nom et la description. L'ajout de parties clés du `inputSchema` pourrait aider le LLM à mieux choisir les outils.
        *   **Impact :** Le LLM pourrait mal choisir les outils s'il manque des informations contextuelles.

    *   **Robustesse du Launcher Discord (`discord_bot_launcher/launcher.py`) :**
        *   **Description :** La gestion des erreurs au démarrage (token invalide, API indisponible) pourrait être améliorée avec des retries plus sophistiqués.
        *   **Impact :** Arrêt du launcher en cas de problèmes de démarrage.

    *   **Consistance et Clarté des Loggers (`Ensemble du backend`)**
        *   **Description :** De nombreuses parties du code (orchestrateur, appels MCP) utilisent une instance de logger générique qui s'identifie à tort comme `(CHROMA_MANAGER)`. Cela rend l'analyse des logs et le débogage difficiles.
        *   **Suggestion :** Adopter la bonne pratique Python d'initialiser les loggers dans chaque module avec `logging.getLogger(__name__)`. Cela nommera automatiquement le logger d'après le chemin du fichier (ex: `app.core.agent_orchestrator`), permettant une identification immédiate de la source d'un message.

    ---

    ## 8. ANNEXE : Anciennes Architectures d'Agent (Obsolètes)

    > **ATTENTION :** Cette section décrit les anciennes architectures qui ne sont plus en production. Elle est conservée à titre de référence historique uniquement.

    ### 8.1. Architecture "Chaîne de Montage" Asynchrone (Session 96-121)

    Cette architecture utilisait une chaîne de 4 LLM (Gardien, Répartiteur, Synthétiseur, Archiviste) principalement orchestrée par le client `bot_process.py`. Le client gérait la décision d'utiliser des outils, leur exécution (interne ou via proxy), et l'envoi des résultats au Synthétiseur. Elle a été remplacée car la logique de décision était trop monolithique (un seul "Répartiteur") et la gestion de la boucle d'outils par le client était trop complexe.

    ### 8.2. Architecture Monolithique (Pré-Session 96)

    Cette architecture initiale reposait sur un unique appel LLM avec une liste d'outils au format `ollama-python`. Le client `bot_process.py` était responsable de la gestion complète de la boucle "appel LLM -> détection d'appel d'outil -> exécution de l'outil -> second appel LLM avec le résultat". Elle a été abandonnée en raison de sa faible fiabilité pour les tâches complexes et du manque de contrôle sur le raisonnement du LLM.