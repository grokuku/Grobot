// FICHIER: frontend/src/workflow_editor.js

import {
    showToast,
    showSpinner,
    hideSpinner
} from './ui.js';
import {
    fetchMcpServers,
    createWorkflow,
    updateWorkflow,
    fetchWorkflowTools,
    fetchDiscordChannels
} from './api.js';

// --- MODAL & FORM HELPERS ---

/**
 * Shows a modal to link a parameter to the output of a previous step.
 * @param {number} currentStepIndex The index of the current step (0-based).
 * @param {string} paramName The name of the parameter being linked.
 * @param {Array<Object>} allStepsData A reference to the array of all step data objects.
 * @param {Function} onLink Callback function executed on successful linking.
 * @param {Array<Object>} allTools All available tools for the bot.
 */
async function showLinkerModal(currentStepIndex, paramName, allStepsData, onLink, allTools) {
    const modal = document.createElement('div');
    modal.className = 'modal';
    modal.innerHTML = `
        <div class="modal-content">
            <span class="close-button">&times;</span>
            <h4>Link Parameter "${paramName}"</h4>
            <form id="linker-form" class="bot-settings-form" style="max-width: none;">
                <fieldset>
                    <label for="source-step-select">Source Step</label>
                    <select id="source-step-select" required></select>
                    <div id="output-key-container" style="margin-top: 1rem;">
                        <label for="output-key-input">Output Key</label>
                        <input type="text" id="output-key-input" placeholder="Select a source step first..." disabled>
                    </div>
                </fieldset>
                <button type="submit" class="primary-button">Link</button>
            </form>
        </div>
    `;
    document.body.appendChild(modal);

    const closeModal = () => document.body.removeChild(modal);
    modal.querySelector('.close-button').addEventListener('click', closeModal);
    const form = modal.querySelector('#linker-form');
    const stepSelect = modal.querySelector('#source-step-select');
    const outputKeyContainer = modal.querySelector('#output-key-container');

    stepSelect.appendChild(new Option('Select a source step...', ''));
    for (let i = 0; i < currentStepIndex; i++) {
        const stepData = allStepsData[i];
        const stepLabel = `Step ${i + 1}: ${stepData.tool_name || 'Unconfigured'}`;
        stepSelect.appendChild(new Option(stepLabel, i + 1));
    }

    // --- FIX: Logic to find tool schema without a new API call ---
    stepSelect.addEventListener('change', (e) => {
        const selectedStepOrder = parseInt(e.target.value);
        outputKeyContainer.innerHTML = `
            <label for="output-key-select">Output Key</label>
            <select id="output-key-select" required disabled>
                <option value="">Loading...</option>
            </select>`;

        if (!selectedStepOrder) return;

        try {
            const sourceStepData = allStepsData.find(step => step.step_order === selectedStepOrder);
            if (!sourceStepData || sourceStepData.mcp_server_id === undefined || !sourceStepData.tool_name) {
                throw new Error("Source step is not fully configured.");
            }

            const toolWrapper = allTools.find(t =>
                t.mcp_server_id === sourceStepData.mcp_server_id &&
                t.tool_definition.name === sourceStepData.tool_name
            );

            if (!toolWrapper) {
                throw new Error(`Could not find schema for tool "${sourceStepData.tool_name}".`);
            }
            const toolSchema = toolWrapper.tool_definition;

            if (!toolSchema || !toolSchema.outputSchema || !toolSchema.outputSchema.properties) {
                throw new Error(`Tool "${sourceStepData.tool_name}" has no defined outputs (outputSchema).`);
            }

            const outputKeys = Object.keys(toolSchema.outputSchema.properties);
            if (outputKeys.length === 0) {
                throw new Error(`Tool "${sourceStepData.tool_name}" has no output keys.`);
            }

            const outputKeySelect = outputKeyContainer.querySelector('#output-key-select');
            outputKeySelect.innerHTML = '<option value="">Select an output...</option>';
            outputKeys.forEach(key => {
                outputKeySelect.appendChild(new Option(key, key));
            });
            outputKeySelect.disabled = false;

        } catch (error) {
            showToast(error.message, 'error');
            outputKeyContainer.innerHTML = `<p class="form-help error-text">${error.message}</p>`;
        }
    });
    // --- END FIX ---

    form.addEventListener('submit', (e) => {
        e.preventDefault();
        const sourceStep = stepSelect.value;
        const outputKeySelect = modal.querySelector('#output-key-select');
        const outputKey = outputKeySelect ? outputKeySelect.value : null;

        if (sourceStep && outputKey) {
            onLink(parseInt(sourceStep), outputKey.trim());
            closeModal();
        } else {
            showToast("Please select a source step and an output key.", "error");
        }
    });
}

function createField(label, input, helpText = '') {
    const container = document.createElement('div');
    container.className = 'form-field-container';
    const labelEl = document.createElement('label');
    labelEl.textContent = label;
    const inputWrapper = document.createElement('div');
    inputWrapper.className = 'input-wrapper';
    inputWrapper.appendChild(input);

    container.appendChild(labelEl);
    container.appendChild(inputWrapper);

    if (helpText) {
        const helpEl = document.createElement('p');
        helpEl.className = 'form-help';
        helpEl.textContent = helpText;
        inputWrapper.appendChild(helpEl);
    }
    return container;
}

// --- REVISED: DYNAMIC ATTACHMENT UI WITH LINKING CAPABILITIES ---
function renderAttachmentsUI(paramSchema, stepData, stepIndex, allStepsData, allTools) {
    const mainContainer = document.createElement('div');
    mainContainer.className = 'attachments-container';

    const label = document.createElement('label');
    label.textContent = paramSchema.title || 'Attachments';
    mainContainer.appendChild(label);

    const attachmentsList = document.createElement('div');
    attachmentsList.className = 'attachments-list';
    mainContainer.appendChild(attachmentsList);

    if (!Array.isArray(stepData.parameter_mappings.attachments)) {
        stepData.parameter_mappings.attachments = [];
    }
    const attachments = stepData.parameter_mappings.attachments;

    function rerenderAttachmentsList() {
        attachmentsList.innerHTML = '';
        attachments.forEach((att, index) => {
            const attachmentItem = document.createElement('div');
            attachmentItem.className = 'attachment-item';

            // Helper to create a linked field for an attachment property
            const createAttachmentField = (propName, placeholder) => {
                const wrapper = document.createElement('div');
                wrapper.className = 'input-wrapper';

                const input = document.createElement('input');
                input.type = 'text';
                input.placeholder = placeholder;

                const isLinked = att[propName] && typeof att[propName] === 'object';

                if (isLinked) {
                    const mapping = att[propName];
                    input.value = `Linked to Step ${mapping.source_step_order}.${mapping.output_key}`;
                    input.disabled = true;
                } else {
                    input.value = att[propName] || '';
                    input.addEventListener('input', e => att[propName] = e.target.value);
                }

                const linkBtn = document.createElement('button');
                linkBtn.type = 'button';
                linkBtn.className = `icon-btn link-param-btn ${isLinked ? 'active' : ''}`;
                linkBtn.title = `Link ${propName}`;
                linkBtn.innerHTML = '🔗';
                linkBtn.disabled = stepIndex === 0;
                linkBtn.addEventListener('click', () => {
                    showLinkerModal(stepIndex, `Attachment ${index + 1} - ${propName}`, allStepsData, (sourceStep, outputKey) => {
                        att[propName] = { source_step_order: sourceStep, output_key: outputKey };
                        rerenderAttachmentsList();
                    }, allTools);
                });

                wrapper.appendChild(input);
                wrapper.appendChild(linkBtn);

                if (isLinked) {
                    const unlinkBtn = document.createElement('button');
                    unlinkBtn.type = 'button';
                    unlinkBtn.className = 'icon-btn unlink-param-btn';
                    unlinkBtn.title = 'Unlink parameter';
                    unlinkBtn.innerHTML = '❌';
                    unlinkBtn.addEventListener('click', () => {
                        att[propName] = ''; // Reset to empty string
                        rerenderAttachmentsList();
                    });
                    wrapper.appendChild(unlinkBtn);
                }
                return wrapper;
            };

            const dataField = createAttachmentField('data', 'Attachment Data (URL or text)');
            const filenameField = createAttachmentField('filename', 'Filename (optional)');

            const removeBtn = document.createElement('button');
            removeBtn.type = 'button';
            removeBtn.className = 'icon-btn';
            removeBtn.innerHTML = '🗑️';
            removeBtn.title = 'Remove Attachment';
            removeBtn.addEventListener('click', () => {
                attachments.splice(index, 1);
                rerenderAttachmentsList();
            });

            attachmentItem.append(dataField, filenameField, removeBtn);
            attachmentsList.appendChild(attachmentItem);
        });

        if (attachments.length === 0) {
            attachmentsList.innerHTML = `<p class="form-help">No attachments added yet.</p>`;
        }
    }

    const addBtn = document.createElement('button');
    addBtn.type = 'button';
    addBtn.className = 'secondary-button add-attachment-btn';
    addBtn.textContent = '+ Add Attachment';
    addBtn.addEventListener('click', () => {
        if (attachments.length < 10) {
            attachments.push({ data: '', filename: '' });
            rerenderAttachmentsList();
        } else {
            showToast('Maximum of 10 attachments reached.', 'info');
        }
    });
    mainContainer.appendChild(addBtn);

    rerenderAttachmentsList();
    return mainContainer;
}

// Renders the parameters for a selected tool
async function renderToolParameters(tool, stepIndex, stepData, allStepsData, botId, allTools) {
    const container = document.createElement('div');
    container.className = 'tool-parameters-container';
    stepData.parameter_mappings = stepData.parameter_mappings || {};

    const schema = tool.inputSchema || { properties: {} };
    if (Object.keys(schema.properties).length === 0) {
        container.innerHTML = `<p class="form-help">This tool has no parameters.</p>`;
        return container;
    }

    for (const [paramName, paramSchema] of Object.entries(schema.properties)) {
        let input;
        const isLinked = stepData.parameter_mappings[paramName] && typeof stepData.parameter_mappings[paramName] === 'object';

        if (tool.name === 'post_to_discord' && paramName === 'attachments') {
            const attachmentsUI = renderAttachmentsUI(paramSchema, stepData, stepIndex, allStepsData, allTools);
            container.appendChild(attachmentsUI);
            continue;
        }

        if (tool.name === 'post_to_discord' && paramName === 'channel_id' && !isLinked) {
            input = document.createElement('select');
            input.innerHTML = `<option value="">Loading channels...</option>`;
            input.disabled = true;

            (async () => {
                try {
                    const channels = await fetchDiscordChannels(botId);
                    input.innerHTML = `<option value="">Select a Discord channel...</option>`;
                    channels.forEach(channel => {
                        input.appendChild(new Option(channel.name, channel.id));
                    });
                    input.value = stepData.parameter_mappings[paramName] || '';
                    input.disabled = false;
                } catch (error) {
                    input.innerHTML = `<option value="">Error loading channels</option>`;
                    showToast(error.message, 'error');
                }
            })();

            input.addEventListener('change', (e) => {
                stepData.parameter_mappings[paramName] = e.target.value;
            });
        } else if (paramSchema.enum && !isLinked) {
            input = document.createElement('select');
            paramSchema.enum.forEach(value => {
                input.appendChild(new Option(value, value));
            });
            input.value = stepData.parameter_mappings[paramName] || paramSchema.default || paramSchema.enum[0];
            input.addEventListener('change', (e) => {
                stepData.parameter_mappings[paramName] = e.target.value;
            });
        } else {
            input = document.createElement('input');
            input.type = 'text';
            input.placeholder = paramSchema.description || `Value for ${paramName}`;
            if (!isLinked) {
                input.value = stepData.parameter_mappings[paramName] || paramSchema.default || '';
            }
            input.addEventListener('input', (e) => {
                stepData.parameter_mappings[paramName] = e.target.value;
            });
        }

        const field = createField(paramSchema.title || paramName, input);
        const inputWrapper = field.querySelector('.input-wrapper');

        const linkBtn = document.createElement('button');
        linkBtn.type = 'button';
        linkBtn.className = 'icon-btn link-param-btn';
        linkBtn.title = 'Link to previous step output';
        linkBtn.innerHTML = '🔗';
        linkBtn.disabled = stepIndex === 0;

        linkBtn.addEventListener('click', () => {
            showLinkerModal(stepIndex, paramName, allStepsData, (sourceStep, outputKey) => {
                const mapping = { source_step_order: sourceStep, output_key: outputKey };
                stepData.parameter_mappings[paramName] = mapping;
                renderToolParameters(tool, stepIndex, stepData, allStepsData, botId, allTools).then(newParams => {
                    container.innerHTML = '';
                    container.appendChild(newParams);
                });
            }, allTools);
        });

        if (isLinked) {
            const mapping = stepData.parameter_mappings[paramName];
            input.value = `Linked to Step ${mapping.source_step_order}.${mapping.output_key}`;
            input.disabled = true;
            linkBtn.classList.add('active');
            const unlinkBtn = document.createElement('button');
            unlinkBtn.type = 'button';
            unlinkBtn.className = 'icon-btn unlink-param-btn';
            unlinkBtn.title = 'Unlink parameter';
            unlinkBtn.innerHTML = '❌';
            unlinkBtn.addEventListener('click', () => {
                delete stepData.parameter_mappings[paramName];
                renderToolParameters(tool, stepIndex, stepData, allStepsData, botId, allTools).then(newParams => {
                    container.innerHTML = '';
                    container.appendChild(newParams);
                });
            });
            inputWrapper.appendChild(unlinkBtn);
        }

        inputWrapper.appendChild(linkBtn);
        container.appendChild(field);
    }
    return container;
}

// Renders a single step in the editor
async function renderStep(stepIndex, stepData, stepsData, container, rerenderAllSteps, allTools, serverMap, botId) {
    const stepElement = document.createElement('div');
    stepElement.className = 'workflow-step-card';
    stepElement.innerHTML = `
        <div class="workflow-step-header">
            <h4>Step ${stepIndex + 1}</h4>
            <button type="button" class="icon-btn delete-step-btn">🗑️</button>
        </div>
    `;

    const toolSelect = document.createElement('select');
    const toolField = createField('Tool', toolSelect);
    const paramsContainer = document.createElement('div');

    stepElement.append(toolField, paramsContainer);
    container.appendChild(stepElement);

    const toolsByServer = allTools.reduce((acc, tool) => {
        const serverId = tool.mcp_server_id;
        if (!acc[serverId]) { acc[serverId] = []; }
        acc[serverId].push(tool);
        return acc;
    }, {});

    toolSelect.innerHTML = '<option value="">Select a tool...</option>';
    for (const serverId in toolsByServer) {
        const serverName = serverMap[serverId] || `Internal Tools (ID ${serverId})`;
        const optgroup = document.createElement('optgroup');
        optgroup.label = serverName;

        toolsByServer[serverId].forEach(toolWrapper => {
            const tool = toolWrapper.tool_definition;
            const optionValue = `${toolWrapper.mcp_server_id}:${tool.name}`;
            const option = new Option(tool.name, optionValue);
            option.dataset.toolData = JSON.stringify(tool);
            option.dataset.serverId = toolWrapper.mcp_server_id;
            optgroup.appendChild(option);
        });
        toolSelect.appendChild(optgroup);
    }

    toolSelect.addEventListener('change', async () => {
        const selectedOption = toolSelect.options[toolSelect.selectedIndex];
        paramsContainer.innerHTML = '';
        if (!selectedOption.value) {
            stepData.tool_name = null;
            stepData.mcp_server_id = null;
            stepData.parameter_mappings = {};
            return;
        }

        stepData.tool_name = selectedOption.text;
        stepData.mcp_server_id = parseInt(selectedOption.dataset.serverId);
        stepData.parameter_mappings = {};
        const toolData = JSON.parse(selectedOption.dataset.toolData);

        paramsContainer.appendChild(await renderToolParameters(toolData, stepIndex, stepData, stepsData, botId, allTools));
    });

    stepElement.querySelector('.delete-step-btn').addEventListener('click', () => {
        stepsData.splice(stepIndex, 1);
        rerenderAllSteps();
    });

    if (stepData.mcp_server_id !== undefined && stepData.tool_name) {
        const serverIdForLookup = stepData.mcp_server_id ?? 0;
        const valueToFind = `${serverIdForLookup}:${stepData.tool_name}`;
        toolSelect.value = valueToFind;
        const selectedOption = toolSelect.options[toolSelect.selectedIndex];
        if (selectedOption && selectedOption.dataset.toolData) {
            const toolData = JSON.parse(selectedOption.dataset.toolData);
            paramsContainer.appendChild(await renderToolParameters(toolData, stepIndex, stepData, stepsData, botId, allTools));
        }
    }
}

export async function showWorkflowEditorModal(bot, onSave, existingWorkflow = null) {
    const isEditing = existingWorkflow !== null;

    let workflowData;
    if (isEditing) {
        workflowData = JSON.parse(JSON.stringify(existingWorkflow));
    } else {
        workflowData = {
            name: '',
            description: '',
            is_enabled: true,
            trigger: { trigger_type: 'cron', config: { cron_schedule: '0 8 * * *' } },
            steps: []
        };
    }

    showSpinner();
    let allTools = [];
    let serverMap = {};
    try {
        const [tools, servers] = await Promise.all([
            fetchWorkflowTools(bot.id),
            fetchMcpServers()
        ]);
        allTools = tools;
        serverMap = servers.reduce((map, server) => {
            map[server.id] = server.name;
            return map;
        }, { 0: "Internal Tools" });
    } catch (error) {
        hideSpinner();
        showToast(`Failed to load workflow data: ${error.message}`, 'error');
        return;
    }
    hideSpinner();

    const modal = document.createElement('div');
    modal.className = 'modal';
    modal.innerHTML = `
        <div class="modal-content large">
            <span class="close-button">&times;</span>
            <h2 id="wf-modal-title">${isEditing ? `Edit Workflow for ${bot.name}` : `Create New Workflow for ${bot.name}`}</h2>
            <form id="workflow-editor-form" class="bot-settings-form">
                <div class="modal-body">
                    <fieldset>
                        <legend>1. General Information</legend>
                        <input type="text" id="wf-name" placeholder="Workflow Name" required>
                        <textarea id="wf-desc" placeholder="Workflow Description" rows="2" style="margin-top: 1rem;"></textarea>
                    </fieldset>
                    <fieldset>
                        <legend>2. Trigger (When to run)</legend>
                        <p class="form-help">Currently, only CRON schedules are supported.</p>
                        <input type="text" id="wf-cron" required>
                    </fieldset>
                    <fieldset>
                        <legend>3. Steps (What to do)</legend>
                        <div id="workflow-steps-container"></div>
                        <button type="button" id="add-step-btn" class="secondary-button" style="margin-top: 1rem;">+ Add Step</button>
                    </fieldset>
                </div>
                <button type="submit" class="primary-button" style="margin-top: 1.5rem;">${isEditing ? 'Update Workflow' : 'Save Workflow'}</button>
            </form>
        </div>
    `;
    document.body.appendChild(modal);

    const closeModal = () => document.body.removeChild(modal);
    modal.querySelector('.close-button').addEventListener('click', closeModal);

    const stepsContainer = modal.querySelector('#workflow-steps-container');

    modal.querySelector('#wf-name').value = workflowData.name;
    modal.querySelector('#wf-desc').value = workflowData.description || '';
    modal.querySelector('#wf-cron').value = workflowData.trigger?.config?.cron_schedule || '0 8 * * *';

    const rerenderAllSteps = async () => {
        stepsContainer.innerHTML = '';

        for (const [index, stepData] of workflowData.steps.entries()) {
            stepData.step_order = index + 1;
            await renderStep(index, stepData, workflowData.steps, stepsContainer, rerenderAllSteps, allTools, serverMap, bot.id);
        }
    };

    modal.querySelector('#wf-name').addEventListener('input', e => workflowData.name = e.target.value);
    modal.querySelector('#wf-desc').addEventListener('input', e => workflowData.description = e.target.value);
    modal.querySelector('#wf-cron').addEventListener('input', e => workflowData.trigger.config.cron_schedule = e.target.value);

    modal.querySelector('#add-step-btn').addEventListener('click', () => {
        const stepIndex = workflowData.steps.length;
        const newStepData = { step_order: stepIndex + 1, parameter_mappings: {} };
        workflowData.steps.push(newStepData);
        renderStep(stepIndex, newStepData, workflowData.steps, stepsContainer, rerenderAllSteps, allTools, serverMap, bot.id);
    });

    if (isEditing) {
        rerenderAllSteps();
    }

    modal.querySelector('#workflow-editor-form').addEventListener('submit', async (e) => {
        e.preventDefault();
        showSpinner();
        try {
            if (!workflowData.name) throw new Error("Workflow name is required.");

            if (isEditing) {
                await updateWorkflow(existingWorkflow.id, workflowData);
                showToast('Workflow updated successfully!', 'success');
            } else {
                await createWorkflow(bot.id, workflowData);
                showToast('Workflow created successfully!', 'success');
            }

            if (onSave) onSave();
            closeModal();
        } catch (error) {
            showToast(`Error: ${error.message}`, 'error');
        } finally {
            hideSpinner();
        }
    });
}