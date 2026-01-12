"""
FastAPI Router for Human Review Endpoints.

Provides REST API for human review workflow:
- View pending reviews
- Submit decisions
- Add annotations
- Evaluate outcomes
"""

from datetime import datetime
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from database.engine import get_session
from database.models_review import ReviewStatus
from human_review.schemas import (
    ReviewEventResponse,
    ReviewEventCreate,
    HumanDecisionCreate,
    HumanDecisionResponse,
    AnnotationCreate,
    AnnotationResponse,
    OutcomeEvaluationCreate,
    OutcomeEvaluationResponse,
    ReviewQueueResponse,
    ALLOWED_ACTIONS,
    FORBIDDEN_ACTIONS,
)
from human_review.service import ReviewService, TriggerDetector

router = APIRouter(prefix="/review", tags=["Human Review"])


# =============================================================
# HELPER: Database dependency
# =============================================================

def get_db():
    db = get_session()
    try:
        yield db
    finally:
        db.close()


# =============================================================
# HELPER: Get service instance
# =============================================================

def get_review_service(db: Session = Depends(get_db)) -> ReviewService:
    return ReviewService(db)


def get_trigger_detector(db: Session = Depends(get_db)) -> TriggerDetector:
    return TriggerDetector(db)


# =============================================================
# REVIEW QUEUE ENDPOINTS
# =============================================================

@router.get("/queue", response_model=ReviewQueueResponse)
def get_review_queue(
    status_filter: Optional[str] = Query(None, description="Filter by status"),
    priority: Optional[str] = Query(None, description="Filter by priority"),
    limit: int = Query(50, ge=1, le=200),
    service: ReviewService = Depends(get_review_service),
):
    """
    Get queue of pending review events.
    
    Returns events sorted by priority (critical > high > normal > low)
    and then by creation time (oldest first).
    """
    # Parse status filter
    status_enum = None
    if status_filter:
        try:
            status_enum = ReviewStatus(status_filter)
        except ValueError:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid status: {status_filter}. Valid values: pending, in_progress, resolved, escalated, expired"
            )
    
    events = service.get_pending_reviews(status=status_enum, limit=limit)
    
    # Apply priority filter if specified
    if priority:
        events = [e for e in events if e.priority == priority]
    
    # Get statistics
    stats = service.get_review_statistics()
    
    return ReviewQueueResponse(
        events=[ReviewEventResponse.model_validate(e.__dict__) for e in events],
        total_pending=stats.get("pending_count", 0),
        total_in_progress=stats.get("in_progress_count", 0),
        total_resolved=stats.get("resolved_24h", 0),
        avg_resolution_time_hours=stats.get("avg_resolution_time_hours"),
    )


@router.get("/event/{event_id}", response_model=ReviewEventResponse)
def get_review_event(
    event_id: int,
    service: ReviewService = Depends(get_review_service),
):
    """Get details of a specific review event."""
    event = service.get_review_event(event_id)
    if not event:
        raise HTTPException(status_code=404, detail=f"Review event {event_id} not found")
    
    return ReviewEventResponse.model_validate(event.__dict__)


@router.get("/event/{event_id}/decisions", response_model=List[HumanDecisionResponse])
def get_event_decisions(
    event_id: int,
    service: ReviewService = Depends(get_review_service),
):
    """Get all decisions made for a review event."""
    event = service.get_review_event(event_id)
    if not event:
        raise HTTPException(status_code=404, detail=f"Review event {event_id} not found")
    
    decisions = service.get_decisions_for_event(event_id)
    return [HumanDecisionResponse.model_validate(d.__dict__) for d in decisions]


# =============================================================
# DECISION SUBMISSION ENDPOINTS
# =============================================================

@router.post("/event/{event_id}/decision", response_model=HumanDecisionResponse, status_code=status.HTTP_201_CREATED)
def submit_decision(
    event_id: int,
    decision: HumanDecisionCreate,
    user_id: str = Query(..., description="ID of the human reviewer"),
    user_role: str = Query("reviewer", description="Role of the reviewer"),
    service: ReviewService = Depends(get_review_service),
):
    """
    Submit a human decision for a review event.
    
    Validates:
    - Action is in ALLOWED_ACTIONS
    - Parameter changes are within bounds
    - Required fields are present
    
    Returns the created decision with audit metadata.
    """
    # Verify event exists
    event = service.get_review_event(event_id)
    if not event:
        raise HTTPException(status_code=404, detail=f"Review event {event_id} not found")
    
    # Check event is still pending
    if event.status not in [ReviewStatus.PENDING, ReviewStatus.IN_PROGRESS]:
        raise HTTPException(
            status_code=400,
            detail=f"Cannot submit decision for event with status: {event.status.value}"
        )
    
    # Ensure event_id matches
    decision.review_event_id = event_id
    
    try:
        new_decision = service.submit_decision(
            data=decision,
            user_id=user_id,
            user_role=user_role,
        )
        return HumanDecisionResponse.model_validate(new_decision.__dict__)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/event/{event_id}/claim")
def claim_review_event(
    event_id: int,
    user_id: str = Query(..., description="ID of the reviewer claiming this event"),
    service: ReviewService = Depends(get_review_service),
):
    """
    Claim a review event to indicate it's being worked on.
    
    Updates status to IN_PROGRESS.
    """
    event = service.get_review_event(event_id)
    if not event:
        raise HTTPException(status_code=404, detail=f"Review event {event_id} not found")
    
    if event.status != ReviewStatus.PENDING:
        raise HTTPException(
            status_code=400,
            detail=f"Event is already {event.status.value}"
        )
    
    event.status = ReviewStatus.IN_PROGRESS
    event.assigned_to = user_id
    event.updated_at = datetime.utcnow()
    service.db.commit()
    
    return {"message": "Event claimed", "event_id": event_id, "assigned_to": user_id}


# =============================================================
# ANNOTATION ENDPOINTS
# =============================================================

@router.post("/event/{event_id}/annotate", response_model=AnnotationResponse, status_code=status.HTTP_201_CREATED)
def add_annotation(
    event_id: int,
    annotation: AnnotationCreate,
    user_id: str = Query(..., description="ID of the annotator"),
    service: ReviewService = Depends(get_review_service),
):
    """
    Add an annotation to a review event.
    
    Annotations are for institutional memory:
    - Notes about the situation
    - Tags for categorization
    - Lessons learned
    """
    event = service.get_review_event(event_id)
    if not event:
        raise HTTPException(status_code=404, detail=f"Review event {event_id} not found")
    
    # Ensure event_id matches
    annotation.review_event_id = event_id
    
    new_annotation = service.add_annotation(annotation, user_id)
    return AnnotationResponse.model_validate(new_annotation.__dict__)


@router.get("/event/{event_id}/annotations", response_model=List[AnnotationResponse])
def get_event_annotations(
    event_id: int,
    service: ReviewService = Depends(get_review_service),
):
    """Get all annotations for a review event."""
    event = service.get_review_event(event_id)
    if not event:
        raise HTTPException(status_code=404, detail=f"Review event {event_id} not found")
    
    return [AnnotationResponse.model_validate(a.__dict__) for a in event.annotations]


# =============================================================
# OUTCOME EVALUATION ENDPOINTS
# =============================================================

@router.post("/event/{event_id}/evaluate", response_model=OutcomeEvaluationResponse, status_code=status.HTTP_201_CREATED)
def evaluate_outcome(
    event_id: int,
    evaluation: OutcomeEvaluationCreate,
    user_id: str = Query(..., description="ID of the evaluator"),
    service: ReviewService = Depends(get_review_service),
):
    """
    Submit a post-hoc outcome evaluation.
    
    Evaluates whether the human decision was:
    - CORRECT: Decision improved outcomes
    - INCORRECT: Decision worsened outcomes
    - NEUTRAL: No significant impact
    - INSUFFICIENT_DATA: Cannot determine yet
    """
    event = service.get_review_event(event_id)
    if not event:
        raise HTTPException(status_code=404, detail=f"Review event {event_id} not found")
    
    # Event should be resolved to evaluate
    if event.status not in [ReviewStatus.RESOLVED, ReviewStatus.EXPIRED]:
        raise HTTPException(
            status_code=400,
            detail="Cannot evaluate event that is not yet resolved"
        )
    
    # Ensure event_id matches
    evaluation.review_event_id = event_id
    
    new_evaluation = service.evaluate_outcome(evaluation, user_id)
    return OutcomeEvaluationResponse.model_validate(new_evaluation.__dict__)


# =============================================================
# STATISTICS ENDPOINTS
# =============================================================

@router.get("/statistics")
def get_review_statistics(
    service: ReviewService = Depends(get_review_service),
):
    """
    Get review queue statistics.
    
    Returns counts and metrics for dashboard widgets.
    """
    return service.get_review_statistics()


# =============================================================
# ALLOWED ACTIONS REFERENCE
# =============================================================

@router.get("/actions/allowed")
def get_allowed_actions():
    """
    Get list of allowed human actions with bounds.
    
    Use this to populate decision forms and validate user input.
    """
    return ALLOWED_ACTIONS


@router.get("/actions/forbidden")
def get_forbidden_actions():
    """
    Get list of forbidden actions for documentation.
    
    These actions are explicitly blocked to maintain system integrity.
    """
    return FORBIDDEN_ACTIONS


# =============================================================
# TRIGGER DETECTION ENDPOINTS
# =============================================================

@router.post("/triggers/check")
def check_triggers(
    detector: TriggerDetector = Depends(get_trigger_detector),
):
    """
    Manually trigger a check for review conditions.
    
    Normally this runs automatically, but can be triggered manually.
    Returns list of new review events created.
    """
    events = detector.check_all_triggers()
    return {
        "message": f"Created {len(events)} new review events",
        "event_ids": [e.id for e in events],
    }


# =============================================================
# ESCALATION ENDPOINT
# =============================================================

@router.post("/event/{event_id}/escalate")
def escalate_event(
    event_id: int,
    reason: str = Query(..., description="Reason for escalation"),
    user_id: str = Query(..., description="ID of the escalating user"),
    service: ReviewService = Depends(get_review_service),
):
    """
    Escalate a review event for additional oversight.
    
    Use when:
    - Reviewer is uncertain
    - High-impact decision needed
    - Multiple perspectives required
    """
    event = service.get_review_event(event_id)
    if not event:
        raise HTTPException(status_code=404, detail=f"Review event {event_id} not found")
    
    event.status = ReviewStatus.ESCALATED
    event.priority = "critical"
    event.updated_at = datetime.utcnow()
    
    # Add escalation annotation
    from human_review.schemas import AnnotationCreate
    service.add_annotation(
        AnnotationCreate(
            review_event_id=event_id,
            note_text=f"ESCALATED: {reason}",
            tags=["escalation"],
        ),
        user_id=user_id,
    )
    
    service.db.commit()
    
    return {
        "message": "Event escalated",
        "event_id": event_id,
        "new_status": "escalated",
        "priority": "critical",
    }
