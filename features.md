#### ★★★☆☆ Section 1: Core Infrastructure

*   **Objectif :** Mettre en place la structure de base du projet, le déploiement et l'interaction fondamentale.
*   **Statut :** Terminé et stable.

*   **Sous-tâches :**
    *   [x] Initialisation du projet avec Docker et Docker Compose.
    *   [x] Mise en place du serveur FastAPI (Backend) et du reverse proxy Nginx.
    *   [x] Connexion à la base de données PostgreSQL avec SQLAlchemy.
    *   [x] Mise en place de la migration de base de données avec Alembic.
    *   [x] Création du service `discord-bot-launcher` pour gérer les processus des bots.
    *   [x] Création du service de base de données vectorielle ChromaDB.
    *   [x] Implémentation de la communication entre le conteneur `app` et l'hôte.

---

#### ★★★★☆ Section 2: Configuration and Management Interface

*   **Objectif :** Permettre l'administration complète des bots via une interface web.
*   **Statut :** Fonctionnalités principales terminées.

*   **Sous-tâches :**
    *   [x] **API Backend :**
        *   [x] CRUD complet pour les bots (`bots_api.py`).
        *   [x] API pour les paramètres globaux (`settings_api.py`).
        *   [x] API pour la sélection des modèles LLM (`llm_api.py`).
        *   [x] API pour la configuration des serveurs MCP (`mcp_api.py`).
    *   [x] **Interface Frontend et UX :**
        *   [x] Interface à deux colonnes (sidebar + contenu).
        *   [x] Affichage de la liste des bots avec leur statut.
        *   [x] Formulaire de création et configuration de bot (général, LLM, prompts).
        *   [x] Intégration d'un système de "tabs" pour la vue de contenu (Logs, Settings, Files, Memory).
        *   [x] Amélioration de la sélection des modèles LLM et de l'UX des paramètres.
        *   [x] Correction des régressions frontend post-refonte architecturale.
        *   [ ] Interface de configuration individuelle pour les outils MCP.
        *   [ ] Interface de gestion de la Base de Connaissances Utilisateur.
    *   [x] **Gestion des Logs :**
        *   [x] Dashboard de logs en temps réel via WebSocket.

---

#### ★★★★☆ Section 3: Bot Intelligence & Awareness

*   **Objectif :** Doter le bot de mémoire, de conscience de son environnement et d'une capacité d'apprentissage.
*   **Statut :** Fonctionnalités de base implémentées et stables.

*   **Sous-tâches :**
    *   [x] **Mémoire Conversationnelle (LTM) :**
        *   [x] Intégration avec ChromaDB pour la mémoire à long terme.
        *   [x] Interface de consultation et de suppression des souvenirs.
        *   [x] Correction du bug de persistance des données.
    *   [x] **Base de Connaissances Utilisateur (Profils & Notes) :**
        *   [x] Architecture à deux niveaux : Profils (instructions) et Notes (faits).
        *   [x] Implémentation des modèles de données, CRUD, schémas et API.
        *   [x] Outils internes (`get_user_profile`, `save_user_note`) pour le bot.
    *   [x] **Conscience de l'Environnement (Discord) :**
        *   [x] Implémentation des outils d'introspection (`get_user_info`, `get_server_layout`, `list_server_channels`).
    *   [x] **Agentique & Architecture du Prompt :**
        *   [x] Boucle de l'agent (tool-use) déplacée côté client (`bot_process.py`).
        *   [x] Architecture de prompt hybride (directives fondamentales + personnalité).
        *   [x] Adoption du standard MCP pour la découverte et l'appel des outils externes.

---

#### ★★★☆☆ Section 4: File Management Tools

*   **Objectif :** Donner au bot la capacité de gérer des fichiers (stocker, rechercher, analyser, partager).
*   **Statut :** API et outils de base implémentés. Intégration et enrichissement en cours.

*   **Sous-tâches :**
    *   [ ] **API Backend (`files_api.py`) :**
        *   [x] Endpoint d'upload (`/files/upload`).
        *   [x] Endpoint de recherche (`/files/search`).
        *   [ ] Endpoint de suppression (soft delete) (`/files/{uuid}`).
        *   [ ] Endpoint de détails (`/files/{uuid}/details`).
        *   [ ] Endpoint de contenu (`/files/{uuid}/content`).
        *   [ ] Endpoint d'analyse (`/files/{uuid}/analyze`).
    *   [x] **Interface :**
        *   [x] Onglet "Files" dans la vue du bot.
        *   [x] Tableau listant les fichiers.
        *   [x] Modal d'upload de fichiers.
        *   [ ] Intégrer les actions sur les fichiers (détails, suppression, etc.).
    *   [x] **Logique du Bot (Outils) :**
        *   [x] Gestion automatique des pièces jointes Discord.
        *   [ ] Outil `search_files` (recherche de fichiers).
        *   [ ] Outil `analyze_file` (analyse de contenu de fichier texte).
        *   [ ] Outil `send_file` (envoi de fichier sur Discord).
    *   [ ] **Fiabilisation et Amélioration :**
        *   [ ] Améliorer les prompts par défaut des outils pour que le LLM les utilise de manière plus fiable.
        *   [ ] Implémenter les outils LLM restants (`set_file_access_level`, `describe_image`).

---

#### ★★★★★ Section 5: Image Generation Tools

*   **Objectif :** Permettre au bot de générer des images sur demande.
*   **Statut :** Terminé et stable.

*   **Sous-tâches :**
    *   [x] Adoption du standard MCP pour l'intégration d'outils externes.
    *   [x] Implémentation d'un proxy d'outils (`tools_api.py`) pour relayer les appels.
    *   [x] Intégration de l'outil `generate_image` pour le bot via un serveur MCP externe.
    *   [x] Mise en place d'une communication asynchrone par WebSocket pour gérer les tâches longues.
    *   [x] Commande applicative `/image` avec autocomplétion pour les paramètres.
    *   [x] Fiabilisation de la chaîne de communication de bout en bout (proxy, client, serveur MCP).

---

#### ☆☆☆☆☆ Section 6: Security and Authentication

*   **Objectif :** Sécuriser l'accès à l'interface de gestion.
*   **Statut :** Non commencé.

*   **Sous-tâches :**
    *   [ ] Mettre en place un système de login/logout pour l'interface web.
    *   [ ] Gérer les sessions utilisateur de manière sécurisée.