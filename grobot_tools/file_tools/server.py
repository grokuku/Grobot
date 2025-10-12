# grobot_tools/file_tools/server.py
import os
import httpx
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from typing import Any, Dict, Optional, List, Union

# --- Configuration ---
API_BASE_URL = os.getenv("API_BASE_URL", "http://app:8000/api")

# --- FastAPI App Initialization ---
app = FastAPI(
    title="GroBot - File Tools",
    description="MCP server for file management tools (list, search, details, delete).",
    version="1.0.0"
)

# --- JSON-RPC Request Model ---
class JsonRpcRequest(BaseModel):
    jsonrpc: str = "2.0"
    method: str
    params: Optional[Dict[str, Any]] = None
    id: int

# --- Tool Definitions (with outputSchema) ---

LIST_FILES_TOOL = {
    "name": "list_files",
    "title": "List All Available Files",
    "description": "Returns a list of all files currently available to you, including their UUIDs and filenames.",
    "inputSchema": { "type": "object", "properties": {} },
    "outputSchema": {
        "type": "object",
        "properties": {
            "files": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "uuid": {"type": "string"},
                        "filename": {"type": "string"}
                    },
                    "required": ["uuid", "filename"]
                }
            },
            "count": {"type": "integer"},
            "human_readable_summary": {"type": "string"}
        },
        "required": ["files", "count", "human_readable_summary"]
    }
}

SEARCH_FILES_TOOL = {
    "name": "search_files",
    "title": "Search for Files",
    "description": "Searches for files based on a query term. The search is performed on filenames and their descriptions.",
    "inputSchema": {
        "type": "object",
        "properties": {"query": {"type": "string", "description": "The search term to look for."}},
        "required": ["query"]
    },
    "outputSchema": LIST_FILES_TOOL["outputSchema"] # Same output structure as list_files
}

GET_FILE_DETAILS_TOOL = {
    "name": "get_file_details",
    "title": "Get Details of a Specific File",
    "description": "Retrieves detailed metadata for a single file using its unique identifier (UUID).",
    "inputSchema": {
        "type": "object",
        "properties": {"uuid": {"type": "string", "description": "The unique identifier (UUID) of the file."}},
        "required": ["uuid"]
    },
    "outputSchema": {
        "type": "object",
        "properties": {
            "file": {
                "type": "object",
                "properties": {
                    "uuid": {"type": "string"},
                    "filename": {"type": "string"},
                    "size_bytes": {"type": "integer"},
                    "file_type": {"type": "string"},
                    "analysis_content": {"type": "string"}
                },
                "required": ["uuid", "filename", "size_bytes", "file_type"]
            },
            "human_readable_summary": {"type": "string"}
        },
        "required": ["file", "human_readable_summary"]
    }
}

DELETE_FILE_TOOL = {
    "name": "delete_file",
    "title": "Delete a File",
    "description": "Permanently deletes a file using its unique identifier (UUID). This action is irreversible. Use with caution.",
    "inputSchema": {
        "type": "object",
        "properties": {"uuid": {"type": "string", "description": "The unique identifier (UUID) of the file to be deleted."}},
        "required": ["uuid"]
    },
    "outputSchema": {
        "type": "object",
        "properties": {
            "success": {"type": "boolean"},
            "uuid": {"type": "string"},
            "human_readable_summary": {"type": "string"}
        },
        "required": ["success", "uuid", "human_readable_summary"]
    }
}

AVAILABLE_TOOLS = [ LIST_FILES_TOOL, SEARCH_FILES_TOOL, GET_FILE_DETAILS_TOOL, DELETE_FILE_TOOL ]

# --- Configuration Schema Definition ---
CONFIGURATION_SCHEMA = {
    "title": "File Tools Configuration",
    "description": "Configure the behavior of the file management tools.",
    "type": "object",
    "properties": {
        "max_results": {
            "title": "Maximum Search Results",
            "description": "The maximum number of files to return in a search result.",
            "type": "integer",
            "default": 10
        }
    }
}

# --- Tool Logic Handlers (returning Dict instead of str) ---

async def handle_list_files(arguments: Dict, configuration: Dict) -> Dict:
    api_url = f"{API_BASE_URL}/files/"
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(api_url)
            response.raise_for_status()
            files_data = response.json()
            
            if not files_data:
                summary = "No files are available."
            else:
                summary = "Available files:\n" + "\n".join([f"- {f.get('filename')} (UUID: {f.get('uuid')})" for f in files_data])
                
            return {
                "files": files_data,
                "count": len(files_data),
                "human_readable_summary": summary
            }
    except Exception as e:
        raise Exception(f"Could not retrieve file list from API. {e}")

async def handle_search_files(arguments: Dict, configuration: Dict) -> Dict:
    query = arguments.get("query")
    if not query:
        raise ValueError("'query' argument is missing.")
    
    max_results = configuration.get("max_results", CONFIGURATION_SCHEMA["properties"]["max_results"]["default"])
    api_url = f"{API_BASE_URL}/files/search"
    params = {"query": query, "limit": max_results}
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(api_url, params=params)
            response.raise_for_status()
            files_data = response.json()
            
            if not files_data:
                summary = f"No files found matching '{query}'."
            else:
                summary = f"Files matching '{query}':\n" + "\n".join([f"- {f.get('filename')} (UUID: {f.get('uuid')})" for f in files_data])

            return {
                "files": files_data,
                "count": len(files_data),
                "human_readable_summary": summary
            }
    except Exception as e:
        raise Exception(f"Could not perform file search via API. {e}")

async def handle_get_file_details(arguments: Dict, configuration: Dict) -> Dict:
    uuid = arguments.get("uuid")
    if not uuid:
        raise ValueError("'uuid' argument is missing.")
    
    api_url = f"{API_BASE_URL}/files/{uuid}"
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(api_url)
            response.raise_for_status()
            details = response.json()
            analysis = details.get("analysis_content", "No analysis available.")
            summary = f"""File Details:
- Filename: {details.get('filename')}
- UUID: {details.get('uuid')}
- Size: {details.get('size_bytes')} bytes
- Type: {details.get('file_type')}
- Description/Analysis: {analysis}"""
            
            return {
                "file": details,
                "human_readable_summary": summary
            }
    except httpx.HTTPStatusError as e:
        if e.response.status_code == 404:
            raise Exception(f"No file found with UUID '{uuid}'.")
        raise Exception(f"API failed with status {e.response.status_code}.")
    except Exception as e:
        raise Exception(f"Could not retrieve file details from API. {e}")

async def handle_delete_file(arguments: Dict, configuration: Dict) -> Dict:
    uuid = arguments.get("uuid")
    if not uuid:
        raise ValueError("'uuid' argument is missing.")
    
    api_url = f"{API_BASE_URL}/files/{uuid}"
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.delete(api_url)
            response.raise_for_status()
            return {
                "success": True,
                "uuid": uuid,
                "human_readable_summary": f"Success: File with UUID '{uuid}' has been deleted."
            }
    except httpx.HTTPStatusError as e:
        if e.response.status_code == 404:
            raise Exception(f"No file found with UUID '{uuid}' to delete.")
        raise Exception(f"API failed with status {e.response.status_code}.")
    except Exception as e:
        raise Exception(f"Could not delete file via API. {e}")


TOOL_HANDLERS = {
    "list_files": handle_list_files,
    "search_files": handle_search_files,
    "get_file_details": handle_get_file_details,
    "delete_file": handle_delete_file,
}

# --- Main RPC Endpoint ---
@app.post("/rpc")
async def rpc_endpoint(request: JsonRpcRequest):
    method = request.method
    params = request.params or {}
    
    if method == "tools/list":
        return JSONResponse(content={"jsonrpc": "2.0", "id": request.id, "result": {"tools": AVAILABLE_TOOLS}})

    elif method == "tools/call":
        tool_name = params.get("name")
        tool_args = params.get("arguments", {})
        tool_config = params.get("configuration", {})
        handler = TOOL_HANDLERS.get(tool_name)

        if not handler:
            return JSONResponse(
                content={"jsonrpc": "2.0", "id": request.id, "error": {"code": -32601, "message": f"Method not found: Tool '{tool_name}' is not available."}},
                status_code=404
            )
        try:
            # The handler now returns a dictionary. We use it to build a richer response.
            result_obj = await handler(tool_args, tool_config)
            
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
            # Centralized error handling for tool execution
            return JSONResponse(
                content={"jsonrpc": "2.0", "id": request.id, "error": {"code": -32602, "message": f"Error executing tool '{tool_name}': {str(e)}"}, "result": None},
                status_code=500
            )
            
    elif method == "tools/getConfigurationSchema":
        return JSONResponse(content={"jsonrpc": "2.0", "id": request.id, "result": CONFIGURATION_SCHEMA})

    else:
        return JSONResponse(
            content={"jsonrpc": "2.0", "id": request.id, "error": {"code": -32601, "message": f"Method not found: '{method}'"}},
            status_code=404
        )

# --- Health Check Endpoint ---
@app.get("/health")
def health_check():
    return {"status": "ok"}