# Plan d'Intégration de l'Agentic Context Engine (ACE)
    
    *   **Date:** 2025-10-24
    *   **Objectif:** Intégrer la librairie `ace-framework` dans le projet GroBot pour doter les bots d'une capacité d'apprentissage et d'amélioration continue.
    *   **Approche:** Une intégration incrémentale en plusieurs phases, traitant `ace-framework` comme une dépendance externe ("boîte noire" experte) sans ré-implémenter sa logique.
    
    ---
    
    ## 1. Analyse Technique des Composants ACE Pertinents
    
    Cette section résume l'analyse du code source de `ace-framework` et identifie les composants clés que nous allons importer et utiliser dans GroBot.
    
    ### 1.1. Le Cycle d'Apprentissage Fondamental
    Le cœur d'ACE est un cycle d'apprentissage orchestré par les classes `OfflineAdapter` ou `OnlineAdapter`. Nous utiliserons la logique de ce cycle au sein d'une tâche de fond (Celery) pour un apprentissage asynchrone. Le workflow est le suivant :
    1.  **Generator**: Produit une réponse à partir d'un contexte.
    2.  **TaskEnvironment**: Évalue cette réponse (nous devrons implémenter cette classe).
    3.  **Reflector**: Analyse le résultat de l'évaluation pour en tirer des leçons.
    4.  **Curator**: Décide des modifications à apporter à la mémoire sur la base de ces leçons.
    5.  **Playbook**: Applique les modifications.
    
    ### 1.2. Composants Clés à Utiliser
    
    *   **`Playbook` et `Bullet` (`ace.playbook`)**:
        *   **Rôle:** C'est la structure de mémoire principale d'ACE, qui remplace notre usage de ChromaDB pour la mémoire stratégique.
        *   Un `Playbook` est une collection de `Bullet`s (stratégies). Chaque `Bullet` a un contenu textuel et des compteurs (`helpful`, `harmful`, `neutral`).
        *   **Utilisation dans GroBot:**
            *   Nous persisterons le `Playbook` de chaque bot dans un fichier JSON dédié (ex: `/data/playbooks/{bot_id}.json`).
            *   La méthode `playbook.as_prompt()` sera cruciale en Phase 2 pour injecter les stratégies apprises dans le contexte de nos agents actuels.
    
    *   **Les Trois Rôles (`ace.roles`)**:
        *   **`Generator`**: Prend un `Playbook` et une question pour générer une réponse. Nous l'utiliserons en Phase 3 pour remplacer notre "chaîne de montage" d'agents.
        *   **`Reflector`**: Analyse une interaction pour identifier les points d'amélioration. Il produit un `key_insight` et des `bullet_tags`. C'est le moteur de l'analyse.
        *   **`Curator`**: Prend l'analyse du `Reflector` et génère des `DeltaOperation`. C'est le moteur de la décision.
    
    *   **`DeltaBatch` et `DeltaOperation` (`ace.delta`)**:
        *   **Rôle:** Mécanisme de mise à jour transactionnel et auditable pour le `Playbook`. Les opérations sont `ADD`, `UPDATE`, `TAG`, `REMOVE`.
        *   **Utilisation dans GroBot:** Le `Curator` produira un `DeltaBatch`, et nous appellerons `playbook.apply_delta(...)` pour l'appliquer.
    
    *   **`TaskEnvironment` (`ace.adaptation`)**:
        *   **Rôle:** C'est le "pont" entre le monde de GroBot et le monde d'ACE. C'est une classe abstraite que *nous devons implémenter*.
        *   **Utilisation dans GroBot:** Nous créerons un `SelfReflectionEnvironment`. Sa méthode `evaluate` n'aura pas de vérité terrain externe. Elle se basera sur l'analyse de la réponse générée par le bot lui-même (cohérence, clarté, etc.) pour permettre au `Reflector` de fonctionner en mode "auto-réflexion".
    
    *   **Clients LLM (`ace.llm_providers`)**:
        *   ACE vient avec son propre `LiteLLMClient`, qui est compatible avec notre usage actuel. Nous instancierons ce client pour les trois rôles, en assurant une configuration cohérente.
    
    ---
    
    ## 2. Stratégie d'Intégration Incrémentale
    
    L'intégration se fera en quatre phases pour minimiser les risques et valider chaque étape.
    
    ### Phase 1 : Intégration Non-Invasive (Mode "Observateur")
    *   **Objectif:** Mettre en place le cycle d'apprentissage en arrière-plan pour commencer à construire des `Playbook`s sans affecter le comportement des bots.
    *   **Étapes Techniques:**
        1.  **Dépendance:** Ajouter `ace-framework` à `requirements.txt`.
        2.  **Stockage:** Ajouter un volume Docker dans `docker-compose.yml` pour persister les playbooks (ex: `./data/playbooks:/app/data/playbooks`).
        3.  **Tâche de Fond:** Créer une nouvelle tâche Celery `learn_from_interaction(bot_id, interaction_context)` dans `app/worker/tasks.py`.
        4.  **Déclenchement:** À la fin d'une interaction réussie dans `app/api/chat_api.py`, appeler `learn_from_interaction.delay(...)`.
        5.  **Logique d'Apprentissage:** Dans la tâche Celery :
            *   Charger ou créer le `Playbook` du bot depuis son fichier JSON.
            *   Instancier les rôles ACE (`Reflector`, `Curator`).
            *   Utiliser un `SelfReflectionEnvironment` qui évalue la réponse finale du bot.
            *   Exécuter le cycle `Reflect -> Curate`.
            *   Appliquer le `Delta` au `Playbook`.
            *   Sauvegarder le `Playbook` mis à jour.
    *   **Résultat:** Des `Playbook`s se construisent passivement. **Aucun impact sur la production.**
    
    ### Phase 2 : Intégration Hybride (Enrichissement du Contexte)
    *   **Objectif:** Utiliser les stratégies apprises pour améliorer les performances de la "chaîne de montage" d'agents existante.
    *   **Étapes Techniques:**
        1.  **Chargement:** Au début du traitement dans `app/core/agent_orchestrator.py`, charger le `Playbook` du bot concerné.
        2.  **Formatage:** Appeler `playbook.as_prompt()` pour obtenir le contexte des stratégies.
        3.  **Injection:** Ajouter ce contexte au prompt système des agents `Planner` et `Synthesizer` pour leur donner plus d'informations et guider leur raisonnement.
    *   **Résultat:** Amélioration potentielle des performances des bots actuels avec un effort de développement modéré.
    
    ### Phase 3 : Intégration Complète (Moteur Agentique Alternatif)
    *   **Objectif:** Permettre à certains bots d'utiliser le `Generator` d'ACE à la place de la "chaîne de montage" via un feature flag.
    *   **Étapes Techniques:**
        1.  **Migration BD:** Ajouter une colonne `use_ace_engine: bool` à la table `bots` via Alembic.
        2.  **Routage:** Dans `app/api/chat_api.py`, ajouter une condition :
            *   Si `bot.use_ace_engine` est `True`, utiliser la nouvelle logique ACE.
            *   Sinon, utiliser l'`agent_orchestrator` actuel.
        3.  **Nouvelle Logique ACE:**
            *   Charger le `Playbook`.
            *   Instancier le `Generator` d'ACE.
            *   Appeler `generator.generate(...)`.
        4.  **Gestion des Outils (Défi Principal):** La logique d'apprentissage de la Phase 1 devra être étendue pour que le `Curator` crée des stratégies sur l'utilisation des outils. Le prompt du `Generator` d'ACE devra être adapté pour qu'il comprenne comment invoquer un outil.
    *   **Résultat:** Deux moteurs agentiques coexistent, permettant des tests A/B et une migration progressive.
    
    ### Phase 4 : Intégration de l'Interface Utilisateur (UI)
    *   **Objectif:** Rendre la connaissance apprise par le bot visible et contrôlable par l'administrateur.
    *   **Étapes Techniques:**
        1.  **API Backend:** Créer un nouvel endpoint `GET /api/bots/{bot_id}/playbook` dans `app/api/bots_api.py` qui lit et retourne le fichier JSON du `Playbook`.
        2.  **UI Frontend:**
            *   Ajouter un onglet "Playbook" à la vue de gestion d'un bot.
            *   Dans `ui.js`, créer une fonction `renderPlaybook()` qui appelle l'API et affiche les `Bullet`s de manière structurée.
        3.  **(Futur):** Ajouter des endpoints `POST/PUT/DELETE` pour permettre l'édition manuelle des stratégies.
    *   **Résultat:** Le système devient transparent et l'administrateur peut auditer et même influencer l'apprentissage du bot.