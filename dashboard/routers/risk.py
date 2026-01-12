from fastapi import APIRouter, HTTPException, Depends
from sqlalchemy.orm import Session
from database.engine import get_session
from dashboard.services import DashboardService
from dashboard.schemas import RiskStateResponse

router = APIRouter(prefix="/risk", tags=["Risk State"])

def get_db():
    db = get_session()
    try:
        yield db
    finally:
        db.close()

@router.get("/state", response_model=RiskStateResponse)
def get_risk_state(db: Session = Depends(get_db)):
    """
    Get the latest global risk state and components.
    """
    service = DashboardService(db)
    try:
        data = service.get_latest_risk_state()
        if not data:
             # Return empty structure if no data yet (or raise 404, but UI prefers structure)
             # Raising 404 for now
             raise HTTPException(status_code=404, detail="No risk state recorded yet.")
             
        return RiskStateResponse(
            success=True,
            data=data
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
