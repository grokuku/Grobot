// frontend/src/ui.js
import { fetchBots, fetchModels, fetchMcpServers, searchFilesForBot, fetchMcpServerSchema, fetchBotMemory, fetchMcpServerTools } from './api.js';
import { handleDeleteMemoryEntry } from './events.js';

const DEFAULT_CONTEXT_PROMPT = `[IF context_type == "DIRECT_MESSAGE"]
You are in a private conversation with the user '{user_display_name}' (username: @{user_name}).
[/IF][IF context_type == "SERVER_CHANNEL"]
This conversation is in the server '{server_name}', in the channel '#{channel_name}'.
The latest message is from '{user_display_name}' (username: @{user_name}).
[/IF][IF channel_is_thread == True]
This conversation is in a thread titled '{thread_name}'.
[/IF]`;

const DEFAULT_TOOLS_PROMPT = `You have access to a set of tools you can use to answer the user's question.
You must call tools by producing a JSON object with a \`tool_calls\` field.
The \`tool_calls\` field must be a list of objects, where each object has a \`function\` field.
The \`function\` object must have a \`name\` and an \`arguments\` field. The \`arguments\` field must be a JSON object with the arguments to the function.
If you need to call a tool, you must stop generating text and produce the JSON object.
If you don't need to call a tool, you must answer the user's question directly.`;


// --- TOAST & SPINNER UTILS ---

export function showToast(message, type = 'success') {
    const toast = document.createElement('div');
    toast.className = `toast toast-${type}`;
    toast.textContent = message;
    document.body.appendChild(toast);
    setTimeout(() => {
        toast.classList.add('show');
    }, 10);
    setTimeout(() => {
        toast.classList.remove('show');
        setTimeout(() => {
            document.body.removeChild(toast);
        }, 500);
    }, 5000);
}

export function showSpinner() {
    document.getElementById('spinner').style.display = 'block';
}

export function hideSpinner() {
    document.getElementById('spinner').style.display = 'none';
}

// --- MODAL UTILS ---

export function hideModal() {
    const modal = document.querySelector('.modal');
    if (modal) {
        modal.parentElement.removeChild(modal);
    }
}

// --- THEME MANAGEMENT ---

export function applyTheme(theme, color) {
    if (theme === 'dark') {
        document.body.classList.add('dark-mode');
    } else {
        document.body.classList.remove('dark-mode');
    }
    document.body.setAttribute('data-color', color);
    localStorage.setItem('theme', theme);
    localStorage.setItem('color', color);
}

export function renderThemeControls() {
    const container = document.getElementById('theme-controls-container');
    if (!container) return;

    const currentTheme = localStorage.getItem('theme') || 'dark';
    const currentColor = localStorage.getItem('color') || 'blue';

    const themeToggleBtn = document.createElement('button');
    themeToggleBtn.id = 'theme-toggle-btn';
    themeToggleBtn.className = 'theme-toggle-btn';
    themeToggleBtn.title = "Toggle Light/Dark Mode";
    themeToggleBtn.innerHTML = `
        <svg width="16" height="16" viewBox="0 0 16 16" fill="currentColor">
            <path d="M6 .278a.768.768 0 0 1 .08.858 7.208 7.208 0 0 0-.878 3.46c0 4.021 3.278 7.277 7.318 7.277.527 0 1.04-.055 1.533-.16a.787.787 0 0 1 .81.316.733.733 0 0 1-.031.893A8.349 8.349 0 0 1 8.344 16C3.734 16 0 12.286 0 7.71 0 4.266 2.114 1.312 5.124.06A.752.752 0 0 1 6 .278Z"/>
            <path d="M10.794 3.148a.217.217 0 0 1 .412 0l.387 1.162c.173.518.579.924 1.097 1.097l1.162.387a.217.217 0 0 1 0 .412l-1.162.387a1.734 1.734 0 0 0-1.097 1.097l-.387 1.162a.217.217 0 0 1-.412 0l-.387-1.162A1.734 1.734 0 0 0 9.31 6.593l-1.162-.387a.217.217 0 0 1 0 .412l1.162-.387a1.734 1.734 0 0 0 1.097-1.097l.387-1.162ZM13.863.099a.145.145 0 0 1 .274 0l.258.774c.115.346.386.617.732.732l.774.258a.145.145 0 0 1 0 .274l-.774.258a1.156 1.156 0 0 0-.732.732l-.258.774a.145.145 0 0 1-.274 0l-.258-.774a1.156 1.156 0 0 0-.732-.732l-.774-.258a.145.145 0 0 1 0 .274l.774.258c.346-.115.617-.386.732-.732L13.863.1z"/>
        </svg>`;
    themeToggleBtn.addEventListener('click', () => {
        const newTheme = document.body.classList.contains('dark-mode') ? 'light' : 'dark';
        applyTheme(newTheme, localStorage.getItem('color') || 'blue');
    });

    const colorPalette = document.createElement('div');
    colorPalette.className = 'color-palette';
    const colors = ['grey', 'blue', 'green', 'purple', 'red', 'orange'];
    colors.forEach(color => {
        const colorOption = document.createElement('div');
        colorOption.className = `color-option ${color === currentColor ? 'active' : ''}`;
        if (color === 'grey') colorOption.style.backgroundColor = '#8b949e';
        else if (color === 'blue') colorOption.style.backgroundColor = '#0969da';
        else if (color === 'green') colorOption.style.backgroundColor = '#1a7f37';
        else if (color === 'purple') colorOption.style.backgroundColor = '#8250df';
        else if (color === 'red') colorOption.style.backgroundColor = '#da3633';
        else if (color === 'orange') colorOption.style.backgroundColor = '#fb8500';

        colorOption.dataset.color = color;
        colorOption.title = color;
        colorOption.addEventListener('click', () => {
            applyTheme(localStorage.getItem('theme') || 'dark', color);
            renderThemeControls();
        });
        colorPalette.appendChild(colorOption);
    });

    container.innerHTML = '';
    container.appendChild(themeToggleBtn);
    container.appendChild(colorPalette);
}


// --- DOM RENDERING ---

export async function refreshBotsList(botsList, selectBotCallback) {
    try {
        const bots = await fetchBots();
        botsList.length = 0;
        Array.prototype.push.apply(botsList, bots);
        renderSidebar(botsList, selectBotCallback);
    } catch (error) {
        console.error('Error fetching bots:', error);
        showToast(`Error fetching bots: ${error.message}`, 'error');
    }
}

export function renderSidebar(bots, selectBotCallback) {
    const sidebarList = document.getElementById('sidebar-bots-list');
    if (!sidebarList) return;
    sidebarList.innerHTML = '';

    bots.forEach(bot => {
        const botElement = document.createElement('div');
        botElement.className = 'sidebar-bot-item';
        botElement.dataset.botId = bot.id;
        botElement.innerHTML = `
            <span class="bot-status ${bot.is_active ? 'online' : 'offline'}"></span>
            <span class="bot-name">${bot.name}</span>
        `;
        sidebarList.appendChild(botElement);
    });

    document.querySelectorAll('.sidebar-bot-item').forEach(item => {
        item.addEventListener('click', async (e) => {
            const botId = e.currentTarget.dataset.botId;
            await selectBotCallback(botId);
        });
    });
}

export async function renderMainContent(bot, activeTab, tabChangeCallback, logConnectCallback, settingsFormCallback, filesViewCallback, testChatCallback, kbCallback) {
    const mainContent = document.getElementById('main-content');
    mainContent.innerHTML = `
        <header id="chat-header">
            <div id="chat-header-title">
                <h3>${bot.name}</h3>
            </div>
            <div id="theme-controls-container"></div>
        </header>
        <div id="central-panel-content">
                <div class="tab-container">
                <div class="tabs">
                    <button class="tab-link ${activeTab === 'test-chat' ? 'active' : ''}" data-tab="test-chat" data-bot-id="${bot.id}">Test Chat</button>
                    <button class="tab-link ${activeTab === 'logs' ? 'active' : ''}" data-tab="logs" data-bot-id="${bot.id}">Logs</button>
                    <button class="tab-link ${activeTab === 'settings' ? 'active' : ''}" data-tab="settings" data-bot-id="${bot.id}">Settings</button>
                    <button class="tab-link ${activeTab === 'files' ? 'active' : ''}" data-tab="files" data-bot-id="${bot.id}">Files</button>
                    <button class="tab-link ${activeTab === 'memory' ? 'active' : ''}" data-tab="memory" data-bot-id="${bot.id}">Memory</button>
                    <button class="tab-link ${activeTab === 'knowledge-base' ? 'active' : ''}" data-tab="knowledge-base" data-bot-id="${bot.id}">Knowledge Base</button>
                </div>
                <div id="tab-content" class="tab-content"></div>
            </div>
        </div>
    `;

    renderThemeControls();
    await renderTabContent(bot, activeTab, logConnectCallback, settingsFormCallback, filesViewCallback, testChatCallback, kbCallback);

    mainContent.querySelectorAll('.tab-link').forEach(button => {
        button.addEventListener('click', async (e) => {
            const tabName = e.target.dataset.tab;
            history.pushState({ botId: bot.id, tab: tabName }, '', `#bot=${bot.id}&tab=${tabName}`);
            await tabChangeCallback(bot, tabName);
        });
    });
}

export async function renderTabContent(bot, tabName, logConnectCallback, settingsFormCallback, filesViewCallback, testChatCallback, kbCallback) {
    const tabContent = document.getElementById('tab-content');
    if (!tabContent) return;

    document.querySelectorAll('.sidebar-bot-item.selected')?.forEach(el => el.classList.remove('selected'));
    const botItem = document.querySelector(`.sidebar-bot-item[data-bot-id='${bot.id}']`);
    if (botItem) botItem.classList.add('selected');

    document.querySelectorAll('.tab-link').forEach(b => b.classList.remove('active'));
    document.querySelector(`.tab-link[data-tab='${tabName}']`)?.classList.add('active');

    if (window.logStreamConnection) {
        window.logStreamConnection.close();
        window.logStreamConnection = null;
    }

    switch (tabName) {
        case 'logs':
            tabContent.innerHTML = `<div id="logs-container" style="height:100%;"><pre>Connecting to log stream...</pre></div>`;
            logConnectCallback(bot.id);
            break;
        case 'settings':
            await renderBotSettingsForm(bot, tabContent, settingsFormCallback);
            break;
        case 'files':
            renderFilesView(bot, tabContent, filesViewCallback);
            break;
        case 'test-chat':
            renderTestChatView(bot, tabContent, testChatCallback);
            break;
        case 'memory':
            await renderBotMemoryView(bot, tabContent);
            break;
        case 'knowledge-base':
            renderBotKnowledgeBaseView(bot, tabContent, kbCallback);
            break;
    }
}

export function populateModelDropdown(selectId, selectedValue, availableModels, forceRefresh = false, ollamaUrl = null) {
    const select = document.getElementById(selectId);
    if (!select) return;

    const populate = () => {
        select.innerHTML = '';
        if (availableModels.length === 0) {
            select.innerHTML = '<option value="">No models found</option>';
        } else {
            const blankOption = document.createElement('option');
            blankOption.value = "";
            blankOption.textContent = "(Use Global Default)";
            select.appendChild(blankOption);

            availableModels.forEach(model => {
                const option = document.createElement('option');
                option.value = model;
                option.textContent = model;
                if (model === selectedValue) {
                    option.selected = true;
                }
                select.appendChild(option);
            });
        }
    };

    if (forceRefresh) {
        showSpinner();
        fetchModels(ollamaUrl)
            .then(models => {
                availableModels.length = 0;
                Array.prototype.push.apply(availableModels, models);
                populate();
                showToast("LLM models list refreshed.", "success");
            })
            .catch(error => {
                console.error("Error refreshing models:", error);
                showToast(error.message, "error");
            })
            .finally(hideSpinner);
    } else {
        populate();
    }
}

// --- Bot Settings Sub-Tab Renderers ---

function renderBotSettingsGeneralTab(bot, draftBot, container) {
    container.innerHTML = `
        <fieldset>
            <legend>General</legend>
            <label for="bot-name">Bot Name</label>
            <input type="text" id="bot-name" name="name" value="${bot.name}" required>
            <label for="discord-token">Discord Token</label>
            <input type="password" id="discord-token" name="discord_token" value="${bot.discord_token ? '********' : ''}" placeholder="Enter new token to change">
            <div class="form-actions">
                    <label for="bot-is-active" class="checkbox-label">
                    <div class="switch">
                        <input type="checkbox" id="bot-is-active" name="is_active" ${bot.is_active ? 'checked' : ''}>
                        <span class="slider round"></span>
                    </div>
                    <span>Bot Active</span>
                </label>
            </div>
        </fieldset>
        <fieldset>
            <legend>Behavior</legend>
            <div class="form-actions">
                <label for="bot-passive-listening" class="checkbox-label">
                    <div class="switch">
                        <input type="checkbox" id="bot-passive-listening" name="passive_listening_enabled" ${bot.passive_listening_enabled ? 'checked' : ''}>
                        <span class="slider round"></span>
                    </div>
                    <span>Enable Passive Listening</span>
                </label>
                <p class="form-help">If enabled, the bot will listen to all messages in a channel and decide for itself when to respond, even if not directly mentioned. Requires the 'Message Content' privileged intent.</p>
            </div>
        </fieldset>
    `;

    container.querySelector('#bot-name').addEventListener('input', (e) => draftBot.name = e.target.value);
    container.querySelector('#discord-token').addEventListener('input', (e) => draftBot.discord_token = e.target.value);
    container.querySelector('#bot-is-active').addEventListener('change', (e) => draftBot.is_active = e.target.checked);
    container.querySelector('#bot-passive-listening').addEventListener('change', (e) => draftBot.passive_listening_enabled = e.target.checked);
}

function renderBotSettingsLlmTab(bot, draftBot, container) {
    container.innerHTML = `
        <fieldset>
            <legend>LLM Configuration</legend>
            <label for="bot-llm-model">LLM Model</label>
            <p class="form-help">Leave blank to use the global default model.</p>
            <div class="model-select-container">
                <select id="bot-llm-model" name="llm_model"></select>
                <button type="button" id="refresh-models-btn-bot" class="refresh-btn icon-btn">⟳</button>
            </div>
        </fieldset>
    `;
    populateModelDropdown('bot-llm-model', bot.llm_model, window.availableModels);
    container.querySelector('#bot-llm-model').addEventListener('change', (e) => draftBot.llm_model = e.target.value);
    document.getElementById('refresh-models-btn-bot').addEventListener('click', () => populateModelDropdown('bot-llm-model', document.getElementById('bot-llm-model').value, window.availableModels, true, null));
}

function renderBotSettingsPersonalityTab(bot, draftBot, container) {
    container.innerHTML = `
            <fieldset>
            <legend>Personality and Behavior</legend>
            <label for="system-prompt">Main System Prompt</label>
            <textarea id="system-prompt" name="system_prompt" rows="12">${bot.system_prompt || ''}</textarea>
        </fieldset>
    `;
    container.querySelector('#system-prompt').addEventListener('input', (e) => draftBot.system_prompt = e.target.value);
}

async function renderBotSettingsToolsTab(bot, draftBot, container) {
    container.innerHTML = '<p>Loading tool servers...</p>';
    try {
        const botServerConfigMap = new Map();
        if (draftBot.mcp_servers) {
            draftBot.mcp_servers.forEach(s => {
                botServerConfigMap.set(s.id, s.configuration || {});
            });
        }
        const allServers = await fetchMcpServers();
        if (allServers.length === 0) {
            container.innerHTML = '<p>No MCP servers have been registered in Global Settings.</p>';
            return;
        }
        container.innerHTML = '';
        const toolsList = document.createElement('div');
        toolsList.className = 'tools-list-container';
        container.appendChild(toolsList);
        allServers.forEach(server => {
            if (!server.enabled) return;
            const isEnabledForBot = botServerConfigMap.has(server.id);
            const itemContainer = document.createElement('div');
            itemContainer.className = 'tool-item';
            const textDiv = document.createElement('div');
            textDiv.className = 'tool-item-text';
            textDiv.innerHTML = `<span class="tool-name">${server.name}</span><p class="form-help">${server.description || 'No description'}</p>`;
            const controlsDiv = document.createElement('div');
            controlsDiv.className = 'tool-item-controls';
            const configButton = document.createElement('button');
            configButton.type = 'button';
            configButton.className = 'secondary-button configure-mcp-btn';
            configButton.innerHTML = 'Configure';
            configButton.disabled = !isEnabledForBot;
            const switchLabel = document.createElement('label');
            switchLabel.className = 'switch';
            const checkbox = document.createElement('input');
            checkbox.type = 'checkbox';
            checkbox.dataset.serverId = server.id;
            checkbox.checked = isEnabledForBot;
            const slider = document.createElement('span');
            slider.className = 'slider round';
            switchLabel.append(checkbox, slider);
            controlsDiv.append(configButton, switchLabel);
            itemContainer.append(textDiv, controlsDiv);
            toolsList.appendChild(itemContainer);
            checkbox.addEventListener('change', (e) => {
                configButton.disabled = !e.target.checked;
                const serverId = parseInt(e.target.dataset.serverId, 10);
                const isChecked = e.target.checked;
                if (!draftBot.mcp_servers) draftBot.mcp_servers = [];
                const serverIndex = draftBot.mcp_servers.findIndex(s => s.id === serverId);
                if (isChecked && serverIndex === -1) {
                    draftBot.mcp_servers.push({ ...server, configuration: {} });
                } else if (!isChecked && serverIndex > -1) {
                    draftBot.mcp_servers.splice(serverIndex, 1);
                }
            });
            configButton.addEventListener('click', () => {
                const serverConfig = draftBot.mcp_servers.find(s => s.id === server.id);
                const updateCallback = (newConfig) => {
                    if (serverConfig) {
                        serverConfig.configuration = newConfig;
                        showToast(`Configuration for ${server.name} updated locally.`, 'success');
                    }
                };
                showMcpConfigModal(server, serverConfig.configuration, updateCallback);
            });
        });
    } catch (error) {
        container.innerHTML = `<p class="error">Could not load MCP tool servers: ${error.message}</p>`;
    }
}

export async function renderBotSettingsForm(bot, container, saveHandler) {
    let draftBot = JSON.parse(JSON.stringify(bot));
    if (draftBot.mcp_servers === null) draftBot.mcp_servers = [];
    container.innerHTML = `
        <form id="bot-settings-form" class="bot-settings-form">
            <div class="sub-tabs">
                <button type="button" class="sub-tab-link active" data-tab="general">General</button>
                <button type="button" class="sub-tab-link" data-tab="llm">LLM</button>
                <button type="button" class="sub-tab-link" data-tab="personality">Personality</button>
                <button type="button" class="sub-tab-link" data-tab="tools">Tools</button>
            </div>
            <div id="settings-sub-tab-content" class="sub-tab-content"></div>
            <button type="submit" class="primary-button" style="margin-top: 1.5rem;">Save Bot Configuration</button>
        </form>
    `;
    const form = container.querySelector('#bot-settings-form');
    const subTabContent = container.querySelector('#settings-sub-tab-content');
    const renderers = {
        general: renderBotSettingsGeneralTab,
        llm: renderBotSettingsLlmTab,
        personality: renderBotSettingsPersonalityTab,
        tools: renderBotSettingsToolsTab
    };
    await renderers.general(bot, draftBot, subTabContent);
    container.querySelectorAll('.sub-tab-link').forEach(button => {
        button.addEventListener('click', async (e) => {
            const tabName = e.target.dataset.tab;
            container.querySelectorAll('.sub-tab-link').forEach(btn => btn.classList.remove('active'));
            e.target.classList.add('active');
            subTabContent.innerHTML = 'Loading...';
            if (renderers[tabName]) {
                await renderers[tabName](bot, draftBot, subTabContent);
            }
        });
    });
    form.addEventListener('submit', (e) => {
        e.preventDefault();
        saveHandler(bot.id, draftBot);
    });
}

export async function renderGlobalSettingsForm(settings, eventHandlers) {
    const mainContent = document.getElementById('main-content');
    mainContent.innerHTML = `
        <header id="chat-header">
            <div id="chat-header-title"><h3>Global Settings</h3></div>
            <div id="theme-controls-container"></div>
        </header>
        <div id="central-panel-content">
            <div class="settings-form-container">
                <form id="global-settings-form" class="bot-settings-form"></form>
            </div>
        </div>
    `;
    document.querySelectorAll('.sidebar-bot-item.selected')?.forEach(el => el.classList.remove('selected'));
    renderThemeControls();
    const form = document.getElementById('global-settings-form');
    form.innerHTML = `
        <fieldset>
            <legend>LLM Configuration</legend>
            <label for="ollama-host-url">Ollama Server URL</label>
            <input type="text" id="ollama-host-url" name="ollama_host_url" value="${settings.ollama_host_url || ''}">
            <label for="default-llm-model">Default LLM Model</label>
            <div class="model-select-container">
                <select id="default-llm-model" name="default_llm_model"></select>
                <button type="button" id="refresh-models-btn-global" class="refresh-btn icon-btn">⟳</button>
            </div>
        </fieldset>
        <fieldset>
            <legend>MCP Tool Servers</legend>
            <div id="mcp-servers-list-container">Loading servers...</div>
            <button type="button" id="add-mcp-server-btn" class="primary-button" style="margin-top: 1rem;">Register New MCP Server</button>
        </fieldset>
        <fieldset>
            <legend>Default System Prompts</legend>
            <div class="form-label-group"><label for="context-header-default-prompt">Default Context Prompt</label><button type="button" id="reset-context-prompt-btn" class="secondary-button small-button">Reset</button></div>
            <textarea id="context-header-default-prompt" name="context_header_default_prompt" rows="6">${settings.context_header_default_prompt || ''}</textarea>
            <div class="form-label-group" style="margin-top: 1rem;"><label for="tools-system-prompt">Tools System Prompt</label><button type="button" id="reset-tools-prompt-btn" class="secondary-button small-button">Reset</button></div>
            <p class="form-help">Instructions given to the LLM on how to call tools. Edit with caution.</p>
            <textarea id="tools-system-prompt" name="tools_system_prompt" rows="8">${settings.tools_system_prompt || ''}</textarea>
        </fieldset>
    `;
    const saveButton = document.createElement('button');
    saveButton.type = 'submit';
    saveButton.className = 'primary-button';
    saveButton.textContent = 'Save Changes';
    form.appendChild(saveButton);
    populateModelDropdown('default-llm-model', settings.default_llm_model, window.availableModels);
    const mcpContainer = document.getElementById('mcp-servers-list-container');
    try {
        const servers = await fetchMcpServers();
        if (servers.length === 0) {
            mcpContainer.innerHTML = '<p>No MCP servers registered yet.</p>';
        } else {
            mcpContainer.innerHTML = `<table class="files-table"><thead><tr><th>Name</th><th>Endpoint</th><th>Status</th><th>Actions</th></tr></thead><tbody>${servers.map(server => `<tr data-server-id="${server.id}"><td>${server.name}</td><td>${server.host}:${server.port}</td><td><span class="bot-status ${server.enabled ? 'online' : 'offline'}"></span> ${server.enabled ? 'Enabled' : 'Disabled'}</td><td class="actions-cell"><button class="icon-btn edit-mcp-btn" title="Edit Server">✏️</button><button class="icon-btn delete-mcp-btn" title="Delete Server">🗑️</button></td></tr>`).join('')}</tbody></table>`;
            mcpContainer.querySelectorAll('.edit-mcp-btn').forEach(b => b.addEventListener('click', e => showMcpServerModal(servers.find(s => s.id == e.target.closest('tr').dataset.serverId), eventHandlers.saveMcpServer)));
            mcpContainer.querySelectorAll('.delete-mcp-btn').forEach(b => b.addEventListener('click', e => eventHandlers.deleteMcpServer(e.target.closest('tr').dataset.serverId)));
        }
    } catch (error) {
        mcpContainer.innerHTML = '<p class="error">Could not load MCP servers.</p>';
    }
    document.getElementById('add-mcp-server-btn').addEventListener('click', () => showMcpServerModal(null, eventHandlers.saveMcpServer));
    document.getElementById('refresh-models-btn-global').addEventListener('click', () => {
        const ollamaUrl = document.getElementById('ollama-host-url').value;
        if (!ollamaUrl) return showToast("Please enter an Ollama Server URL.", "error");
        populateModelDropdown('default-llm-model', document.getElementById('default-llm-model').value, window.availableModels, true, ollamaUrl);
    });
    document.getElementById('reset-context-prompt-btn').addEventListener('click', () => {
        document.getElementById('context-header-default-prompt').value = DEFAULT_CONTEXT_PROMPT;
        showToast('Prompt has been reset. Click "Save Changes" to apply.');
    });
    document.getElementById('reset-tools-prompt-btn').addEventListener('click', () => {
        document.getElementById('tools-system-prompt').value = DEFAULT_TOOLS_PROMPT;
        showToast('Tools prompt has been reset. Click "Save Changes" to apply.');
    });
    form.addEventListener('submit', eventHandlers.saveGlobalSettings);
}

export function renderBotKnowledgeBaseView(bot, container, eventHandlers) {
    container.innerHTML = `
        <div class="user-kb-view">
            <div class="user-kb-search-container">
                <form id="user-search-form" data-bot-id="${bot.id}">
                    <input type="search" id="user-search-input" placeholder="Search users known to ${bot.name}..." required>
                    <button type="submit" class="primary-button">Search</button>
                </form>
            </div>
            <div id="user-kb-results-container">
                <p class="form-help">Loading known users...</p>
            </div>
        </div>
    `;
    eventHandlers.loadKb(bot.id);
    const form = container.querySelector('#user-search-form');
    const input = container.querySelector('#user-search-input');

    form.addEventListener('submit', (e) => {
        e.preventDefault();
        const query = input.value;
        if (query) {
            eventHandlers.searchUser(bot.id, query);
        }
    });

    // NOUVEAU: Ajout d'un écouteur pour réinitialiser la vue quand le champ est vidé.
    input.addEventListener('input', (e) => {
        if (e.target.value.trim() === '') {
            eventHandlers.loadKb(bot.id);
        }
    });
}

// MODIFIÉ: Amélioration de la robustesse et renommage pour la clarté.
// Cette fonction est maintenant le seul point d'entrée pour afficher une liste d'utilisateurs.
export function renderUserList(users, eventHandlers) {
    const resultsContainer = document.getElementById('user-kb-results-container');
    if (!resultsContainer) return;

    if (!users || users.length === 0) {
        resultsContainer.innerHTML = '<p>No users found in this bot\'s knowledge base yet.</p>';
        return;
    }

    const userListItems = users.map(user => {
        // Ajout de valeurs par défaut pour éviter l'affichage de "undefined"
        const displayName = user.display_name || 'Unnamed User';
        const username = user.username || 'unknown_user';
        const userId = user.discord_user_id;

        return `
        <li class="user-list-item" data-user-id="${userId}">
            <span class="user-name">${displayName}</span>
            <span class="text-muted">(@${username})</span>
        </li>
    `}).join('');

    resultsContainer.innerHTML = `
        <ul class="user-list">${userListItems}</ul>
    `;

    resultsContainer.querySelectorAll('.user-list-item').forEach(item => {
        item.addEventListener('click', (e) => {
            const userId = e.currentTarget.dataset.userId;
            if (eventHandlers.handleUserSelect) {
                eventHandlers.handleUserSelect(userId);
            } else {
                console.warn("handleUserSelect event handler is not defined.");
                showToast(`UI for user details is not yet implemented.`);
            }
        });
    });
}

// NOUVEAU: Fonction pour afficher la vue détaillée d'un profil utilisateur.
export function renderUserDetailView(userDetail, eventHandlers) {
    const resultsContainer = document.getElementById('user-kb-results-container');
    if (!resultsContainer) return;

    const displayName = userDetail.display_name || 'Unnamed User';
    const username = userDetail.username || 'unknown_user';

    const notesRows = userDetail.notes.map(note => `
        <tr data-note-id="${note.id}">
            <td><div class="note-content">${note.note_content}</div></td>
            <td>${note.reliability_score}</td>
            <td>${new Date(note.created_at).toLocaleString()}</td>
            <td class="actions-cell">
                <button class="icon-btn delete-user-note-btn" title="Delete Note" data-note-id="${note.id}">🗑️</button>
            </td>
        </tr>
    `).join('');

    resultsContainer.innerHTML = `
        <div class="user-detail-view">
            <div class="user-detail-header">
                <button type="button" class="secondary-button back-to-list-btn">&larr; Back to List</button>
                <h3>${displayName} <span class="text-muted">(@${username})</span></h3>
            </div>

            <form class="bot-settings-form" id="user-profile-form">
                <fieldset>
                    <legend>Behavioral Instructions</legend>
                    <p class="form-help">Specific instructions for the bot on how to interact with this user.</p>
                    <textarea id="user-profile-prompt-${userDetail.bot_id}" rows="6">${userDetail.behavioral_instructions || ''}</textarea>
                    <button type="button" class="primary-button save-user-profile-btn"
                            data-bot-id="${userDetail.bot_id}"
                            data-server-id="${userDetail.server_discord_id}"
                            data-user-id="${userDetail.discord_user_id}">
                        Save Profile
                    </button>
                </fieldset>

                <fieldset>
                    <legend>Factual Notes</legend>
                    <p class="form-help">Facts the bot has learned about the user. These can be added by the bot or manually.</p>
                    <table class="files-table user-notes-table">
                        <thead>
                            <tr>
                                <th>Note</th>
                                <th>Reliability</th>
                                <th>Created At</th>
                                <th>Actions</th>
                            </tr>
                        </thead>
                        <tbody>
                            ${notesRows || '<tr><td colspan="4">No notes for this user yet.</td></tr>'}
                        </tbody>
                    </table>
                </fieldset>
            </form>
        </div>
    `;

    // Attach event listeners
    resultsContainer.querySelector('.back-to-list-btn').addEventListener('click', () => {
        if (eventHandlers.loadKb) eventHandlers.loadKb(userDetail.bot_id);
    });

    resultsContainer.querySelector('.save-user-profile-btn').addEventListener('click', (e) => {
        const btn = e.currentTarget;
        if (eventHandlers.handleSaveUserProfile) {
            eventHandlers.handleSaveUserProfile(btn.dataset.botId, btn.dataset.serverId, btn.dataset.userId);
        }
    });

    resultsContainer.querySelectorAll('.delete-user-note-btn').forEach(button => {
        button.addEventListener('click', (e) => {
            if (eventHandlers.handleDeleteUserNote) {
                eventHandlers.handleDeleteUserNote(e.currentTarget.dataset.noteId);
            }
        });
    });
}


// SUPPRIMÉ: Cette fonction est obsolète car elle est basée sur l'ancienne structure de l'API (objet unique).
// La nouvelle API retourne une liste, qui doit être gérée par renderUserList.
/*
export function renderUserSearchResults(userDetails, eventHandlers) { ... }
*/

export function renderFilesView(bot, container, uploadHandler) {
    container.innerHTML = `
        <div class="files-header">
            <h3>Managed Files for ${bot.name}</h3>
            <button id="upload-file-btn" class="primary-button">Upload File</button>
        </div>
        <div id="files-table-container">Loading files...</div>
    `;
    loadAndRenderFiles(bot.id, uploadHandler.deleteFile);
    document.getElementById('upload-file-btn').addEventListener('click', () => showUploadModal(bot.id, uploadHandler.uploadFile));
}

export async function loadAndRenderFiles(botId, deleteHandler) {
    const container = document.getElementById('files-table-container');
    try {
        const files = await searchFilesForBot(botId);
        if (files.length === 0) {
            container.innerHTML = '<p>No files uploaded for this bot yet.</p>';
            return;
        }
        container.innerHTML = `<table class="files-table"><thead><tr><th>Filename</th><th>Type</th><th>Size</th><th>Owner</th><th>Uploaded At</th><th>Actions</th></tr></thead><tbody>${files.map(file => `<tr data-file-uuid="${file.uuid}"><td>${file.filename}</td><td>${file.file_type}</td><td>${(file.file_size_bytes / 1024).toFixed(2)} KB</td><td>${file.owner_discord_id}</td><td>${new Date(file.created_at).toLocaleString()}</td><td><button class="icon-btn delete-file-btn" title="Delete File">🗑️</button></td></tr>`).join('')}</tbody></table>`;
        container.querySelectorAll('.delete-file-btn').forEach(button => {
            button.addEventListener('click', async (e) => {
                const uuid = e.target.closest('tr').dataset.fileUuid;
                if (confirm('Are you sure you want to delete this file?')) {
                    await deleteHandler(uuid, botId);
                }
            });
        });
    } catch (error) {
        container.innerHTML = `<p class="error">Error loading files: ${error.message}</p>`;
    }
}

export function renderTestChatView(bot, container, submitHandler) {
    container.innerHTML = `
        <div class="test-chat-container">
            <div id="test-chat-messages" class="test-chat-messages">
                <div class="bot-message"><p>Hello! Send a message to start testing "${bot.name}".</p></div>
            </div>
            <form id="test-chat-form" class="test-chat-form">
                <input type="text" id="test-chat-input" placeholder="Type your message..." autocomplete="off">
                <button type="submit">Send</button>
            </form>
        </div>
    `;
    const form = document.getElementById('test-chat-form');
    form.addEventListener('submit', (e) => {
        e.preventDefault();
        const input = document.getElementById('test-chat-input');
        const message = input.value.trim();
        if (message) {
            const messagesContainer = document.getElementById('test-chat-messages');
            const userMessageDiv = document.createElement('div');
            userMessageDiv.className = 'user-message';
            userMessageDiv.innerHTML = `<p>${message}</p>`;
            messagesContainer.appendChild(userMessageDiv);
            messagesContainer.scrollTop = messagesContainer.scrollHeight;
            input.value = '';
            submitHandler(bot.id, message);
        }
    });
}

export async function renderBotMemoryView(bot, container) {
    container.innerHTML = `<div id="memory-table-container">Loading memory entries...</div>`;
    const tableContainer = document.getElementById('memory-table-container');
    try {
        const memoryData = await fetchBotMemory(bot.id);
        if (memoryData.count === 0) {
            tableContainer.innerHTML = `<p>No memory entries found for this bot.</p>`;
            return;
        }
        const tableRows = memoryData.items.map(item => `<tr data-memory-id="${item.id}"><td class="memory-id-cell">${item.id}</td><td><div class="memory-document-cell">${item.document.replace(/</g, "&lt;").replace(/>/g, "&gt;")}</div></td><td><pre class="memory-metadata-cell"><code>${JSON.stringify(item.metadata, null, 2)}</code></pre></td><td class="actions-cell"><button class="icon-btn delete-memory-btn" title="Delete Entry" data-bot-id="${bot.id}" data-memory-id="${item.id}">🗑️</button></td></tr>`).join('');
        tableContainer.innerHTML = `<table class="files-table memory-table"><thead><tr><th>ID</th><th>Document</th><th>Metadata</th><th>Actions</th></tr></thead><tbody>${tableRows}</tbody></table>`;
        tableContainer.querySelectorAll('.delete-memory-btn').forEach(button => {
            button.addEventListener('click', (e) => {
                const btn = e.currentTarget;
                handleDeleteMemoryEntry(btn.dataset.botId, btn.dataset.memoryId);
            });
        });
    } catch (error) {
        tableContainer.innerHTML = `<p class="error">Error loading bot memory: ${error.message}</p>`;
    }
}


// --- MODALS & DYNAMIC FORMS ---

function generateFormFromSchema(schema, currentData, container) {
    container.innerHTML = '';
    if (schema.description) {
        const desc = document.createElement('p');
        desc.className = 'form-help';
        desc.textContent = schema.description;
        container.appendChild(desc);
    }
    const properties = schema.properties || {};
    if (Object.keys(properties).length === 0) {
        container.innerHTML = '<p>This tool server has no configurable options.</p>';
        return;
    }
    for (const key in properties) {
        const prop = properties[key];
        const fieldContainer = document.createElement('div');
        fieldContainer.className = 'form-field';
        const label = document.createElement('label');
        label.htmlFor = `config-${key}`;
        label.textContent = prop.title || key;
        fieldContainer.appendChild(label);
        const currentValue = (currentData && currentData[key] !== undefined) ? currentData[key] : prop.default;
        let input;
        switch (prop.type) {
            case 'boolean':
                input = document.createElement('input');
                input.type = 'checkbox';
                input.checked = currentValue || false;
                const switchLabel = document.createElement('label');
                switchLabel.className = 'switch';
                const slider = document.createElement('span');
                slider.className = 'slider round';
                switchLabel.append(input, slider);
                fieldContainer.appendChild(switchLabel);
                break;
            case 'integer':
            case 'number':
                input = document.createElement('input');
                input.type = 'number';
                input.value = currentValue || '';
                fieldContainer.appendChild(input);
                break;
            case 'string':
            default:
                input = document.createElement('input');
                input.type = prop.format === 'password' ? 'password' : 'text';
                input.value = currentValue || '';
                fieldContainer.appendChild(input);
                break;
        }
        input.id = `config-${key}`;
        input.name = key;
        if (schema.required && schema.required.includes(key)) input.required = true;
        if (prop.description) {
            const propDesc = document.createElement('p');
            propDesc.className = 'form-help';
            propDesc.textContent = prop.description;
            fieldContainer.appendChild(propDesc);
        }
        container.appendChild(fieldContainer);
    }
}

async function showMcpConfigModal(server, currentConfig, saveCallback) {
    const modal = document.createElement('div');
    modal.className = 'modal';
    modal.innerHTML = `
        <div class="modal-content large">
            <span class="close-button">&times;</span>
            <h2>Configure: ${server.name}</h2>
            <form id="mcp-config-form" class="bot-settings-form">
                <fieldset>
                    <legend>Server-Side Configuration</legend>
                    <div id="server-config-container"><p>Loading config schema...</p></div>
                </fieldset>
                <fieldset>
                    <legend>Bot-Specific Tool Overrides</legend>
                    <p class="form-help">Configure bot behavior for specific tools. This does not affect other bots using this server.</p>
                    <div id="tool-overrides-container"><p>Loading tools...</p></div>
                </fieldset>
                <button type="submit" class="primary-button">Save Configuration</button>
            </form>
        </div>
    `;
    document.body.appendChild(modal);

    const closeModal = () => document.body.removeChild(modal);
    modal.querySelector('.close-button').addEventListener('click', closeModal);
    modal.addEventListener('click', (e) => e.target === modal && closeModal());

    const form = modal.querySelector('#mcp-config-form');
    const serverConfigContainer = modal.querySelector('#server-config-container');
    const toolOverridesContainer = modal.querySelector('#tool-overrides-container');

    let schema = null;

    const [schemaResult, toolsResult] = await Promise.allSettled([
        fetchMcpServerSchema(server.id),
        fetchMcpServerTools(server.id)
    ]);

    if (schemaResult.status === 'fulfilled') {
        schema = schemaResult.value;
        generateFormFromSchema(schema, currentConfig, serverConfigContainer);
    } else {
        serverConfigContainer.innerHTML = `<p class="error">Failed to load config schema: ${schemaResult.reason.message}</p>`;
    }

    if (toolsResult.status === 'fulfilled') {
        // MODIFIED: The API now returns a direct array of tools.
        const tools = toolsResult.value;
        toolOverridesContainer.innerHTML = '';
        if (!tools || tools.length === 0) {
            toolOverridesContainer.innerHTML = '<p>No tools found on this server.</p>';
        } else {
            const toolConfig = (currentConfig && currentConfig.tool_config) ? currentConfig.tool_config : {};
            tools.forEach(tool => {
                const toolSettings = toolConfig[tool.name] || {};
                const toolContainer = document.createElement('div');
                toolContainer.className = 'tool-override-item';
                toolContainer.dataset.toolName = tool.name;
                toolContainer.innerHTML = `
                    <div class="tool-override-header">
                        <span class="tool-name">${tool.name}</span>
                        <p class="form-help">${tool.description || 'No description available.'}</p>
                    </div>
                    <div class="tool-override-controls">
                        <div class="form-field-inline">
                                <label for="is-slow-${tool.name}" class="checkbox-label">
                                <div class="switch">
                                    <input type="checkbox" id="is-slow-${tool.name}" ${toolSettings.is_slow ? 'checked' : ''}>
                                    <span class="slider round"></span>
                                </div>
                                <span>Is a slow tool?</span>
                            </label>
                        </div>
                        <div class="form-field-inline">
                            <label for="reaction-emoji-${tool.name}">Reaction Emoji</label>
                            <input type="text" id="reaction-emoji-${tool.name}" value="${toolSettings.reaction_emoji || ''}" placeholder="e.g., ✏️" size="5">
                        </div>
                    </div>
                `;
                // This is where the magic happens: generate form for inputSchema
                const inputSchemaContainer = document.createElement('div');
                inputSchemaContainer.className = 'tool-input-schema-container';
                if (tool.inputSchema) {
                    generateFormFromSchema(tool.inputSchema, (currentConfig && currentConfig.default_arguments) ? currentConfig.default_arguments[tool.name] : {}, inputSchemaContainer);
                }
                toolContainer.appendChild(inputSchemaContainer);

                toolOverridesContainer.appendChild(toolContainer);
            });
        }
    } else {
        toolOverridesContainer.innerHTML = `<p class="error">Failed to load tools list: ${toolsResult.reason.message}</p>`;
    }

    form.addEventListener('submit', (e) => {
        e.preventDefault();
        const newConfig = {};

        // Part 1: Handle server-side configuration (from schema)
        if (schema) {
            for (const key in (schema.properties || {})) {
                const prop = schema.properties[key];
                const input = form.querySelector(`#config-${key}`);
                if (input) {
                    switch (prop.type) {
                        case 'boolean': newConfig[key] = input.checked; break;
                        case 'integer': newConfig[key] = parseInt(input.value, 10); break;
                        case 'number': newConfig[key] = parseFloat(input.value); break;
                        default: newConfig[key] = input.value; break;
                    }
                }
            }
        }

        // Part 2: Handle bot-specific tool overrides (meta and arguments)
        const tool_config = {};
        const default_arguments = {};

        modal.querySelectorAll('.tool-override-item').forEach(item => {
            const toolName = item.dataset.toolName;

            // 2a. Process meta-config (is_slow, reaction_emoji)
            const isSlow = item.querySelector(`#is-slow-${toolName}`).checked;
            const reactionEmoji = item.querySelector(`#reaction-emoji-${toolName}`).value.trim();
            if (isSlow || reactionEmoji) {
                tool_config[toolName] = {
                    is_slow: isSlow,
                    reaction_emoji: reactionEmoji || null
                };
            }

            // 2b. Process default arguments from the tool's inputSchema
            const toolArguments = {};
            let hasToolArguments = false;
            const inputSchemaContainer = item.querySelector('.tool-input-schema-container');
            if (inputSchemaContainer) {
                inputSchemaContainer.querySelectorAll('input[name], select[name], textarea[name]').forEach(input => {
                    const argName = input.name;
                    let value;
                    switch (input.type) {
                        case 'checkbox':
                            value = input.checked;
                            break;
                        case 'number':
                            const num = parseFloat(input.value);
                            value = isNaN(num) ? null : num;
                            break;
                        default:
                            value = input.value;
                            break;
                    }
                    toolArguments[argName] = value;
                    hasToolArguments = true;
                });
            }

            if (hasToolArguments) {
                default_arguments[toolName] = toolArguments;
            }
        });

        if (Object.keys(tool_config).length > 0) {
            newConfig.tool_config = tool_config;
        }
        if (Object.keys(default_arguments).length > 0) {
            newConfig.default_arguments = default_arguments;
        }

        saveCallback(newConfig);
        closeModal();
    });
}

export function showUploadModal(botId, uploadHandler) {
    const modal = document.createElement('div');
    modal.className = 'modal';
    modal.innerHTML = `
        <div class="modal-content">
            <span class="close-button">&times;</span>
            <h2>Upload File</h2>
            <form id="upload-form">
                <input type="file" id="file-input" required>
                <label for="owner-id">Owner Discord ID (optional)</label>
                <input type="text" id="owner-id" placeholder="Defaults to system ID">
                <button type="submit" class="primary-button">Upload</button>
            </form>
        </div>
    `;
    document.body.appendChild(modal);
    const closeModal = () => document.body.removeChild(modal);
    modal.querySelector('.close-button').addEventListener('click', closeModal);
    modal.addEventListener('click', (e) => e.target === modal && closeModal());
    modal.querySelector('#upload-form').addEventListener('submit', async (e) => {
        e.preventDefault();
        const fileInput = document.getElementById('file-input');
        const ownerId = document.getElementById('owner-id').value;
        if (fileInput.files.length > 0) {
            await uploadHandler(botId, fileInput.files[0], ownerId);
            closeModal();
        }
    });
}

export function showMcpServerModal(server = null, saveHandler) {
    const isEditing = server !== null;
    const modal = document.createElement('div');
    modal.className = 'modal';
    modal.innerHTML = `
        <div class="modal-content">
            <span class="close-button">&times;</span>
            <h2>${isEditing ? 'Edit' : 'Register'} MCP Server</h2>
            <form id="mcp-server-form" class="bot-settings-form">
                <fieldset>
                    <label for="mcp-name">Server Name</label>
                    <input type="text" id="mcp-name" name="name" value="${server?.name || ''}" required>
                    <label for="mcp-description">Description</label>
                    <textarea id="mcp-description" name="description" rows="3">${server?.description || ''}</textarea>
                    <label for="mcp-host">Host</label>
                    <input type="text" id="mcp-host" name="host" value="${server?.host || ''}" required>
                    <label for="mcp-port">Port</label>
                    <input type="number" id="mcp-port" name="port" value="${server?.port || ''}" required>
                    <label for="mcp-rpc-endpoint-path">RPC Endpoint Path</label>
                    <input type="text" id="mcp-rpc-endpoint-path" name="rpc_endpoint_path" value="${server?.rpc_endpoint_path || '/rpc'}" required>
                    <label for="mcp-enabled" class="checkbox-label"><div class="switch"><input type="checkbox" id="mcp-enabled" name="enabled" ${server?.enabled ?? true ? 'checked' : ''}><span class="slider round"></span></div><span>Server Enabled</span></label>
                </fieldset>
                <button type="submit" class="primary-button">${isEditing ? 'Save' : 'Register'}</button>
            </form>
        </div>
    `;
    document.body.appendChild(modal);
    const closeModal = () => document.body.removeChild(modal);
    modal.querySelector('.close-button').addEventListener('click', closeModal);
    modal.addEventListener('click', (e) => e.target === modal && closeModal());
    modal.querySelector('#mcp-server-form').addEventListener('submit', (e) => {
        saveHandler(e, server?.id);
        closeModal();
    });
}

export function showAddBotModal(createBotHandler) {
    const modal = document.createElement('div');
    modal.className = 'modal';
    modal.innerHTML = `
        <div class="modal-content">
            <span class="close-button">&times;</span>
            <h2>Add New Bot</h2>
            <form id="add-bot-form" class="bot-settings-form">
                <fieldset>
                    <label for="add-bot-name">Bot Name</label>
                    <input type="text" id="add-bot-name" name="name" required>
                    
                    <label for="add-bot-token">Discord Token (Optional)</label>
                    <input type="password" id="add-bot-token" name="discord_token">
                    
                    <label for="add-bot-model">LLM Model</label>
                    <p class="form-help">Leave blank to use the global default model.</p>
                    <select id="add-bot-model" name="llm_model"></select>
                    
                    <label for="add-bot-prompt">Main System Prompt</label>
                    <textarea id="add-bot-prompt" name="system_prompt" rows="8" placeholder="e.g., You are a helpful assistant."></textarea>
                </fieldset>
                <button type="submit" class="primary-button">Create Bot</button>
            </form>
        </div>
    `;
    document.body.appendChild(modal);

    populateModelDropdown('add-bot-model', '', window.availableModels);

    const closeModal = () => document.body.removeChild(modal);
    modal.querySelector('.close-button').addEventListener('click', closeModal);
    modal.addEventListener('click', (e) => e.target === modal && closeModal());

    modal.querySelector('#add-bot-form').addEventListener('submit', (e) => {
        createBotHandler(e);
    });
}