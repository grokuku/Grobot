# CONTEXTE MAÎTRE DU PROJET "GroBot"
#### Date de dernière mise à jour : 2025-09-22
#### Ce fichier sert de référence unique et doit être fourni en intégralité au début de chaque session.

---
### AXIOMES FONDAMENTAUX DE LA SESSION ###
---

**AXIOME COMPORTEMENTAL : Tu es un expert en développement logiciel, méticuleux et proactif.**
*   Tu anticipes les erreurs et suggères des points d'observation après chaque modification.
*   Tu respectes le principe de moindre intervention : tu ne modifies que ce qui est nécessaire et tu ne fais aucune optimisation non demandée.
*   Tu agis comme un partenaire de développement, pas seulement comme un exécutant.

**AXIOME DE DIAGNOSTIC ET DE SÉCURITÉ : Vérifier avant d'agir.**
*   Avant TOUTE modification de fichier, si tu ne disposes de son contenu intégral et à jour dans notre session actuelle, tu dois impérativement me le demander.
*   Tu ne proposeras jamais de code de modification (`sed` ou autre) sans avoir analysé le contenu du fichier concerné au préalable.
*   Tu fondes tes diagnostics sur des **faits vérifiés**. Avant de conclure à un problème de version ou de compatibilité, tu utilises des commandes d'introspection (`pip freeze`, `python --version`, `curl`) pour confirmer l'état réel de l'environnement d'exécution.
*   Tu consultes activement la **documentation officielle** des bibliothèques et des technologies concernées pour valider le comportement attendu (ex: arguments de fonction, prérequis de version), en évitant les suppositions.

**AXIOME DE RESTITUTION DU CODE : La clarté et la fiabilité priment.**
1.  **Modification par `sed` :**
    *   Tu fournis les modifications via une commande `sed` pour Git Bash, sur **une seule ligne**, avec l'argument encapsulé dans des guillemets simples (`'`).
    *   **CONDITION STRICTE :** Uniquement si la commande est basique et sans risque d'erreur. Dans ce cas, tu ne montres pas le code, seulement la commande.
    *   Tu n'utiliseras **jamais** un autre outil (`patch`, `awk`, `tee`, etc.).
2.  **Modification par Fichier Complet :**
    *   Si une commande `sed` en une seule ligne est impossible ou risquée, tu abandonnes `sed`.
    *   À la place, tu fournis le **contenu intégral et mis à jour** du fichier.
3.  **Formatage des Fichiers et Blocs de Code :**
    *   **Fichiers Markdown (`.md`) :** L'intégralité du contenu du fichier que tu fournis sera indenté de quatre espaces.
    *   **Autres Fichiers (Code, Config) :** Tu utiliseras un bloc de code standard (```) formaté comme suit :
        *   Les balises d'ouverture et de fermeture (```) ne sont **jamais** indentées.
        *   Le code contenu à l'intérieur **doit systématiquement** être indenté de quatre espaces.

**AXIOME DE WORKFLOW : Un pas après l'autre.**
1.  **Validation Explicite :** Après chaque proposition de modification (commande `sed` ou fichier complet), tu t'arrêtes et attends mon accord explicite avant de continuer sur une autre tâche ou un autre fichier.
2.  **Mise à Jour de la Documentation :** À la fin du développement d'une fonctionnalité majeure et après ma validation, tu proposeras de manière proactive la mise à jour des fichiers `project_context.md` et `features.md`.

**AXIOME LINGUISTIQUE : Bilinguisme strict.**
*   **Nos Interactions :** Toutes tes réponses et nos discussions se feront en **français**.
*   **Le Produit Final :** Absolument tout le code, les commentaires, les docstrings, les variables et les textes destinés à l'utilisateur (logs, UI, API) doivent être rédigés exclusively en **anglais**.

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
8.  **Architecture de Prompt Hybride :** Le prompt système final envoyé au LLM est assemblé dynamiquement par la logique métier (`agent_logic.py`). Il combine des **directives fondamentales non-modifiables** (codées en dur pour tous les bots) avec le **contexte d'exécution dynamique** (serveur/salon Discord, fichiers joints, mémoire LTM) et la **personnalité spécifique au bot** (stockée en base de données).
9.  **Agentique et Exécution des Outils Côté Client :** La boucle de l'agent (LLM -> appel d'outil -> LLM) est gérée par le client, c'est-à-dire `bot_process.py`, et non par le backend. Cette approche garantit la **sécurité maximale** (le token Discord ne quitte jamais son processus) et permet l'implémentation d'**outils internes** qui interagissent directement avec l'objet client `discord.py`. Les outils externes (MCP) sont appelés via un **endpoint API proxy dédié (`/api/tools/call`)** qui centralise la logique de communication.
10. **Mémoire Utilisateur à Deux Composants :** La connaissance persistante du bot sur les utilisateurs est divisée en deux types de données distincts : les **Profils Utilisateurs** (contenant des directives comportementales modifiables par un administrateur) et les **Notes Utilisateurs** (contenant des faits textuels avec un score de fiabilité, que le bot peut créer et lire lui-même via ses outils).
11. **Architecture d'Agent Spécialisé ("Chaîne de Montage") :** Pour fiabiliser l'utilisation des outils, le traitement d'un message est décomposé en une chaîne d'appels LLM spécialisés. Le **Gardien (Gatekeeper)**, un premier appel LLM, filtre les messages pour décider si le bot doit répondre. Le **Répartiteur (Dispatcher)**, un deuxième appel LLM, a pour unique rôle de décider si un outil est nécessaire. Le **Synthétiseur (Synthesizer)**, un troisième appel LLM, formule la réponse conversationnelle finale. L'orchestration de cette chaîne est gérée par `bot_process.py`.

---

## 3. Architecture et Technologies

### 3.1. Technologies Principales
*   **Orchestration :** Docker, Docker Compose
*   **Backend API :** FastAPI
*   **Frontend :** JavaScript/HTML/CSS (approche SPA avec Modules ES)
*   **Serveur Applicatif :** Nginx (agissant comme serveur web statique et reverse proxy) et Uvicorn (pour l'API FastAPI).
*   **Gestion des processus Bots :** Python 3.11+, `subprocess`
*   **Base de Données Relationnelle (Gestion) :** PostgreSQL (via SQLAlchemy)
*   **Migration de Base de Données :** Alembic (pour les mises à jour de schéma non-destructives)
*   **Base de Données Vectorielle (Mémoire LTM Isolée) :** ChromaDB
*   **Interaction LLM :** `requests`, `httpx`, `ollama-python`
*   **Client Discord :** `discord.py`
*   **Tâches Asynchrones :** Celery, Redis

### 3.2. Arborescence Complète du Projet et Rôle des Fichiers (Post-Refactorisation DB)

```    📁 GroBot/
  ├─ 📄 docker-compose.yml          # Définit et orchestre tous les services de l'application.
  ├─ 📄 Dockerfile                    # Recette multi-stage pour l'image app (API+Frontend).
  ├─ 📄 requirements.txt              # Dépendances Python pour le service 'app'.
  ├─ 📄 project_context.md            # Ce fichier.
  ├─ 📄 features.md                   # Suivi de haut niveau des fonctionnalités implémentées et planifiées.
  │
  ├─ 📁 app/                           # Cœur du Backend : API et logique métier.
  │  ├─ 📄 __init__.py                 # Marque le dossier comme un package Python.
  │  ├─ 📄 alembic.ini                 # Fichier de configuration pour Alembic.
  │  ├─ 📁 alembic/                    # Dossier contenant les scripts de migration générés.
  │  │  └─ 📁 versions/
  │  ├─ 📄 main.py                     # Point d'entrée de l'API FastAPI, gère le cycle de vie, les middlewares et les routeurs.
  │  ├─ 📄 config.py                   # Charge les variables d'environnement via Pydantic.
  │  ├─ 📁 api/                        # Contient les routeurs FastAPI (endpoints) pour chaque ressource.
  │  │  ├─ 📄 __init__.py               # Marque le dossier comme un package Python.
  │  │  ├─ 📄 bots_api.py               # API pour la gestion des bots (CRUD).
  │  │  ├─ 📄 chat_api.py               # API pour la gestion des conversations (gatekeeper, dispatch, synthesize, archive).
  │  │  ├─ 📄 files_api.py              # API pour la gestion des fichiers (upload, recherche, etc.).
  │  │  ├─ 📄 llm_api.py                # API pour l'interaction avec le LLM.
  │  │  ├─ 📄 mcp_api.py              # API pour la gestion des serveurs MCP.
  │  │  ├─ 📄 settings_api.py           # API pour les paramètres globaux.
  │  │  ├─ 📄 tools_api.py              # API pour l'exécution des outils externes (MCP).
  │  │  └─ 📄 user_profiles_api.py      # API pour la gestion des profils et des notes sur les utilisateurs.
  │  ├─ 📁 core/                       # Logique métier principale de l'application.
  │  │  ├─ 📄 __init__.py               # Marque le dossier comme un package Python.
  │  │  ├─ 📁 llm/
  │  │  │  ├─ 📄 __init__.py           # Marque le dossier comme un package Python.
  │  │  │  └─ 📄 ollama_client.py      # Client centralisé pour communiquer avec l'API Ollama.
  │  │  └─ 📄 agent_logic.py          # Contient la logique des appels LLM spécialisés : Gardien, Répartiteur, Synthétiseur et Archiviste.
  │  ├─ 📁 database/                   # Module pour l'accès aux BDD.
  │  │  ├─ 📄 __init__.py               # Marque le dossier comme un package Python.
  │  │  ├─ 📄 base.py                 # Déclaration de la base pour les modèles SQLAlchemy.
  │  │  ├─ 📄 chroma_manager.py       # Gestionnaire de connexion pour ChromaDB.
  │  │  ├─ 📄 crud_bots.py            # Opérations CRUD pour les bots.
  │  │  ├─ 📄 crud_files.py           # Opérations CRUD pour les fichiers.
  │  │  ├─ 📄 crud_mcp.py             # Opérations CRUD pour les serveurs MCP.
  │  │  ├─ 📄 crud_settings.py        # Opérations CRUD pour les paramètres.
  │  │  ├─ 📄 crud_user_notes.py      # Opérations CRUD pour les notes sur les utilisateurs.
  │  │  ├─ 📄 crud_user_profiles.py   # Opérations CRUD pour les profils utilisateurs.
  │  │  ├─ 📄 sql_models.py           # Définition des modèles de table SQLAlchemy.
  │  │  └─ 📄 sql_session.py          # Gestion de la session de base de données.
  │  ├─ 📁 schemas/                    # Contient les schémas Pydantic pour la validation des données API.
  │  │  ├─ 📄 __init__.py               # Marque le dossier comme un package Python.
  │  │  ├─ 📄 bot_schemas.py          # Schémas Pydantic pour les bots.
  │  │  ├─ 📄 chat_schemas.py         # Schémas Pydantic pour le chat et l'archiviste.
  │  │  ├─ 📄 file_schemas.py         # Schémas Pydantic pour les fichiers.
  │  │  ├─ 📄 mcp_schemas.py          # Schémas Pydantic pour les serveurs MCP.
  │  │  ├─ 📄 settings_schema.py      # Schémas Pydantic pour les paramètres.
  │  │  ├─ 📄 user_note_schemas.py    # Schémas Pydantic pour les notes utilisateurs.
  │  │  └─ 📄 user_profile_schemas.py # Schémas Pydantic pour les profils utilisateurs.
  │  └─ 📁 worker/                     # Contient la configuration pour les tâches de fond (Celery).
  │     ├─ 📄 __init__.py               # Marque le dossier comme un package Python.
  │     ├─ 📄 celery_app.py           # Initialisation de l'application Celery.
  │     └─ 📄 tasks.py                # Définit les tâches Celery asynchrones (ex: Archiviste).
  │
  ├─ 📁 chromadb_overriden/
  │  └─ 📄 Dockerfile                  # Personnalise l'image ChromaDB (ex: ajout de 'curl' pour le healthcheck).
  │
  ├─ 📁 data/                         # (Non utilisé activement, placeholder pour des données futures).
  │
  ├─ 📁 discord_bot_launcher/         # Service isolé qui gère les processus des bots Discord.
  │  ├─ 📄 Dockerfile                  # Image Docker pour le service launcher.
  │  ├─ 📄 launcher.py                 # Script principal qui surveille l'API et lance/arrête les bots.
  │  ├─ 📄 bot_process.py              # Orchestre la chaîne d'appels d'agent (Gardien -> Répartiteur -> Synthétiseur -> Archiviste).
  │  └─ 📄 requirements.txt            # Dépendances Python pour le service launcher.
  │
  ├─ 📁 frontend/                     # Contient tout ce qui est relatif à l'application combinée.
  │  ├─ 📄 entrypoint.sh               # Script de démarrage pour Uvicorn, Alembic et Nginx.
  │  ├─ 📄 nginx.conf                  # Configuration Nginx pour le reverse proxy.
  │  └─ 📁 src/                         # Fichiers sources du frontend.
  │     ├─ 📄 index.html                # Point d'entrée HTML de la SPA.
  │     ├─ 📄 api.js                    # Couche de communication : centralise tous les appels à l'API backend.
  │     ├─ 📄 ui.js                     # Couche de rendu : gère la manipulation du DOM, l'affichage des vues, formulaires et modales.
  │     ├─ 📄 events.js                 # Couche de logique applicative : contient les gestionnaires d'événements (clics, etc.).
  │     ├─ 📄 main.js                   # Point d'entrée : initialise l'app, gère l'état global et orchestre les modules.
  │     └─ 📄 style.css                 # Feuille de style principale.
  │
  └─ 📁 grobot_tools/                 # Service MCP contenant les outils standards.
     ├─ 📄 Dockerfile                  # Image Docker pour le service d'outils.
     ├─ 📄 requirements.txt            # Dépendances Python pour les outils.
     ├─ 📄 supervisord.conf            # Fichier de configuration pour lancer plusieurs serveurs d'outils.
     ├─ 📁 file_tools/                 # Outils liés aux fichiers.
     │  └─ 📄 server.py                 # Serveur MCP pour les outils de fichiers.
     └─ 📁 time_tool/                  # Outils liés au temps.
        └─ 📄 server.py                 # Serveur MCP pour l'outil 'get_current_time'.
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
            *   **Settings :** Le formulaire de configuration du bot.
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
3.  **Définition via JSON Schema :** La "signature" d'un outil (son nom, sa description, ses paramètres et leurs types) est décrite de manière structurée via une **JSON Schema**. C'est ce qui permet une découverte véritablement automatique et fiable.

### 6.2. Méthodes RPC Standard

#### 6.2.1. `tools/list`

*   **Rôle :** Permet à un client de découvrir les outils disponibles sur un serveur.
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

*   **Rôle :** Permet à un client d'exécuter un outil spécifique avec des arguments.
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

## 7. Documentation : Flux de Traitement d'un Message (Architecture Asynchrone "Chaîne de Montage")

> **ATTENTION :** Cette section décrit la nouvelle architecture de traitement des messages, implémentée lors de la session 96. **Cette fonctionnalité n'a pas encore été testée en conditions réelles.** Les détails techniques sont fournis pour faciliter le débogage.

Cette section décrit le flux de traitement complet d'un message utilisateur. L'objectif est de rendre le bot non-bloquant lors de l'utilisation d'outils lents et de fournir un retour d'information clair à l'utilisateur.

### 7.1. Étape 1: Déclenchement et Réaction Initiale (Client, `bot_process.py`)
*   Le client (`bot_process.py`, dans `on_message`) reçoit un message via Discord.
*   Il effectue un filtrage initial (auto-réponse, etc.). Si le message est pertinent, il **ajoute immédiatement la réaction `🤔`** au message de l'utilisateur pour indiquer qu'il est en cours d'analyse.
*   Si l'écoute passive est activée, le **Gardien (Gatekeeper)** est appelé pour décider si le bot doit répondre.

### 7.2. Étape 2: Décision par le Répartiteur (Backend, `agent_logic.py`)
*   Le client **remplace la réaction `🤔` par `💬`** pour indiquer que la décision est déléguée à l'IA.
*   Il envoie une requête `POST /api/chat/dispatch` au backend.
*   Le backend utilise le **Répartiteur (Dispatcher)**, pour décider si un ou plusieurs outils sont nécessaires.
*   Il retourne une réponse JSON contenant soit une liste d'appels d'outils (`tool_calls`), soit `null`.

### 7.3. Étape 3: Analyse de la Décision et Tri (Client, `bot_process.py`)
*   Le client reçoit la décision du Répartiteur.
*   **Si aucun outil n'est nécessaire** (`tool_calls` est `null`), le flux passe directement à l'étape 6 (Synthèse directe).
*   **Si des outils sont nécessaires :**
    *   Le client analyse la configuration de chaque outil demandé (via `_get_tool_config`) pour déterminer s'il est considéré comme "lent" (`is_slow: true`).
    *   Il sélectionne une réaction emoji appropriée pour l'outil (via `_get_reaction_for_tools`).
    *   Il **remplace la réaction `💬` par l'emoji de l'outil** (ex: `✏️` pour la génération d'image).

### 7.4. Étape 4: Branchement Asynchrone pour Outils Lents (Client, `bot_process.py`)
*   **Cette étape n'est exécutée que si au moins un des outils est marqué comme "lent".**
*   Le client envoie une requête `POST /api/chat/acknowledge` au backend.
*   Le backend utilise un cinquième LLM spécialisé, **l'Acknowledge-Synthesizer**, pour formuler un court message d'attente.
*   Le client envoie ce message d'attente sur Discord, en utilisant la fonction `send_response` qui **répond au message original uniquement si de nouveaux messages sont apparus entre-temps**.
*   Le client lance l'exécution des outils et la synthèse finale dans une **tâche de fond non-bloquante** via `asyncio.create_task(execute_tools_and_synthesize(...))`.
*   La fonction `on_message` se termine immédiatement, **rendant le bot disponible pour traiter d'autres requêtes**.

### 7.5. Étape 5: Exécution Synchrone pour Outils Rapides (Client, `bot_process.py`)
*   **Cette étape est exécutée si des outils sont nécessaires, mais aucun n'est "lent".**
*   Le client appelle et `await` directement la fonction `execute_tools_and_synthesize(...)`. Le bot reste bloqué sur le traitement de ce message jusqu'à sa complétion.

### 7.6. Étape 6: Exécution, Synthèse et Réponse Finale (Client, `execute_tools_and_synthesize`)
*   Cette fonction est le "moteur" de la génération de réponse. Elle est soit exécutée en tâche de fond (outils lents), soit de manière bloquante (outils rapides / pas d'outil).
*   Elle exécute les outils (internes ou externes via le proxy) et ajoute leurs résultats à l'historique de conversation.
*   Elle envoie la requête finale `POST /api/chat/` au backend.
*   Le backend utilise le **Synthétiseur (Synthesizer)** pour formuler la réponse conversationnelle finale, qui est streamée vers le client.
*   Le client gère l'affichage progressif de la réponse via `MessageStreamManager`, qui est capable d'agréger des pièces jointes (comme des images) avec le premier morceau de texte pour garantir une réponse unifiée, et qui utilise `send_response` pour l'envoi et les modifications.

### 7.7. Étape 7: Nettoyage et Archivage (Asynchrone)
*   À la toute fin du traitement (que ce soit en tâche de fond ou non), le bloc `finally` de `on_message` **supprime la réaction** du message original de l'utilisateur.
*   Après avoir envoyé la réponse, le client lance une tâche "fire-and-forget" `POST /api/chat/archive` où l'**Archiviste (Archivist)** décide si une information doit être sauvegardée.

---

## 8. ANNEXE : Ancienne Architecture d'Agent (Obsolète)

> **ATTENTION :** Cette section décrit l'ancienne architecture d'agent monolithique qui n'est plus en production. Elle est conservée à titre de référence historique uniquement pour comprendre l'évolution du projet. La source de vérité actuelle est la **Section 7**.

### Intégration des Outils avec Ollama (via `ollama-python`)

Cette section servait de référence technique pour la manière dont **`bot_process.py` (agissant comme client de l'agent)** devait interagir avec l'API Ollama pour activer l'utilisation des outils. La boucle de gestion des appels d'outils résidait dans ce processus client.

#### Définir l’outil (Format Cible)

Le format des outils découvert via MCP doit être transformé dans le format suivant avant d'être passé à la bibliothèque `ollama`.

```python
# Exemple de format attendu par ollama.chat()
tools = [
  {
    "type": "function",
    "function": {
      "name": "echo_tool",
      "description": "Renvoie simplement le texte reçu",
      "parameters": {
        "type": "object",
        "properties": {
          "message": {
            "type": "string",
            "description": "Texte à renvoyer"
          }
        },
        "required": ["message"]
      }
    }
  }
]
```

#### Appeler le modèle avec l’outil

L'appel initial au modèle doit inclure la liste des outils transformés dans le paramètre `tools`.

```python
import ollama

response = ollama.chat(
    model="mon-llm-personnalise:1b",
    messages=[{"role": "user", "content": "Utilise echo_tool avec message='Bonjour, IA'"}],
    tools=tools
)
```

#### Gérer l’appel de l’outil par le Modèle

Quand le modèle décide d’appeler un outil, il renvoie une réponse avec une clé `tool_calls`. Le client (`bot_process.py`) doit alors exécuter l'outil (soit en interne, soit via l'API proxy MCP) et renvoyer le résultat dans un second appel au modèle.

```python
# Pseudo-code de la boucle de gestion

if response["message"].get("tool_calls"):
    # Le modèle veut utiliser un outil
    call = response["message"]["tool_calls"]
    tool_name = call["function"]["name"]
    tool_args = call["function"]["arguments"]

    # 1. Appeler le vrai outil (interne ou externe)
    tool_result_content = dispatch_tool_call(tool_name, tool_args) # Ceci est une fonction à implémenter

    # 2. Préparer le second appel au LLM
    # On reprend l'historique et on ajoute la demande d'appel d'outil...
    messages = [
        {"role": "user", "content": "Utilise echo_tool avec message='Bonjour, IA'"},
        response["message"],
        # ... et le résultat de l'outil.
        {"role": "tool", "content": tool_result_content, "tool_call_id": call.get("id")}
    ]

    # 3. Renvoyer le tout au LLM pour qu'il formule la réponse finale
    final_response = ollama.chat(
        model="mon-llm-personnalise:1b",
        messages=messages
    )
    print(final_response["message"]["content"])
else:
    # Le modèle n'a pas utilisé d'outil, on affiche directement sa réponse
    print(response["message"]["content"])
```

---

## 9. SESSIONS DE DÉVELOPPEMENT (Historique)

*Les sessions antérieures à la 113 sont omises pour la brièveté.*

### 113. Correction de l'Expérience Utilisateur et de Régression Critique du Backend (Session du 2025-09-20)
*   **Résumé :** La session a débuté par la correction d'un bug prioritaire de l'interface utilisateur. La modale de configuration des outils ne permettait pas le défilement et, plus important, son bouton "Sauvegarder" ne déclenchait pas de sauvegarde réelle, créant un flux de travail contre-intuitif. Après une série de corrections qui a mené à une régression critique du backend (une `SyntaxError` dans `bots_api.py` due à une commande `sed` défectueuse), le problème a été résolu de manière méthodique.
    1.  **Correction de l'Interface :** Le CSS a été corrigé pour permettre le défilement. La logique dans `ui.js` a été revue pour que le bouton de sauvegarde de la modale déclenche un appel API direct et immédiat, rendant le comportement prévisible et intuitif pour l'utilisateur.
    2.  **Correction de la Régression :** Le fichier `bots_api.py`, qui avait été corrompu et empêchait le serveur de démarrer, a été restauré avec une version complète et correcte, remettant l'application en ligne.
*   **Résultat :** **SUCCÈS.** L'application est de nouveau stable. Le bug de l'interface de configuration des outils est entièrement résolu, améliorant significativement l'expérience utilisateur pour l'administration des bots.

### 114. Débogage et Amélioration de l'Interface de Configuration des Outils (Session du 2025-09-22)
*   **Résumé :** Cette session a été consacrée à la résolution d'un bug de l'interface utilisateur révélé par l'ajout de plusieurs outils sur un même serveur MCP.
    1.  **Diagnostic de la Découverte d'Outils :** Il a été confirmé que le backend de `GroBot` ne découvrait pas tous les outils de `MCP_GenImage`. Un test `curl` a permis de diagnostiquer que le problème venait d'une mauvaise configuration dans la base de données de `MCP_GenImage` (les "Render Types" pour l'upscale n'étaient pas marqués comme visibles), qui a été corrigée.
    2.  **Diagnostic du Bug d'Affichage :** Une fois tous les outils découverts, la modale de configuration des outils dans `GroBot` est devenue inutilisable car le contenu débordait sans barre de défilement.
    3.  **Amélioration de l'Expérience Utilisateur :** Sur demande, l'objectif a été élargi pour non seulement corriger le défilement mais aussi pour ajouter une distinction visuelle claire (sous forme de "cartes") entre chaque outil dans la liste.
    4.  **Correction Itérative (CSS/JS) :** Un processus de débogage méthodique a été nécessaire. Après avoir vérifié que le cache n'était pas en cause, l'inspection du DOM a révélé que la structure HTML était correcte mais que la mise en page CSS ne s'appliquait pas comme prévu. Le problème a été isolé à un comportement de `flexbox` sur la balise `<form>`, qui empêchait le conteneur interne de grandir et d'activer son propre défilement.
*   **Résultat :** **SUCCÈS.** Les fichiers `style.css` et `ui.js` ont été corrigés. La modale de configuration des outils est désormais robuste, capable d'afficher un grand nombre d'outils de manière claire, distincte et avec un défilement fonctionnel.

### 115. Intégration de l'Outil d'Upscale via Détection Contextuelle et Commande Slash (Session du 2025-09-22)
*   **Résumé :** L'objectif de la session était d'intégrer pleinement l'outil `upscale_image`. Le travail a suivi un flux logique complet, du client au backend, et a inclus la résolution d'une régression et d'un problème de déploiement.
    1.  **Logique Client (`bot_process.py`) :** Le client a été modifié pour détecter une image pertinente dans le contexte d'un message (pièces jointes du message ou du message de référence) et transmettre son URL au backend.
    2.  **Correction de Régression :** Une première version de cette modification a introduit une régression (`NameError`), qui a été rapidement identifiée et corrigée.
    3.  **Schéma Backend (`chat_schemas.py`) :** Le schéma de la requête a été étendu pour accepter la nouvelle URL d'image contextuelle.
    4.  **Logique Backend (`agent_logic.py`) :** Le prompt du Répartiteur a été enrichi pour qu'il soit informé de la présence d'une image et qu'il sache comment utiliser l'outil `upscale_image` en conséquence.
    5.  **Intégration Discord (`bot_process.py`) :** Une nouvelle commande `/upscale` a été créée, permettant un appel direct de l'outil avec gestion automatique de l'image la plus récente dans le salon si aucune URL n'est fournie.
    6.  **Diagnostic de Déploiement :** La nouvelle commande n'apparaissant pas dans Discord, le problème a été diagnostiqué comme un potentiel cache de build Docker. Une reconstruction forcée de l'image et du conteneur du service `discord-bot-launcher` a résolu le problème et a fait apparaître la commande.
*   **Résultat :** **SUCCÈS.** L'outil `upscale_image` est désormais pleinement intégré et accessible aux utilisateurs de manière intuitive, soit en répondant à une image, soit en utilisant la commande dédiée `/upscale`.

### 116. Fiabilisation et Amélioration Ergonomique de l'Outil d'Upscale (Session du 2025-09-22)
*   **Résumé :** La session a été consacrée à une refonte en profondeur de la fonctionnalité d'upscale pour corriger des bugs de fiabilité et des problèmes majeurs d'expérience utilisateur.
    1.  **Correction de la Condition de Concurrence :** Une première tentative de fiabilisation via un prompt LLM trop strict dans `agent_logic.py` a causé une régression, empêchant le bot de détecter l'outil. Le problème a été résolu de manière robuste en revenant à un prompt simple et en ajoutant une logique de code Python déterministe qui injecte de force l'URL de l'image dans les arguments de l'outil, éliminant ainsi toute ambiguïté.
    2.  **Amélioration Radicale de l'UX :** La commande textuelle `/upscale` a été supprimée au profit d'une commande de menu contextuel (clic droit). Face aux limitations de celle-ci, la fonctionnalité a été améliorée pour ouvrir une **modale (formulaire)**, permettant à l'utilisateur de spécifier toutes les options avancées (`prompt`, `denoise`, `seed`).
    3.  **Correction Itérative :** Le développement de cette modale a révélé et permis de corriger plusieurs bugs :
        *   La détection d'image est désormais robuste, cherchant dans les pièces jointes, puis les intégrations (`embeds`), et enfin via une expression régulière dans le contenu du message.
        *   Pour pallier l'absence d'autocomplétion dans les modales, un **menu déroulant dynamique** a été implémenté pour le paramètre `upscale_type`, qui se peuple en interrogeant l'API des outils.
        *   Un bug qui provoquait un échec après la soumission de la modale a été identifié et corrigé.
*   **Résultat :** **SUCCÈS (Partiel).** L'interface de l'outil d'upscale est désormais fiable, complète et intuitive. Cependant, l'analyse des logs de fin de session a révélé un **nouveau bug critique** : une incohérence de nom de paramètre. `GroBot` envoie `image_url` tandis que le service `MCP_GenImage` attend `input_image_url`, ce qui cause l'échec de l'appel final à l'outil. La correction de ce nommage sera la priorité de la prochaine session.

### 117. Correction du Bug Critique de Nommage et Finalisation de l'Outil d'Upscale (Session du 2025-09-22)
*   **Résumé :** Cette session a eu pour unique objectif de corriger le bug critique identifié à la fin de la session 116, qui empêchait l'outil d'upscale de fonctionner.
    1.  **Correction du Nommage :** Le bug provenait d'une incohérence de nom de paramètre dans `bot_process.py`. La logique de la modale d'upscale envoyait `image_url`, alors que le serveur d'outils `MCP_GenImage` attendait `input_image_url`. Une simple commande `sed` a permis de corriger ce nommage et de rendre la fonctionnalité opérationnelle.
    2.  **Diagnostic du Menu Manquant :** Il a été confirmé que l'absence du menu déroulant pour le type d'upscale n'était pas un bug dans `GroBot`, mais était dû à une absence de la liste `enum` dans le schéma JSON de l'outil côté `MCP_GenImage`.
*   **Résultat :** **SUCCÈS.** La fonctionnalité d'upscale, via le menu contextuel et la modale avancée, est désormais entièrement fiable et opérationnelle. Le dernier bug critique est résolu.

---

## 10. État Actuel et Plan d'Action

### État Actuel (Bugs Connus et Statut)
*   **CORRIGÉ (Bug Critique de l'Outil d'Upscale) :** L'incohérence de nom de paramètre (`image_url` vs `input_image_url`) a été corrigée. La fonctionnalité d'upscale via la modale est désormais pleinement opérationnelle. (Session 117)
*   **IMPLÉMENTÉ (Intégration Ergonomique de l'Upscale) :** L'outil `upscale_image` est accessible de manière fiable et intuitive via un menu contextuel ouvrant une modale avec des options avancées (y compris un menu déroulant dynamique). (Session 116)
*   **CORRIGÉ (Interface de Configuration des Outils) :** La modale de configuration des outils est désormais fonctionnelle, avec un défilement correct, une distinction visuelle claire entre les outils, et prête pour l'ajout de nouveaux outils. (Session 114)
*   **CORRIGÉ (Stabilité du Synthétiseur) :** Le Synthétiseur est maintenant fiable sous charge et ne "fuit" plus sa logique interne dans le chat. (Session 112)
*   **CORRIGÉ (URL d'Image Redondante) :** La réponse finale à une génération d'image ne contient plus de lien URL redondant. (Session 112)
*   **CORRIGÉ (Régression ChromaDB) :** L'erreur `TypeError` lors de l'interrogation de la mémoire à long terme (LTM) est résolue. (Session 112)
*   **CORRIGÉ (Communication Inter-Services) :** La communication entre le service `app` et les serveurs d'outils externes (MCP) est entièrement fonctionnelle, y compris via WebSocket. (Session 111)
*   **EN ATTENTE (Incohérence de la Personnalité) :** Le message d'attente (`Acknowledge-Synthesizer`) pour les outils lents est générique ("Got it. Starting..."), en anglais, et ne respecte pas la personnalité/langue du bot. C'est le dernier élément non personnalisé du flux.
*   **FAIBLE (Fiabilité de l'Interface de Test) :** Les outils ne fonctionnent pas lorsqu'ils sont appelés depuis la fenêtre de test du frontend.
*   **FAIBLE (CRUD des Bots) :** La suppression d'un bot depuis l'interface est impossible.

### Nouveau Plan d'Action (Priorités)

1.  **Personnaliser le message d'attente (`Acknowledge-Synthesizer`) :** Modifier la logique pour que ce message soit généré en tenant compte de la personnalité et de la langue du bot, afin d'offrir une expérience utilisateur cohérente.