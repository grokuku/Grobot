# grobot_tools/time_tool/server.py
import asyncio
from datetime import datetime
import pytz
import re  # Added for regex parsing
from typing import Any, List

from mcp.server import Server
from mcp.server.sse import SseServerTransport
import mcp.types as types
from starlette.applications import Starlette
from starlette.routing import Route
from starlette.requests import Request
from starlette.responses import Response

# --- FIX: Custom Response that does nothing ---
class NoOpResponse(Response):
    """
    A response that does nothing when called.
    Used because the MCP SDK handles the ASGI response sending directly,
    but Starlette requires the endpoint to return a Response object.
    """
    def __init__(self):
        super().__init__()
    
    async def __call__(self, scope, receive, send):
        # Do not send anything, as it has already been handled.
        pass

# 1. Initialize the MCP Server
mcp_server = Server("time-tool")

# 2. Define Tool Schemas explicitly
GET_CURRENT_TIME_TOOL = types.Tool(
    name="get_current_time",
    description="Returns the current date and time for a specific location. Use for any questions about time.",
    inputSchema={
        "type": "object",
        "properties": {
            "location": {
                "type": "string",
                "description": "The city, region, or timezone offset (e.g., 'Paris', 'UTC+2', 'GMT-5'). Defaults to UTC."
            }
        },
        "required": []
    }
)

# 3. Register Handlers
@mcp_server.list_tools()
async def handle_list_tools() -> List[types.Tool]:
    return [GET_CURRENT_TIME_TOOL]

@mcp_server.call_tool()
async def handle_call_tool(
    name: str, arguments: dict | None
) -> list[types.TextContent | types.ImageContent | types.EmbeddedResource]:
    if name != "get_current_time":
        raise ValueError(f"Unknown tool: {name}")

    arguments = arguments or {}
    location = arguments.get("location")
    
    tz_name = "UTC"
    
    if location:
        clean_loc = location.lower().strip()
        
        # 1. Dictionary map for common cities/aliases
        tz_map = { 
            "montreal": "America/Montreal", 
            "paris": "Europe/Paris", 
            "london": "Europe/London",
            "berlin": "Europe/Berlin",
            "tokyo": "Asia/Tokyo",
            "new york": "America/New_York",
            "cet": "Europe/Paris",
            "cest": "Europe/Paris"
        }
        
        if clean_loc in tz_map:
            tz_name = tz_map[clean_loc]
        else:
            # 2. Try parsing offsets like UTC+2 or GMT-5
            # Regex captures: (utc/gmt) optional space, then a signed number
            offset_match = re.match(r"^(?:utc|gmt)\s*([+-]?\d+)", clean_loc)
            if offset_match:
                try:
                    offset = int(offset_match.group(1))
                    # IMPORTANT: In 'Etc/GMT' format, signs are INVERTED.
                    # UTC+2 becomes Etc/GMT-2. UTC-5 becomes Etc/GMT+5.
                    inv_offset = -offset
                    sign = "+" if inv_offset >= 0 else "-"
                    tz_name = f"Etc/GMT{sign}{abs(inv_offset)}"
                except Exception:
                    # Fallback to direct try if math fails
                    tz_name = location
            else:
                # 3. Assume it's a raw timezone name (e.g., "Europe/Madrid")
                tz_name = location

    try:
        tz = pytz.timezone(tz_name)
    except pytz.UnknownTimeZoneError:
        # Soft error message to encourage LLM to show the fallback time
        return [types.TextContent(type="text", text=f"Notice: Could not identify timezone '{location}'. Showing UTC time instead.")]

    now = datetime.now(tz)
    # Outputting the requested timezone explicitly helps the LLM context
    result_text = f"Current time in {tz.zone}: {now.strftime('%Y-%m-%d %H:%M:%S')}"
    
    return [types.TextContent(type="text", text=result_text)]

# 4. Transport Adapter (Starlette / SSE)
sse = SseServerTransport("/messages")

async def handle_sse(request: Request):
    async with sse.connect_sse(request.scope, request.receive, request._send) as streams:
        await mcp_server.run(streams[0], streams[1], mcp_server.create_initialization_options())

async def handle_messages(request: Request):
    # Delegate the response logic to the MCP SDK
    await sse.handle_post_message(request.scope, request.receive, request._send)
    return NoOpResponse()

app = Starlette(
    routes=[
        Route("/mcp", endpoint=handle_sse, methods=["GET"]),
        Route("/mcp", endpoint=handle_messages, methods=["POST"]),
        Route("/messages", endpoint=handle_messages, methods=["POST"]),
        Route("/health", endpoint=lambda r: Response("ok"))
    ]
)