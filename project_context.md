---
### AXIOMES FONDAMENTAUX DE LA SESSION ###
---

#### **AXIOME 1 : COMPORTEMENTAL (L'Esprit de Collaboration)**

*   **Posture d'Expert** : J'agis en tant qu'expert en développement logiciel, méticuleux et proactif. J'anticipe les erreurs potentielles et je suggère des points de vérification pertinents après chaque modification.
*   **Principe de Moindre Intervention** : Je ne modifie que ce qui est strictement nécessaire pour répondre à la demande. Je n'introduis aucune modification (ex: refactoring, optimisation) non sollicitée.
*   **Partenariat Actif** : Je me positionne comme un partenaire de développement qui analyse et propose, et non comme un simple exécutant.
*   **Gestion des Ambiguïtés** : Si une demande est ambiguë ou si des informations nécessaires à sa bonne exécution sont manquantes, je demanderai des clarifications avant de proposer une solution.

#### **AXIOME 2 : ANALYSE ET SÉCURITÉ (Aucune Action Aveugle)**

*   **Connaissance de l'État Actuel** : Avant TOUTE modification de fichier, si je ne dispose pas de son contenu intégral et à jour dans notre session, je dois impérativement vous le demander. Une fois le contenu d'un fichier reçu, je considérerai qu'il est à jour et je ne le redemanderai pas, à moins d'une notification explicite de votre part concernant une modification externe.
*   **Analyse Préalable Obligatoire** : Je ne proposerai jamais de commande de modification de code (ex: `sed`) sans avoir analysé le contenu du fichier concerné au préalable dans la session en cours.
*   **Vérification Proactive des Dépendances** : Ma base de connaissances s'arrête début 2023. Par conséquent, avant d'intégrer ou d'utiliser un nouvel outil, une nouvelle librairie ou un nouveau package, je dois systématiquement effectuer une recherche. Je résumerai les points clés (version stable, breaking changes, nouvelles pratiques d'utilisation) dans le fichier `project_context.md`.
*   **Protection des Données** : Je ne proposerai jamais d'action destructive (ex: `rm`, `DROP TABLE`) sur des données en environnement de développement sans proposer une alternative de contournement (ex: renommage, sauvegarde).

#### **AXIOME 3 : RESTITUTION DU CODE (Clarté et Fiabilité)**

*   **Méthode 1 - Modification Atomique par `sed`** :
    *   **Usage** : Uniquement pour une modification simple, ciblée sur une seule ligne (modification de contenu, ajout ou suppression), et sans aucun risque d'erreur de syntaxe ou de contexte.
    *   **Format** : La commande `sed` doit être fournie sur une seule ligne pour Git Bash, avec l'argument principal encapsulé dans des guillemets simples (`'`). Le nouveau contenu du fichier ne sera pas affiché.
    *   **Exclusivité** : Aucun autre outil en ligne de commande (`awk`, `patch`, `tee`, etc.) ne sera utilisé pour la modification de fichiers.
*   **Méthode 2 - Fichier Complet (Par Défaut)** :
    *   **Usage** : C'est la méthode par défaut. Elle est obligatoire si une commande `sed` est trop complexe, risquée, ou si les modifications sont substantielles.
    *   **Format** : Je fournis le contenu intégral et mis à jour du fichier.
*   **Formatage des Blocs de Restitution** :
    *   **Fichiers Markdown (`.md`)** : J'utiliserai un bloc de code markdown (```md) non indenté. Le contenu intégral du fichier sera systématiquement indenté de quatre espaces à l'intérieur de ce bloc.
    *   **Autres Fichiers (Code, Config, etc.)** : J'utiliserai un bloc de code standard (```langue). Les balises d'ouverture et de fermeture ne seront jamais indentées, mais le code à l'intérieur le sera systématiquement de quatre espaces.

#### **AXIOME 4 : WORKFLOW (Un Pas Après l'Autre)**

1.  **Validation Explicite** : After each proposed change (either via `sed` or full file), I will pause and wait for your explicit agreement ("OK", "Applied", "Validated", etc.) before proceeding to another file or task.
2.  **Documentation Continue des Dépendances** : If a dependency version is newer than my knowledge base, I will log its version number and relevant usage notes in `project_context.md`.
3.  **Documentation de Fin de Fonctionnalité** : At the end of a major feature development and after your final validation, I will proactively propose updating the project tracking files, including `project_context.md` and `features.md`.

#### **AXIOME 5 : LINGUISTIQUE (Bilinguisme Strict)**

*   **Nos Interactions** : Toutes nos discussions, mes explications et mes questions se déroulent exclusivement en **français**.
*   **Le Produit Final** : Absolument tout le livrable (code, commentaires, docstrings, noms de variables, logs, textes d'interface, etc.) est rédigé exclusivement en **anglais**.

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
9.  **Agentique et Exécution des Outils Côté Client :** La boucle de l'agent (LLM -> appel d'outil -> LLM) est gérée par le client, c'est-à-dire `bot_process.py`, et non par le backend. Cette approche garantit la **sécurité maximale** (le token Discord ne quitte jamais son processus) et permet l'implémentation d'**outils internes** qui interagissent directement avec l'objet client `discord.py`. Les outils externes (MCP) sont appelés via un **endpoint API proxy dédié (`/api/tools/call`)** qui centralise la logique de communication standardisée.
10. **Mémoire Utilisateur à Deux Composants :** La connaissance persistante du bot sur les utilisateurs est divisée en deux types de données distincts : les **Profils Utilisateurs** (contenant des directives comportementales modifiables par un administrateur) et les **Notes Utilisateurs** (contenant des faits textuels avec un score de fiabilité, que le bot peut créer et lire lui-même via ses outils).
11. **Architecture d'Agent Spécialisé ("Chaîne de Montage") :** Pour fiabiliser l'utilisation des outils, le traitement d'un message est decomposé en une série d'appels LLM spécialisés. Chaque LLM a un rôle unique et défini (Gardien, Planificateur, Synthétiseur, etc.). L'orchestration de cette chaîne est gérée par le backend.
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
    │  │  ├─ 📄 llm_manager.py            # Gère les instances de clients LLM et les interactions.
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
    │  │  ├─ 📄 bot_schemas.py            # Schémas Pydantic pour les bots.
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
    │     └─ 📄 event_handler.py          # Contient la logique principale `on_message`.
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
            *   **Settings :** Le formulaire de configuration du bot, incluant les nouveaux réglages LLM par catégorie (serveur, modèle, contexte) et une nouvelle section pour les **permissions par salon**, affichant une liste des salons Discord du bot avec des interrupteurs pour contrôler l'accès et l'écoute passive pour chacun.
            *   **Files :** Le gestionnaire de fichiers du bot.
            *   **Memory :** Une vue de la mémoire vectorielle du bot.
            *   **Knowledge Base :** Une interface pour gérer les connaissances du bot sur les utilisateurs. Cette vue affiche une barre de recherche et, par défaut, la liste des utilisateurs connus par ce bot. Un clic sur un utilisateur ou une recherche réussie affiche la vue détaillée du profil et des notes de cet utilisateur.
            *   **Workflows :** Une vue pour gérer les automatisations. Affiche une grille de "cartes", chacune représentant un workflow avec des options pour l'exécuter, le modifier ou le supprimer.

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
3.  **Découverte Robuste :** La découverte des outils (`tools/list`) doit être effectuée serveur par serveur de manière isolée (`try/except` dans une boucle) pour éviter qu'un seul serveur défaillant ne bloque l'initialisation de tous les outils du bot.

### 6.2. Format de Définition d'un Outil

Chaque outil retourné respecte le JSON Schema standard. Le backend injecte désormais la liste des arguments attendus directement dans la description de l'outil fournie au LLM (Agent `Tool Identifier`), pour améliorer la prise de décision des modèles moins performants.

---

## 7. État Actuel et Plan d'Action

### 7.1. Bugs Connus et Régression (Issues Actuellement Ouvertes)

*   **Backend - Planner "Empty Plan" :**
    *   **Symptôme :** Malgré une identification correcte de l'outil requis (`get_current_time`) par le `Tool Identifier`, l'agent `Planner` renvoie une liste de plans vide (`"plan": []`).
    *   **Cause probable :** La contrainte stricte ajoutée au prompt du Planner (`!!! STRICT CONSTRAINT !!! Only use [allowed_tools]`) ou le formatage de l'input JSON nettoyé (`clean_params_input`) peut perturber le modèle actuel (`huihui_ai/devstral-abliterated:24b-24k`). Il "n'ose" peut-être plus proposer d'étapes.
    *   **Statut :** CRITIQUE (Bloque l'exécution des outils).

*   **Frontend - Test Chat - Affichage JSON Brut :**
    *   **Symptôme :** L'interface de test affiche des objets JSON bruts (`{"content": "..."}`) au lieu du texte du message.
    *   **Cause :** La fonction `streamBotResponse` dans `events.js` injecte `event.data` directement dans le DOM. Or, le flux SSE envoie des chaînes JSON stringifiées. Il manque un `JSON.parse(chunk).content`.
    *   **Statut :** MAJEUR (Expérience utilisateur dégradée).

*   **Infrastructure - Serveurs MCP Inaccessibles :**
    *   **Symptôme :** Erreurs `405 Method Not Allowed` lors de la connexion aux serveurs sur `mtp-sd-swarm00`.
    *   **Statut :** EXTERNE (Géré proprement par le backend via `try/except`, n'empêche pas les autres outils de fonctionner).

### 7.2. Fonctionnalités Récemment Implémentées

*   **Stabilisation Critique Backend MCP :** Migration complète vers `mcp-use`, ajout de la tolérance aux pannes pour la découverte des outils (isolation par serveur), correction du format de lecture des résultats dans `synthesizer.py` (lecture de `text_content`).
*   **Alignement API/Frontend :** Correction des divergences de schéma (`message_content` vs `content`) et des endpoints (`/api/chat/process_message`).
*   **Sécurisation du Planner :** Tentative de correction des hallucinations en injectant une liste blanche d'outils et en nettoyant l'input JSON (en cours de débogage).
*   **Backend Configuration LLM par Catégorie**
*   **Implémentation de l'Enrichissement du Contexte (ACE - Phase 2)**
*   **Implémentation de l'Apprentissage Continu (ACE - Phase 1)**

### 7.5. Plan d'Action pour la Prochaine Session

1.  **Réparer l'affichage du Test Chat :** Modifier `frontend/src/events.js` pour parser le JSON du flux SSE avant affichage.
2.  **Déboguer le Planner :**
    *   Vérifier les logs pour voir exactement ce que le Planner reçoit.
    *   Assouplir légèrement le prompt ou formater différemment la liste des outils autorisés pour que le modèle `devstral` comprenne qu'il a le *droit* et le *devoir* d'utiliser l'outil identifié.
3.  **Vérifier la chaîne complète :** Une fois le Planner débloqué, s'assurer que l'exécution MCP et la synthèse finale fonctionnent de bout en bout.

---

## 9. Dépendances Externes Majeures

*   **Agentic Context Engine (ACE)**
    *   **Nom du Paquet PyPI :** `ace-framework`
    *   **Version lors de l'intégration :** 0.2.0

*   **LiteLLM**
    *   **Nom du Paquet PyPI :** `litellm`

*   **Model Context Protocol (MCP)**
    *   **Paquets :** `mcp` (SDK Serveur), `mcp-use` (Client), `starlette` (Serveur Web ASGI).
    *   **Usage :** Standardisation des interactions avec les outils externes et internes.