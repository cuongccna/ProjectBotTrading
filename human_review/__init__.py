"""
Human Review Package.

Provides human-in-the-loop decision review capabilities for the trading system.

Core Principles:
- System trades automatically by default
- Human NEVER places orders directly
- Humans adjust rules, parameters, or permissions
- Every intervention is logged and auditable

Modules:
- schemas: Pydantic models for review data structures
- service: Business logic for review workflow
- router: FastAPI endpoints for review API
- telegram_notifier: Telegram notification formatting

Usage:
    from human_review.service import ReviewService, TriggerDetector
    from human_review.router import router as review_router
"""

from human_review.schemas import (
    ReviewEventCreate,
    ReviewEventResponse,
    HumanDecisionCreate,
    HumanDecisionResponse,
    AnnotationCreate,
    AnnotationResponse,
    OutcomeEvaluationCreate,
    OutcomeEvaluationResponse,
    ALLOWED_ACTIONS,
    FORBIDDEN_ACTIONS,
)

from human_review.service import (
    ReviewService,
    TriggerDetector,
    TriggerConditions,
)

from human_review.router import router

from human_review.telegram_notifier import (
    TelegramReviewNotifier,
    format_template,
)

__all__ = [
    # Schemas
    "ReviewEventCreate",
    "ReviewEventResponse",
    "HumanDecisionCreate",
    "HumanDecisionResponse",
    "AnnotationCreate",
    "AnnotationResponse",
    "OutcomeEvaluationCreate",
    "OutcomeEvaluationResponse",
    "ALLOWED_ACTIONS",
    "FORBIDDEN_ACTIONS",
    # Service
    "ReviewService",
    "TriggerDetector",
    "TriggerConditions",
    # Router
    "router",
    # Telegram
    "TelegramReviewNotifier",
    "format_template",
]
