from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from monitor import get_system_metrics
from log_agent import analyze_log

app = FastAPI(
    title="AI DevOps Assistant",
    description="A FastAPI service for system monitoring and log analysis",
    version="1.0.0"
)

class LogInput(BaseModel):
    log: str

@app.get("/")
async def root():
    """Root endpoint that returns a status message."""
    return {"status": "running", "message": "AI DevOps Assistant is operational"}

@app.get("/health")
async def health():
    """Health endpoint that returns system metrics."""
    try:
        metrics = get_system_metrics()
        return {
            "status": "healthy",
            "metrics": metrics
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/analyze-log")
async def analyze_log_endpoint(log_input: LogInput):
    """
    Analyze log endpoint that takes a log text and returns AI recommendations.
    
    Args:
        log_input (LogInput): The log text to analyze
        
    Returns:
        dict: Analysis results and recommendations
    """
    try:
        recommendation = analyze_log(log_input.log)
        return {
            "status": "success",
            "recommendation": recommendation
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) 