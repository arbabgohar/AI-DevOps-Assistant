import os
from contextlib import asynccontextmanager

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

load_dotenv()

from monitor import get_system_metrics
from log_agent import analyze_log
from log_ingest import LogIngestor

log_ingestor: LogIngestor | None = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Manage startup and graceful shutdown of background services."""
    global log_ingestor
    log_file_path = os.getenv("LOG_FILE_PATH")
    if log_file_path:
        poll_interval = float(os.getenv("LOG_POLL_INTERVAL", "1.0"))
        max_lines = int(os.getenv("LOG_MAX_LINES", "500"))
        log_ingestor = LogIngestor(
            path=log_file_path,
            poll_interval=poll_interval,
            max_lines=max_lines,
        )
        log_ingestor.start()
    yield
    if log_ingestor:
        log_ingestor.stop()


app = FastAPI(
    title="AI DevOps Assistant",
    description="A FastAPI service for system monitoring and AI-powered log analysis.",
    version="1.0.0",
    lifespan=lifespan,
)

allowed_origins = [
    origin.strip()
    for origin in os.getenv(
        "ALLOWED_ORIGINS",
        "http://localhost:5173,http://127.0.0.1:5173",
    ).split(",")
    if origin.strip()
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class LogInput(BaseModel):
    log: str = Field(..., min_length=1, max_length=50_000, description="Log text to analyze (max 50 000 chars)")


@app.get("/")
async def root():
    return {"status": "running", "message": "AI DevOps Assistant is operational"}


@app.get("/health")
async def health():
    """Return live system metrics (CPU, memory, disk)."""
    try:
        metrics = get_system_metrics()
        return {"status": "healthy", "metrics": metrics}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/analyze-log")
async def analyze_log_endpoint(log_input: LogInput):
    """Analyze pasted log text and return AI recommendations."""
    try:
        recommendation = analyze_log(log_input.log)
        return {"status": "success", "recommendation": recommendation}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/log-source")
async def log_source_status():
    """Return log ingestion status and configuration."""
    if not log_ingestor:
        return {"status": "disabled", "message": "LOG_FILE_PATH not configured"}
    return {"status": "enabled", "source": log_ingestor.status()}


@app.get("/latest-log")
async def latest_log():
    """Return the latest buffered log text from the background ingestor."""
    if not log_ingestor:
        raise HTTPException(status_code=404, detail="LOG_FILE_PATH not configured")
    return {"status": "success", "log": log_ingestor.get_text()}


@app.post("/analyze-latest")
async def analyze_latest_log():
    """Analyze the latest buffered log text using the AI agent."""
    if not log_ingestor:
        raise HTTPException(status_code=404, detail="LOG_FILE_PATH not configured")
    log_text = log_ingestor.get_text()
    if not log_text.strip():
        raise HTTPException(status_code=400, detail="No log data buffered yet")
    try:
        recommendation = analyze_log(log_text)
        return {"status": "success", "recommendation": recommendation}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
