#### Fichier : project_context.md
# CONTEXTE MAÎTRE DU PROJET "GroBot"
#### Date de dernière mise à jour : 2025-09-14
#### Ce fichier sert de référence unique et doit être fourni en intégralité au début de chaque session.

---
### AXIOMES FONDAMENTAUX DE LA SESSION ###
---

**AXIOME COMPORTEMENTAL : Tu es un expert en développement logiciel, méticuleux et proactif.**
*   Tu anticipes les erreurs et suggères des points d'observation après chaque modification.
*   Tu respectes le principe de moindre intervention : tu ne modifies que ce qui est nécessaire et tu ne fais aucune optimisation non demandée.
*   Tu agis comme un partenaire de développement, pas seulement comme un exécutant.

**AXIOME D'ANALYSE ET DE SÉCURITÉ : Aucune action avele.**
*   Avant TOUTE modification de fichier, si tu ne disposes de son contenu intégral et à jour dans notre session actuelle, tu dois impérativement me le demander.
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
```    ---

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

*Les sessions antérieures à la 101 sont omises pour la brièveté.*

### 101. Tentative de Résolution de la Régression "Knowledge Base" par Refactorisation (Session du 2025-09-12)
*   **Résumé :** Cette session a été entièrement consacrée à la résolution de la régression critique de l'onglet "Knowledge Base". Le débogage a suivi un parcours en profondeur à travers toute la pile applicative.
    1.  **Corrections Frontend :** Les premières tentatives ont corrigé la logique du frontend (`ui.js`, `events.js`) pour s'assurer que le clic sur un utilisateur appelle correctement l'API de recherche avec le bon ID utilisateur. Ces corrections ont fonctionné, mais ont révélé que le backend retournait un résultat vide.
    2.  **Diagnostic de la Base de Données :** L'analyse des logs a confirmé que l'API recevait la bonne requête mais que la base de données ne trouvait aucun enregistrement correspondant. L'analyse du modèle de données (`sql_models.py`) a révélé la cause racine : un défaut de conception majeur où la table des notes (`UserNote`) n'était pas correctement reliée par une clé étrangère à la table des profils (`UserProfile`).
    3.  **Refactorisation Majeure :** Une refactorisation complète de la structure de la base de données a été entreprise. Le modèle `sql_models.py` a été corrigé pour introduire une relation propre. Une migration de données complexe avec Alembic a été créée et appliquée pour mettre à jour le schéma existant et lier les anciennes notes aux profils correspondants, en supprimant les données orphelines.
    4.  **Mise à Jour de la Pile :** Les fichiers de schémas (`user_note_schemas.py`), de logique de base de données (`crud_user_notes.py`) et d'API (`user_profiles_api.py`) ont tous été mis à jour pour utiliser cette nouvelle structure de données, plus simple et plus robuste.
*   **Résultat :** **ÉCHEC.** Malgré la refactorisation complète et structurellement correcte, le bug initial persiste. Le clic sur un utilisateur dans l'interface résulte toujours en une erreur "User not found", car l'API continue de retourner une liste vide.
*   **Nouveau Diagnostic :** La refactorisation, bien que bénéfique pour la santé du projet, n'était pas la solution au bug. Le problème est plus subtil et se situe dans l'interaction de bas niveau avec la base de données. Le fait qu'une requête générale pour lister les utilisateurs fonctionne, mais qu'une requête spécifique pour un ID d'utilisateur (pourtant valide et visible) échoue, pointe vers une contradiction logique que les logs actuels n'expliquent pas.
*   **État Actuel :** La régression de la "Knowledge Base" est **toujours critique et bloquante**. La structure de la base de données est maintenant saine, mais la cause racine du bug reste non identifiée.

### 102. Résolution de la Régression "Knowledge Base" par Diagnostic Approfondi (Session du 2025-09-12)
*   **Résumé :** Cette session a repris le débogage de la régression de la "Knowledge Base" en suivant une approche systématique.
    1.  **Logging SQL et Inspection :** L'activation du logging SQL et l'inspection directe de la base de données via `psql` ont confirmé que les requêtes étaient correctes mais ne retournaient aucun résultat pour les ID spécifiques, bien que les utilisateurs apparaissent dans la liste générale.
    2.  **Découverte de la Cause Racine :** La comparaison entre l'ID de la requête API échouée et les données réelles de la base de données a révélé une corruption de l'ID. La cause a été identifiée comme une limitation de JavaScript (`Number.MAX_SAFE_INTEGER`), qui ne peut pas représenter de manière fiable les ID 64-bit de Discord et les arrondit lors du parsing JSON.
    3.  **Correction Multi-Niveaux :** Une correction complète a été appliquée sur toute la pile applicative pour traiter les ID Discord comme des chaînes de caractères (`String`) et non des nombres (`Integer`). Cela a impliqué :
        *   La modification des schémas Pydantic (`user_profile_schemas.py`, `user_note_schemas.py`) pour passer le type de `int` à `str`.
        *   La modification des modèles SQLAlchemy (`sql_models.py`) pour changer le type de colonne de `BigInteger` à `String`.
        *   La génération et l'application d'une migration Alembic pour mettre à jour le schéma de la base de données PostgreSQL (`BIGINT` -> `VARCHAR`).
        *   La mise à jour de la couche API (`user_profiles_api.py`) et de la couche de données (`crud_user_profiles.py`) pour qu'elles attendent et manipulent les ID comme des `str`.
*   **Résultat :** **SUCCÈS.** Le bug critique a été entièrement résolu. L'onglet "Knowledge Base" est de nouveau pleinement fonctionnel.
*   **État Actuel :** La régression est corrigée et la stabilité de la fonctionnalité est restaurée.

### 103. Résolution de la Confusion des Utilisateurs et Finalisation de la Configuration des Outils (Session du 2025-09-12)
*   **Résumé :** Cette session a abordé deux problèmes distincts.
    1.  **Finalisation de la Configuration des Outils :** La logique de sauvegarde dans la modale de configuration des outils (`frontend/src/ui.js`) a été complétée. Elle collecte désormais correctement les valeurs des paramètres spécifiques à chaque outil (définis dans leur `inputSchema`) et les enregistre dans l'objet `default_arguments` de la configuration du bot.
    2.  **Correction de la Confusion des Utilisateurs :** Un bug critique où le bot confondait les interlocuteurs dans une conversation a été diagnostiqué et résolu. La cause racine était un historique de conversation "anonyme" qui n'attribuait pas chaque message à son auteur, rendant le contexte ambigu pour le LLM. La correction a consisté à modifier `discord_bot_launcher/bot_process.py` pour préfixer systématiquement chaque message de l'historique avec le nom de l'auteur (`[DisplayName]: message`), fournissant ainsi un contexte clair et non ambigu au modèle.
    3.  **Analyse d'un Problème de Fiabilité :** Un décalage horaire ponctuel a été observé. L'analyse a conclu qu'il ne s'agissait pas d'un bug de code mais d'une hallucination mineure et non reproductible du LLM lors de la phase de synthèse de la réponse.
*   **Résultat :** **SUCCÈS.** Les deux fonctionnalités ciblées sont maintenant pleinement opérationnelles et le comportement du bot dans les conversations multi-utilisateurs est devenu fiable.
*   **État Actuel :** La base de code est stable. Les principaux bugs critiques ont été résolus.

### 104. Résolution des Conditions de Concurrence sur l'Ensemble de la Pile Applicative (Session du 2025-09-12)
*   **Résumé :** Suite à un rapport de bug montrant que des requêtes simultanées se mélangeaient ou échouaient, une investigation a révélé deux conditions de concurrence critiques distinctes.
    1.  **Conflit de Contexte dans GroBot :** Le bot mélangeait les conversations car plusieurs exécutions de `on_message` modifiaient la même référence partagée de l'historique de conversation (`chat_histories`). La correction a consisté à isoler le contexte de chaque requête en travaillant sur une copie locale (`local_history`) dans `discord_bot_launcher/bot_process.py`.
    2.  **Conflit de Session dans l'Outil d'Image :** Lors de multiples appels à l'outil de génération d'images (`MCP_GenImage`), seule la dernière requête réussissait. La cause était un `clientId` WebSocket partagé dans le serveur d'outil, où chaque nouvelle connexion écrasait la précédente. La correction a consisté à générer un `clientId` unique pour chaque appel d'outil, garantissant des sessions WebSocket isolées.
*   **Résultat :** **SUCCÈS.** Le système est désormais capable de gérer de multiples requêtes complexes et simultanées de manière robuste et fiable, sans corruption de données ni perte de requêtes.
*   **État Actuel :** La stabilité du bot face à une charge de travail élevée est significativement améliorée.

### 105. Fiabilisation du Proxy d'Outils par Mise en Cache (Session du 2025-09-12)
*   **Résumé :** Un bug subtil a été découvert où une seconde requête concurrente à un outil pouvait échouer. L'analyse a révélé que la cause n'était pas un cache défectueux, mais l'absence de cache : le proxy d'outils (`app/api/tools_api.py`) effectuait une découverte réseau (`tools/list`) coûteuse et fragile à chaque appel d'outil. Sous une charge concurrente, ce processus de découverte échouait silencieusement pour la seconde requête, l'empêchant d'être exécutée.
*   **Correction :** Le fichier `app/api/tools_api.py` a été refactorisé pour inclure un cache en mémoire simple. L'emplacement d'un outil est maintenant découvert via le réseau une seule fois, puis stocké dans le cache. Les appels suivants utilisent l'emplacement mis en cache, ce qui élimine la découverte redondante et rend le proxy à la fois plus rapide et plus fiable.
*   **Résultat :** **SUCCÈS.** Le bug des "appels d'outils perdus" est résolu. La performance et la robustesse du proxy d'outils sont grandement améliorées.

### 106. Tentative de Fiabilisation du Proxy d'Outils et Rollback (Session du 2025-09-12)
*   **Résumé :** Suite à la correction de la Session 105, une régression critique est apparue : le bot ne répondait plus dans les salons publics, bien qu'il fonctionnait encore en messages privés. Après plusieurs diagnostics erronés, il a été déterminé que la refactorisation du proxy d'outils (`app/api/tools_api.py`) avait incorrectement mélangé des appels de base de données synchrones avec des opérations réseau asynchrones. Cela provoquait un blocage silencieux (deadlock) de l'API lorsqu'elle était sollicitée par le Gatekeeper (utilisé uniquement pour les messages de salon).
*   **Résultat :** **ROLLBACK.** Pour restaurer immédiatement la stabilité de l'application, la décision a été prise d'annuler toutes les modifications apportées à `app/api/tools_api.py` et de revenir à la version antérieure fonctionnelle (celle de la fin de la Session 104). Le bug de non-réponse dans les salons est résolu, mais le problème d'inefficacité du proxy d'outils persiste.
*   **État Actuel :** L'application est de nouveau stable. Le bug initial qui a motivé la Session 105 est de nouveau un problème connu et actif.

### 107. Unification des Réponses d'Images et Correction de la Conformité MCP (Session du 2025-09-14)
*   **Résumé :** Cette session a corrigé un problème majeur d'expérience utilisateur où le bot envoyait une image générée dans un message séparé de sa réponse textuelle. Une régression qui transformait l'image en simple lien a également été traitée.
    1.  **Correction Côté Client (`GroBot`) :** La logique de `discord_bot_launcher/bot_process.py` a été refactorisée. Au lieu d'envoyer l'image immédiatement, le bot télécharge désormais les fichiers en mémoire et les passe au `MessageStreamManager`. Ce dernier a été amélioré pour pouvoir attacher tous les fichiers collectés au premier morceau de la réponse streamée, garantissant un message unique et unifié. Une logique de détection d'URL d'image dans les réponses textuelles a été ajoutée pour plus de robustesse.
    2.  **Correction Côté Serveur (`MCP_GenImage`) :** Le serveur d'outils de génération d'images a été mis en conformité avec le standard MCP. Sa réponse `tools/call` retourne maintenant `"content"` sous forme d'une liste `[{"type": "image", ...}]` au lieu d'un objet simple, corrigeant la source de la régression.
*   **Résultat :** **SUCCÈS.** Le bot envoie désormais une réponse unique et cohérente contenant à la fois le texte final et l'image en tant que pièce jointe. Le comportement est fiable et l'expérience utilisateur est grandement améliorée.

---

## 10. État Actuel et Plan d'Action

### État Actuel (Bugs Connus et Statut)
*   **CORRIGÉ (Réponses d'Images Unifiées) :** Le bot envoie désormais les images et le texte dans un message unique et cohérent. (Session 107)
*   **CORRIGÉ (Conditions de Concurrence) :** Les requêtes multiples, y compris les appels à des outils lents comme la génération d'images, sont désormais gérées de manière fiable et simultanée. Les contextes de conversation sont isolés (`bot_process.py`) et les appels d'outils externes ont des sessions uniques (`MCP_GenImage`), empêchant les interférences. (Session 104)
*   **CORRIGÉ (Confusion des Utilisateurs) :** Le bot identifie et répond désormais correctement aux différents utilisateurs dans une conversation. (Session 103)
*   **CORRIGÉ (Sauvegarde de la Configuration des Outils) :** La logique de sauvegarde des arguments par défaut des outils dans `ui.js` est fonctionnelle. (Session 103)
*   **CORRIGÉ (Régression de la Knowledge Base) :** La sélection d'un utilisateur est de nouveau fonctionnelle. (Session 102)
*   **NOUVEAU / FAIBLE (Appels d'Outils Répétés) :** Une seconde requête concurrente à un outil (ex: 'refaire une image') peut échouer silencieusement. La cause est que le proxy d'outils (`app/api/tools_api.py`) effectue une découverte réseau (`tools/list`) fragile et inefficace à chaque appel, qui peut échouer sous une charge concurrente. (Bug identifié en Session 105, ré-ouvert après le rollback de la Session 106).
*   **TRÈS FAIBLE (Fiabilité du LLM) :** Le LLM peut occasionnellement faire des erreurs mineures et non reproductibles. Classé comme un problème inhérent au modèle et non comme un bug du code.
*   **FAIBLE (Fiabilité de l'Interface de Test) :** Les outils ne fonctionnent pas lorsqu'ils sont appelés depuis la fenêtre de test du frontend.
*   **FAIBLE (CRUD des Bots) :** La suppression d'un bot depuis l'interface est impossible.

### Nouveau Plan d'Action (Priorités)

1.  **PRIO 1 (Fiabilisation de l'Interface de Test) :**
    *   Isoler et corriger la cause du non-fonctionnement des outils dans l'interface de test. Cela implique probablement de vérifier comment le contexte (serveur, utilisateur) est simulé lors de l'appel aux API depuis `events.js` ou `ui.js`.

2.  **PRIO 2 (Finalisation du CRUD des Bots) :**
    *   Ajouter un bouton de suppression dans l'interface (probablement dans l'onglet "Settings" d'un bot).
    *   Implémenter la logique dans `events.js` et `api.js` pour appeler l'endpoint `DELETE /api/bots/{bot_id}`.
    *   Assurer une confirmation de l'utilisateur avant la suppression.

3.  **PRIO 3 (Refactorisation du Proxy d'Outils) :**
    *   Ré-aborder la fiabilisation du proxy d'outils (`app/api/tools_api.py`) pour résoudre le bug des appels répétés, en s'assurant cette fois de ne pas introduire de régressions.