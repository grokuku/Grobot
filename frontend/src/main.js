// frontend/src/main.js

import * as api from './api.js';
import * as ui from './ui.js';
import * as events from './events.js';

// --- GLOBAL STATE ---
// We expose a few critical items on the window object to allow modules to interact
// without creating complex dependency cycles. This is a pragmatic choice for this app's scale.
window.availableModels = [];
window.botsList = [];
window.logStreamConnection = null;


// --- CORE NAVIGATION & ORCHESTRATION ---

/**
 * Selects a bot, updates the UI, and handles URL routing.
 * This is the main function for displaying content related to a specific bot.
 * @param {number} botId - The ID of the bot to select.
 * @param {string} defaultTab - The tab to open by default ('logs', 'settings', etc.).
 */
async function selectBot(botId, defaultTab = 'test-chat') {
    history.pushState({ botId, tab: defaultTab }, '', `#bot=${botId}&tab=${defaultTab}`);

    // Highlight the selected bot in the sidebar
    document.querySelector('.sidebar-bot-item.selected')?.classList.remove('selected');
    document.querySelector(`.sidebar-bot-item[data-bot-id='${botId}']`)?.classList.add('selected');

    ui.showSpinner();
    try {
        const bot = await api.fetchBotDetails(botId);
        if (!bot) throw new Error("Bot details not found.");

        // The UI rendering functions need callbacks for handling events within them.
        const tabChangeCallback = (bot, tabName) => renderTabContent(bot, tabName);
        const eventHandlers = events.getBotViewEventHandlers();

        await ui.renderMainContent(
            bot,
            defaultTab,
            tabChangeCallback,
            events.handleConnectToLogStream,
            eventHandlers.saveBotSettings,
            eventHandlers.fileHandlers,
            eventHandlers.testChat,
            eventHandlers.kbHandlers // MODIFICATION : Ajout des handlers pour la KB
        );

    } catch (error) {
        document.getElementById('main-content').innerHTML = `<p class="error">Failed to load bot content: ${error.message}</p>`;
        console.error(error);
    } finally {
        ui.hideSpinner();
    }
}
// Expose selectBot globally so it can be called from other modules (e.g., after saving settings)
window.selectBot = selectBot;

/**
 * A wrapper function to specifically handle rendering tab content.
 * It ensures the correct event handlers are passed down.
 * @param {object} bot - The bot object.
 * @param {string} tabName - The name of the tab to render.
 */
async function renderTabContent(bot, tabName) {
    const eventHandlers = events.getBotViewEventHandlers();
    await ui.renderTabContent(
        bot,
        tabName,
        events.handleConnectToLogStream,
        eventHandlers.saveBotSettings,
        eventHandlers.fileHandlers,
        eventHandlers.testChat,
        eventHandlers.kbHandlers // MODIFICATION : Ajout des handlers pour la KB
    );
}


// --- INITIALIZATION ---

/**
 * Initializes the application: sets up the theme, fetches initial data,
 * handles routing, and attaches global event listeners.
 */
async function init() {
    ui.showSpinner();

    // 1. Apply theme immediately
    ui.applyTheme(localStorage.getItem('theme') || 'dark', localStorage.getItem('color') || 'blue');

    // 2. Fetch initial data
    try {
        const models = await api.fetchModels();
        window.availableModels.length = 0;
        Array.prototype.push.apply(window.availableModels, models);

        await ui.refreshBotsList(window.botsList, selectBot);
    } catch (error) {
        // MODIFIED: If fetching models or bots fails, stop initialization and show a clear error.
        const mainContent = document.getElementById('main-content');
        mainContent.innerHTML = `<div class="error-container">
            <h2>Initialization Failed</h2>
            <p>Could not connect to the backend or fetch essential data. Please check that all services are running and refresh the page.</p>
            <pre>${error.message}</pre>
        </div>`;
        ui.hideSpinner();
        console.error("Fatal initialization error:", error);
        return; // Stop execution
    }

    // 3. Routing based on URL hash
    const params = new URLSearchParams(window.location.hash.slice(1));
    const botId = params.get('bot');
    const tab = params.get('tab');
    const view = params.get('view');

    if (botId) {
        await selectBot(botId, tab || 'test-chat');
    } else if (view === 'globals') {
        const settings = await api.fetchGlobalSettings();
        if (settings) {
            await ui.renderGlobalSettingsForm(settings, events.getGlobalSettingsEventHandlers());
        }
    } else if (window.botsList.length > 0) { // MODIFICATION : Logique pour `view=user-kb` retirée
        // Default view: select the first bot if none is specified
        await selectBot(window.botsList[0].id, 'test-chat');
    } else {
        // Welcome screen if no bots exist
        document.getElementById('main-content').innerHTML = `
        <header id="chat-header">
            <div id="chat-header-title"><h3>Welcome</h3></div>
            <div id="theme-controls-container"></div>
        </header>
        <div id="central-panel-content"><h2>No bots configured. Add a new bot to get started.</h2></div>`;
        ui.renderThemeControls();
    }

    ui.hideSpinner();
}

/**
 * Attaches event listeners to persistent elements of the shell.
 */
function attachShellEventListeners() {
    // The old button was 'new-bot-btn'. The new one is 'add-bot-btn' in the sidebar header.
    // Let's ensure we target the correct one from the HTML shell.
    const addBotButton = document.getElementById('new-bot-btn');
    if (addBotButton) {
        addBotButton.addEventListener('click', () => {
            const sidebarEventHandlers = events.getSidebarEventHandlers();
            ui.showAddBotModal(sidebarEventHandlers.createBot);
        });
    }

    document.getElementById('global-settings-btn').addEventListener('click', async () => {
        history.pushState({ view: 'globals' }, '', `#view=globals`);
        ui.showSpinner();
        try {
            const settings = await api.fetchGlobalSettings();
            if (settings) {
                await ui.renderGlobalSettingsForm(settings, events.getGlobalSettingsEventHandlers());
            }
        } catch (error) {
            ui.showToast(`Could not load global settings: ${error.message}`, 'error');
        } finally {
            ui.hideSpinner();
        }
    });

    // MODIFICATION : Le listener pour le bouton global de la KB a été supprimé.

    // Handle browser back/forward navigation
    window.addEventListener('popstate', () => init());

    // Sidebar resize logic
    const sidebar = document.getElementById('sidebar');
    const resizeHandle = document.getElementById('resize-handle-left');
    if (sidebar && resizeHandle) {
        let isResizing = false;
        const handleMouseMove = (e) => {
            if (!isResizing) return;
            const newWidth = e.clientX;
            if (newWidth > 200 && newWidth < 600) sidebar.style.width = `${newWidth}px`;
        };
        const handleMouseUp = () => {
            isResizing = false;
            document.removeEventListener('mousemove', handleMouseMove);
            document.removeEventListener('mouseup', handleMouseUp);
            document.body.style.userSelect = '';
        };
        resizeHandle.addEventListener('mousedown', () => {
            isResizing = true;
            document.addEventListener('mousemove', handleMouseMove);
            document.addEventListener('mouseup', handleMouseUp);
            document.body.style.userSelect = 'none';
        });
    }

    // NEW: Event delegation for dynamically created "Evaluate" buttons.
    const mainContent = document.getElementById('main-content');
    if (mainContent) {
        mainContent.addEventListener('click', (event) => {
            const evaluateBtn = event.target.closest('.evaluate-llm-btn');
            if (evaluateBtn) {
                // Determine the correct context (global or bot-specific)
                const isGlobalSettings = !!event.target.closest('#global-settings-form');
                const handlers = isGlobalSettings
                    ? events.getGlobalSettingsEventHandlers()
                    : events.getBotViewEventHandlers();

                if (handlers.evaluateLlm) {
                    handlers.evaluateLlm(event);
                }
            }
        });
    }
}

// --- APP START ---
document.addEventListener('DOMContentLoaded', () => {
    init();
    attachShellEventListeners();
});