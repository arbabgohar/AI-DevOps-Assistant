# ClawOps – AI DevOps Copilot

An AI-powered DevOps assistant with structured execution capabilities. Analyze system logs, monitor infrastructure health, inspect Kubernetes pods and Docker containers, and trigger guarded remediations — all from a React dashboard or a terminal CLI.

### Highlights

- AI log analysis via OpenAI GPT-4o-mini — free-form and structured JSON modes
- Structured action system: LLM output is Pydantic-validated before anything executes
- Guarded execution layer with an allowlist, approval gate, RBAC check, and audit log
- Typer CLI (`clawops`) — works without a running HTTP server
- Kubernetes plugin: list pods, fetch logs, detect CrashLoopBackOff, restart pods
- Docker plugin: list containers, detect unhealthy state, restart containers
- Extensible plugin registry — drop in a new `BasePlugin` subclass to add a platform
- Live system health metrics (CPU, memory, disk) auto-refreshed every 10 s
- Background log ingestion from a file with rotation/truncation detection
- Clean dark React dashboard with manual paste and auto-pull modes

---

## Tech Stack

| Layer     | Technology                                          |
| --------- | --------------------------------------------------- |
| Backend   | Python · FastAPI · LangChain · psutil               |
| AI        | OpenAI GPT-4o-mini via langchain-openai             |
| CLI       | Typer · Rich                                        |
| Plugins   | kubernetes (official client) · docker SDK           |
| Frontend  | React 19 · Vite · Tailwind CSS                      |

---

## Repo Layout

```
AI-DevOps-Assistant/
├── main.py               FastAPI entry point
├── log_agent.py          LLM chains: free-form + structured JSON
├── log_ingest.py         Background file-based log ingestion
├── monitor.py            System health metrics (psutil)
├── action_router.py      Guarded execution layer + audit logging
├── cli.py                Typer CLI (clawops)
├── requirements.txt      Python dependencies
│
├── schemas/
│   ├── __init__.py
│   └── llm_response.py   Pydantic models: LLMAnalysisResponse, AllowedAction
│
├── plugins/
│   ├── __init__.py        PluginRegistry – dynamic, lazy-init
│   ├── base_plugin.py     Abstract BasePlugin interface
│   ├── k8s_plugin.py      Kubernetes plugin
│   └── docker_plugin.py   Docker plugin
│
└── ai-devops-dashboard/   React + Vite frontend
```

---

## Quickstart

### 1. Backend

```bash
python -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate
pip install -r requirements.txt
```

Create a `.env` file (copy from `.env.example`):

```env
OPENAI_API_KEY=your-openai-key

# Optional – enables auto log-pull mode
LOG_FILE_PATH=/path/to/your/logfile.log
LOG_POLL_INTERVAL=1.0
LOG_MAX_LINES=500

# CORS – add your frontend origin if different
ALLOWED_ORIGINS=http://localhost:5173,http://127.0.0.1:5173

# Optional – defaults to OS root drive
DISK_PATH=/

# Optional – path for the action audit log (default: audit.log)
CLAWOPS_AUDIT_LOG=audit.log
```

Start the API server:

```bash
uvicorn main:app --reload
```

### 2. Frontend

```bash
cd ai-devops-dashboard
npm install
npm run dev
```

Create `ai-devops-dashboard/.env`:

```env
VITE_API_BASE_URL=http://127.0.0.1:8000
```

Open [http://localhost:5173](http://localhost:5173).

### 3. CLI (no server required)

```bash
python cli.py --help
```

---

## CLI Reference

The `clawops` CLI talks directly to backend logic — no HTTP server needed.

```
clawops monitor                                          System health metrics

clawops k8s pods      [--namespace TEXT]                List pods + health
clawops k8s analyze   [--namespace TEXT] [--json]       Analyze all pods
clawops k8s logs      <pod> [--namespace TEXT]          Fetch pod logs
                           [--tail INT] [--analyze]
clawops k8s restart   <pod> [--namespace TEXT] [--yes]  Restart a pod (guarded)

clawops docker ps                                        List containers
clawops docker analyze  [--json]                        Analyze containers

clawops logs analyze  <log-file>                        Free-form AI analysis
                      [--structured]                    Structured JSON output
                      [--execute] [--yes] [--json]      Route suggested action
```

Every destructive command (`k8s restart`, `logs analyze --execute`) passes through the action router with an interactive confirmation prompt unless `--yes` is supplied. All executions are recorded in `audit.log`.

---

## API Reference

| Method | Route                 | Description                                              |
| ------ | --------------------- | -------------------------------------------------------- |
| GET    | `/`                   | API status                                               |
| GET    | `/health`             | Live system metrics (CPU, memory, disk)                  |
| POST   | `/analyze-log`        | Free-form AI analysis — plain text response              |
| GET    | `/log-source`         | Log ingestion status and config                          |
| GET    | `/latest-log`         | Latest lines from the background buffer                  |
| POST   | `/analyze-latest`     | Free-form analysis of the buffered log                   |
| POST   | `/analyze-structured` | Validated structured JSON (`LLMAnalysisResponse`)        |

Interactive docs: [http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs)

### `/analyze-structured` response shape

```json
{
  "status": "success",
  "analysis": {
    "issue_summary": "Pod web-abc is crash-looping due to missing env var.",
    "probable_cause": "DATABASE_URL is not set in the container environment.",
    "suggested_action": {
      "action": "restart_pod",
      "parameters": { "pod": "web-abc", "namespace": "default" }
    }
  }
}
```

`action` is always one of `restart_pod` · `restart_container` · `no_action`. Any other value is rejected by Pydantic before the response is returned.

---

## Security Architecture

```
Log text
   │
   ▼
log_agent.analyze_log_structured()
   │  LLM output stripped and parsed as JSON
   ▼
schemas.LLMAnalysisResponse   ◄── Pydantic validation gate
   │  fails → None returned, nothing executes
   ▼
action_router.route_action()
   ├── Gate 1: ALLOWLIST check      hardcoded frozenset, not config-driven
   ├── Gate 2: approved=True        explicit operator flag required
   ├── Gate 3: RBAC pre-check       plugin.validate_permissions()
   └── Gate 4: Plugin dispatch      plugin.execute_action()
         │
         ▼
   audit.log   timestamp · action · param hash · outcome
```

**Key invariants**

- Free-form LLM text **never** reaches the execution layer.
- `ALLOWLIST` in `action_router.py` is a hardcoded `frozenset` — it cannot be extended via config files or LLM prompts.
- Every routing attempt (success, rejection, or error) is appended to `audit.log`.
- Kubernetes RBAC is verified via `SelfSubjectAccessReview` before every action.
- No `eval()`, no `exec()`, no `subprocess` calls from LLM output.

---

## Plugin Architecture

Each plugin subclasses `BasePlugin` and implements four methods:

```python
class BasePlugin(ABC):
    name: str                                                  # registry key
    get_state()  -> dict                                       # read-only snapshot
    analyze()    -> dict                                       # diagnosis (no mutations)
    execute_action(action, params, *, approved) -> dict        # write path
    validate_permissions() -> dict[str, bool]                  # RBAC pre-check
```

Register a new plugin in `plugins/__init__.py`:

```python
registry.register_named("mypluform", MyPlatformPlugin)
```

The registry is lazy — constructors are called at `registry.get()` time, so a missing optional dependency (e.g. `kubernetes` not installed) disables only that plugin without breaking the rest of the application.

---

## Kubernetes RBAC Setup

Minimum namespace-scoped permissions required:

```yaml
apiVersion: rbac.authorization.k8s.io/v1
kind: Role
metadata:
  namespace: default
  name: clawops-role
rules:
  - apiGroups: [""]
    resources: ["pods"]
    verbs: ["get", "list", "delete"]
  - apiGroups: [""]
    resources: ["pods/log"]
    verbs: ["get"]
---
apiVersion: rbac.authorization.k8s.io/v1
kind: ClusterRole
metadata:
  name: clawops-sar
rules:
  - apiGroups: ["authorization.k8s.io"]
    resources: ["selfsubjectaccessreviews"]
    verbs: ["create"]
```

Do **not** grant `cluster-admin`. Bind the Role to a namespace-scoped `RoleBinding`.

---

## Dashboard Demo Flow

**Manual mode** — paste any log text and click **Analyze Log**.  
**Auto mode** — set `LOG_FILE_PATH` in `.env`, click **Pull Latest Logs**, then **Analyze Latest Logs**.  
Use **Load Sample Logs** in manual mode for an instant demo without a real log file.
