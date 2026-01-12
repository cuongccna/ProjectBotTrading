# Human-in-the-Loop Decision Review Engine

A structured human oversight system for the automated crypto trading platform.

## 🎯 Core Principles

1. **Automatic Execution**: System trades autonomously by default
2. **Human Adjustment**: Humans adjust parameters, thresholds, and permissions
3. **No Direct Orders**: Humans NEVER place trades directly
4. **Full Auditability**: Every intervention is logged and traceable
5. **Learning Loop**: Outcomes are evaluated to improve future decisions

## 📁 Module Structure

```
human_review/
├── __init__.py           # Package exports
├── schemas.py            # Pydantic models for API
├── service.py            # Business logic (ReviewService, TriggerDetector)
├── router.py             # FastAPI endpoints
├── telegram_notifier.py  # Telegram alert formatting
├── GOVERNANCE.md         # Detailed governance documentation
└── README.md             # This file
```

## 🗄️ Database Tables

Tables defined in `database/models_review.py`:

| Table | Purpose |
|-------|---------|
| `review_events` | System-generated events requiring human review |
| `human_decisions` | Logged human actions on review events |
| `parameter_changes` | History of parameter modifications |
| `annotations` | Human notes and tags for institutional memory |
| `outcome_evaluations` | Post-hoc evaluation of decision quality |

## 🔔 Review Triggers

| Trigger | Threshold | Priority |
|---------|-----------|----------|
| Trade Guard Block | > 2 hours | High |
| Drawdown | > 5% day, > 10% week | High/Critical |
| Consecutive Losses | ≥ 5 trades | Normal |
| Risk Oscillation | > 30 pts/hour | Normal |
| Data Source Degraded | Error rate > 50% | Normal |
| Signal Contradiction | 3+ sources disagree | Low |

## ✅ Allowed Actions

- `adjust_risk_threshold` - Modify risk tolerance (drawdown 5-20%, position 1-10%)
- `pause_strategy` - Temporarily pause trading (max 168 hours)
- `resume_strategy` - Resume paused trading
- `reduce_position_limit` - Reduce max position size (0-100%)
- `enable_data_source` / `disable_data_source` - Toggle data sources
- `mark_anomaly` - Tag as anomalous (no action needed)
- `acknowledge_only` - Acknowledge without intervention

## ❌ Forbidden Actions

- ❌ Place trades directly
- ❌ Force trade execution
- ❌ Override Trade Guard manually
- ❌ Modify historical data

## 🌐 API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/review/queue` | Get pending review events |
| GET | `/review/event/{id}` | Get single review event |
| POST | `/review/event/{id}/claim` | Claim event for review |
| POST | `/review/event/{id}/decision` | Submit decision |
| POST | `/review/event/{id}/annotate` | Add annotation |
| POST | `/review/event/{id}/evaluate` | Submit outcome evaluation |
| POST | `/review/event/{id}/escalate` | Escalate event |
| GET | `/review/statistics` | Get queue statistics |
| GET | `/review/actions/allowed` | List allowed actions |
| GET | `/review/actions/forbidden` | List forbidden actions |

## 📱 Telegram Notifications

Example notification format:

```
🔴 🛡️ **REVIEW REQUIRED**

📌 **Trigger:** Trade Guard Block
🔢 **Event ID:** #15
⏰ **Time:** 2024-01-15 10:30 UTC
🎯 **Priority:** HIGH

📝 **Reason:**
_Trading blocked for 2.5 hours by volatility guard_

📈 **Market:** BTC @ $42,500 (+2.3%)
⚡ **Risk:** 65/100 (ELEVATED) - 🚫 Blocked

━━━━━━━━━━━━━━━━━━━━━
🔍 **Action Required:**
Open Dashboard → Review Panel
Event ID: #15
```

## 🚀 Usage

### Starting the API

The review endpoints are automatically included when running the dashboard:

```bash
cd ProjectBotTrading
$env:PYTHONPATH = "."
python -m uvicorn dashboard.main:app --reload --port 8000
```

### Submitting a Decision

```bash
curl -X POST "http://localhost:8000/review/event/15/decision?user_id=analyst_01&user_role=senior_analyst" \
  -H "Content-Type: application/json" \
  -d '{
    "decision_type": "adjust_risk_threshold",
    "reason_code": "market_volatility",
    "reason_text": "Elevated volatility due to Fed announcement",
    "parameter_after": {"max_drawdown_percent": 7.5},
    "confidence_level": "high"
  }'
```

### Running the Trigger Detector

```python
from database.engine import get_session
from human_review.service import TriggerDetector

with get_session() as db:
    detector = TriggerDetector(db)
    new_events = detector.check_all_triggers()
    print(f"Created {len(new_events)} review events")
```

## 📊 Dashboard Integration

The Human Review Panel is integrated into the Streamlit dashboard at Panel 7.

Features:
- Pending review count with priority coloring
- In-progress and resolved statistics
- Average resolution time metric
- Expandable review event details
- Allowed/forbidden actions reference

## 📖 Documentation

See [GOVERNANCE.md](GOVERNANCE.md) for complete governance framework including:
- Detailed trigger conditions
- Role-based permissions
- Decision workflow diagrams
- Audit trail specifications
- Emergency procedures
