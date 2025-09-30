// frontend/src/api.js
const API_BASE_URL = '/api';

/**
 * A wrapper for the fetch API that handles authentication.
 * For now, it assumes cookie-based auth and handles 401 redirects.
 * @param {string} url - The URL to fetch.
 * @param {object} options - Fetch options.
 * @returns {Promise<Response>} - The fetch response.
 */
export async function fetchWithAuth(url, options = {}) {
    const response = await fetch(url, options);
    if (response.status === 401) {
        window.location.href = '/login.html'; // Or your login page
        throw new Error('User not authenticated');
    }
    return response;
}

/**
 * Fetches the list of available LLM models from the backend.
 * @param {string|null} ollamaUrl - An optional Ollama URL to test.
 * @returns {Promise<Array<object>>} - A list of model objects.
 */
export async function fetchModels(ollamaUrl = null) {
    let url = `${API_BASE_URL}/settings/llm/models`;
    if (ollamaUrl) {
        url += `?ollama_url=${encodeURIComponent(ollamaUrl)}`;
    }
    const response = await fetchWithAuth(url);
    if (!response.ok) {
        const errorData = await response.json();
        throw new Error(errorData.detail || 'Failed to fetch models');
    }
    const models = await response.json();
    // FIX: The endpoint returns an array of objects like [{ "model": "name", ... }].
    // We should return this array directly, as the UI layer is responsible for processing it.
    return models;
}

/**
 * Fetches the list of all configured bots.
 * @returns {Promise<Array<object>>} - The list of bots.
 */
export async function fetchBots() {
    const response = await fetchWithAuth(`${API_BASE_URL}/bots/`);
    if (!response.ok) throw new Error('Failed to fetch bots');
    return await response.json();
}

/**
 * Fetches the detailed configuration for a single bot.
 * @param {number} botId - The ID of the bot.
 * @returns {Promise<object>} - The bot's details.
 */
export async function fetchBotDetails(botId) {
    const response = await fetchWithAuth(`${API_BASE_URL}/bots/${botId}`);
    if (!response.ok) throw new Error('Failed to fetch bot details');
    return await response.json();
}

/**
 * Creates a new bot.
 * @param {object} data - The data for the new bot (name, token, etc.).
 * @returns {Promise<object>} - The created bot object.
 */
export async function createBot(data) {
    // Add default history limits required by the backend schema.
    const payload = {
        ...data,
        gatekeeper_history_limit: 5,
        conversation_history_limit: 15,
    };

    const response = await fetchWithAuth(`${API_BASE_URL}/bots/`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
    });
    if (!response.ok) {
        const errorData = await response.json();
        throw new Error(errorData.detail || 'Failed to create bot');
    }
    return await response.json();
}

/**
 * Fetches the global settings for the application.
 * @returns {Promise<object>} - The global settings object.
 */
export async function fetchGlobalSettings() {
    const response = await fetchWithAuth(`${API_BASE_URL}/settings/global`);
    if (!response.ok) throw new Error('Failed to fetch global settings');
    return await response.json();
}

/**
 * Fetches the list of all registered MCP servers.
 * @returns {Promise<Array<object>>} - The list of MCP servers.
 */
export async function fetchMcpServers() {
    const response = await fetchWithAuth(`${API_BASE_URL}/mcp-servers/`);
    if (!response.ok) throw new Error('Failed to fetch MCP servers');
    return await response.json();
}

/**
 * Fetches the JSON Schema for an MCP server's configuration via the backend proxy.
 * @param {number} serverId - The ID of the MCP server.
 * @returns {Promise<object>} - The JSON Schema object.
 */
export async function fetchMcpServerSchema(serverId) {
    const response = await fetchWithAuth(`${API_BASE_URL}/mcp-servers/${serverId}/config-schema`);
    if (!response.ok) {
        const errorData = await response.json();
        throw new Error(errorData.detail || 'Failed to fetch MCP server schema');
    }
    return await response.json();
}

/**
 * Fetches the list of available tools from an MCP server via the backend proxy.
 * @param {number} serverId - The ID of the MCP server.
 * @returns {Promise<object>} - An object containing the list of tools.
 */
export async function fetchMcpServerTools(serverId) {
    const response = await fetchWithAuth(`${API_BASE_URL}/mcp-servers/${serverId}/tools`);
    if (!response.ok) {
        const errorData = await response.json();
        throw new Error(errorData.detail || 'Failed to fetch MCP server tools');
    }
    return await response.json();
}


/**
 * Saves (patches) the settings for a specific bot.
 * @param {number} botId - The ID of the bot to update.
 * @param {object} data - The data to patch.
 * @returns {Promise<object>} - The updated bot object.
 */
export async function saveBotSettings(botId, data) {
    const response = await fetchWithAuth(`/api/bots/${botId}`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(data),
    });
    if (!response.ok) {
        const errorData = await response.json();
        throw new Error(errorData.detail || 'Failed to save bot settings');
    }
    return await response.json();
}

/**
 * Updates the MCP server associations for a specific bot, including configurations.
 * This replaces all existing associations.
 * @param {number} botId - The ID of the bot to update.
 * @param {Array<object>} associations - An array of association objects ({ mcp_server_id, configuration }).
 * @returns {Promise<object>} - The updated bot object.
 */
export async function updateBotMcpServers(botId, associations) {
    const response = await fetchWithAuth(`${API_BASE_URL}/bots/${botId}/mcp_servers`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(associations),
    });
    if (!response.ok) {
        const errorData = await response.json();
        throw new Error(errorData.detail || 'Failed to update MCP server associations');
    }
    return await response.json();
}

/**
 * Saves (patches) the global settings.
 * @param {object} data - The data to patch.
 * @returns {Promise<object>} - The updated settings object.
 */
export async function saveGlobalSettings(data) {
    const response = await fetchWithAuth(`/api/settings/global`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(data),
    });
    if (!response.ok) throw new Error('Failed to save global settings');
    return await response.json();
}

/**
 * Creates or updates an MCP server.
 * @param {object} data - The server data.
 * @param {number|null} serverId - The ID of the server to update, or null to create.
 * @returns {Promise<object>} - The created/updated server object.
 */
export async function saveMcpServer(data, serverId = null) {
    const url = serverId ? `${API_BASE_URL}/mcp-servers/${serverId}` : `${API_BASE_URL}/mcp-servers/`;
    const method = serverId ? 'PATCH' : 'POST';
    const response = await fetchWithAuth(url, {
        method: method,
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(data),
    });
    if (!response.ok) {
        const errorData = await response.json();
        throw new Error(errorData.detail || 'Failed to save MCP server');
    }
    return await response.json();
}

/**
 * Deletes an MCP server.
 * @param {number} serverId - The ID of the server to delete.
 * @returns {Promise<Response>} - The raw response.
 */
export async function deleteMcpServer(serverId) {
    const response = await fetchWithAuth(`${API_BASE_URL}/mcp-servers/${serverId}`, {
        method: 'DELETE'
    });
    if (!response.ok) {
        const errorData = await response.json();
        throw new Error(errorData.detail || 'Failed to delete MCP server');
    }
    return response;
}

/**
 * Fetches all files associated with a specific bot.
 * @param {number} botId - The ID of the bot.
 * @returns {Promise<Array<object>>} - A list of file objects.
 */
export async function searchFilesForBot(botId) {
    const response = await fetchWithAuth(`/api/files/admin/bot/${botId}`);
    if (!response.ok) throw new Error('Failed to fetch files');
    return await response.json();
}

/**
 * Uploads a file for a specific bot.
 * @param {number} botId - The bot's ID.
 * @param {File} file - The file to upload.
 * @param {string} ownerId - The Discord ID of the owner.
 * @returns {Promise<object>} - The created file record.
 */
export async function uploadFile(botId, file, ownerId) {
    const formData = new FormData();
    formData.append('file', file);
    formData.append('owner_discord_id', ownerId || '0');
    const response = await fetchWithAuth(`/api/files/upload/bot/${botId}`, {
        method: 'POST',
        body: formData,
    });
    if (!response.ok) {
        const errorData = await response.json();
        throw new Error(errorData.detail || 'File upload failed');
    }
    return await response.json();
}

/**
 * Deletes a file.
 * @param {string} uuid - The UUID of the file to delete.
 * @returns {Promise<Response>} - The raw response.
 */
export async function deleteFile(uuid) {
    const response = await fetchWithAuth(`/api/files/${uuid}`, {
        method: 'DELETE',
    });
    if (!response.ok) {
        const errorData = await response.json();
        throw new Error(errorData.detail || 'File deletion failed');
    }
    return response;
}

/**
 * Sends a message to the test chat endpoint.
 * @param {number} botId - The ID of the bot.
 * @param {string} message - The user's message.
 * @returns {Promise<object>} - The bot's response object.
 */
export async function sendTestChatMessage(botId, message) {
    const response = await fetchWithAuth(`${API_BASE_URL}/chat/test`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ bot_id: botId, user_message: message }),
    });
    if (!response.ok) {
        const errorData = await response.json();
        throw new Error(errorData.detail || 'Failed to send test message');
    }
    return await response.json();
}

/**
 * Establishes a WebSocket connection to the bot's log stream.
 * @param {string} botId - The ID of the bot for which to fetch logs.
 * @param {function} onMessageCallback - Function to call when a log message is received.
 * @param {function} onErrorCallback - Function to call when a connection error occurs.
 * @param {function} onOpenCallback - Function to call when the connection is successfully opened.
 * @returns {WebSocket} The WebSocket instance.
 */
export function connectToLogStream(botId, onMessageCallback, onErrorCallback, onOpenCallback) {
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const host = window.location.host;
    const wsUrl = `${protocol}//${host}/api/bots/${botId}/logs/ws`;

    const ws = new WebSocket(wsUrl);

    ws.onopen = () => {
        console.log(`WebSocket connection opened for bot ${botId}`);
        if (onOpenCallback) onOpenCallback();
    };

    ws.onmessage = (event) => {
        if (onMessageCallback) {
            onMessageCallback(event);
        }
    };

    ws.onerror = (event) => {
        console.error('WebSocket error:', event);
        if (onErrorCallback) onErrorCallback(event);
    };

    ws.onclose = () => {
        console.log(`WebSocket connection closed for bot ${botId}`);
        if (onErrorCallback) onErrorCallback();
    };

    return ws;
}

/**
 * Fetches the memory content for a specific bot.
 * @param {number} botId - The ID of the bot.
 * @returns {Promise<object>} - The bot's memory object ({ count, items }).
 */
export async function fetchBotMemory(botId) {
    const response = await fetchWithAuth(`${API_BASE_URL}/chat/memory/${botId}`);
    if (!response.ok) {
        const errorData = await response.json();
        throw new Error(errorData.detail || 'Failed to fetch bot memory');
    }
    return await response.json();
}

/**
 * Deletes a single memory entry for a bot.
 * @param {number} botId - The ID of the bot.
 * @param {string} memoryId - The unique ID of the memory entry.
 * @returns {Promise<Response>} - The raw fetch response.
 */
export async function deleteBotMemoryEntry(botId, memoryId) {
    const response = await fetchWithAuth(`${API_BASE_URL}/chat/memory/${botId}/${memoryId}`, {
        method: 'DELETE',
    });
    if (!response.ok) {
        const errorData = await response.json();
        throw new Error(errorData.detail || 'Failed to delete memory entry');
    }
    return response;
}

// --- USER KNOWLEDGE BASE ---
/**
 * Fetches a list of all users known by a specific bot.
 * @param {number} botId - The ID of the bot.
 * @returns {Promise<Array<object>>} - A list of user profile summaries.
 */
export async function fetchUsersForBot(botId) {
    const response = await fetchWithAuth(`${API_BASE_URL}/bots/${botId}/users`);
    if (!response.ok) {
        throw new Error('Failed to fetch users for bot');
    }
    return await response.json();
}


/**
 * Searches for a user in the knowledge base for a specific bot.
 * @param {number} botId - The ID of the bot.
 * @param {string} query - The Discord ID or display name to search for.
 * @returns {Promise<object>} - The user's full knowledge base entry.
 */
// MODIFIÉ: L'URL de l'endpoint est corrigée pour correspondre à la nouvelle API.
export async function searchUser(botId, query) {
    const response = await fetchWithAuth(`${API_BASE_URL}/bots/${botId}/users/search?query=${encodeURIComponent(query)}`);
    if (!response.ok) {
        if (response.status === 404) {
            const errorData = await response.json();
            throw new Error(errorData.detail || 'User not found');
        }
        throw new Error('Failed to search for user');
    }
    return await response.json();
}

/**
 * Updates a user's profile for a specific bot and server context.
 * @param {number} botId - The ID of the bot.
 * @param {number} serverId - The ID of the server.
 * @param {number} userId - The user's Discord ID.
 * @param {object} profileData - The profile data, e.g., { behavioral_instructions: "..." }.
 * @returns {Promise<object>} - The updated user profile object.
 */
export async function updateUserProfile(botId, serverId, userId, profileData) {
    const response = await fetchWithAuth(`${API_BASE_URL}/bots/${botId}/servers/${serverId}/users/${userId}/profile`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(profileData),
    });
    if (!response.ok) {
        const errorData = await response.json();
        throw new Error(errorData.detail || 'Failed to update user profile');
    }
    return await response.json();
}


/**
 * Deletes a specific note for a user.
 * @param {number} noteId - The ID of the note to delete.
 * @returns {Promise<Response>} - The raw fetch response.
 */
export async function deleteUserNote(noteId) {
    // CORRIGÉ: L'endpoint est global et ne dépend que de l'ID de la note.
    const response = await fetchWithAuth(`${API_BASE_URL}/users/notes/${noteId}`, {
        method: 'DELETE',
    });
    if (!response.ok) {
        const errorData = await response.json();
        throw new Error(errorData.detail || 'Failed to delete user note');
    }
    return response;
}