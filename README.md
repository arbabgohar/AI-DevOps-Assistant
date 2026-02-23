## AI DevOps Assistant

AI DevOps Assistant is a FastAPI + React app that analyzes system logs with an LLM and surfaces actionable recommendations. It also exposes live system health metrics and supports automatic log pulling for hands-free demos.

### Highlights

- AI log analysis using OpenAI GPT-4o-mini via LangChain
- Live system health metrics (CPU, memory, disk) — auto-refreshed every 10 s
- Background log ingestion from a file with rotation/truncation detection
- Clean dark dashboard with manual paste and auto-pull modes

### Tech Stack

| Layer    | Technology                              |
| -------- | --------------------------------------- |
| Backend  | Python · FastAPI · LangChain · psutil   |
| AI       | OpenAI GPT-4o-mini via langchain-openai |
| Frontend | React 19 · Vite · Tailwind CSS          |

---

### Quickstart

#### 1. Backend

```bash
python -m venv venv
source venv/bin/activate   # Windows: venv\Scripts\activate
pip install -r requirements.txt
```

Create a `.env` file (copy from `.env.example`):

```
OPENAI_API_KEY=your-openai-key

# Optional – enables auto log-pull mode
LOG_FILE_PATH=/path/to/your/logfile.log
LOG_POLL_INTERVAL=1.0
LOG_MAX_LINES=500

# CORS – add your frontend origin if different
ALLOWED_ORIGINS=http://localhost:5173,http://127.0.0.1:5173

# Optional – defaults to OS root drive
DISK_PATH=/
```

Start the server:

```bash
uvicorn main:app --reload
```

#### 2. Frontend

```bash
cd ai-devops-dashboard
npm install
npm run dev
```

Create `ai-devops-dashboard/.env` (copy from `.env.example`):

```
VITE_API_BASE_URL=http://127.0.0.1:8000
```

Open [http://localhost:5173](http://localhost:5173).

---

### Demo Flow

**Manual mode** — paste any log text and click **Analyze Log**.  
**Auto mode** — set `LOG_FILE_PATH` in `.env`, click **Pull Latest Logs**, then **Analyze Latest Logs**.

Use **Load Sample Logs** in manual mode for an instant demo without a real log file.

---

### API Reference

| Method | Route             | Description                              |
| ------ | ----------------- | ---------------------------------------- |
| GET    | `/`               | API status                               |
| GET    | `/health`         | Live system metrics (CPU, memory, disk)  |
| POST   | `/analyze-log`    | Analyze pasted log text (max 50 000 chars) |
| GET    | `/log-source`     | Log ingestion status and config          |
| GET    | `/latest-log`     | Latest lines from the background buffer  |
| POST   | `/analyze-latest` | Analyze the buffered log text            |

Interactive docs available at [http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs) when the backend is running.

---

### Repo Layout

```
ai-devops-dashboard/   React + Vite frontend
main.py                FastAPI entry point
log_agent.py           LangChain LLM prompt and analysis
log_ingest.py          Background file-based log ingestion
monitor.py             System health metrics (psutil)
requirements.txt       Python dependencies
```

---

### Notes

- `LOG_FILE_PATH` is optional. If not set, manual mode still works.
- Disk metrics use `DISK_PATH` if set; otherwise defaults to the OS root drive.
- The AI prompt instructs the model to respond with **Summary**, **Issues Found**, and **Recommended Actions** sections.

---

## ClawOps Copilot Architecture

Version 2 of this project upgrades the assistant into a structured AI DevOps Copilot with controlled execution capabilities.

### New Folder Structure

```
AI-DevOps-Assistant/
├── main.py               FastAPI entry point (+ /analyze-structured)
├── log_agent.py          LLM chains: free-form + structured JSON
├── log_ingest.py         Background file log ingestion
├── monitor.py            System health metrics
├── action_router.py      Guarded execution layer + audit logging
├── cli.py                Typer CLI entry point (clawops)
├── requirements.txt      Python dependencies
│
├── schemas/
│   ├── __init__.py
│   └── llm_response.py   Pydantic models: LLMAnalysisResponse, AllowedAction
│
└── plugins/
    ├── __init__.py        Plugin registry (dynamic, lazy-init)
    ├── base_plugin.py     Abstract BasePlugin interface
    ├── k8s_plugin.py      Kubernetes plugin (pods, logs, restart)
    └── docker_plugin.py   Docker plugin (containers, restart)
```

### Security Architecture

```
Log text
   │
   ▼
log_agent.analyze_log_structured()
   │  (LLM output parsed as JSON)
   ▼
schemas.LLMAnalysisResponse   ◄── Pydantic validation gate
   │  (fails here → None returned, nothing executes)
   ▼
action_router.route_action()
   ├── Gate 1: ALLOWLIST check   (hardcoded set, not config-driven)
   ├── Gate 2: approved=True     (explicit operator flag)
   ├── Gate 3: Plugin RBAC check (validate_permissions())
   └── Gate 4: Plugin dispatch   (execute_action())
         │
         ▼
   audit.log  (every attempt recorded, append-only)
```

**Key invariants:**

- Free-form LLM text **never** reaches the execution layer.
- The action allowlist (`ALLOWLIST` in `action_router.py`) is a hardcoded `frozenset` – it cannot be expanded via config files or LLM prompts.
- Every execution attempt is audit-logged with a timestamp, action token, parameter hash, and outcome.
- RBAC is checked before every action via `SelfSubjectAccessReview` (Kubernetes) or daemon ping (Docker).

### CLI Reference

Install dependencies then run:

```bash
pip install -r requirements.txt
python cli.py --help
```

Or add to `pyproject.toml` scripts for `clawops` as an entry point:

```
clawops k8s pods      [--namespace TEXT]
clawops k8s analyze   [--namespace TEXT] [--json]
clawops k8s logs      <pod> [--namespace TEXT] [--tail INT] [--analyze]
clawops k8s restart   <pod> [--namespace TEXT] [--yes]

clawops docker ps
clawops docker analyze  [--json]

clawops logs analyze  <log-file>  [--structured] [--execute] [--yes] [--json]

clawops monitor
```

### Updated API Reference

| Method | Route                 | Description                                           |
| ------ | --------------------- | ----------------------------------------------------- |
| GET    | `/`                   | API status                                            |
| GET    | `/health`             | Live system metrics (CPU, memory, disk)               |
| POST   | `/analyze-log`        | Free-form AI analysis (plain text response)           |
| GET    | `/log-source`         | Log ingestion status and config                       |
| GET    | `/latest-log`         | Latest lines from the background buffer               |
| POST   | `/analyze-latest`     | Free-form analysis of the buffered log                |
| POST   | `/analyze-structured` | Validated structured JSON response (LLMAnalysisResponse) |

### Plugin Architecture

Each plugin implements the `BasePlugin` interface:

```python
class BasePlugin(ABC):
    name: str                          # Registry key
    get_state()   -> dict              # Read-only snapshot
    analyze()     -> dict              # AI-powered diagnosis (no mutations)
    execute_action(action, params, *, approved) -> dict  # Write path
    validate_permissions() -> dict[str, bool]            # RBAC pre-check
```

New plugins are registered in `plugins/__init__.py`:

```python
registry.register_named("myplugin", MyPlugin)
```

### Kubernetes RBAC Setup

Minimum namespace-scoped Role required:

```yaml
apiVersion: rbac.authorization.k8s.io/v1
kind: Role
metadata:
  namespace: default
  name: clawops-reader
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

Do **not** grant `cluster-admin`. Namespace-scope the `RoleBinding`.
