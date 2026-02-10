## AI DevOps Assistant

AI DevOps Assistant is a FastAPI + React app that analyzes system logs with an LLM and surfaces actionable recommendations. It also exposes live system health metrics and supports automatic log pulling for hands‑free demos.

### Highlights

- AI log analysis using OpenAI + LangChain
- System health metrics (CPU, memory, disk)
- Automatic log pulling from a file
- Clean dashboard UI with manual and auto modes

### Quickstart

#### 1) Backend

```bash
python -m venv venv
source venv/bin/activate  # or venv\Scripts\activate on Windows
pip install -r requirements.txt
```

Create a `.env` file (see `.env.example`):

```
OPENAI_API_KEY=your-openai-key
LOG_FILE_PATH=/path/to/your/logfile.log
LOG_POLL_INTERVAL=1.0
LOG_MAX_LINES=500
ALLOWED_ORIGINS=http://localhost:5173,http://127.0.0.1:5173
```

Run the backend:

```bash
uvicorn main:app --reload
```

#### 2) Frontend

```bash
cd ai-devops-dashboard
npm install
npm run dev
```

Create `ai-devops-dashboard/.env` (see `.env.example`):

```
VITE_API_BASE_URL=http://127.0.0.1:8000
```

Open `http://localhost:5173`.

### Demo Flow

- Manual mode: paste logs, click **Analyze Log**.
- Auto mode: set `LOG_FILE_PATH`, click **Pull Latest Logs**, then **Analyze Latest Logs**.

### API Endpoints

| Method | Route             | Description                         |
| ------ | ----------------- | ----------------------------------- |
| GET    | `/`               | API status                          |
| GET    | `/health`         | System metrics                      |
| POST   | `/analyze-log`    | Analyze pasted log text             |
| GET    | `/log-source`     | Log ingestion status                |
| GET    | `/latest-log`     | Latest buffered log text            |
| POST   | `/analyze-latest` | Analyze buffered log text           |

### Repo Layout

```
ai-devops-dashboard/  # React + Vite frontend
main.py               # FastAPI entrypoint
log_agent.py          # LLM prompt + analysis
log_ingest.py         # File-based log ingestion
monitor.py            # System health metrics
```

### Notes

- `LOG_FILE_PATH` is optional. If not set, manual mode still works.
- Disk metrics use `DISK_PATH` if provided; otherwise use the OS root.
