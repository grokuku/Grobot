# grobot_tools/time_tool/server.py
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from typing import Any, Dict, Optional
from datetime import datetime
import pytz # Added for timezone handling

app = FastAPI(
    title="GroBot - Time Tool",
    description="MCP server for time-related tools.",
    version="1.0.0"
)

# --- JSON-RPC Request Model ---
class JsonRpcRequest(BaseModel):
    jsonrpc: str = "2.0"
    method: str
    params: Optional[Dict[str, Any]] = None
    id: int

# --- Tool Definitions ---
# MODIFIED: The tool's own inputSchema now contains the configurable parameters.
GET_CURRENT_TIME_TOOL = {
    "name": "get_current_time",
    "title": "Get Current Time",
    "description": "Returns the current server date and time. Use this for any questions about the current time, date, or day of the week.",
    "inputSchema": {
        "type": "object",
        "properties": {
            "timezone": {
                "title": "Timezone",
                "description": "The IANA timezone name for accurate time reporting (e.g., 'Europe/Paris', 'America/New_York').",
                "type": "string",
                "default": "UTC"
            },
            "format": {
                "title": "Output Format",
                "description": "The Python 'strftime' format for the returned date and time string.",
                "type": "string",
                "default": "%A, %Y-%m-%d %H:%M:%S %Z%z"
            }
        }
    }
}
AVAILABLE_TOOLS = [GET_CURRENT_TIME_TOOL]

# REMOVED: The separate CONFIGURATION_SCHEMA is no longer needed as its
# properties have been moved into the tool's inputSchema.

# --- Tool Logic Handlers ---
# MODIFIED: The handler now reads parameters from 'arguments' instead of 'configuration'.
async def handle_get_current_time(arguments: Dict, configuration: Dict) -> str:
    # Get default values from the tool's own inputSchema
    schema_props = GET_CURRENT_TIME_TOOL["inputSchema"]["properties"]
    
    # Get parameter values from the tool call arguments, falling back to schema defaults
    tz_name = arguments.get("timezone", schema_props["timezone"]["default"])
    time_format = arguments.get("format", schema_props["format"]["default"])

    try:
        # Get the timezone object
        tz = pytz.timezone(tz_name)
    except pytz.UnknownTimeZoneError:
        # Fallback to UTC if the timezone is invalid
        tz = pytz.utc
        tz_name = f"UTC (invalid timezone '{tz_name}' provided)"

    # Get the current time and localize it to the target timezone
    now = datetime.now(tz)
    
    # Format the output string
    return f"The current time in {tz_name} is: {now.strftime(time_format)}"


TOOL_HANDLERS = { "get_current_time": handle_get_current_time }


# --- Main RPC Endpoint ---
@app.post("/rpc")
async def rpc_endpoint(request: JsonRpcRequest):
    # --- Standard MCP Method: tools/list ---
    if request.method == "tools/list":
        return JSONResponse(content={"jsonrpc": "2.0", "id": request.id, "result": {"tools": AVAILABLE_TOOLS}})

    # --- Standard MCP Method: tools/call ---
    elif request.method == "tools/call":
        tool_name = request.params.get("name") if request.params else None
        tool_args = request.params.get("arguments", {}) if request.params else {}
        
        # GroBot EXTENSION: Pass the tool-specific configuration to the handler
        # This is kept for compatibility with the launcher, but will likely be empty for this tool.
        tool_config = request.params.get("configuration", {}) if request.params else {}
        
        handler = TOOL_HANDLERS.get(tool_name)

        if not handler:
            return JSONResponse(
                content={"jsonrpc": "2.0", "id": request.id, "error": {"code": -32601, "message": f"Method not found: Tool '{tool_name}' is not available."}},
                status_code=404
            )
        try:
            # Pass both arguments and configuration to the handler
            result_text = await handler(tool_args, tool_config)
            return JSONResponse(content={"jsonrpc": "2.0", "id": request.id, "result": {"content": [{"type": "text", "text": result_text}]}})
        except Exception as e:
            return JSONResponse(
                content={"jsonrpc": "2.0", "id": request.id, "error": {"code": -32602, "message": f"Error executing tool '{tool_name}': {e}"}},
                status_code=500
            )
            
    # REMOVED: The custom and now obsolete 'tools/getConfigurationSchema' method has been removed.

    # --- Fallback for unknown methods ---
    else:
        return JSONResponse(
            content={"jsonrpc": "2.0", "id": request.id, "error": {"code": -32601, "message": f"Method not found: '{request.method}'"}},
            status_code=404
        )

# --- Health Check Endpoint ---
@app.get("/health")
def health_check():
    return {"status": "ok"}