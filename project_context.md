#### project_context.md
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
11. **Architecture d'Agent Spécialisé ("Chaîne de Montage") :** Pour fiabiliser l'utilisation des outils, le traitement d'un message est décomposé en une chaîne d'appels LLM spécialisés. Chaque LLM a un rôle unique et défini (Gardien, Planificateur, Synthétiseur, etc.). L'orchestration de cette chaîne est gérée par le backend.

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

### 3.2. Arborescence Complète du Projet et Rôle des Fichiers (Post-Refactorisation des Agents)

> **NOTE :** *Cette arborescence représente la structure actuelle du projet suite à la refactorisation de l'architecture des agents.*

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
  │  ├─ 📄 main.py                     # Point d'entrée de l'API FastAPI, gère le cycle de vie (lifespan), middlewares et routeurs.
  │  ├─ 📄 config.py                   # Charge les variables d'environnement via Pydantic.
  │  ├─ 📁 api/                        # Contient les routeurs FastAPI (endpoints) pour chaque ressource.
  │  │  ├─ 📄 __init__.py               # Marque le dossier comme un package Python.
  │  │  ├─ 📄 bots_api.py               # API pour la gestion des bots (CRUD).
  │  │  ├─ 📄 chat_api.py               # API pour la gestion des conversations et l'orchestration des agents.
  │  │  ├─ 📄 files_api.py              # API pour la gestion des fichiers (upload, recherche, etc.).
  │  │  ├─ 📄 llm_api.py                # API pour l'interaction avec le LLM (ex: lister les modèles).
  │  │  ├─ 📄 mcp_api.py              # API pour la gestion des serveurs MCP.
  │  │  ├─ 📄 settings_api.py           # API pour les paramètres globaux.
  │  │  ├─ 📄 tools_api.py              # API pour l'exécution des outils externes (MCP).
  │  │  └─ 📄 user_profiles_api.py      # API pour la gestion des profils et des notes sur les utilisateurs.
  │  ├─ 📁 core/                       # Logique métier principale de l'application.
  │  │  ├─ 📄 __init__.py               # Marque le dossier comme un package Python.
  │  │  ├─ 📄 agent_orchestrator.py   # Orchestre la chaîne d'appels aux agents spécialisés.
  │  │  ├─ 📁 agents/                 # Contient la logique pour chaque agent LLM spécialisé.
  │  │  │  ├─ 📄 __init__.py           # Marque le dossier comme un package Python.
  │  │  │  ├─ 📄 acknowledger.py       # Agent pour générer les messages d'attente.
  │  │  │  ├─ 📄 archivist.py          # Agent pour archiver les informations en mémoire.
  │  │  │  ├─ 📄 clarifier.py          # Agent pour demander des informations manquantes.
  │  │  │  ├─ 📄 gatekeeper.py         # Agent pour décider si le bot doit répondre.
  │  │  │  ├─ 📄 parameter_extractor.py# Agent pour extraire les paramètres des outils.
  │  │  │  ├─ 📄 planner.py            # Agent pour créer le plan d'exécution des outils.
  │  │  │  ├─ 📄 prompts.py            # Centralise tous les prompts système des agents.
  │  │  │  ├─ 📄 synthesizer.py        # Agent pour formuler la réponse finale.
  │  │  │  └─ 📄 tool_identifier.py    # Agent pour identifier les outils nécessaires.
  │  │  └─ 📁 llm/
  │  │     ├─ 📄 __init__.py           # Marque le dossier comme un package Python.
  │  │     └─ 📄 ollama_client.py      # Client centralisé pour communiquer avec l'API Ollama, initialisé au démarrage.
  │  ├─ 📁 database/                   # Module pour l'accès aux BDD.
  │  │  ├─ 📄 __init__.py
  │  │  ├─ 📄 base.py
  │  │  ├─ 📄 chroma_manager.py
  │  │  ├─ 📄 crud_bots.py
  │  │  ├─ 📄 crud_files.py
  │  │  ├─ 📄 crud_mcp.py
  │  │  ├─ 📄 crud_settings.py
  │  │  ├─ 📄 crud_user_notes.py
  │  │  ├─ 📄 crud_user_profiles.py
  │  │  ├─ 📄 redis_session.py        # Gère la connexion au client Redis.
  │  │  ├─ 📄 sql_models.py
  │  │  └─ 📄 sql_session.py
  │  ├─ 📁 schemas/                    # Contient les schémas Pydantic pour la validation des données API.
  │  │  └─ ... (contenu inchangé)
  │  └─ 📁 worker/                     # Contient la configuration pour les tâches de fond (Celery).
  │     └─ ... (contenu inchangé)
  │
  ├─ 📁 chromadb_overriden/
  │  └─ 📄 Dockerfile                  # Personnalise l'image ChromaDB (ex: ajout de 'curl' pour le healthcheck).
  │
  ├─ 📁 data/                         # (Non utilisé activement, placeholder pour des données futures).
  │
  ├─ 📁 discord_bot_launcher/         # Service isolé qui gère les processus des bots Discord.
  │  ├─ 📄 Dockerfile                  # Image Docker pour le service launcher.
  │  ├─ 📄 launcher.py                 # Script principal qui surveille l'API et lance/arrête les bots.
  │  ├─ 📄 bot_process.py              # Point d'entrée du client Discord, initialise et attache les handlers.
  │  ├─ 📁 client/                     # Contient la logique modulaire du client Discord.
  │  │  ├─ 📄 __init__.py               # Marque le dossier comme un package Python.
  │  │  ├─ 📄 api_client.py           # Centralise toutes les requêtes vers l'API backend.
  │  │  ├─ 📄 discord_ui.py           # Fonctions utilitaires pour interagir avec l'UI de Discord (réactions, etc.).
  │  │  └─ 📄 event_handler.py        # Contient la logique principale `on_message`.
  │  └─ 📄 requirements.txt            # Dépendances Python pour le service launcher.
  │
  ├─ 📁 frontend/                     # Contient tout ce qui est relatif à l'application combinée.
  │  └─ ... (contenu inchangé)
  │
  └─ 📁 grobot_tools/                 # Service MCP contenant les outils standards.
     └─ ... (contenu inchangé)
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
### 6.3. Format de Définition d'un Ooutil

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

## 7. Documentation : Flux de Traitement d'un Message (Architecture 'Chaîne de Montage d'Agents Spécialisés')

> **Source de Vérité :** Cette section décrit la nouvelle architecture de traitement des messages, conçue pour privilégier la **fiabilité** et la **cohérence de la personnalité** par rapport à la latence. Elle remplace toutes les implémentations précédentes.

L'objectif de cette architecture est de décomposer une requête utilisateur complexe en une série d'étapes simples, chacune gérée par un agent LLM spécialisé. L'ensemble du processus est orchestré par le backend.

### Étape 1 : Triage Initial (Client, `client/event_handler.py`)
*   **Déclencheur :** Un message est reçu sur Discord.
*   **Logique de Code (Pré-filtrage) :**
    1.  **Pièce jointe seule :** Le message ne contient que des fichiers ? -> Ignorer.
    2.  **Mention `@` directe :** Le message commence par `@BotName` ? -> Le message est validé. Passage direct à l'**Étape 3**, en contournant le Gardien pour optimiser la réponse.
    3.  **Autres cas :** Le message est une conversation ambiante. -> Passage à l'**Étape 2**.

### Étape 2 : Gardien (Backend, `agents/gatekeeper.py`)
*   **Rôle :** Déterminer si le bot doit répondre à une conversation ambiante.
*   **Mécanique :** Appel à un LLM spécialisé (le **Gardien**) avec un prompt strict qui lui demande de répondre `oui` uniquement dans 3 cas : mention du nom du bot, continuation d'une conversation, ou question d'intérêt général.
*   **Sortie :** Une décision binaire. Si `non`, le traitement s'arrête. Si `oui`, passage à l'**Étape 3**.

### Étape 3 : Identification des Outils (Backend, `agents/tool_identifier.py`)
*   **Rôle :** Analyser la demande et lister tous les outils potentiellement utiles.
*   **Mécanique :** Appel LLM #1 (**Tool Identifier**) qui reçoit la conversation et la liste des outils disponibles.
*   **Sortie :** Une liste de noms d'outils (`["get_weather", "generate_image"]`). Si la liste est vide, passage direct à l'**Étape 8 (Synthèse)**.

### Étape 4 : Extraction des Paramètres (Backend, `agents/parameter_extractor.py`)
*   **Rôle :** Vérifier si toutes les informations requises pour chaque outil identifié sont présentes.
*   **Mécanique :** Appel LLM #2 (**Parameter Extractor**) qui tente d'extraire les valeurs des paramètres pour chaque outil depuis la conversation.
*   **Sortie :** Un objet JSON listant les paramètres trouvés et ceux qui sont manquants. Si aucun paramètre ne manque, passage à l'**Étape 6 (Planification)**.

### Étape 5 : Demande de Clarification (Backend, `agents/clarifier.py`)
*   **Rôle :** Formuler une question à l'utilisateur pour obtenir les informations manquantes.
*   **Mécanique :** Appel LLM #3 (**Clarifier**) qui reçoit la liste des paramètres manquants et les **instructions de personnalité du bot**.
*   **Sortie :** Une question en langage naturel, respectant la personnalité du bot. Cette question est envoyée à Discord. **Le flux de traitement s'arrête en attendant la réponse de l'utilisateur.**

### Étape 6 : Planification (Backend, `agents/planner.py`)
*   **Rôle :** Créer un plan d'action ordonné maintenant que toutes les informations sont disponibles.
*   **Mécanique :** Appel LLM #4 (**Planner**) qui organise les appels d'outils dans un ordre logique, en identifiant les dépendances (ex: le résultat de l'outil 1 est l'entrée de l'outil 2).
*   **Sortie :** Un plan d'exécution séquentiel au format JSON.

### Étape 7 : Exécution et Acquittement (Backend + Client)
*   **Rôle :** Exécuter le plan et informer l'utilisateur.
*   **Mécanique :**
    1.  **Acquittement :** Si le plan contient des outils lents (ex: génération d'image), le backend fait un appel à un LLM #5 (**Acknowledger**). Cet agent utilise la **personnalité du bot** pour générer un message d'attente (ex: "J'ai compris, je me mets au travail !"). Ce message est envoyé à l'utilisateur.
    2.  **Exécution :** Le backend exécute le plan, en appelant les outils dans l'ordre et en propageant les résultats entre les étapes.

### Étape 8 : Synthèse Finale (Backend, `agents/synthesizer.py`)
*   **Rôle :** Formuler la réponse finale en langage naturel.
*   **Mécanique :** Le LLM final (#6, le **Synthesizer**) reçoit la question originale, les résultats de l'exécution des outils, et les **instructions de personnalité du bot**.
*   **Sortie :** La réponse finale, cohérente et personnalisée, qui est envoyée à l'utilisateur.

---

## 8. ANNEXE : Anciennes Architectures d'Agent (Obsolètes)

> **ATTENTION :** Cette section décrit les anciennes architectures qui ne sont plus en production. Elle est conservée à titre de référence historique uniquement. La source de vérité actuelle est la **Section 7**.

### 8.1. Architecture "Chaîne de Montage" Asynchrone (Session 96-121)

Cette architecture utilisait une chaîne de 4 LLM (Gardien, Répartiteur, Synthétiseur, Archiviste) principalement orchestrée par le client `bot_process.py`. Le client gérait la décision d'utiliser des outils, leur exécution (interne ou via proxy), et l'envoi des résultats au Synthétiseur. Elle a été remplacée car la logique de décision était trop monolithique (un seul "Répartiteur") et la gestion de la boucle d'outils par le client était trop complexe.

### 8.2. Architecture Monolithique (Pré-Session 96)

Cette architecture initiale reposait sur un unique appel LLM avec une liste d'outils au format `ollama-python`. Le client `bot_process.py` était responsable de la gestion complète de la boucle "appel LLM -> détection d'appel d'outil -> exécution de l'outil -> second appel LLM avec le résultat". Elle a été abandonnée en raison de sa faible fiabilité pour les tâches complexes et du manque de contrôle sur le raisonnement du LLM.

---

## 10. État Actuel et Plan d'Action

### État Actuel (Bugs Connus et Statut)
*   **CORRIGÉ (Triage des Messages et Bypass du Gatekeeper) :** La logique de triage côté client (`event_handler.py`) a été renforcée. Le bot répond désormais de manière fiable lorsqu'il est mentionné directement (@BotName) dans un canal ou contacté en message privé (PM), en contournant le `Gatekeeper`. De plus, toutes les mentions d'utilisateurs (`<@ID>`) sont maintenant remplacées par des noms lisibles (`@DisplayName`) avant d'être envoyées au backend, ce qui fiabilise le contexte pour tous les agents LLM.
*   **CORRIGÉ (Comportement Eratique des Agents) :** Les prompts des agents `Parameter Extractor` et `Clarifier` ont été renforcés pour être plus directifs et mieux respecter leur rôle respectif. Le `Gatekeeper` a également été rendu plus strict. (Session 130)
*   **CORRIGÉ (Crash du Worker Celery) :** Le service `worker` ne plante plus au démarrage. L'ancienne importation `agent_logic` dans `app/worker/tasks.py` a été remplacée et la logique de la tâche a été mise à jour pour correspondre à la nouvelle architecture des agents.
*   **CORRIGÉ (Problèmes de Personnalité et d'Identité) :** La chaîne complète (UI > Events > API > Schémas > CRUD > DB) a été auditée et corrigée. La personnalité définie dans l'interface est maintenant correctement sauvegardée en base de données et utilisée par l'agent `Synthesizer` pour générer la réponse finale. Le bot respecte l'identité et le ton qui lui sont assignés.
*   **CORRIGÉ (Fuite de Contexte entre les conversations) :** Le contexte de conversation stocké dans Redis est maintenant systématiquement effacé après l'envoi de la réponse, empêchant les résultats d'outils d'une requête d'apparaître dans la réponse d'une requête ultérieure.
*   **NON RÉSOLU - MINEUR (Frontend) :** L'onglet "Memory" dans l'interface web ne fonctionne pas. La cause est probablement une erreur JavaScript ou un endpoint API défaillant.
*   **NON RÉSOLU - FAIBLE (Fiabilité de l'Interface de Test) :** Les outils ne fonctionnent pas lorsqu'ils sont appelés depuis la fenêtre de test du frontend.
*   **NON RÉSOLU - FAIBLE (CRUD des Bots) :** La suppression d'un bot depuis l'interface est impossible.

### Nouveau Plan d'Action (Priorités pour la prochaine session)

1.  **Implémenter la Génération Personnalisée des Messages d'Attente :**
    *   **Objectif :** Remplacer le message d'attente générique par un message personnalisé par le LLM (`Acknowledger`).
    *   **Action 1 :** Créer le nouvel endpoint API `/api/chat/generate-acknowledgement`.
    *   **Action 2 :** Modifier la logique client (`event_handler.py`) pour appeler ce nouvel endpoint lorsque des outils lents sont détectés.

2.  **Investiguer le bug de l'onglet "Memory".**

3.  **Fiabiliser l'Interface de Test du Frontend.**

4.  **Implémenter la suppression des bots.**

---

## 11. Suivi des Modifications de la Session Actuelle

*   **Date de Début :** 2025-09-28
*   **Objectif Principal :** Corriger les bugs critiques bloquant le bon fonctionnement du bot (Worker Celery, Personnalité).

### Fichiers Modifiés

1.  **`app/worker/tasks.py`**
    *   **Action :** Remplacement de l'importation obsolète `app.core.agent_logic` par `app.core.agents.archivist`. Mise à jour de la logique de la tâche pour gérer la nouvelle signature de la fonction `run_archivist` et prendre en charge l'écriture en base de données.
    *   **Raison :** Correction d'une `ImportError` qui provoquait le crash du service `worker` au démarrage.
    *   **Statut :** Appliqué. **Corrigé.**

2.  **`app/database/crud_user_notes.py`**
    *   **Action :** Ajout de la fonction `create_user_notes_from_archivist`.
    *   **Raison :** Fonction utilitaire requise par la nouvelle logique de la tâche Celery de l'archiviste pour sauvegarder les notes.
    *   **Statut :** Appliqué. **Corrigé.**

3.  **`app/core/agents/synthesizer.py`**
    *   **Action :** Correction des placeholders (`{{variable}}` -> `{variable}`) lors du formatage du prompt.
    *   **Raison :** Les variables de personnalité et de nom du bot n'étaient pas correctement injectées dans le prompt système.
    *   **Statut :** Appliqué.

4.  **`app/core/agents/prompts.py`**
    *   **Action :** Réécriture du `SYNTHESIZER_SYSTEM_PROMPT` pour le rendre neutre et agnostique de la personnalité.
    *   **Raison :** Le prompt contenait des instructions contradictoires ("tu es un assistant") qui entraient en conflit avec la personnalité personnalisée.
    *   **Statut :** Appliqué.

5.  **`app/api/chat_api.py`**
    *   **Action :** Ajout d'un bloc `finally` pour supprimer la clé de contexte de Redis après la fin du streaming d'une réponse.
    *   **Raison :** Correction d'un bug de "fuite de contexte" où les résultats d'outils d'une conversation pouvaient apparaître dans la suivante.
    *   **Statut :** Appliqué. **Corrigé.**

6.  **`frontend/src/ui.js`**
    *   **Action :** Modification de la fonction `renderBotSettingsPersonalityTab` pour qu'elle affiche et édite le champ `personality` au lieu de `system_prompt`.
    *   **Raison :** Correction d'un "mauvais câblage" dans l'interface qui empêchait l'édition du bon champ.
    *   **Statut :** Appliqué.

7.  **`app/schemas/bot_schemas.py`**
    *   **Action :** Ajout du champ `personality` aux schémas Pydantic `BotCreate`, `BotUpdate` et `Bot`.
    *   **Raison :** Nécessaire pour que l'API backend puisse accepter, valider et traiter la donnée `personality` envoyée par le frontend lors de la sauvegarde.
    *   **Statut :** Appliqué.

8.  **`frontend/src/events.js`**
    *   **Action :** Ajout du champ `personality` à l'objet `generalData` dans la fonction `handleSaveBotSettings`.
    *   **Raison :** Correction du bug final où le gestionnaire d'événement "oubliait" d'inclure la personnalité dans la charge utile envoyée à l'API de sauvegarde.
    *   **Statut :** Appliqué. **Corrigé.**