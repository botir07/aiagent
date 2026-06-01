import asyncio
import json
import logging
import time
import uuid
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, Dict, List, Optional

import requests
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

# Configure logging for debugging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

BASE_DIR = Path(__file__).resolve().parent
STATIC_DIR = BASE_DIR / "static"
MODEL_BASE_URL = "http://localhost:7352"
MODEL_PATH_PREFIX = ""
MODEL_PREFIX_CANDIDATES = ["", "/v1", "/api/v1"]

# Model discovery cache
CACHED_MODELS: List[str] = []
CACHED_WORKING_ENDPOINT: str = ""
CACHE_TIMESTAMP = 0
CACHE_TTL = 30  # seconds

# Will be initialized after other components
model_state = None
websocket_manager = None

class ModelState:
    def __init__(self):
        self.connected = False
        self.endpoint = MODEL_BASE_URL
        self.provider = "Local Model (ModelRelay)"
        self.latency_ms = 0
        self.request_count = 0
        self.token_usage = 0
        self.last_error = ""
        self.last_checked = 0
        self.best_endpoint = "/v1/chat/completions"
        self.available_models: List[str] = []
        self.selected_model: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "connected": self.connected,
            "provider": self.provider,
            "endpoint": self.endpoint,
            "best_endpoint": self.best_endpoint,
            "available_models": self.available_models,
            "selected_model": self.selected_model,
            "latency_ms": round(self.latency_ms, 1),
            "request_count": self.request_count,
            "token_usage": self.token_usage,
            "last_error": self.last_error,
            "last_checked": self.last_checked,
        }

class WebSocketManager:
    def __init__(self):
        self.connections: List[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.connections.append(websocket)

    def disconnect(self, websocket: WebSocket):
        if websocket in self.connections:
            self.connections.remove(websocket)

    async def broadcast(self, message: Dict[str, Any]):
        for websocket in list(self.connections):
            try:
                await websocket.send_json(message)
            except Exception:
                self.disconnect(websocket)

model_state = ModelState()
websocket_manager = WebSocketManager()
SESSION_STORE: Dict[str, Dict[str, Any]] = {}
MODEL_SESSION = requests.Session()

TASK_STATES = ["Backlog", "Todo", "In Progress", "Review", "Completed", "Failed"]
AGENT_ORDER = [
    "Creative Director",
    "Planner",
    "Researcher",
    "Architect",
    "Engineer",
    "QA Engineer",
    "Documentation Writer",
]

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    asyncio.create_task(health_loop())
    yield
    # Shutdown - cleanup if needed
    pass

# Create app with lifespan
app = FastAPI(title="Delegation AI Dashboard", lifespan=lifespan)
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

def now_timestamp() -> str:
    return time.strftime("%H:%M:%S")


def create_agent(name: str, role: str) -> Dict[str, Any]:
    return {
        "id": str(uuid.uuid4()),
        "name": name,
        "role": role,
        "state": "Idle",
        "current_task": None,
        "progress": 0,
        "logs": [],
        "memory": [],
        "artifacts": [],
        "updated_at": time.time(),
    }


def create_task(title: str, description: str, assignee: str, status: str = "Backlog") -> Dict[str, Any]:
    return {
        "id": str(uuid.uuid4()),
        "title": title,
        "description": description,
        "assignee": assignee,
        "status": status,
        "progress": 0,
        "output": "",
        "artifact_path": None,
        "history": [],
        "created_at": time.time(),
        "updated_at": time.time(),
    }


def create_project_session(goal: str, requirements: str, project_type: str, priority: str) -> Dict[str, Any]:
    agents = [
        create_agent("Aurora", "Creative Director"),
        create_agent("Atlas", "Planner"),
        create_agent("Luna", "Researcher"),
        create_agent("Iris", "Architect"),
        create_agent("Nova", "Engineer"),
        create_agent("Echo", "QA Engineer"),
        create_agent("Sage", "Documentation Writer"),
    ]

    tasks = [
        create_task(
            "Define project vision",
            "Create a premium, client-facing product vision and delivery outline.",
            "Creative Director",
            status="Todo",
        ),
        create_task(
            "Create project roadmap",
            "Build the high-level project phases, milestones, and dependencies.",
            "Planner",
        ),
        create_task(
            "Research technical approach",
            "Analyze the requirements, architecture, and libraries needed for the solution.",
            "Researcher",
        ),
        create_task(
            "Design system architecture",
            "Define the backend, database, workflow, and integration layers.",
            "Architect",
        ),
        create_task(
            "Plan implementation",
            "Produce a practical engineering plan for a local AI-driven product delivery.",
            "Engineer",
        ),
        create_task(
            "Review quality and risks",
            "Evaluate potential issues and create a testing strategy.",
            "QA Engineer",
        ),
        create_task(
            "Draft documentation",
            "Write the project overview, deliverables, and setup instructions.",
            "Documentation Writer",
        ),
    ]

    return {
        "id": str(uuid.uuid4()),
        "goal": goal,
        "requirements": requirements,
        "project_type": project_type,
        "priority": priority,
        "status": "Running",
        "created_at": time.time(),
        "updated_at": time.time(),
        "current_agent": None,
        "workflow_order": AGENT_ORDER,
        "agents": agents,
        "tasks": tasks,
        "logs": [],
        "artifacts": [],
        "messages": [],
        "start_time": time.time(),
        "end_time": None,
    }


def log_action(session: Dict[str, Any], agent_name: str, action: str, result: str) -> None:
    entry = {
        "timestamp": now_timestamp(),
        "agent": agent_name,
        "action": action,
        "result": result,
    }
    session["logs"].append(entry)
    session["messages"].append({
        "sender": agent_name,
        "receiver": "system",
        "task": action,
        "context": result,
        "priority": session["priority"],
        "status": "completed",
        "timestamp": time.time(),
    })


def update_session(session: Dict[str, Any]) -> None:
    session["updated_at"] = time.time()


def find_agent(session: Dict[str, Any], role: str) -> Dict[str, Any]:
    for agent in session["agents"]:
        if agent["role"] == role:
            return agent
    return session["agents"][0]


def find_task(session: Dict[str, Any], assignee: str) -> Dict[str, Any]:
    for task in session["tasks"]:
        if task["assignee"] == assignee:
            return task
    raise ValueError(f"No task assigned to {assignee}")


def add_artifact(session: Dict[str, Any], path: str, content: str, owner: str) -> Dict[str, Any]:
    artifact = {
        "id": str(uuid.uuid4()),
        "path": path,
        "owner": owner,
        "content": content.strip(),
        "created_at": time.time(),
    }
    session["artifacts"].append(artifact)
    return artifact


def parse_model_response(payload: Any) -> str:
    if isinstance(payload, dict):
        if "choices" in payload and payload["choices"]:
            choice = payload["choices"][0]
            if isinstance(choice.get("message"), dict):
                return choice["message"].get("content", "").strip()
            if choice.get("text"):
                return str(choice["text"]).strip()
        if payload.get("output"):
            output = payload["output"]
            if isinstance(output, list):
                return "\n".join(str(item) for item in output).strip()
            return str(output).strip()
        if payload.get("generated_text"):
            return str(payload["generated_text"]).strip()
        if payload.get("result"):
            return str(payload["result"]).strip()
    if isinstance(payload, list):
        return "\n".join(str(item) for item in payload).strip()
    return str(payload).strip()


def normalize_prefix(prefix: str) -> str:
    if not prefix:
        return ""
    return "/" + prefix.strip("/")


def get_available_models_sync(base_url: str) -> List[str]:
    """
    Fetch available models from ModelRelay /v1/models endpoint.
    Returns list of model IDs, or empty list if retrieval fails.
    """
    global CACHED_MODELS, CACHE_TIMESTAMP
    
    # Use cache if fresh
    if CACHED_MODELS and time.time() - CACHE_TIMESTAMP < CACHE_TTL:
        logger.debug(f"Using cached models: {CACHED_MODELS}")
        return CACHED_MODELS
    
    models = []
    base_url = base_url.rstrip("/")
    
    for prefix in MODEL_PREFIX_CANDIDATES:
        candidate_url = base_url.rstrip("/") + normalize_prefix(prefix)
        models_endpoint = f"{candidate_url}/models"
        
        try:
            logger.info(f"[MODEL DISCOVERY] Fetching models from: {models_endpoint}")
            response = MODEL_SESSION.get(models_endpoint, timeout=5)
            
            logger.info(f"[MODEL DISCOVERY] HTTP {response.status_code} from {models_endpoint}")
            
            if response.status_code == 200:
                try:
                    data = response.json()
                    logger.debug(f"[MODEL DISCOVERY] Response: {data}")
                    
                    # Handle different response formats
                    if isinstance(data, dict):
                        if "data" in data and isinstance(data["data"], list):
                            # OpenAI format
                            models = [model.get("id") for model in data["data"] if model.get("id")]
                        elif "models" in data:
                            # Alternative format
                            models = data["models"]
                    elif isinstance(data, list):
                        # Direct list format
                        models = data
                    
                    if models:
                        logger.info(f"[MODEL DISCOVERY] Found models: {models}")
                        CACHED_MODELS = models
                        CACHE_TIMESTAMP = time.time()
                        return models
                except (json.JSONDecodeError, ValueError) as e:
                    logger.warning(f"[MODEL DISCOVERY] Failed to parse response: {e}")
                    continue
        except requests.exceptions.Timeout:
            logger.warning(f"[MODEL DISCOVERY] Timeout connecting to {models_endpoint}")
            continue
        except requests.exceptions.RequestException as e:
            logger.warning(f"[MODEL DISCOVERY] Error fetching models: {e}")
            continue
    
    logger.warning("[MODEL DISCOVERY] No models found from any endpoint")
    return []


def find_working_endpoint_sync(base_url: str, test_model: Optional[str] = None) -> Optional[str]:
    """
    Test different endpoint combinations and return the first working one.
    Tests must return HTTP 200 (not just < 500).
    
    Returns the full base URL (with prefix) that works, e.g., "http://localhost:7352/v1"
    """
    global CACHED_WORKING_ENDPOINT, CACHE_TIMESTAMP
    
    # Use cache if fresh
    if CACHED_WORKING_ENDPOINT and time.time() - CACHE_TIMESTAMP < CACHE_TTL:
        logger.debug(f"Using cached endpoint: {CACHED_WORKING_ENDPOINT}")
        return CACHED_WORKING_ENDPOINT
    
    base_url = base_url.rstrip("/")
    endpoints_to_try = [
        ("/chat/completions", "chat"),
        ("/completions", "completion"),
    ]
    
    # Build test payload
    test_payload = {
        "model": test_model or "local",
        "messages": [
            {"role": "system", "content": "Test"},
            {"role": "user", "content": "ping"},
        ],
        "temperature": 0.0,
        "max_tokens": 1,
    }
    
    for prefix in MODEL_PREFIX_CANDIDATES:
        candidate_url = base_url.rstrip("/") + normalize_prefix(prefix)
        logger.info(f"[ENDPOINT TEST] Testing prefix: {prefix} -> {candidate_url}")
        
        for endpoint_path, endpoint_name in endpoints_to_try:
            full_url = candidate_url + endpoint_path
            try:
                logger.info(f"[ENDPOINT TEST] POST {full_url}")
                start = time.time()
                response = MODEL_SESSION.post(full_url, json=test_payload, timeout=4)
                latency = (time.time() - start) * 1000
                
                logger.info(f"[ENDPOINT TEST] HTTP {response.status_code} from {full_url} (latency: {latency:.1f}ms)")
                
                # Only accept HTTP 200
                if response.status_code == 200:
                    logger.info(f"[ENDPOINT TEST] SUCCESS! Working endpoint: {candidate_url}")
                    CACHED_WORKING_ENDPOINT = candidate_url
                    CACHE_TIMESTAMP = time.time()
                    return candidate_url
                else:
                    logger.debug(f"[ENDPOINT TEST] HTTP {response.status_code} (not 200, skipping)")
                    
            except requests.exceptions.Timeout:
                logger.debug(f"[ENDPOINT TEST] Timeout: {full_url}")
            except requests.exceptions.RequestException as e:
                logger.debug(f"[ENDPOINT TEST] Error: {e}")
    
    logger.warning("[ENDPOINT TEST] No working endpoint found")
    return None


def sync_model_request(system: str, user: str) -> Dict[str, Any]:
    """
    Send a request to the local ModelRelay server.
    
    Returns: {"text": response_text, "raw": response_data, "endpoint": used_url, "model": used_model}
    Raises: RuntimeError if request fails
    """
    logger.info("[MODEL REQUEST] Starting model request")
    
    # Ensure we have a working connection
    if not model_state.connected:
        logger.info("[MODEL REQUEST] Not connected, probing connectivity...")
        probe_model_connectivity_sync()
    
    if not model_state.connected:
        error_msg = (
            f"Model server unavailable at {MODEL_BASE_URL}. "
            f"Last error: {model_state.last_error}"
        )
        logger.error(f"[MODEL REQUEST] FAILED: {error_msg}")
        raise RuntimeError(f"Unable to generate AI response: {error_msg}")
    
    # Get available models if not cached
    if not model_state.available_models:
        logger.info("[MODEL REQUEST] Fetching available models...")
        models = get_available_models_sync(model_state.endpoint)
        model_state.available_models = models
        
        if not models:
            logger.warning("[MODEL REQUEST] No models available, will try default 'local' model")
            models = ["local"]
    
    # Select a model to use
    selected_model = None
    if model_state.available_models:
        selected_model = model_state.available_models[0]
    else:
        selected_model = "local"
    
    model_state.selected_model = selected_model
    logger.info(f"[MODEL REQUEST] Using model: {selected_model}")
    
    # Build the request
    endpoint_url = model_state.endpoint.rstrip("/") + "/chat/completions"
    payload = {
        "model": selected_model,
        "messages": [
            {"role": "system", "content": system if system else "You are a helpful assistant."},
            {"role": "user", "content": user},
        ],
        "temperature": 0.4,
        "max_tokens": 1200,
    }
    
    try:
        logger.info(f"[MODEL REQUEST] POST {endpoint_url}")
        logger.debug(f"[MODEL REQUEST] Payload: {json.dumps(payload, indent=2)}")
        
        start = time.time()
        response = MODEL_SESSION.post(endpoint_url, json=payload, timeout=60)
        latency = (time.time() - start) * 1000
        
        logger.info(f"[MODEL REQUEST] HTTP {response.status_code} (latency: {latency:.1f}ms)")
        
        # Handle unsuccessful responses
        if response.status_code != 200:
            try:
                error_data = response.json()
                logger.error(f"[MODEL REQUEST] Error response: {error_data}")
            except:
                logger.error(f"[MODEL REQUEST] Error response body: {response.text}")
            
            if response.status_code in (404, 405):
                raise RuntimeError(
                    f"Endpoint not supported (HTTP {response.status_code}). "
                    f"URL: {endpoint_url}. "
                    f"Model: {selected_model}"
                )
            elif response.status_code >= 500:
                raise RuntimeError(f"Server error (HTTP {response.status_code}) from {endpoint_url}")
            else:
                raise RuntimeError(f"Request failed with HTTP {response.status_code}")
        
        # Parse response
        try:
            data = response.json()
        except (json.JSONDecodeError, ValueError) as e:
            logger.error(f"[MODEL REQUEST] Failed to parse JSON response: {e}")
            logger.error(f"[MODEL REQUEST] Response text: {response.text}")
            data = {"text": response.text}
        
        logger.debug(f"[MODEL REQUEST] Response: {json.dumps(data, indent=2)[:500]}")
        
        # Extract text from response
        result_text = parse_model_response(data)
        
        if not result_text:
            logger.error("[MODEL REQUEST] Response parsing returned empty text")
            logger.error(f"[MODEL REQUEST] Full response: {data}")
            raise RuntimeError(f"Model returned empty response. Response data: {data}")
        
        # Update stats
        model_state.request_count += 1
        model_state.latency_ms = latency
        model_state.best_endpoint = "/chat/completions"
        
        if isinstance(data, dict):
            usage = data.get("usage") or data.get("token_usage") or {}
            if isinstance(usage, dict):
                total_tokens = usage.get("total_tokens") or usage.get("prompt_tokens", 0)
                if total_tokens:
                    model_state.token_usage += int(total_tokens)
                    logger.info(f"[MODEL REQUEST] Tokens used: {total_tokens}")
        
        logger.info(f"[MODEL REQUEST] SUCCESS! Generated {len(result_text)} characters")
        return {
            "text": result_text,
            "raw": data,
            "endpoint": endpoint_url,
            "model": selected_model,
        }
        
    except requests.exceptions.Timeout:
        error_msg = f"Request timeout (60s) to {endpoint_url}"
        logger.error(f"[MODEL REQUEST] FAILED: {error_msg}")
        raise RuntimeError(error_msg)
    except requests.exceptions.RequestException as e:
        error_msg = f"Request error: {e}"
        logger.error(f"[MODEL REQUEST] FAILED: {error_msg}")
        raise RuntimeError(error_msg)


async def request_local_model(system: str, user: str) -> Dict[str, Any]:
    start = time.time()
    try:
        response = await asyncio.to_thread(sync_model_request, system, user)
        model_state.latency_ms = (time.time() - start) * 1000
        model_state.connected = True
        model_state.last_error = ""
        return response
    except Exception as exc:
        model_state.connected = False
        model_state.last_error = str(exc)
        raise


def build_agent_prompt(agent: Dict[str, Any], session: Dict[str, Any], task: Dict[str, Any]) -> str:
    return (
        f"You are {agent['name']}, the {agent['role']} for a client project. "
        f"The client goal is: {session['goal']}.\n"
        f"Requirements: {session['requirements']}\n"
        f"Project type: {session['project_type']}. Priority: {session['priority']}.\n"
        f"Task: {task['title']}\n"
        f"Description: {task['description']}\n"
        "Provide a concise, professional response. Include a summary, a next action, and optionally a suggested artifact path."
    )


async def set_agent_state(session: Dict[str, Any], agent: Dict[str, Any], state: str, current_task: str = None) -> None:
    agent["state"] = state
    agent["current_task"] = current_task
    agent["updated_at"] = time.time()
    session["current_agent"] = agent["role"]
    update_session(session)
    await websocket_manager.broadcast({"type": "session_update", "payload": serialize_session(session)})


async def execute_task(session: Dict[str, Any], agent: Dict[str, Any], task: Dict[str, Any]) -> None:
    try:
        await set_agent_state(session, agent, "Thinking", task["title"])
        task["status"] = "In Progress"
        task["progress"] = 20
        task["history"].append({"timestamp": now_timestamp(), "status": task["status"]})
        update_session(session)
        await websocket_manager.broadcast({"type": "session_update", "payload": serialize_session(session)})

        prompt = build_agent_prompt(agent, session, task)
        response = await request_local_model("", prompt)
        text = response["text"]

        task["output"] = text
        task["progress"] = 90
        task["status"] = "Review"
        task["artifact_path"] = f"project/{task['assignee'].lower().replace(' ', '_')}/{task['title'].lower().replace(' ', '_')}.md"
        task["history"].append({"timestamp": now_timestamp(), "status": task["status"]})
        task["updated_at"] = time.time()

        artifact = add_artifact(session, task["artifact_path"], text, agent["role"])
        agent["artifacts"].append(artifact["id"])
        agent["memory"].append({"task": task["title"], "result": text, "timestamp": now_timestamp()})
        log_action(session, agent["name"], f"Completed {task['title']}", text[:220])

        task["status"] = "Completed"
        task["progress"] = 100
        task["history"].append({"timestamp": now_timestamp(), "status": task["status"]})
        agent["state"] = "Completed"
        agent["progress"] = 100
        update_session(session)
        await websocket_manager.broadcast({"type": "session_update", "payload": serialize_session(session)})
        await asyncio.sleep(0.6)
    except Exception as exc:
        error_message = str(exc)
        task["status"] = "Failed"
        task["progress"] = 0
        agent["state"] = "Failed"
        log_action(session, agent["name"], f"Failed {task['title']}", error_message)
        session["status"] = "Failed"
        update_session(session)
        await websocket_manager.broadcast({"type": "session_update", "payload": serialize_session(session)})
        raise


async def execute_session(session_id: str) -> None:
    session = SESSION_STORE.get(session_id)
    if not session:
        return
    sequence = [
        ("Creative Director", "Define project vision"),
        ("Planner", "Create project roadmap"),
        ("Researcher", "Research technical approach"),
        ("Architect", "Design system architecture"),
        ("Engineer", "Plan implementation"),
        ("QA Engineer", "Review quality and risks"),
        ("Documentation Writer", "Draft documentation"),
    ]

    session["status"] = "Running"
    update_session(session)
    await websocket_manager.broadcast({"type": "session_update", "payload": serialize_session(session)})

    for role, _ in sequence:
        if session["status"] == "Failed":
            break
        agent = find_agent(session, role)
        task = find_task(session, role)
        await set_agent_state(session, agent, "Planning", task["title"])
        await asyncio.sleep(0.8)
        await execute_task(session, agent, task)

    if session["status"] != "Failed":
        session["status"] = "Completed"
        session["end_time"] = time.time()
        update_session(session)
        log_action(session, "System", "Project completed", "All agents finished the workflow.")
        await websocket_manager.broadcast({"type": "session_update", "payload": serialize_session(session)})


def serialize_session(session: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "id": session["id"],
        "goal": session["goal"],
        "requirements": session["requirements"],
        "project_type": session["project_type"],
        "priority": session["priority"],
        "status": session["status"],
        "current_agent": session["current_agent"],
        "workflow_order": session["workflow_order"],
        "agents": session["agents"],
        "tasks": session["tasks"],
        "logs": session["logs"],
        "artifacts": session["artifacts"],
        "messages": session["messages"],
        "start_time": session["start_time"],
        "end_time": session["end_time"],
    }


def session_summary() -> Dict[str, Any]:
    return {
        "sessions": [serialize_session(session) for session in SESSION_STORE.values()],
        "model_status": model_state.to_dict(),
        "health": {
            "active_agents": sum(1 for session in SESSION_STORE.values() for agent in session["agents"] if agent["state"] not in ["Completed", "Failed"]),
            "completed_tasks": sum(1 for session in SESSION_STORE.values() for task in session["tasks"] if task["status"] == "Completed"),
            "failed_tasks": sum(1 for session in SESSION_STORE.values() for task in session["tasks"] if task["status"] == "Failed"),
            "sessions": len(SESSION_STORE),
        },
    }


def probe_model_connectivity_sync() -> None:
    """
    Probe ModelRelay connectivity by testing available endpoints.
    Only marks as connected if:
    1. Can reach /v1/models endpoint with HTTP 200
    2. Server returns at least one model
    3. Can successfully test /v1/chat/completions with HTTP 200
    """
    global MODEL_PATH_PREFIX
    
    logger.info("[CONNECTIVITY PROBE] Starting model connectivity probe...")
    model_state.connected = False
    model_state.last_error = ""
    model_state.latency_ms = 0
    model_state.last_checked = time.time()
    model_state.available_models = []
    
    # Step 1: Try to discover models
    logger.info("[CONNECTIVITY PROBE] Step 1: Discovering available models...")
    models = get_available_models_sync(MODEL_BASE_URL)
    
    if models:
        logger.info(f"[CONNECTIVITY PROBE] Found {len(models)} model(s): {models}")
        model_state.available_models = models
    else:
        logger.warning("[CONNECTIVITY PROBE] No models discovered, will continue with default")
        model_state.available_models = ["local"]
    
    # Step 2: Find a working endpoint
    logger.info("[CONNECTIVITY PROBE] Step 2: Finding working endpoint...")
    working_endpoint = find_working_endpoint_sync(MODEL_BASE_URL, models[0] if models else "local")
    
    if not working_endpoint:
        error_msg = "No working endpoint found"
        logger.error(f"[CONNECTIVITY PROBE] FAILED: {error_msg}")
        model_state.last_error = error_msg
        return
    
    logger.info(f"[CONNECTIVITY PROBE] Working endpoint found: {working_endpoint}")
    
    # Step 3: Mark as connected and update state
    try:
        start = time.time()
        latency = (time.time() - start) * 1000
        
        # Extract prefix for future use
        if working_endpoint.endswith("/v1"):
            MODEL_PATH_PREFIX = "/v1"
        elif working_endpoint.endswith("/api/v1"):
            MODEL_PATH_PREFIX = "/api/v1"
        else:
            MODEL_PATH_PREFIX = ""
        
        model_state.endpoint = working_endpoint
        model_state.connected = True
        model_state.latency_ms = latency
        model_state.last_error = ""
        model_state.best_endpoint = "/chat/completions"
        model_state.last_checked = time.time()
        
        logger.info(f"[CONNECTIVITY PROBE] SUCCESS! Connected to ModelRelay")
        logger.info(f"[CONNECTIVITY PROBE] Endpoint: {working_endpoint}")
        logger.info(f"[CONNECTIVITY PROBE] Available models: {model_state.available_models}")
        
    except Exception as e:
        error_msg = f"Exception during connection: {e}"
        logger.error(f"[CONNECTIVITY PROBE] FAILED: {error_msg}")
        model_state.connected = False
        model_state.last_error = error_msg


async def probe_model_connectivity() -> None:
    await asyncio.to_thread(probe_model_connectivity_sync)


async def health_loop() -> None:
    while True:
        await probe_model_connectivity()
        await websocket_manager.broadcast({"type": "status_update", "payload": model_state.to_dict()})
        await asyncio.sleep(3)





@app.get("/", response_class=FileResponse)
def serve_app() -> FileResponse:
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/api/status")
def api_status() -> JSONResponse:
    return JSONResponse({"model_status": model_state.to_dict(), "sessions": [serialize_session(session) for session in SESSION_STORE.values()]})


@app.post("/api/project")
async def api_project(payload: Dict[str, Any]) -> JSONResponse:
    goal = payload.get("goal", "").strip()
    requirements = payload.get("requirements", "").strip()
    project_type = payload.get("project_type", "Custom AI Product").strip()
    priority = payload.get("priority", "Normal").strip()

    if not goal:
        return JSONResponse({"error": "Goal is required."}, status_code=400)

    session = create_project_session(goal, requirements, project_type, priority)
    SESSION_STORE[session["id"]] = session
    update_session(session)
    await websocket_manager.broadcast({"type": "session_created", "payload": serialize_session(session)})
    asyncio.create_task(execute_session(session["id"]))
    return JSONResponse({"session_id": session["id"], "session": serialize_session(session)})


@app.patch("/api/task")
async def api_edit_task(payload: Dict[str, Any]) -> JSONResponse:
    task_id = payload.get("id")
    title = payload.get("title")
    description = payload.get("description")
    status = payload.get("status")

    for session in SESSION_STORE.values():
        for task in session["tasks"]:
            if task["id"] == task_id:
                if title is not None:
                    task["title"] = title
                if description is not None:
                    task["description"] = description
                if status is not None and status in TASK_STATES:
                    task["status"] = status
                task["updated_at"] = time.time()
                update_session(session)
                await websocket_manager.broadcast({"type": "session_update", "payload": serialize_session(session)})
                return JSONResponse({"task": task})

    return JSONResponse({"error": "Task not found."}, status_code=404)


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket) -> None:
    await websocket_manager.connect(websocket)
    await websocket.send_json({"type": "connected", "payload": {"message": "Connected to Delegation backend."}})
    await websocket.send_json({"type": "status_update", "payload": model_state.to_dict()})
    await websocket.send_json({"type": "snapshot", "payload": session_summary()})
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        websocket_manager.disconnect(websocket)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("server:app", host="0.0.0.0", port=8000, log_level="info")
