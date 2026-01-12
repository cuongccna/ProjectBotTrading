from fastapi import APIRouter, HTTPException, Depends
from sqlalchemy.orm import Session
from database.engine import get_session
from dashboard.services import DashboardService
from dashboard.schemas import PositionExecutionResponse

router = APIRouter(prefix="/positions", tags=["Positions & Execution"])

def get_db():
    db = get_session()
    try:
        yield db
    finally:
        db.close()

@router.get("/monitor", response_model=PositionExecutionResponse)
def get_position_monitor(db: Session = Depends(get_db)):
    """
    Get current positions and recent specific execution metrics.
    """
    service = DashboardService(db)
    try:
        data = service.get_position_execution_stats()
        return PositionExecutionResponse(
            success=True,
            positions=data["positions"],
            recent_executions=data["recent_executions"]
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
