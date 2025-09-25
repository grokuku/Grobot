    #### Méthode 2 - Fichier Complet (Par Défaut)

    #### AXIOMES FONDAMENTAUX DE LA SESSION ####

    #### **AXIOME 1 : COMPORTEMENTAL (L'Esprit de Collaboration)**

    *   **Posture d'Expert** : J'agis en tant qu'expert en développement logiciel, méticuleux et proactif. J'anticipe les erreurs potentielles et je suggère des points de vérification pertinents après chaque modification.
    *   **Principe de Moindre Intervention** : Je ne modifie que ce qui est strictement nécessaire pour répondre à la demande. Je n'introduis aucune modification (ex: refactoring, optimisation) non sollicitée.
    *   **Partenariat Actif** : Je me positionne comme un partenaire de développement qui analyse et propose, et non comme un simple exécutant.

    #### **AXIOME 2 : ANALYSE ET SÉCURITÉ (Aucune Action Avele)**

    *   **Connaissance de l'État Actuel** : Avant TOUTE modification de fichier, si je ne dispose pas de son contenu intégral et à jour dans notre session, je dois impérativement vous le demander.
    *   **Analyse Préalable Obligatoire** : Je ne proposerai jamais de commande de modification de code (ex: `sed`) sans avoir analysé le contenu du fichier concerné au préalable dans la session en cours.
    *   **Vérification Proactive des Dépendances** : Ma base de connaissances s'arrête début 2023. Par conséquent, avant d'intégrer ou d'utiliser un nouvel outil, une nouvelle librairie ou un nouveau package, je dois systématiquement effectuer une recherche pour :
        1.  Déterminer la version stable la plus récente.
        2.  Consulter sa documentation pour identifier tout changement majeur (*breaking change*) ou toute nouvelle pratique d'utilisation par rapport à ma base de connaissances.
    *   **Protection des Données** : Je ne proposerai jamais d'action destructive (ex: `rm`, `DROP TABLE`) sur des données en environnement de développement sans proposer une alternative de contournement (ex: renommage, sauvegarde).

    #### **AXIOME 3 : RESTITUTION DU CODE (Clarté et Fiabilité)**

    *   **Méthode 1 - Modification Atomique par `sed`** :
        *   **Usage** : Uniquement pour une modification simple, sur une seule ligne, et sans aucun risque d'erreur de syntaxe ou de contexte.
        *   **Format** : La commande `sed` doit être fournie sur une seule ligne pour Git Bash, avec l'argument principal encapsulé dans des guillemets simples (`'`). Le nouveau contenu du fichier ne sera pas affiché.
        *   **Exclusivité** : Aucun autre outil en ligne de commande (`awk`, `patch`, `tee`, etc.) ne sera utilisé pour la modification de fichiers.
    *   **Méthode 2 - Fichier Complet (Par Défaut)** :
        *   **Usage** : C'est la méthode par défaut. Elle est obligatoire si une commande `sed` est trop complexe, risquée, ou si les modifications sont substantielles.
        *   **Format** : Je fournis le contenu intégral et mis à jour du fichier.
    *   **Formatage des Blocs de Restitution** :
        *   **Fichiers Markdown (`.md`)** : Le contenu intégral du fichier sera systématiquement indenté de quatre espaces.
        *   **Autres Fichiers (Code, Config, etc.)** : J'utiliserai un bloc de code standard. Les balises d'ouverture et de fermeture (```) ne seront jamais indentées, mais le code à l'intérieur le sera systématiquement de quatre espaces.

    #### **AXIOME 4 : WORKFLOW (Un Pas Après l'Autre)**

    1.  **Validation Explicite** : Après chaque proposition de modification (que ce soit par `sed` ou par fichier complet), je marque une pause. J'attends votre accord explicite ("OK", "Appliqué", "Validé", etc.) avant de passer à un autre fichier ou à une autre tâche.
    2.  **Documentation Continue des Dépendances** : Si la version d'une dépendance s'avère plus récente que ma base de connaissances, je consigne son numéro de version et les notes d'utilisation pertinentes (liens, exemples de code si la syntaxe a changé) dans le fichier `project_context.md`.
    3.  **Documentation de Fin de Fonctionnalité** : À la fin du développement d'une fonctionnalité majeure et après votre validation finale, je proposerai de manière proactive la mise à jour des fichiers de suivi du projet, notamment `project_context.md` et `features.md`.

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

    ### 3.2. Arborescence Complète du Projet et Rôle des Fichiers (Post-Refactorisation DB)

    > **NOTE :** *Cette arborescence représente la structure cible après la refactorisation de l'architecture des agents planifiée.*

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
      │  │  ├─ 📄 chat_api.py               # API pour la gestion des conversations et l'orchestration des agents.
      │  │  ├─ 📄 files_api.py              # API pour la gestion des fichiers (upload, recherche, etc.).
      │  │  ├─ 📄 llm_api.py                # API pour l'interaction avec le LLM.
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
      │  │     └─ 📄 ollama_client.py      # Client centralisé pour communiquer avec l'API Ollama.
      │  ├─ 📁 database/                   # Module pour l'accès aux BDD.
      │  │  └─ ... (contenu inchangé)
      │  ├─ 📁 schemas/                    # Contient les schémas Pydantic pour la validation des données API.
      │  │  └─ ... (contenu inchangé, `chat_schemas.py` sera modifié)
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

    ## 9. SESSIONS DE DÉVELOPPEMENT (Historique)

    *Les sessions antérieures à la 118 sont omises pour la brièveté.*

    ... (L'historique des sessions 118 à 121 reste inchangé) ...

    ---

    ## 10. Plan d'Action : Refactorisation de l'Architecture des Agents

    ### Contexte et Objectif

    L'architecture actuelle, bien que fonctionnelle, repose sur des fichiers monolithiques (`agent_logic.py`, `bot_process.py`) qui deviennent difficiles à maintenir et à faire évoluer. La logique de l'agent est également trop simple, ce qui limite sa fiabilité pour les requêtes complexes.

    L'objectif de cette phase de travail est de mettre en œuvre l'architecture "Chaîne de Montage d'Agents Spécialisés" décrite à la Section 7. Ce refactoring majeur vise à remplacer la logique monolithique par une approche modulaire, plus robuste et plus facile à maintenir, où chaque étape du raisonnement du bot est gérée par un agent spécialisé et indépendant.

    ### Plan de Travail Détaillé

    1.  **Phase 1 : Préparation et Structuration (Backend)**
        *   Créer la nouvelle arborescence de fichiers : `app/core/agent_orchestrator.py` et le répertoire `app/core/agents/` avec ses modules vides (`gatekeeper.py`, `planner.py`, etc.).
        *   Créer le fichier `app/core/agents/prompts.py` pour centraliser les prompts système.
        *   Dans `app/schemas/chat_schemas.py`, définir les nouvelles structures Pydantic nécessaires pour les plans d'exécution, les listes de paramètres, etc.

    2.  **Phase 2 : Implémentation des Agents (Backend)**
        *   Remplir `prompts.py` avec les prompts système en anglais pour chaque agent.
        *   Pour chaque module dans `app/core/agents/`, implémenter la fonction `run_*` correspondante. Chaque fonction sera responsable d'appeler le LLM avec le bon prompt et de retourner une sortie JSON structurée.

    3.  **Phase 3 : Orchestration et Exposition API (Backend)**
        *   Implémenter la logique principale dans `app/core/agent_orchestrator.py` pour enchaîner les appels aux différents agents.
        *   Dans `app/api/chat_api.py`, créer un nouvel endpoint (ex: `POST /api/chat/process_message`) qui utilise l'orchestrateur.
        *   Cet endpoint devra retourner des objets d'action clairs pour le client (ex: `{"action": "CLARIFY", "message": "..."}`).

    4.  **Phase 4 : Refactorisation du Client Discord**
        *   Créer la nouvelle arborescence de fichiers `discord_bot_launcher/client/`.
        *   Déplacer la logique de communication réseau de `bot_process.py` vers `client/api_client.py`.
        *   Déplacer la logique de manipulation de l'UI Discord vers `client/discord_ui.py`.
        *   Déplacer la logique de l'événement `on_message` vers `client/event_handler.py`.
        *   Simplifier `bot_process.py` pour qu'il ne soit plus qu'un point d'entrée.

    5.  **Phase 5 : Connexion et Test de Bout-en-Bout**
        *   Mettre à jour `event_handler.py` pour appeler le nouvel endpoint API via `api_client.py`.
        *   Implémenter la logique pour gérer les différentes actions retournées par l'API (`CLARIFY`, `ACKNOWLEDGE_AND_EXECUTE`, `SYNTHESIZE`).
        *   Mettre en place un mécanisme de gestion de l'état de la conversation pour gérer les clarifications.

    6.  **Phase 6 : Finalisation de la Documentation**
        *   S'assurer que ce fichier `project_context.md` est parfaitement à jour avec l'implémentation finale.