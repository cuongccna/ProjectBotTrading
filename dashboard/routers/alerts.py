from fastapi import APIRouter, HTTPException, Depends
from sqlalchemy.orm import Session
from database.engine import get_session
from dashboard.services import DashboardService
from dashboard.schemas import AlertsResponse

router = APIRouter(prefix="/alerts", tags=["Alerts & Incidents"])

def get_db():
    db = get_session()
    try:
        yield db
    finally:
        db.close()

@router.get("/active", response_model=AlertsResponse)
def get_active_alerts(limit: int = 50, db: Session = Depends(get_db)):
    """
    Get active alerts and recent incidents.
    """
    service = DashboardService(db)
    try:
        data = service.get_active_alerts(limit=limit)
        return AlertsResponse(
            success=True,
            data=data
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
