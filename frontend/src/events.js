// Fichier: frontend/src/events.js
import * as api from './api.js';
import * as ui from './ui.js';

// NEW EVENT HANDLER for channel permission toggles
/**
 * Handles the click event on a channel permission toggle switch.
 * @param {Event} event - The click/change event.
 */
async function handleUpdateChannelPermission(event) {
    const toggle = event.target;
    const { botId, channelId, settingName } = toggle.dataset;
    const newValue = toggle.checked;

    // Disable the toggle temporarily to prevent rapid clicking
    toggle.disabled = true;

    try {
        const payload = { [settingName]: newValue };
        await api.updateBotChannelSettings(botId, channelId, payload);
        ui.showToast('Permission updated successfully!', 'success');
    } catch (error) {
        ui.showToast(`Error: ${error.message}`, 'error');
        // Revert the checkbox to its previous state on error
        toggle.checked = !newValue;
    } finally {
        // Re-enable the toggle
        toggle.disabled = false;
    }
}


/**
 * Handles the connection to the log stream WebSocket and updates the UI.
 * @param {string} botId - The ID of the bot to connect to.
 */
export function handleConnectToLogStream(botId) {
    const logsContainer = document.getElementById('logs-container');
    if (!logsContainer) return;

    // Callbacks for the WebSocket connection
    const onOpen = () => {
        const pre = logsContainer.querySelector('pre');
        if (pre) pre.textContent = 'Log stream connected. Waiting for messages...';
    };

    const onError = (event) => {
        const pre = logsContainer.querySelector('pre');
        if (pre) {
            pre.textContent = 'Log stream connection error.';
            pre.classList.add('error');
        }
        console.error('WebSocket error occurred:', event);
    };

    const onMessage = (event) => {
        try {
            const logEntry = JSON.parse(event.data);

            const pre = logsContainer.querySelector('pre');
            if (pre) {
                pre.remove();
            }

            const logLine = document.createElement('div');
            const level = (logEntry.level || 'unknown').toLowerCase();
            logLine.className = `log-line log-${level}`;

            const timestamp = new Date(logEntry.timestamp).toLocaleTimeString();

            const messageContent = logEntry.message;
            const messageString = typeof messageContent === 'object'
                ? JSON.stringify(messageContent)
                : String(messageContent);

            const sanitizedMessage = messageString.replace(/</g, "&lt;").replace(/>/g, "&gt;");

            logLine.innerHTML = `
                <span class="log-timestamp">${timestamp}</span>
                <span class="log-level">${logEntry.level || 'UNKNOWN'}</span>
                <span class="log-type">${logEntry.source || 'N/A'}</span>
                <span class="log-payload">${sanitizedMessage}</span>
            `;
            logsContainer.appendChild(logLine);
            logsContainer.scrollTop = logsContainer.scrollHeight; // Auto-scroll

        } catch (error) {
            console.error('CRITICAL ERROR processing log message:', error);
            const errorLine = document.createElement('div');
            errorLine.className = 'log-line log-error';
            errorLine.innerHTML = `<span class="log-payload">A critical error occurred while processing a log message. Check the browser console for details.</span>`;
            logsContainer.appendChild(errorLine);
        }
    };

    window.logStreamConnection = api.connectToLogStream(botId, onMessage, onError, onOpen);
}


/**
 * Handles the submission of the bot settings form using a state object.
 * @param {number} botId - The ID of the bot being edited.
 * @param {object} draftBot - The complete, updated state object for the bot.
 */
export async function handleSaveBotSettings(botId, draftBot) {
    ui.showSpinner();

    const generalData = {
        name: draftBot.name,
        is_active: draftBot.is_active,
        passive_listening_enabled: draftBot.passive_listening_enabled,
        system_prompt: draftBot.system_prompt,
        personality: draftBot.personality,

        // --- FIX: Using correct field names for bot-specific settings ---
        decisional_llm_server_url: draftBot.decisional_llm_server_url,
        decisional_llm_model: draftBot.decisional_llm_model,
        decisional_llm_context_window: draftBot.decisional_llm_context_window,
        decisional_llm_api_key: draftBot.decisional_llm_api_key,

        tools_llm_server_url: draftBot.tools_llm_server_url,
        tools_llm_model: draftBot.tools_llm_model,
        tools_llm_context_window: draftBot.tools_llm_context_window,
        tools_llm_api_key: draftBot.tools_llm_api_key,

        output_client_llm_server_url: draftBot.output_client_llm_server_url,
        output_client_llm_model: draftBot.output_client_llm_model,
        output_client_llm_context_window: draftBot.output_client_llm_context_window,
        output_client_llm_api_key: draftBot.output_client_llm_api_key,
    };

    if (draftBot.discord_token && draftBot.discord_token !== '********') {
        generalData.discord_token = draftBot.discord_token;
    }

    const mcpAssociations = draftBot.mcp_servers.map(server => ({
        mcp_server_id: server.id,
        configuration: server.configuration || {}
    }));

    try {
        await api.saveBotSettings(botId, generalData);
        const updatedBot = await api.updateBotMcpServers(botId, mcpAssociations);
        ui.showToast('Bot settings saved successfully!');
        await ui.refreshBotsList(window.botsList, window.selectBot);
        const eventHandlers = getBotViewEventHandlers();
        await ui.renderTabContent(updatedBot, 'settings', handleConnectToLogStream, eventHandlers.saveBotSettings, eventHandlers.fileHandlers, eventHandlers.testChat);
    } catch (error) {
        ui.showToast(`Error saving settings: ${error.message}`, 'error');
        console.error('Error saving bot settings:', error);
    } finally {
        ui.hideSpinner();
    }
}

/**
 * Handles the submission of the "Add Bot" form.
 * @param {Event} event - The form submission event.
 */
export async function handleCreateBot(event) {
    event.preventDefault();
    ui.showSpinner();
    const form = event.target;

    const tokenValue = form.discord_token.value.trim();

    const data = {
        name: form.name.value,
        discord_token: tokenValue ? tokenValue : null,
        // Note: llm_model here is just a helper for quick creation, backend handles mapping if needed
        // but ideally we should use categories even on creation in the future.
        llm_model: form.llm_model.value,
        system_prompt: form.system_prompt.value,
        // Proactively adding personality to the create function as well
        personality: form.system_prompt.value // Defaulting to system_prompt for now on creation
    };

    try {
        const newBot = await api.createBot(data);
        ui.showToast('Bot created successfully!');

        ui.hideModal();
        document.getElementById('main-content').innerHTML = '';

        await ui.refreshBotsList(window.botsList, window.selectBot);

        if (window.selectBot) {
            window.selectBot(newBot.id);
        }

    } catch (error) {
        ui.showToast(`Error creating bot: ${error.message}`, 'error');
        console.error('Error creating bot:', error);
    } finally {
        ui.hideSpinner();
    }
}

/**
 * Handles the submission of the global settings form.
 * @param {Event} event - The form submission event.
 */
export async function handleSaveGlobalSettings(event) {
    event.preventDefault();
    ui.showSpinner();
    const form = event.target;

    // --- FIX: Updated field names to match ui.js refactoring (tools instead of tool, output_client instead of output) ---
    const data = {
        default_decisional_llm_server: form.default_decisional_llm_server.value || null,
        default_decisional_llm_model: form.default_decisional_llm_model.value || null,
        default_decisional_llm_context_window: form.default_decisional_llm_context_window.value ? parseInt(form.default_decisional_llm_context_window.value, 10) : null,
        default_decisional_llm_api_key: (form.default_decisional_llm_api_key.value && form.default_decisional_llm_api_key.value !== '********') ? form.default_decisional_llm_api_key.value : null,

        default_tool_llm_server: form.default_tools_llm_server.value || null,
        default_tool_llm_model: form.default_tools_llm_model.value || null,
        default_tool_llm_context_window: form.default_tools_llm_context_window.value ? parseInt(form.default_tools_llm_context_window.value, 10) : null,
        default_tool_llm_api_key: (form.default_tools_llm_api_key.value && form.default_tools_llm_api_key.value !== '********') ? form.default_tools_llm_api_key.value : null,

        default_output_llm_server: form.default_output_client_llm_server.value || null,
        default_output_llm_model: form.default_output_client_llm_model.value || null,
        default_output_llm_context_window: form.default_output_client_llm_context_window.value ? parseInt(form.default_output_client_llm_context_window.value, 10) : null,
        default_output_llm_api_key: (form.default_output_client_llm_api_key.value && form.default_output_client_llm_api_key.value !== '********') ? form.default_output_client_llm_api_key.value : null,
        
        // --- NEW: Embedding Configuration Retrieval ---
        default_embedding_provider: form.default_embedding_provider.value,
        default_embedding_model: form.default_embedding_model.value,
        default_embedding_server: form.default_embedding_server.value || null,
        default_embedding_api_key: (form.default_embedding_api_key.value && form.default_embedding_api_key.value !== '********') ? form.default_embedding_api_key.value : null,

        tools_system_prompt: form.tools_system_prompt.value,
        context_header_default_prompt: form.context_header_default_prompt.value
    };

    try {
        const updatedSettings = await api.saveGlobalSettings(data);
        ui.showToast('Global settings saved successfully!');
        await ui.renderGlobalSettingsForm(updatedSettings, getGlobalSettingsEventHandlers());
    } catch (error) {
        ui.showToast(`Error saving settings: ${error.message}`, 'error');
        console.error('Error saving global settings:', error);
    } finally {
        ui.hideSpinner();
    }
}

/**
 * Handles saving (creating or updating) an MCP server.
 * @param {Event} event - The form submission event.
 * @param {number|null} serverId - The ID of the server, or null if new.
 */
export async function handleSaveMcpServer(event, serverId = null) {
    event.preventDefault();
    ui.showSpinner();
    const form = event.target;
    const data = {
        name: form.name.value,
        description: form.description.value,
        host: form.host.value,
        port: parseInt(form.port.value, 10),
        rpc_endpoint_path: form.rpc_endpoint_path.value,
        enabled: form.enabled.checked
    };

    try {
        await api.saveMcpServer(data, serverId);
        ui.hideModal();
        ui.showToast(`MCP server ${serverId ? 'updated' : 'created'} successfully!`);
        const settings = await api.fetchGlobalSettings();
        if (settings) {
            await ui.renderGlobalSettingsForm(settings, getGlobalSettingsEventHandlers());
        }
    } catch (error) {
        ui.showToast(`Error: ${error.message}`, 'error');
    } finally {
        ui.hideSpinner();
    }
}

/**
 * Handles deleting an MCP server.
 * @param {number} serverId - The ID of the server to delete.
 */
export async function handleDeleteMcpServer(serverId) {
    if (!confirm('Are you sure you want to delete this MCP server? This cannot be undone.')) return;
    ui.showSpinner();
    try {
        await api.deleteMcpServer(serverId);
        ui.showToast('MCP server deleted successfully!');
        const settings = await api.fetchGlobalSettings();
        if (settings) {
            await ui.renderGlobalSettingsForm(settings, getGlobalSettingsEventHandlers());
        }
    } catch (error) {
        ui.showToast(`Error: ${error.message}`, 'error');
    } finally {
        ui.hideSpinner();
    }
}

/**
 * Handles file uploads.
 * @param {number} botId - The ID of the bot.
 * @param {File} file - The file object.
 * @param {string} ownerId - The owner's Discord ID.
 */
export async function handleUploadFile(botId, file, ownerId) {
    ui.showSpinner();
    try {
        await api.uploadFile(botId, file, ownerId);
        ui.showToast('File uploaded successfully!');
        const bot = await api.fetchBotDetails(botId);
        if (bot) {
            const eventHandlers = getBotViewEventHandlers();
            await ui.renderTabContent(bot, 'files', handleConnectToLogStream, eventHandlers.saveBotSettings, eventHandlers.fileHandlers, eventHandlers.testChat);
        }
    } catch (error) {
        ui.showToast(`Error uploading file: ${error.message}`, 'error');
    } finally {
        ui.hideSpinner();
    }
}

/**
 * Handles file deletion.
 * @param {string} uuid - The UUID of the file.
 * @param {number} botId - The bot ID for context after deletion.
 */
export async function handleDeleteFile(uuid, botId) {
    ui.showSpinner();
    try {
        await api.deleteFile(uuid);
        ui.showToast('File deleted successfully!');
        const bot = await api.fetchBotDetails(botId);
        if (bot) {
            const eventHandlers = getBotViewEventHandlers();
            await ui.renderTabContent(bot, 'files', handleConnectToLogStream, eventHandlers.saveBotSettings, eventHandlers.fileHandlers, eventHandlers.testChat);
        }
    } catch (error) {
        ui.showToast(`Error deleting file: ${error.message}`, 'error');
    } finally {
        ui.hideSpinner();
    }
}

/**
 * Handles the deletion of a single bot memory entry.
 * @param {string} botId - The ID of the bot owning the memory.
 * @param {string} memoryId - The unique ID of the memory entry to delete.
 */
export async function handleDeleteMemoryEntry(botId, memoryId) {
    if (!confirm('Are you sure you want to permanently delete this memory entry?')) {
        return;
    }
    ui.showSpinner();
    try {
        await api.deleteBotMemoryEntry(botId, memoryId);
        ui.showToast('Memory entry deleted successfully!');
        const row = document.querySelector(`tr[data-memory-id="${memoryId}"]`);
        if (row) {
            row.remove();
        }
    } catch (error) {
        ui.showToast(`Error deleting memory entry: ${error.message}`, 'error');
    } finally {
        ui.hideSpinner();
    }
}


// --- CHAT & STREAMING HANDLERS ---

/**
 * Helper to handle the EventSource streaming for bot responses.
 * @param {string} streamUrl - The relative URL to stream events from.
 * @param {HTMLElement} targetElement - The DOM element to append text to.
 * @param {object} uiControls - Objects to re-enable on finish { input, button }.
 */
function streamBotResponse(streamUrl, targetElement, uiControls) {
    const source = new EventSource(streamUrl);

    source.onmessage = (event) => {
        try {
            // Attempt to parse the JSON chunk
            const parsedData = JSON.parse(event.data);
            // If valid JSON and has content, use it. Otherwise fallback.
            const textContent = parsedData.content || event.data;

            if (textContent) {
                // Replace newlines with <br> for basic readability
                const formattedChunk = textContent.replace(/\n/g, '<br>');
                targetElement.insertAdjacentHTML('beforeend', formattedChunk);

                // Scroll to bottom
                if (targetElement.parentElement) {
                    targetElement.parentElement.scrollTop = targetElement.parentElement.scrollHeight;
                }
            }
        } catch (e) {
            // Fallback for non-JSON strings (e.g. simple text)
            // Or log warning if expected format is strictly JSON
            const formattedChunk = event.data.replace(/\n/g, '<br>');
            targetElement.insertAdjacentHTML('beforeend', formattedChunk);
        }
    };

    // Browsers fire 'error' when the connection is closed by the server (which FastAPI does on finish)
    source.onerror = (event) => {
        source.close();
        if (uiControls.input) uiControls.input.disabled = false;
        if (uiControls.button) {
            uiControls.button.disabled = false;
            uiControls.button.textContent = 'Send';
        }
        if (uiControls.input) uiControls.input.focus();
    };
}


/**
 * Handles the submission of a message from the test chat interface.
 * REWRITTEN to support the new Orchestrator response types (Stop, Clarify, Ack+Plan+Stream).
 * @param {number} botId - The ID of the bot to chat with.
 * @param {string} message - The message from the user.
 */
export async function handleTestChatSubmit(botId, message) {
    const messagesContainer = document.getElementById('test-chat-messages');
    const form = document.getElementById('test-chat-form');
    const input = document.getElementById('test-chat-input');
    const submitButton = form.querySelector('button');

    input.disabled = true;
    submitButton.disabled = true;
    submitButton.textContent = '...';

    try {
        // 1. Send the message. Expects a JSON object back (ProcessMessageResponse).
        const response = await api.sendTestChatMessage(botId, message);

        // 2. Determine Response Type

        // CASE A: StopResponse (Gatekeeper blocked it)
        if (response.reason) {
            const errorDiv = document.createElement('div');
            errorDiv.className = 'bot-message error';
            errorDiv.innerHTML = `<p><strong>Blocked:</strong> ${response.reason}</p>`;
            messagesContainer.appendChild(errorDiv);

            // Re-enable UI immediately
            input.disabled = false;
            submitButton.disabled = false;
            submitButton.textContent = 'Send';
            return;
        }

        // CASE B: ClarifyResponse (Bot needs more info)
        if (response.message && !response.final_response_stream_url) {
            const botMessageDiv = document.createElement('div');
            botMessageDiv.className = 'bot-message';
            botMessageDiv.innerHTML = `<p>${response.message}</p>`;
            messagesContainer.appendChild(botMessageDiv);

            // Re-enable UI immediately
            input.disabled = false;
            submitButton.disabled = false;
            submitButton.textContent = 'Send';
            return;
        }

        // CASE C: Streamable Response (Synthesize OR AcknowledgeAndExecute)
        const botMessageDiv = document.createElement('div');
        botMessageDiv.className = 'bot-message';
        messagesContainer.appendChild(botMessageDiv);

        // If tools are used, show the Acknowledgement
        if (response.acknowledgement_message) {
            const ackP = document.createElement('p');
            ackP.style.fontStyle = 'italic';
            ackP.style.color = '#8b949e';
            ackP.style.marginBottom = '0.5rem';
            ackP.textContent = `🤖 ${response.acknowledgement_message}`;
            botMessageDiv.appendChild(ackP);
        }

        // If a plan exists, visualize it briefly
        if (response.plan && response.plan.plan) {
            const planDiv = document.createElement('div');
            planDiv.style.fontSize = '0.85em';
            planDiv.style.backgroundColor = 'rgba(0,0,0,0.2)';
            planDiv.style.padding = '5px';
            planDiv.style.borderRadius = '4px';
            planDiv.style.marginBottom = '0.5rem';

            const stepsCount = response.plan.plan.length;
            const toolsNames = response.plan.plan.map(s => s.tool_name).join(', ');
            planDiv.innerHTML = `<strong>Executing Plan (${stepsCount} steps):</strong> ${toolsNames}`;
            botMessageDiv.appendChild(planDiv);
        }

        // Create container for the final streamed text
        const contentDiv = document.createElement('div');
        contentDiv.className = 'streamed-content';
        botMessageDiv.appendChild(contentDiv);

        // Start Streaming
        if (response.final_response_stream_url) {
            streamBotResponse(response.final_response_stream_url, contentDiv, { input, button: submitButton });
        } else {
            // Fallback if URL is missing
            contentDiv.textContent = "(No response stream URL provided)";
            input.disabled = false;
            submitButton.disabled = false;
            submitButton.textContent = 'Send';
        }

    } catch (error) {
        ui.showToast(`Error in test chat: ${error.message}`, 'error');
        const errorDiv = document.createElement('div');
        errorDiv.className = 'bot-message error';
        errorDiv.innerHTML = `<p>Error: ${error.message}</p>`;
        messagesContainer.appendChild(errorDiv);

        input.disabled = false;
        submitButton.disabled = false;
        submitButton.textContent = 'Send';
    } finally {
        messagesContainer.scrollTop = messagesContainer.scrollHeight;
    }
}


// --- USER KNOWLEDGE BASE EVENT HANDLERS ---

/**
 * Loads the initial list of users for the bot's knowledge base tab.
 * @param {number} botId - The ID of the bot.
 */
export async function handleLoadBotKnowledgeBase(botId) {
    ui.showSpinner();
    try {
        const users = await api.fetchUsersForBot(botId);
        ui.renderUserList(users, getUserKbEventHandlers(botId));
    } catch (error) {
        ui.showToast(error.message, 'error');
        document.getElementById('user-kb-results-container').innerHTML = `<p class="error">${error.message}</p>`;
    } finally {
        ui.hideSpinner();
    }
}

/**
 * Handles searching for a user within a specific bot's knowledge base.
 * @param {number} botId - The ID of the bot.
 * @param {string} query - The search query (ID or name).
 */
export async function handleUserSearch(botId, query) {
    ui.showSpinner();
    try {
        const userDetailsList = await api.searchUser(botId, query);
        ui.renderUserList(userDetailsList, getUserKbEventHandlers(botId));
    } catch (error) {
        ui.showToast(error.message, 'error');
        document.getElementById('user-kb-results-container').innerHTML = `<p class="error">${error.message}</p>`;
    } finally {
        ui.hideSpinner();
    }
}

/**
 * Fetches a single user's full details and renders the detail view.
 * @param {number} botId - The ID of the bot.
 * @param {string} userId - The Discord ID of the user to display.
 */
async function handleShowUserDetails(botId, userId) {
    ui.showSpinner();
    try {
        // The searchUser API is used to get the full profile with notes
        const userDetailsList = await api.searchUser(botId, userId);
        if (userDetailsList && userDetailsList.length > 0) {
            const userDetail = userDetailsList[0];
            ui.renderUserDetailView(userDetail, getUserKbEventHandlers(botId));
        } else {
            throw new Error(`User with ID ${userId} not found.`);
        }
    } catch (error) {
        ui.showToast(error.message, 'error');
        // Fallback to the main list if a user can't be loaded
        await handleLoadBotKnowledgeBase(botId);
    } finally {
        ui.hideSpinner();
    }
}

/**
 * Handles saving a user's updated profile for a specific bot context.
 * @param {number} botId - The ID of the bot for this profile.
 * @param {number} serverId - The ID of the server for this profile.
 * @param {number} userId - The user's Discord ID.
 */
export async function handleSaveUserProfile(botId, serverId, userId) {
    const textarea = document.getElementById(`user-profile-prompt-${botId}`);
    if (!textarea) return;

    ui.showSpinner();
    try {
        const profileData = { behavioral_instructions: textarea.value };
        await api.updateUserProfile(botId, serverId, userId, profileData);
        ui.showToast('User profile saved successfully!');
    } catch (error) {
        ui.showToast(`Error saving profile: ${error.message}`, 'error');
    } finally {
        ui.hideSpinner();
    }
}

/**
 * Handles deleting a user's note.
 * @param {number} noteId - The ID of the note to delete.
 */
export async function handleDeleteUserNote(noteId) {
    if (!confirm('Are you sure you want to delete this note?')) return;
    ui.showSpinner();
    try {
        await api.deleteUserNote(noteId);
        ui.showToast('Note deleted successfully!');
        const row = document.querySelector(`.user-notes-table tr[data-note-id="${noteId}"]`);
        if (row) row.remove();
    } catch (error) {
        ui.showToast(`Error deleting note: ${error.message}`, 'error');
    } finally {
        ui.hideSpinner();
    }
}

// --- NEW: LLM Evaluation Event Handler ---
/**
 * Handles the click on an "Evaluate" button for an LLM configuration.
 * @param {Event} event - The click event.
 */
async function handleEvaluateLlm(event) {
    const button = event.target;
    // --- MODIFICATION START ---
    const { category, serverFieldId, modelFieldId, contextFieldId } = button.dataset;

    const serverInput = document.getElementById(serverFieldId);
    const modelSelect = document.getElementById(modelFieldId);
    const contextInput = document.getElementById(contextFieldId);

    if (!serverInput || !modelSelect || !contextInput) {
        console.error("Could not find server, model, or context input fields for evaluation.");
        ui.showToast("UI error: could not find configuration fields.", "error");
        return;
    }

    const serverUrl = serverInput.value;
    const modelName = modelSelect.value;
    const contextWindow = contextInput.value ? parseInt(contextInput.value, 10) : null;
    // --- MODIFICATION END ---

    if (!serverUrl || !modelName) {
        ui.showToast("Please select a server URL and a model name before evaluating.", "warning");
        return;
    }

    ui.showSpinner();
    try {
        // --- MODIFICATION START ---
        const evaluationData = {
            llm_category: category,
            llm_server_url: serverUrl,
            llm_model_name: modelName,
            llm_context_window: contextWindow,
        };
        // --- MODIFICATION END ---

        const result = await api.startLLMEvaluation(evaluationData);
        ui.showToast(`Evaluation for model '${modelName}' started. Task ID: ${result.task_id}`, 'info');
        // Here we could potentially open a new view to monitor the task progress.

    } catch (error) {
        ui.showToast(`Error starting evaluation: ${error.message}`, 'error');
        console.error("Evaluation start error:", error);
    } finally {
        ui.hideSpinner();
    }
}


// --- EVENT HANDLER GETTERS ---

export function getSidebarEventHandlers() {
    return {
        createBot: handleCreateBot,
    };
}

export function getGlobalSettingsEventHandlers() {
    return {
        saveGlobalSettings: handleSaveGlobalSettings,
        saveMcpServer: handleSaveMcpServer,
        deleteMcpServer: handleDeleteMcpServer,
        // NEW: Add the evaluation handler
        evaluateLlm: handleEvaluateLlm
    };
}

export function getBotViewEventHandlers() {
    return {
        saveBotSettings: handleSaveBotSettings,
        fileHandlers: {
            uploadFile: handleUploadFile,
            deleteFile: handleDeleteFile
        },
        testChat: handleTestChatSubmit,
        kbHandlers: {
            loadKb: handleLoadBotKnowledgeBase,
            searchUser: handleUserSearch,
            saveProfile: handleSaveUserProfile,
            deleteNote: handleDeleteUserNote
        },
        // NEW: Add the evaluation handler
        evaluateLlm: handleEvaluateLlm,
        // NEW: Add the channel permission handler
        updateChannelPermission: handleUpdateChannelPermission
    };
}

export function getUserKbEventHandlers(botId) {
    return {
        loadKb: () => handleLoadBotKnowledgeBase(botId),
        handleUserSearch: (query) => handleUserSearch(botId, query),
        handleSaveUserProfile: handleSaveUserProfile,
        handleDeleteUserNote: handleDeleteUserNote,
        handleUserSelect: (userId) => handleShowUserDetails(botId, userId)
    };
}