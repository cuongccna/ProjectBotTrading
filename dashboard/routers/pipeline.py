from fastapi import APIRouter, HTTPException, Depends
from sqlalchemy.orm import Session
from database.engine import get_session
from dashboard.services import DashboardService
from dashboard.schemas import PipelineVisibilityResponse

router = APIRouter(prefix="/pipeline", tags=["Data Pipeline"])

def get_db():
    db = get_session()
    try:
        yield db
    finally:
        db.close()

@router.get("/stats", response_model=PipelineVisibilityResponse)
def get_pipeline_stats(db: Session = Depends(get_db)):
    """
    Get data pipeline statistics (counts, freshness) within last 24h.
    """
    service = DashboardService(db)
    try:
        data = service.get_pipeline_stats()
        return PipelineVisibilityResponse(
            success=True,
            data=data
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
