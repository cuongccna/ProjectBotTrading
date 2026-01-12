from fastapi import APIRouter, HTTPException, Depends
from sqlalchemy.orm import Session
from database.engine import get_session
from dashboard.services import DashboardService
from dashboard.schemas import DecisionTraceResponse

router = APIRouter(prefix="/decisions", tags=["Decision Trace"])

def get_db():
    db = get_session()
    try:
        yield db
    finally:
        db.close()

@router.get("/latest", response_model=DecisionTraceResponse)
def get_latest_decisions(limit: int = 50, db: Session = Depends(get_db)):
    """
    Get recent trading decisions with full audit trace.
    """
    service = DashboardService(db)
    try:
        data = service.get_recent_decisions(limit=limit)
        return DecisionTraceResponse(
            success=True,
            data=data
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
