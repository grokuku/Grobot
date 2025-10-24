#### Ce fichier sert de référence unique et doit être fourni en intégralité au début de chaque session.

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

1.  **Validation Explicite** : Après chaque proposition de modification (que ce soit par `sed` ou par fichier complet), je marque une pause. J'attends votre accord explicite ("OK", "Appliqué", "Validé", etc.) avant de passer à un autre fichier ou à une autre tâche.
2.  **Documentation Continue des Dépendances** : Si la version d'une dépendance s'avère plus récente que ma base de connaissances, je consigne son numéro de version et les notes d'utilisation pertinentes dans le fichier `project_context.md`.
3.  **Documentation de Fin de Fonctionnalité** : À la fin du développement d'une fonctionnalité majeure et après votre validation finale, je proposerai de manière proactive la mise à jour des fichiers de suivi du projet, notamment `project_context.md` et `features.md`.

#### **AXIOME 5 : LINGUISTIQUE (Bilinguisme Strict)**

*   **Nos Interactions** : Toutes nos discussions, mes explications et mes questions se déroulent exclusivement en **français**.
*   **Le Produit Final** : Absolument tout le livrable (code, commentaires, docstrings, noms de variables, logs, textes d'interface, etc.) est rédigé exclusivement en **anglais**.

---
### FIN DES AXIOMES FONDAMENTAUX ###
---


---
### 1. Vision et Objectifs du Projet

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
    │  │  ├─ 📄 bots_api.py.bak           # Fichier de sauvegarde, non utilisé.
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
    │  │  ├─ 📄 agent_logic.py.old        # Fichier de sauvegarde, non utilisé.
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
    ```
*   **Réponse du Serveur :**
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
    ```
*   **Réponse du Serveur :**
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

*   **Timeout de la commande `/prompt_generator` et Échec de l'Autocomplétion des Styles (`app/api/tools_api.py`, `discord_bot_launcher/client/event_handler.py`)**
    *   **Description :** La commande `/prompt_generator` échoue par intermittence avec une erreur "Cette interaction a échoué" (timeout de 3 secondes de Discord). Simultanément, la liste des styles pour l'autocomplétion est souvent vide. Le bug ne se produit que lorsque le cache des définitions d'outils du backend est expiré.
    *   **Hypothèse :** Il s'agit d'une "course au délai". La découverte des outils, qui interroge tous les serveurs MCP, prend parfois trop de temps, même en local, et dépasse les délais stricts de Discord pour la réponse à une interaction.
    *   **Plan d'action :** L'investigation est en cours. La première étape convenue est d'appliquer une version instrumentée de `app/api/tools_api.py` qui ajoute des logs de performance détaillés. Ces logs permettront de mesurer précisément le temps pris par les appels réseau et de confirmer ou d'infirmer l'hypothèse de la latence avant d'appliquer un correctif.
    *   **Statut :** EN COURS D'INVESTIGATION.

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

### 7.2. Fonctionnalités Récemment Implémentées

*   **Gestion Fine des Permissions par Salon**
    *   **Analyse :** Le simple interrupteur global "Passive Listening" était insuffisant pour tester le `Gatekeeper` dans un environnement de production sans perturber les utilisateurs. Un besoin a été identifié pour contrôler le comportement du bot de manière granulaire, salon par salon, avec deux niveaux de contrôle : un blocage total ("Access") et un contrôle de l'écoute passive ("Passive Listening").
    *   **Résolution :** La fonctionnalité a été implémentée sur l'ensemble de la pile. **1. Base de Données :** Une nouvelle table `channel_settings` a été ajoutée via un modèle SQLAlchemy (`sql_models.py`) et une migration Alembic pour stocker les permissions. **2. Backend :** Un nouveau fichier CRUD (`crud_channel_settings.py`) et de nouveaux schémas Pydantic (`bot_schemas.py`) ont été créés. Deux nouveaux endpoints ont été ajoutés à `bots_api.py` : un `POST` pour sauvegarder les permissions et un `GET` qui utilise une requête WebSocket vers le client Discord pour obtenir la liste des salons en temps réel et la fusionner avec les permissions stockées. **3. Frontend :** L'interface utilisateur dans l'onglet "Settings" (`ui.js`) a été refondue pour remplacer l'ancien interrupteur par un tableau affichant chaque salon avec ses deux interrupteurs. Les appels API (`api.js`) et les gestionnaires d'événements (`events.js`, `main.js`) correspondants ont été implémentés pour rendre l'interface interactive. **4. Client Discord :** La logique au début de la fonction `on_message` dans `event_handler.py` a été entièrement revue pour lire les permissions par salon depuis la configuration du bot mise en cache et appliquer les règles d'accès et d'écoute passive avant tout traitement.
    *   **Statut :** IMPLÉMENTÉ.

*   **Implémentation du Logging des Interactions LLM**
    *   **Analyse :** Un besoin crucial de débogage a été identifié : visualiser les prompts exacts envoyés aux LLM et les réponses brutes reçues. Cela est essentiel pour comprendre le comportement des agents et corriger les problèmes de contexte.
    *   **Résolution :** Un système de logging dédié a été implémenté. **1. Infrastructure :** Un répertoire `logs/` a été créé et monté via un volume dans `docker-compose.yml`. **2. Backend :** Une fonction de logging dédiée (`log_llm_interaction`) a été ajoutée dans `app/core/llm_manager.py`. Elle écrit chaque interaction (prompt et réponse) dans un fichier `logs/llm_interactions.md` dans un format Markdown lisible. Cette fonction est appelée depuis les points d'entrée `call_llm` et `call_llm_stream`, garantissant que tous les appels LLM, quelle que soit leur catégorie (décisionnel, outils, output), sont tracés.
    *   **Statut :** IMPLÉMENTÉ.

*   **Amélioration de la Visualisation des Évaluations LLM : Ajout du Modèle et du Contexte**
    *   **Analyse :** La fonctionnalité de visualisation des résultats d'évaluation était fonctionnelle mais incomplète. Elle n'affichait pas les informations cruciales que sont le nom du modèle et la taille de la fenêtre de contexte utilisés pour chaque test, rendant les résultats difficiles à comparer et à interpréter.
    *   **Résolution :** L'implémentation a été réalisée sur l'ensemble de la pile. **1. Backend :** La colonne `llm_context_window` a été ajoutée à la table `llm_evaluation_runs` via un modèle (`sql_models.py`) et une migration Alembic. Les schémas Pydantic (`settings_schema.py`) ont été mis à jour pour recevoir et retourner cette donnée, et la fonction CRUD (`crud_settings.py`) a été adaptée pour la sauvegarder. **2. Frontend :** L'appel API dans `api.js` a été modifié pour inclure la fenêtre de contexte. Le gestionnaire d'événements dans `events.js` a été corrigé pour lire la valeur du champ de contexte et la passer à l'API. Enfin, la fonction de rendu dans `ui.js` a été mise à jour pour afficher les nouvelles colonnes "Model Name" et "Context" dans le tableau des résultats.
    *   **Statut :** IMPLÉMENTÉ.

*   **Visualisation des Résultats d'Évaluation des Modèles LLM**
    *   **Analyse :** La fonctionnalité d'évaluation des LLM a été implémentée, mais il n'existait aucun moyen de visualiser l'historique des résultats, rendant la fonctionnalité incomplète.
    *   **Résolution :** L'historique des évaluations est maintenant consultable directement depuis l'interface. **1. Backend :** Un nouveau schéma Pydantic (`LLMEvaluationRunResult`) a été créé dans `app/schemas/settings_schema.py`. Une fonction CRUD `get_llm_evaluation_runs_by_category` a été ajoutée à `app/database/crud_settings.py` pour récupérer les données. Un nouvel endpoint `GET /api/settings/llm/evaluations/{llm_category}` a été implémenté dans `app/api/settings_api.py` pour exposer ces données. **2. Frontend :** Une fonction d'appel `fetchLLMEvaluationResults` a été ajoutée à `frontend/src/api.js`. Dans `frontend/src/ui.js`, la logique d'affichage a été créée via une nouvelle fonction `renderEvaluationResults`. Un bouton "View Results" a été ajouté aux blocs de configuration LLM, avec un gestionnaire d'événements qui déclenche l'appel API et affiche les résultats dans un tableau, avec un comportement de bascule (afficher/masquer).
    *   **Statut :** IMPLÉMENTÉ.

*   **Implémentation de l'Évaluation des Modèles LLM (Backend & Frontend)**
    *   **Analyse :** Un besoin a été identifié pour tester objectivement la fiabilité et la performance des modèles LLM locaux directement depuis l'interface GroBot. L'objectif était de simuler une charge de travail réaliste en faisant varier la taille du contexte et la fenêtre de contexte maximale allouée.
    *   **Résolution :** La fonctionnalité a été implémentée de bout en bout. **1. Correctif Préalable :** Un bug empêchant la prise en compte du paramètre `context_window` a été corrigé dans `app/core/llm_manager.py`. **2. Backend (Base de Données) :** Une nouvelle table `llm_evaluation_runs` a été créée via un modèle dans `app/database/sql_models.py` et une migration Alembic pour stocker les résultats. **3. Backend (API & Worker) :** Un nouvel endpoint `POST /api/settings/llm/evaluate` a été créé dans `app/api/settings_api.py` pour lancer les évaluations. Il utilise de nouveaux schémas Pydantic (`app/schemas/settings_schema.py`) et une fonction CRUD (`app/database/crud_settings.py`) pour créer une tâche en base de données avant de la déléguer à Celery. Une nouvelle tâche `run_llm_evaluation` a été ajoutée dans `app/worker/tasks.py`, contenant la logique de test (double boucle, gestion d'état, sauvegarde des résultats). **4. Frontend (Interface & Logique) :** Un bouton "Evaluate" a été ajouté aux blocs de configuration LLM dans `frontend/src/ui.js`. Une fonction `startLLMEvaluation` a été créée dans `frontend/src/api.js` pour appeler le nouvel endpoint. Enfin, la logique de gestion du clic a été implémentée dans `frontend/src/events.js` et connectée dans `frontend/src/main.js`.
    *   **Statut :** IMPLÉMENTÉ.

### 7.3. Bugs Récemment Résolus

*   **Échec de la Restitution des Résultats d'Outils en Langage Naturel (Images et Personnalité)**
    *   **Analyse :** Les outils appelés en langage naturel, comme la génération d'images, échouaient à restituer correctement leur résultat. L'investigation a révélé que l'hypothèse initiale d'une défaillance du `Planner` était incorrecte. La cause racine était une **perte de données critiques** dans la fonction `_format_tool_results_for_prompt` (`app/core/agents/synthesizer.py`), qui ignorait tous les résultats d'outils n'étant pas de type `text`. L'agent `Synthesizer`, ne recevant aucune URL d'image, était alors forcé d'halluciner une réponse textuelle erronée.
    *   **Résolution :** Une refonte architecturale de la phase de synthèse a été implémentée. **1. Spécialisation des Agents :** Le `Synthesizer` a été scindé en deux agents spécialisés. Le `Synthesizer` conversationnel original est conservé pour les interactions sans outils, tandis qu'un nouveau `ToolResultSynthesizer` a été créé avec un prompt dédié à la restitution des résultats. **2. Routage Backend :** Une fonction d'aiguillage `run_synthesis_phase` a été ajoutée à `app/core/agent_orchestrator.py` et est appelée par l'API (`app/api/chat_api.py`). Elle sélectionne le synthétiseur approprié en fonction de la présence de résultats d'outils. **3. Correction de la Perte de Données :** La fonction `_format_tool_results_for_prompt` a été corrigée pour traiter correctement les résultats de type `image`, en les transformant en une description textuelle claire pour le LLM. **4. Contrat Client :** Pour garantir la fiabilité, le `ToolResultSynthesizer` a été instruit de formater les URL d'images dans une balise technique non-ambiguë (`[IMAGE_URL:...]`). **5. Implémentation Client :** La fonction `_handle_streaming_response` dans `discord_bot_launcher/client/event_handler.py` a été modifiée pour détecter cette balise dans le message final, extraire l'URL, télécharger l'image via la fonction existante `_download_and_prepare_file`, et l'attacher au message Discord final. **6. Amélioration de la Personnalité :** Le prompt du `ToolResultSynthesizer` a été affiné pour prioriser la personnalité du bot, produisant des réponses plus naturelles tout en respectant le formatage technique de l'image.
    *   **Statut :** RÉSOLU.

*   **Échec de l'Exécution des Outils via Langage Naturel (Incompatibilité de Protocole)**
    *   **Analyse :** Les outils lents (ex: `generate_image`) échouaient lorsqu'ils étaient appelés en langage naturel. L'investigation a montré que l'orchestrateur (`agent_orchestrator.py`) effectuait un appel HTTP synchrone et attendait une réponse directe. Cependant, le serveur d'outils répondait correctement avec un message `stream/start` pour initier une connexion WebSocket, ce que l'orchestrateur ne savait pas gérer.
    *   **Résolution :** La fonction d'exécution des outils dans `app/core/agent_orchestrator.py` a été rendue "consciente du streaming". Elle est maintenant capable de détecter la réponse `stream/start`, d'extraire l'URL WebSocket et d'utiliser une nouvelle fonction helper (`_handle_mcp_stream`) pour se connecter au stream et attendre le résultat final. Le mécanisme de keepalive (ping/pong) a été ajouté pour garantir la robustesse de la connexion sans imposer de limite de temps arbitraire.
    *   **Statut :** RÉSOLU (remplacé par un bug plus spécifique).

*   **Échec de l'Exécution des Workflows avec Outils Asynchrones (Streaming)**
    *   **Analyse :** Les workflows utilisant des outils asynchrones (ex: `generate_image`) échouaient systématiquement. L'investigation a révélé une incompatibilité de protocole dans la tâche Celery `execute_workflow`. Le worker effectuait un appel HTTP synchrone et attendait une réponse directe, alors que le serveur d'outils (MCP) répondait avec un message `stream/start` pour initier une connexion WebSocket, conformément au standard pour les tâches longues. La logique du worker interprétait cette réponse de streaming valide comme une erreur, car elle ne contenait pas la clé `"result"` attendue, provoquant un `ValueError`.
    *   **Résolution :** Le bug a été corrigé en rendant la tâche `execute_workflow` (`app/worker/tasks.py`) "consciente du streaming". La logique de gestion de la réponse MCP a été entièrement revue pour traiter trois cas distincts : une réponse d'erreur, une réponse synchrone contenant une clé `"result"`, ou une réponse de démarrage de streaming (`{"method": "stream/start"}`). Dans ce dernier cas, la tâche extrait maintenant l'URL WebSocket (`ws_url`) de la réponse et utilise la fonction asynchrone existante `_handle_mcp_stream` pour se connecter au stream, attendre et récupérer le résultat final de l'outil. De plus, la mécanique de nouvelle tentative automatique (`retry`) sur échec a été supprimée, car les erreurs de workflow sont généralement déterministes.
    *   **Statut :** RÉSOLU.

*   **Non-lancement des Workflows (Manuels et Cron)**
    *   **Analyse :** Les workflows ne se lançaient pas du tout. Les logs du worker Celery montraient que la tâche `execute_workflow` se terminait avec succès en 1ms, car son contenu avait été accidentellement supprimé. De plus, la planification (cron) n'était pas implémentée.
    *   **Résolution :** Une série de correctifs a été appliquée. **1. Ré-implémentation :** La logique complète de `execute_workflow` a été restaurée dans `app/worker/tasks.py`. **2. Implémentation du Cron :** Une nouvelle tâche `schedule_cron_workflows` a été créée pour scanner et lancer les workflows planifiés, et le `beat_schedule` a été configuré dans `app/worker/celery_app.py` pour l'exécuter toutes les minutes. **3. Dépendances :** La librairie `croniter` a été ajoutée à `requirements.txt`. **4. Débogage Itératif :** Plusieurs `AttributeError` et `UnsupportedProtocol` ont été corrigés en reconstruisant correctement l'URL des serveurs MCP. Des erreurs de validation de type (string vs list) ont été corrigées en ajoutant une logique de transformation de données dans le worker pour les outils `generate_prompt` et `generate_image`.
    *   **Statut :** RÉSOLU (remplacé par un bug plus spécifique).

*   **Anonymat de l'Historique de Conversation**
    *   **Analyse :** Les nouveaux logs LLM ont révélé un bug critique : l'historique des conversations envoyé au LLM anonymisait tous les participants sous le rôle générique "user". Le LLM était incapable de distinguer qui parlait, ce qui l'empêchait de suivre des conversations multi-utilisateurs et de répondre de manière contextuelle.
    *   **Résolution :** Une correction a été appliquée sur l'ensemble de la chaîne de données. **1. Schéma :** Le champ optionnel `name` a été ajouté au schéma `ChatMessage` dans `app/schemas/chat_schemas.py`. **2. Client Discord :** La fonction `_fetch_history` dans `discord_bot_launcher/client/event_handler.py` a été modifiée pour récupérer et inclure le `display_name` de chaque auteur de message. **3. Logging :** La fonction `log_llm_interaction` dans `app/core/llm_manager.py` a été mise à jour pour afficher ce nouveau nom, rendant les logs lisibles et confirmant le correctif.
    *   **Statut :** RÉSOLU.

*   **Fenêtre de Contexte non Sauvegardée lors de l'Évaluation LLM**
    *   **Analyse :** Après la mise en place de l'interface pour l'ajout de la fenêtre de contexte, il a été constaté que la valeur n'était pas enregistrée. La colonne "Context" dans les résultats affichait systématiquement "N/A". L'investigation a montré que le gestionnaire d'événements JavaScript ne lisait pas la valeur de ce nouveau champ avant de lancer l'appel API.
    *   **Résolution :** Le bug a été corrigé dans la fonction `handleEvaluateLlm` du fichier `frontend/src/events.js`. La fonction a été modifiée pour lire l'attribut `data-context-field-id` du bouton, récupérer la valeur de l'input correspondant et l'inclure dans la charge utile de la requête envoyée à l'API.
    *   **Statut :** RÉSOLU.

*   **Échec de l'Évaluation LLM et Cascade d'Erreurs Associées**
    *   **Analyse :** Le symptôme initial était une erreur 404 "Not Found" lors du clic sur le bouton "Evaluate". L'enquête a révélé une cascade d'erreurs à plusieurs niveaux. La cause de la 404 était que l'endpoint `/api/settings/llm/evaluate` était complètement manquant dans `app/api/settings_api.py`. Après sa réintégration, une `TypeError` a été déclenchée car l'API appelait la tâche Celery avec des arguments incorrects. Une fois ce problème corrigé, une `AttributeError` est apparue dans le worker car il tentait d'importer un modèle SQLAlchemy depuis le mauvais module. Le dernier obstacle était une `ConnectionError`, car le conteneur du worker ne parvenait pas à joindre le serveur Ollama. La cause en était une configuration réseau manquante (`extra_hosts`) pour le service `worker` dans `docker-compose.yml`. Parallèlement, un bug de régression a été découvert : le bouton "Save Changes" des paramètres globaux était inopérant à cause d'une `TypeError` JavaScript, due à une incohérence entre les noms de champs générés dans `ui.js` et ceux lus dans `events.js`.
    *   **Résolution :** Une série de correctifs a été appliquée sur l'ensemble de la pile. **1. API (`app/api/settings_api.py`) :** L'endpoint manquant a été réimplémenté et l'appel à la tâche Celery a été corrigé pour utiliser un dictionnaire unique, correspondant à la signature attendue. **2. Worker (`app/worker/tasks.py`) :** L'importation du modèle `LLMEvaluationRun` a été corrigée pour pointer vers `app/database/sql_models.py`. **3. Frontend (`frontend/src/ui.js`) :** Les noms de catégories LLM ('tool', 'output') dans la fonction de rendu du formulaire ont été corrigés pour correspondre à ceux attendus par le gestionnaire d'événements, réparant ainsi le bouton de sauvegarde. **4. Orchestration (`docker-compose.yml`) :** La directive `extra_hosts` a été ajoutée aux services `worker` et `celery-beat` pour leur permettre de résoudre `host.docker.internal` et de se connecter au serveur Ollama, résolvant ainsi l'erreur de connexion finale.
    *   **Statut :** RÉSOLU.

### 7.4. Points d'Amélioration Potentiels (Code/Architecture)

*   **Standardiser les Sorties d'Outils avec `outputSchema` :** Pour résoudre le bug d'exécution des workflows et améliorer radicalement l'UX de l'éditeur, il est nécessaire d'étendre la définition des outils MCP pour inclure un `outputSchema`. Cela permettra à l'application de connaître de manière déterministe la structure des données retournées par un outil, fiabilisant la liaison des données et permettant une interface utilisateur intuitive.

*   **Backend Implementation for Categorized LLM Configuration (`app/database/sql_models.py`, `app/schemas/*`, `app/api/*`)**
    *   **Description :** Le frontend a été mis à jour pour permettre la configuration de modèles LLM par catégorie (Décisionnel, Outils, Output). Le backend doit maintenant être adapté pour supporter cette nouvelle structure (migration de base de données, mise à jour des schémas Pydantic et des endpoints, refactorisation de l'orchestrateur).
    *   **Impact :** La nouvelle configuration LLM n'est pas pleinement fonctionnelle tant que le backend n'est pas mis à jour.

*   **Améliorer la Gestion de l'Identité Utilisateur via un Système de Profils**
    *   **Problématique :** L'implémentation actuelle envoie le `display_name` de l'utilisateur dans le prompt du LLM. C'est optimal pour la compréhension du modèle en langage naturel, mais cette donnée est volatile. Si un utilisateur change de pseudo, le bot perd le lien avec l'historique de ses connaissances sur cette personne, ce qui fragilise sa mémoire à long terme.
    *   **Solution Proposée :**
        *   Ancrer l'identité de chaque utilisateur à son **ID Discord**, qui est unique et immuable.
        *   Créer une nouvelle table en base de données (ex: `user_profiles`) avec l'ID Discord comme clé primaire.
        *   Cette table stockera des informations enrichies : le pseudo actuel (`current_display_name`), une liste des anciens pseudos connus (`known_aliases`), et une liste de surnoms (`nicknames`).
        *   Mettre en place une logique qui, à chaque interaction, compare le pseudo actuel de l'utilisateur avec celui stocké. En cas de différence, le système met à jour le pseudo actuel et archive l'ancien dans la liste des alias.
    *   **Impact et Bénéfices :**
        *   **Fiabilité de la Mémoire :** Le bot reconnaîtra les utilisateurs de manière permanente, même s'ils changent de pseudo.
        *   **Contexte Enrichi :** Ouvre la possibilité d'interactions plus personnelles et contextuelles (ex: "Je vois que tu as changé de nom, je te connaissais en tant que 'AncienPseudo'").
        *   **Fondation Solide :** Crée la base nécessaire pour implémenter de futures fonctionnalités liées aux préférences et au profil de chaque utilisateur.

---

### 7.5. Plan d'Action pour la Prochaine Session

*   **Tâche Prioritaire : Résoudre le timeout de la commande `/prompt_generator`.**
    *   **Description :** Maintenant que la gestion des permissions par salon est implémentée et stable, la prochaine priorité est de reprendre l'investigation du bug de timeout intermittent sur les commandes slash. Cette tâche était la priorité initiale avant la demande de gestion des permissions. L'investigation se poursuivra en se basant sur le plan d'action défini (instrumentation et logging de performance).

---

## 8. ANNEXE : Anciennes Architectures d'Agent (Obsolètes)

> **ATTENTION :** Cette section décrit les anciennes architectures qui ne sont plus en production. Elle est conservée à titre de référence historique uniquement.

### 8.1. Architecture "Chaîne de Montage" Asynchrone (Session 96-121)

Cette architecture utilisait une chaîne de 4 LLM (Gardien, Répartiteur, Synthétiseur, Archiviste) principalement orchestrée par le client `bot_process.py`. Le client gérait la décision d'utiliser des outils, leur exécution (interne ou via proxy), et l'envoi des résultats au Synthétiseur. Elle a été remplacée car la logique de décision était trop monolithique (un seul "Répartiteur") et la gestion de la boucle d'outils par le client était trop complexe.

### 8.2. Architecture Monolithique (Pré-Session 96)

Cette architecture initiale reposait sur un unique appel LLM avec une liste d'outils au format `ollama-python`. Le client `bot_process.py` était responsable de la gestion complète de la boucle "appel LLM -> détection d'appel d'outil -> exécution de l'outil -> second appel LLM avec le résultat". Elle a été abandonnée en raison de sa faible fiabilité pour les tâches complexes et du manque de contrôle sur le raisonnement du LLM.