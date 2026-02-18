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
