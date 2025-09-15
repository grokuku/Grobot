# discord_bot_launcher/launcher.py

import time
import sys
import os
import subprocess
import httpx
import json

# --- Constants ---
API_BASE_URL = "http://app/api"
REFRESH_INTERVAL = 15
API_STARTUP_RETRY_DELAY = 5
API_STARTUP_MAX_RETRIES = 12 # Total wait time: 12 * 5s = 60s

# Dictionary to keep track of running bot processes
running_bots = {}

def get_active_bots():
    """
    Fetches the list of active bots from the GroBot API.
    Returns the list of bots, or None in case of a communication error.
    """
    bots_url = f"{API_BASE_URL.rstrip('/')}/bots/"
    try:
        response = httpx.get(bots_url, timeout=10.0)
        response.raise_for_status()
        
        all_bots = response.json()
        active_bots = [bot for bot in all_bots if bot.get("is_active")]
        return active_bots

    except json.JSONDecodeError:
        print(f"[Launcher] ERREUR: La réponse de l'API n'est pas un JSON valide.", file=sys.stderr)
        print(f"    Status: {response.status_code}, Contenu (début): {response.text[:250]}...", file=sys.stderr)
        return None

    except httpx.HTTPStatusError as e:
        print(f"[Launcher] ERREUR: L'API a retourné un statut d'erreur {e.response.status_code}.", file=sys.stderr)
        print(f"    URL: {e.request.url}", file=sys.stderr)
        print(f"    Contenu: {e.response.text}", file=sys.stderr)
        return None

    except httpx.RequestError as e:
        print(f"[Launcher] ERREUR: Impossible de contacter l'API (erreur réseau).", file=sys.stderr)
        print(f"    URL: {e.request.url}", file=sys.stderr)
        print(f"    Détails: {e}", file=sys.stderr)
        return None

    except Exception as e:
        print(f"[Launcher] ERREUR CRITIQUE inattendue dans get_active_bots: {e}", file=sys.stderr)
        return None

def get_bot_config(bot_id: int):
    """
    Fetches the full configuration for a single bot to check for a token.
    """
    config_url = f"{API_BASE_URL.rstrip('/')}/bots/{bot_id}/config"
    try:
        response = httpx.get(config_url, timeout=10.0)
        response.raise_for_status()
        return response.json()
    except Exception as e:
        print(f"[Launcher] ERREUR: Impossible de récupérer la config pour le bot {bot_id}. Détails: {e}", file=sys.stderr)
        return None

def start_bot_process(bot_config: dict):
    """Starts a new bot process using its full configuration object."""
    bot_id = bot_config['id']
    if bot_id in running_bots:
        return
    
    print(f"[Launcher] Démarrage du bot avec l'ID: {bot_id}...")
    
    gatekeeper_limit = bot_config.get('gatekeeper_history_limit', 5)
    conversation_limit = bot_config.get('conversation_history_limit', 15)

    command = [
        sys.executable,
        "-u",
        "bot_process.py",
        "--bot-id", str(bot_id),
        "--gatekeeper-history-limit", str(gatekeeper_limit),
        "--conversation-history-limit", str(conversation_limit)
    ]
    
    process = subprocess.Popen(command, stdout=sys.stdout, stderr=sys.stderr)
    running_bots[bot_id] = process
    print(f"[Launcher] Bot {bot_id} démarré avec le PID: {process.pid}.")

def stop_bot_process(bot_id: int):
    if bot_id not in running_bots:
        return
    
    process = running_bots.pop(bot_id)
    print(f"[Launcher] Arrêt du bot avec l'ID: {bot_id} (PID: {process.pid})...")
    process.terminate()
    try:
        process.wait(timeout=5) 
    except subprocess.TimeoutExpired:
        print(f"[Launcher] AVERTISSEMENT: Le bot {bot_id} n'a pas répondu. Forçage.", file=sys.stderr)
        process.kill()
    print(f"[Launcher] Bot {bot_id} arrêté.")

def main_loop():
    print("[Launcher] Démarrage du manager de processus GroBot...")
    while True:
        try:
            print(f"[Launcher] Cycle de vérification... (Prochain dans {REFRESH_INTERVAL}s)")
            active_bots_from_api = get_active_bots()
            if active_bots_from_api is not None:
                active_bot_ids = {bot['id'] for bot in active_bots_from_api}
                running_bot_ids = set(running_bots.keys())
                
                bots_to_start = active_bot_ids - running_bot_ids
                for bot_id in bots_to_start:
                    config = get_bot_config(bot_id)
                    token = config.get("discord_token") if config else None

                    # A bot should only start if its config was fetched, it has a token,
                    # and the token is not a placeholder for pre-configuration.
                    if token and not token.startswith("PLACEHOLDER_TOKEN_"):
                        start_bot_process(config)
                    else:
                        print(f"[Launcher] Bot {bot_id} est actif mais n'a pas de token valide. Lancement ignoré.")
                
                bots_to_stop = running_bot_ids - active_bot_ids
                for bot_id in bots_to_stop:
                    stop_bot_process(bot_id)
            else:
                print(f"[Launcher] AVERTISSEMENT: Cycle sauté, API indisponible.", file=sys.stderr)
            
            for bot_id, process in list(running_bots.items()):
                if process.poll() is not None:
                    print(f"[Launcher] AVERTISSEMENT: Proc. du bot {bot_id} arrêté. Relance au prochain cycle.", file=sys.stderr)
                    running_bots.pop(bot_id)
        except Exception as e:
            print(f"[Launcher] ERREUR CRITIQUE dans la boucle principale: {e}", file=sys.stderr)
        time.sleep(REFRESH_INTERVAL)

def wait_for_api():
    """Waits for the API to be available before starting the main loop."""
    print("[Launcher] En attente de l'API...")
    for i in range(API_STARTUP_MAX_RETRIES):
        try:
            response = httpx.get(f"http://app/health", timeout=5.0)
            if response.status_code == 200:
                print("[Launcher] API est disponible. Démarrage.")
                return True
        except httpx.RequestError:
            pass # Ignore connection errors during startup
        
        print(f"[Launcher] API non disponible, nouvelle tentative dans {API_STARTUP_RETRY_DELAY}s... ({i+1}/{API_STARTUP_MAX_RETRIES})")
        time.sleep(API_STARTUP_RETRY_DELAY)

    print("[Launcher] ERREUR CRITIQUE: L'API n'a pas pu être jointe après plusieurs tentatives. Arrêt.", file=sys.stderr)
    return False

if __name__ == "__main__":
    if wait_for_api():
        main_loop()
    else:
        sys.exit(1)