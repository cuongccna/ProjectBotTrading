from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from dashboard.routers import health, pipeline, risk, decisions, positions, alerts
from human_review.router import router as review_router

app = FastAPI(
    title="Institutional Trading Dashboard API",
    description="Operational control panel for monitoring system health, risk, and decisions.",
    version="1.0.0",
)

# CORS (Allow local frontend development)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], # Restrict in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include Routers
app.include_router(health.router)
app.include_router(pipeline.router)
app.include_router(risk.router)
app.include_router(decisions.router)
app.include_router(positions.router)
app.include_router(alerts.router)
app.include_router(review_router)

@app.get("/")
def root():
    return {"status": "ok", "message": "Trading Dashboard API is running"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
