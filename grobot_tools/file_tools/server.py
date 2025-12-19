# grobot_tools/file_tools/server.py
import os
import httpx
from typing import Optional, List

from mcp.server import Server
from mcp.server.sse import SseServerTransport
import mcp.types as types
from starlette.applications import Starlette
from starlette.routing import Route
from starlette.requests import Request
from starlette.responses import Response

API_BASE_URL = os.getenv("API_BASE_URL", "http://app:8000/api")

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

# 1. Initialize
mcp_server = Server("file-tools")

# 2. Define Schemas
LIST_FILES_TOOL = types.Tool(
    name="list_files",
    description="List all available files with their UUIDs.",
    inputSchema={"type": "object", "properties": {}}
)

SEARCH_FILES_TOOL = types.Tool(
    name="search_files",
    description="Search files by name or description.",
    inputSchema={
        "type": "object", 
        "properties": {"query": {"type": "string"}}, 
        "required": ["query"]
    }
)

GET_FILE_DETAILS_TOOL = types.Tool(
    name="get_file_details",
    description="Get detailed metadata and analysis for a file by UUID.",
    inputSchema={
        "type": "object", 
        "properties": {"uuid": {"type": "string"}}, 
        "required": ["uuid"]
    }
)

DELETE_FILE_TOOL = types.Tool(
    name="delete_file",
    description="Permanently delete a file by UUID.",
    inputSchema={
        "type": "object", 
        "properties": {"uuid": {"type": "string"}}, 
        "required": ["uuid"]
    }
)

# 3. Helpers & Handlers
async def _api_call(method: str, endpoint: str, params: dict = None) -> dict:
    url = f"{API_BASE_URL}{endpoint}"
    async with httpx.AsyncClient(timeout=30.0) as client:
        if method == "GET": response = await client.get(url, params=params)
        elif method == "DELETE": response = await client.delete(url)
        else: raise ValueError(f"Method {method} not supported")
        
        try:
            response.raise_for_status()
            if response.status_code == 204 or not response.content: return {"status": "success"}
            return response.json()
        except Exception as e:
            return {"error": str(e)}

@mcp_server.list_tools()
async def handle_list_tools() -> List[types.Tool]:
    return [LIST_FILES_TOOL, SEARCH_FILES_TOOL, GET_FILE_DETAILS_TOOL, DELETE_FILE_TOOL]

@mcp_server.call_tool()
async def handle_call_tool(
    name: str, arguments: dict | None
) -> list[types.TextContent | types.ImageContent | types.EmbeddedResource]:
    
    arguments = arguments or {}
    text_result = ""

    if name == "list_files":
        data = await _api_call("GET", "/files/")
        if "error" in data: text_result = f"Error: {data['error']}"
        elif not data: text_result = "No files available."
        else:
            lines = ["Available files:"] + [f"- {f.get('filename')} (UUID: {f.get('uuid')})" for f in data]
            text_result = "\n".join(lines)

    elif name == "search_files":
        query = arguments.get("query")
        data = await _api_call("GET", "/files/search", params={"query": query, "limit": 10})
        if "error" in data: text_result = f"Error: {data['error']}"
        elif not data: text_result = f"No files found for '{query}'."
        else:
            lines = [f"Files matching '{query}':"] + [f"- {f.get('filename')} (UUID: {f.get('uuid')})" for f in data]
            text_result = "\n".join(lines)

    elif name == "get_file_details":
        uuid = arguments.get("uuid")
        data = await _api_call("GET", f"/files/{uuid}")
        if "error" in data: text_result = f"Error: {data['error']}"
        else:
            analysis = data.get("analysis_content", "N/A")
            text_result = (
                f"File: {data.get('filename')}\n"
                f"UUID: {data.get('uuid')}\n"
                f"Size: {data.get('size_bytes')} bytes\n"
                f"Type: {data.get('file_type')}\n"
                f"Analysis: {analysis}"
            )

    elif name == "delete_file":
        uuid = arguments.get("uuid")
        data = await _api_call("DELETE", f"/files/{uuid}")
        if "error" in data: text_result = f"Error: {data['error']}"
        else: text_result = f"File {uuid} deleted successfully."

    else:
        raise ValueError(f"Unknown tool: {name}")

    return [types.TextContent(type="text", text=text_result)]

# 4. App
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
        # FIX: Allow POST on /mcp to handle clients that use one URL for everything
        Route("/mcp", endpoint=handle_messages, methods=["POST"]),
        Route("/messages", endpoint=handle_messages, methods=["POST"]),
        Route("/health", endpoint=lambda r: Response("ok"))
    ]
)