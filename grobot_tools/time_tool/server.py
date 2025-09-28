# /app/grobot_tools/time_tool/server.py
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from typing import Any, Dict, Optional
from datetime import datetime
import pytz

app = FastAPI(
    title="GroBot - Time Tool",
    description="MCP server for time-related tools.",
    version="1.0.0"
)

class JsonRpcRequest(BaseModel):
    jsonrpc: str = "2.0"
    method: str
    params: Optional[Dict[str, Any]] = None
    id: int

# === MODIFICATION MAJEURE: Le paramètre est renommé de "timezone" à "location" ===
# Cela rend la tâche de l'agent d'extraction beaucoup plus simple et directe.
GET_CURRENT_TIME_TOOL = {
    "name": "get_current_time",
    "title": "Get Current Time",
    "description": "Returns the current date and time for a specific location. Use for any questions about time.",
    "inputSchema": {
        "type": "object",
        "properties": {
            "location": {
                "title": "Location",
                "description": "The city or region for which to get the time (e.g., 'Paris', 'Montreal').",
                "type": "string"
            }
        },
        "required": [] # Le paramètre reste optionnel, la logique interne gérera les cas par défaut.
    }
}
AVAILABLE_TOOLS = [GET_CURRENT_TIME_TOOL]

# La logique interne gère toujours la conversion de location -> timezone
async def handle_get_current_time(arguments: Dict, configuration: Dict) -> str:
    # === MODIFICATION: On cherche "location" au lieu de "timezone" ===
    location_name = arguments.get("location") if arguments else None
    
    # Logique de fallback hiérarchique
    tz_name = "UTC" # Valeur par défaut finale
    source = "server default"

    if location_name:
        tz_name = location_name # On utilise la location comme base pour trouver la timezone
        source = "user request"
    elif configuration and configuration.get("timezone"):
        tz_name = configuration["timezone"]
        source = "user profile"
    
    time_format = configuration.get("format", "%H:%M:%S")

    try:
        tz_map = { "montreal": "America/Montreal", "paris": "Europe/Paris", "london": "Europe/London" }
        tz_name_mapped = tz_map.get(tz_name.lower(), tz_name)
        tz = pytz.timezone(tz_name_mapped)
    except pytz.UnknownTimeZoneError:
        # On retourne le nom original pour un message d'erreur plus clair
        return f"I'm sorry, I don't recognize '{tz_name}' as a valid location or timezone."

    now = datetime.now(tz)
    
    if source == "user request":
        # On utilise le nom de la timezone résolue pour plus de précision
        return f"The current time in {tz.zone} is {now.strftime(time_format)}."
    else:
        return f"It is currently {now.strftime(time_format)} ({tz.zone})."

TOOL_HANDLERS = { "get_current_time": handle_get_current_time }

@app.post("/rpc")
async def rpc_endpoint(request: JsonRpcRequest):
    if request.method == "tools/list":
        return JSONResponse(content={"jsonrpc": "2.0", "id": request.id, "result": {"tools": AVAILABLE_TOOLS}})
    elif request.method == "tools/call":
        tool_name = request.params.get("name") if request.params else None
        tool_args = request.params.get("arguments", {}) if request.params else {}
        tool_config = request.params.get("configuration", {}) if request.params else {}
        handler = TOOL_HANDLERS.get(tool_name)
        if not handler:
            return JSONResponse(
                content={"jsonrpc": "2.0", "id": request.id, "error": {"code": -32601, "message": f"Method not found: Tool '{tool_name}' is not available."}},
                status_code=404
            )
        try:
            result_text = await handler(tool_args, tool_config)
            return JSONResponse(content={"jsonrpc": "2.0", "id": request.id, "result": {"content": [{"type": "text", "text": result_text}]}})
        except Exception as e:
            return JSONResponse(
                content={"jsonrpc": "2.0", "id": request.id, "error": {"code": -32602, "message": f"Error executing tool '{tool_name}': {e}"}},
                status_code=500
            )
    else:
        return JSONResponse(
            content={"jsonrpc": "2.0", "id": request.id, "error": {"code": -32601, "message": f"Method not found: '{request.method}'"}},
            status_code=404
        )

@app.get("/health")
def health_check():
    return {"status": "ok"}