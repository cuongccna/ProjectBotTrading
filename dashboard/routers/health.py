from fastapi import APIRouter, HTTPException, Depends
from sqlalchemy.orm import Session
from database.engine import get_db_session, get_session
from dashboard.services import DashboardService
from dashboard.schemas import SystemHealthResponse, BaseResponse

router = APIRouter(prefix="/health", tags=["System Health"])

def get_db():
    db = get_session()
    try:
        yield db
    finally:
        db.close()

@router.get("/system", response_model=SystemHealthResponse)
def get_system_health(db: Session = Depends(get_db)):
    """
    Get system health status for all modules.
    """
    service = DashboardService(db)
    try:
        data = service.get_system_health()
        return SystemHealthResponse(
            success=True,
            data=data
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
