# grobot_tools/time_tool/server.py
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from typing import Any, Dict, Optional, Union
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
        "required": []
    },
    "outputSchema": {
        "type": "object",
        "properties": {
            "time": {
                "type": "string",
                "description": "The formatted time (HH:MM:SS)."
            },
            "timezone": {
                "type": "string",
                "description": "The full IANA timezone name (e.g., 'Europe/Paris')."
            },
            "iso_datetime": {
                "type": "string",
                "format": "date-time",
                "description": "The full date and time in ISO 8601 format."
            },
            "human_readable_summary": {
                "type": "string",
                "description": "A natural language sentence describing the current time."
            }
        },
        "required": ["time", "timezone", "iso_datetime", "human_readable_summary"]
    }
}
AVAILABLE_TOOLS = [GET_CURRENT_TIME_TOOL]

async def handle_get_current_time(arguments: Dict, configuration: Dict) -> Dict[str, str]:
    location_name = arguments.get("location") if arguments else None
    
    tz_name = "UTC"
    source = "server default"

    if location_name:
        tz_name = location_name
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
        # For errors, we can return a string which will be handled by the RPC endpoint.
        raise ValueError(f"I'm sorry, I don't recognize '{tz_name}' as a valid location or timezone.")

    now = datetime.now(tz)
    formatted_time = now.strftime(time_format)
    
    if source == "user request":
        summary = f"The current time in {tz.zone} is {formatted_time}."
    else:
        summary = f"It is currently {formatted_time} ({tz.zone})."
    
    return {
        "time": formatted_time,
        "timezone": str(tz.zone),
        "iso_datetime": now.isoformat(),
        "human_readable_summary": summary
    }

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
            result_obj = await handler(tool_args, tool_config)
            
            # The handler now returns a dictionary. We use it to build a richer response.
            response_payload = {
                "jsonrpc": "2.0",
                "id": request.id,
                "result": {
                    "structured_output": result_obj,
                    "content": [{"type": "text", "text": result_obj.get("human_readable_summary", "Tool executed successfully.")}]
                }
            }
            return JSONResponse(content=response_payload)
        except Exception as e:
            return JSONResponse(
                content={"jsonrpc": "2.0", "id": request.id, "error": {"code": -32602, "message": f"Error executing tool '{tool_name}': {str(e)}"}, "result": None},
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