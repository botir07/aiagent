const state = {
  model: {
    connected: false,
    provider: "Local Model",
    endpoint: "http://localhost:7352",
    latency_ms: 0,
    request_count: 0,
    token_usage: 0,
    last_error: null,
  },
  currentSession: null,
  sessions: [],
  selectedAgentId: null,
  selectedArtifactId: null,
};

const goalInput = document.getElementById("goalInput");
const requirementsInput = document.getElementById("requirementsInput");
const typeInput = document.getElementById("typeInput");
const priorityInput = document.getElementById("priorityInput");
const startButton = document.getElementById("startButton");
const modelStatus = document.getElementById("modelStatus");
const statusProvider = document.getElementById("statusProvider");
const statusEndpoint = document.getElementById("statusEndpoint");
const statusLatency = document.getElementById("statusLatency");
const projectStatus = document.getElementById("projectStatus");
const activeAgent = document.getElementById("activeAgent");
const requestCount = document.getElementById("requestCount");
const workflowGraph = document.getElementById("workflowGraph");
const logList = document.getElementById("logList");
const agentInspector = document.getElementById("agentInspector");
const artifactList = document.getElementById("artifactList");
const artifactPreview = document.getElementById("artifactPreview");
const activeAgents = document.getElementById("activeAgents");
const completedTasks = document.getElementById("completedTasks");
const failedTasks = document.getElementById("failedTasks");
const executionTime = document.getElementById("executionTime");
const healthStatus = document.getElementById("healthStatus");

const columns = ["Backlog", "Todo", "In Progress", "Review", "Completed"];

function formatStatusLabel(status) {
  return status.replace("In Progress", "In Progress");
}

function makeRequest(path, options = {}) {
  return fetch(path, options).then(async (res) => {
    if (!res.ok) {
      const payload = await res.json().catch(() => ({}));
      throw new Error(payload.error || `Request failed ${res.status}`);
    }
    return res.json();
  });
}

function connectWebSocket() {
  const protocol = location.protocol === "https:" ? "wss" : "ws";
  const ws = new WebSocket(`${protocol}://${location.host}/ws`);

  ws.addEventListener("open", () => {
    modelStatus.classList.remove("disconnected");
    modelStatus.classList.add("connected");
    modelStatus.textContent = "🟢 Connected to local AI";
  });

  ws.addEventListener("message", (event) => {
    const packet = JSON.parse(event.data);
    if (packet.type === "status_update") {
      updateModel(packet.payload);
    }
    if (packet.type === "snapshot") {
      state.sessions = packet.payload.sessions;
      if (!state.currentSession && state.sessions.length) {
        state.currentSession = state.sessions[0];
      }
      renderAll();
    }
    if (packet.type === "session_update" || packet.type === "session_created") {
      updateSessionFromPayload(packet.payload);
    }
  });

  ws.addEventListener("close", () => {
    modelStatus.classList.remove("connected");
    modelStatus.classList.add("disconnected");
    modelStatus.textContent = "🔴 Disconnected — reconnecting...";
    setTimeout(connectWebSocket, 2000);
  });

  ws.addEventListener("error", () => {
    modelStatus.classList.remove("connected");
    modelStatus.classList.add("disconnected");
    modelStatus.textContent = "⚠️ AI connection error";
  });
}

function updateModel(payload) {
  state.model = { ...state.model, ...payload };
  statusProvider.textContent = state.model.provider;
  statusEndpoint.textContent = state.model.endpoint;
  statusLatency.textContent = `${Math.round(state.model.latency_ms)} ms`;
  requestCount.textContent = state.model.request_count;
  healthStatus.textContent = state.model.connected ? "Healthy" : "Offline";
  if (!state.model.connected) {
    modelStatus.classList.add("disconnected");
    modelStatus.textContent = `🔴 Disconnected — ${state.model.last_error || "waiting"}`;
  }
}

function updateSessionFromPayload(payload) {
  state.currentSession = payload;
  const existingIndex = state.sessions.findIndex((session) => session.id === payload.id);
  if (existingIndex >= 0) {
    state.sessions[existingIndex] = payload;
  } else {
    state.sessions.unshift(payload);
  }
  renderAll();
}

function renderAll() {
  renderOverview();
  renderWorkflow();
  renderBoard();
  renderLogs();
  renderInspector();
  renderArtifacts();
  renderMonitor();
}

function renderOverview() {
  if (!state.currentSession) {
    projectStatus.textContent = "Waiting for project";
    activeAgent.textContent = "—";
    requestCount.textContent = state.model.request_count;
    return;
  }
  projectStatus.textContent = state.currentSession.status;
  activeAgent.textContent = state.currentSession.current_agent || "—";
}

function renderWorkflow() {
  workflowGraph.innerHTML = "";
  if (!state.currentSession) {
    workflowGraph.innerHTML = "<div class=\"placeholder\">Start a project to watch the workflow activate.</div>";
    return;
  }
  state.currentSession.workflow_order.forEach((role) => {
    const agent = state.currentSession.agents.find((item) => item.role === role);
    const item = document.createElement("button");
    item.type = "button";
    item.className = `workflow-node ${state.currentSession.current_agent === role ? "active" : ""}`;
    item.textContent = `${agent.name} · ${role}`;
    item.addEventListener("click", () => selectAgent(agent.id));
    workflowGraph.appendChild(item);
  });
}

function renderBoard() {
  columns.forEach((status) => {
    const container = document.getElementById(`column-${status}`);
    if (!container) return;
    container.innerHTML = "";
    if (!state.currentSession) {
      container.innerHTML = "<div class=\"placeholder\">No tasks yet.</div>";
      return;
    }
    const tasks = state.currentSession.tasks.filter((task) => task.status === status);
    if (!tasks.length) {
      container.innerHTML = "<div class=\"placeholder\">No tasks</div>";
      return;
    }
    tasks.forEach((task) => {
      const card = document.createElement("div");
      card.className = "task-card";
      card.innerHTML = `
        <div class="task-header">
          <strong>${task.title}</strong>
          <span>${task.assignee}</span>
        </div>
        <div class="task-meta">
          <span>${task.progress}%</span>
          <button class="link-button" data-task-id="${task.id}">Inspect</button>
        </div>
      `;
      card.querySelector("[data-task-id]").addEventListener("click", () => inspectTask(task.id));
      container.appendChild(card);
    });
  });
}

function renderLogs() {
  if (!state.currentSession) {
    logList.innerHTML = "<div class=\"placeholder\">Workflow logs appear here.</div>";
    return;
  }
  logList.innerHTML = state.currentSession.logs
    .slice()
    .reverse()
    .map((entry) => `
      <div class="log-item">
        <span class="log-time">${entry.timestamp}</span>
        <span class="log-agent">${entry.agent}</span>
        <span class="log-action">${entry.action}</span>
        <p>${entry.result}</p>
      </div>
    `)
    .join("");
}

function renderInspector() {
  if (!state.currentSession) {
    agentInspector.innerHTML = "<p class=\"placeholder\">Inspect an agent after project start.</p>";
    return;
  }
  const agent = state.currentSession.agents.find((item) => item.id === state.selectedAgentId) || state.currentSession.agents[0];
  if (!agent) {
    agentInspector.innerHTML = "<p class=\"placeholder\">No agent available.</p>";
    return;
  }
  state.selectedAgentId = agent.id;
  agentInspector.innerHTML = `
    <div class="inspector-header">
      <h3>${agent.name}</h3>
      <span>${agent.role}</span>
    </div>
    <div class="inspector-row"><strong>State</strong><span>${agent.state}</span></div>
    <div class="inspector-row"><strong>Task</strong><span>${agent.current_task || "Idle"}</span></div>
    <div class="inspector-row"><strong>Progress</strong><span>${agent.progress}%</span></div>
    <div class="inspector-section"><strong>Memory</strong><pre>${agent.memory.slice(-3).map((item) => `${item.timestamp} · ${item.task}`).join("\n") || "No memory yet."}</pre></div>
    <div class="inspector-section"><strong>Artifacts</strong><pre>${agent.artifacts.length ? agent.artifacts.join("\n") : "No artifacts yet."}</pre></div>
  `;
}

function renderArtifacts() {
  if (!state.currentSession) {
    artifactList.innerHTML = "<div class=\"placeholder\">Artifacts will appear here.</div>";
    artifactPreview.textContent = "Select an artifact to preview generated files.";
    return;
  }
  artifactList.innerHTML = state.currentSession.artifacts
    .map((artifact) => `
      <button class="artifact-item ${state.selectedArtifactId === artifact.id ? "selected" : ""}" data-artifact-id="${artifact.id}">
        ${artifact.path}
      </button>
    `)
    .join("");
  artifactList.querySelectorAll("[data-artifact-id]").forEach((button) => {
    button.addEventListener("click", () => {
      state.selectedArtifactId = button.dataset.artifactId;
      renderArtifacts();
      previewArtifact();
    });
  });
  previewArtifact();
}

function previewArtifact() {
  if (!state.currentSession || !state.selectedArtifactId) {
    artifactPreview.textContent = "Select an artifact to preview generated files.";
    return;
  }
  const artifact = state.currentSession.artifacts.find((item) => item.id === state.selectedArtifactId);
  artifactPreview.textContent = artifact ? artifact.content : "Artifact not found.";
}

function selectAgent(agentId) {
  state.selectedAgentId = agentId;
  renderInspector();
}

function inspectTask(taskId) {
  if (!state.currentSession) return;
  const task = state.currentSession.tasks.find((item) => item.id === taskId);
  if (!task) return;
  const details = `Title: ${task.title}\nAssignee: ${task.assignee}\nStatus: ${task.status}\nProgress: ${task.progress}%\n\n${task.description}\n\nOutput:\n${task.output || "Pending"}`;
  const newStatus = prompt("Update status:\nBacklog, Todo, In Progress, Review, Completed, Failed", task.status);
  if (newStatus && columns.includes(newStatus)) {
    makeRequest("/api/task", {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ id: taskId, status: newStatus }),
    }).then(() => {}).catch((error) => console.error(error));
  } else {
    alert(details);
  }
}

function renderMonitor() {
  if (!state.currentSession) {
    activeAgents.textContent = "0";
    completedTasks.textContent = "0";
    failedTasks.textContent = "0";
    executionTime.textContent = "0s";
    return;
  }
  const activeCount = state.currentSession.agents.filter((agent) => !["Completed", "Failed"].includes(agent.state)).length;
  const completedCount = state.currentSession.tasks.filter((task) => task.status === "Completed").length;
  const failedCount = state.currentSession.tasks.filter((task) => task.status === "Failed").length;
  const elapsed = Math.max(0, Date.now() / 1000 - state.currentSession.start_time);
  activeAgents.textContent = activeCount;
  completedTasks.textContent = completedCount;
  failedTasks.textContent = failedCount;
  executionTime.textContent = `${Math.round(elapsed)}s`;
}

async function startProject() {
  const goal = goalInput.value.trim();
  const requirements = requirementsInput.value.trim();
  if (!goal) {
    alert("Enter a project goal before starting.");
    return;
  }
  const payload = {
    goal,
    requirements,
    project_type: typeInput.value,
    priority: priorityInput.value,
  };
  try {
    const response = await makeRequest("/api/project", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    state.currentSession = response.session;
    state.sessions.unshift(response.session);
    renderAll();
  } catch (error) {
    alert(error.message);
  }
}

startButton.addEventListener("click", startProject);
window.addEventListener("load", () => {
  connectWebSocket();
  renderAll();
});
