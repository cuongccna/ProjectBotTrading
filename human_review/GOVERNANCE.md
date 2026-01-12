# Human-in-the-Loop Governance Framework

## 1. Overview

This document defines the governance rules for human oversight of the automated crypto trading system. The system trades automatically by default, with humans providing strategic oversight and parameter adjustments—never direct trade execution.

### Core Principles

| Principle | Description |
|-----------|-------------|
| **Automatic Execution** | System trades autonomously based on signals and rules |
| **Human Adjustment** | Humans adjust parameters, thresholds, and permissions |
| **No Direct Orders** | Humans NEVER place trades directly |
| **Full Auditability** | Every intervention is logged and traceable |
| **Learning Loop** | Outcomes are evaluated to improve future decisions |

---

## 2. Review Trigger Conditions

The system automatically creates review events when specific conditions are detected.

### Mandatory Triggers

| Trigger | Threshold | Priority | Description |
|---------|-----------|----------|-------------|
| **Trade Guard Block** | > 2 hours | High | Trading blocked by protective rules |
| **Drawdown Threshold** | > 5% day, > 10% week | High/Critical | Account drawdown exceeds limits |
| **Consecutive Losses** | ≥ 5 trades | Normal | Multiple losing trades in sequence |
| **Risk Score Oscillation** | > 30 pts/hour | Normal | Unusual risk score volatility |
| **Data Source Degraded** | Error rate > 50% | Normal | Data pipeline reliability issues |
| **Signal Contradiction** | 3+ sources disagree | Low | Conflicting trading signals |
| **Backtest Divergence** | Live vs backtest > 20% | Normal | Performance diverges from expectations |
| **Manual Request** | User-initiated | Normal | Human requested a review |

### Trigger Detection Logic

```python
# Pseudo-code for trigger detection
if trade_guard.blocked_for > 2_hours:
    create_review_event("trade_guard_block", priority="high")

if account.daily_drawdown > 0.05:
    create_review_event("drawdown_threshold", priority="high")

if account.weekly_drawdown > 0.10:
    create_review_event("drawdown_threshold", priority="critical")
```

---

## 3. Allowed Human Actions

The following actions are permitted with specified bounds:

### Parameter Adjustments

| Action | Category | Bounds | Description |
|--------|----------|--------|-------------|
| `adjust_risk_threshold` | Risk | Drawdown: 5-20%, Position: 1-10% | Modify risk tolerance thresholds |
| `reduce_position_limit` | Position | 0-100% of current | Reduce maximum position size |
| `pause_strategy` | Strategy | Max 168 hours (7 days) | Temporarily pause automated trading |
| `resume_strategy` | Strategy | N/A | Resume paused trading |
| `enable_data_source` | Data | Must be valid source | Re-enable a disabled data source |
| `disable_data_source` | Data | Must be valid source | Disable a problematic data source |
| `mark_anomaly` | Classification | N/A | Tag event as anomalous (not actionable) |
| `request_escalation` | Workflow | N/A | Escalate for additional review |
| `acknowledge_only` | Workflow | N/A | Acknowledge without action |

### Example: Adjusting Risk Threshold

```json
{
  "decision_type": "adjust_risk_threshold",
  "reason_code": "market_volatility",
  "reason_text": "Elevated volatility due to Fed announcement",
  "parameter_before": {"max_drawdown_percent": 5.0},
  "parameter_after": {"max_drawdown_percent": 7.5},
  "confidence_level": "high"
}
```

---

## 4. Forbidden Actions

The following actions are explicitly blocked to maintain system integrity:

| Forbidden Action | Reason |
|-----------------|--------|
| ❌ **Place trades directly** | Bypasses all safety systems |
| ❌ **Force trade execution** | Overrides position management |
| ❌ **Override Trade Guard manually** | Disables protective mechanisms |
| ❌ **Modify historical data** | Corrupts audit trail |
| ❌ **Disable all data sources** | Leaves system blind |
| ❌ **Set unlimited position sizes** | Removes risk controls |

### Enforcement

These restrictions are enforced at the API level. Any attempt to perform a forbidden action will:

1. Reject the request with HTTP 400
2. Log the attempt as a security event
3. Notify administrators
4. Increment a violation counter for the user

---

## 5. Decision Workflow

### Standard Review Process

```
┌─────────────────────────────────────────────────────────────────────┐
│                        REVIEW EVENT LIFECYCLE                        │
├─────────────────────────────────────────────────────────────────────┤
│                                                                     │
│  1. TRIGGER DETECTED                                                │
│     ├── System creates ReviewEvent                                  │
│     ├── Status: PENDING                                             │
│     └── Telegram notification sent (if enabled)                     │
│                                                                     │
│  2. HUMAN CLAIMS EVENT                                              │
│     ├── Reviewer opens Dashboard                                    │
│     ├── Clicks "Claim" on event                                     │
│     └── Status: IN_PROGRESS                                         │
│                                                                     │
│  3. HUMAN SUBMITS DECISION                                          │
│     ├── Selects action from ALLOWED_ACTIONS                         │
│     ├── Provides reason (code + text)                               │
│     ├── Sets confidence level                                       │
│     └── Submits decision                                            │
│                                                                     │
│  4. SYSTEM APPLIES DECISION                                         │
│     ├── Validates bounds                                            │
│     ├── Creates HumanDecision record                                │
│     ├── Creates ParameterChange record (if applicable)              │
│     ├── Updates system parameters                                   │
│     └── Status: RESOLVED                                            │
│                                                                     │
│  5. OUTCOME EVALUATION (Optional, after 24-72h)                     │
│     ├── Measure impact of decision                                  │
│     ├── Compare actual vs expected outcome                          │
│     └── Create OutcomeEvaluation record                             │
│                                                                     │
└─────────────────────────────────────────────────────────────────────┘
```

### Priority Handling

| Priority | Response Target | Escalation After |
|----------|----------------|------------------|
| Critical | 15 minutes | 30 minutes |
| High | 1 hour | 4 hours |
| Normal | 4 hours | 24 hours |
| Low | 24 hours | 72 hours |

---

## 6. Audit Trail

Every human intervention is logged with:

### HumanDecision Record

```python
{
    "id": 42,
    "review_event_id": 15,
    "user_id": "analyst_01",
    "user_role": "senior_analyst",
    "decision_type": "adjust_risk_threshold",
    "reason_code": "market_volatility",
    "reason_text": "Elevated volatility due to Fed announcement",
    "parameter_before": {"max_drawdown_percent": 5.0},
    "parameter_after": {"max_drawdown_percent": 7.5},
    "confidence_level": "high",
    "created_at": "2024-01-15T10:30:00Z"
}
```

### SystemMonitoring Audit Entry

```python
{
    "module_name": "human_review",
    "severity": "INFO",
    "message": "Human decision submitted: adjust_risk_threshold by analyst_01",
    "metadata": {
        "review_event_id": 15,
        "decision_id": 42,
        "action": "adjust_risk_threshold"
    }
}
```

### Retention

| Data Type | Retention Period |
|-----------|-----------------|
| Review Events | Permanent |
| Human Decisions | Permanent |
| Parameter Changes | Permanent |
| Annotations | Permanent |
| Outcome Evaluations | Permanent |

---

## 7. Learning & Feedback Loop

### Outcome Evaluation

After sufficient time has passed (typically 24-72 hours), evaluate whether the human decision:

| Verdict | Description |
|---------|-------------|
| **CORRECT** | Decision improved outcomes or prevented losses |
| **INCORRECT** | Decision worsened outcomes |
| **NEUTRAL** | No significant measurable impact |
| **INSUFFICIENT_DATA** | Cannot determine yet |

### Feedback Integration

1. **Analyst Leaderboard**: Track decision quality by reviewer
2. **Pattern Recognition**: Identify which triggers lead to good/bad decisions
3. **Threshold Refinement**: Adjust trigger thresholds based on false positive rate
4. **Training Data**: Use outcomes to improve future recommendations

### Example Evaluation

```json
{
  "review_event_id": 15,
  "decision_id": 42,
  "evaluator_id": "risk_manager_01",
  "verdict": "correct",
  "pnl_impact_usd": 1250.00,
  "actual_outcome": "Avoided 2.5% additional drawdown during volatility spike",
  "expected_outcome": "Reduce exposure during uncertainty",
  "lessons_learned": "Fed announcement volatility was correctly anticipated",
  "created_at": "2024-01-17T14:00:00Z"
}
```

---

## 8. Role-Based Permissions

### Reviewer Roles

| Role | Permissions |
|------|-------------|
| **Junior Analyst** | View, acknowledge_only, request_escalation |
| **Analyst** | All above + mark_anomaly, add annotations |
| **Senior Analyst** | All above + parameter adjustments |
| **Risk Manager** | All above + pause/resume strategy |
| **Administrator** | All above + enable/disable data sources |

### Role Enforcement

```python
ROLE_PERMISSIONS = {
    "junior_analyst": ["acknowledge_only", "request_escalation"],
    "analyst": ["acknowledge_only", "request_escalation", "mark_anomaly"],
    "senior_analyst": ["adjust_risk_threshold", "reduce_position_limit", "mark_anomaly", ...],
    "risk_manager": ["pause_strategy", "resume_strategy", ...],
    "administrator": ["enable_data_source", "disable_data_source", ...],
}
```

---

## 9. API Reference

### Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/review/queue` | Get pending review events |
| `GET` | `/review/event/{id}` | Get single review event |
| `POST` | `/review/event/{id}/claim` | Claim event for review |
| `POST` | `/review/event/{id}/decision` | Submit decision |
| `POST` | `/review/event/{id}/annotate` | Add annotation |
| `POST` | `/review/event/{id}/evaluate` | Submit outcome evaluation |
| `POST` | `/review/event/{id}/escalate` | Escalate event |
| `GET` | `/review/statistics` | Get queue statistics |
| `GET` | `/review/actions/allowed` | List allowed actions |
| `GET` | `/review/actions/forbidden` | List forbidden actions |

### Example: Submit Decision

```bash
POST /review/event/15/decision?user_id=analyst_01&user_role=senior_analyst
Content-Type: application/json

{
  "decision_type": "adjust_risk_threshold",
  "reason_code": "market_volatility",
  "reason_text": "Elevated volatility due to Fed announcement",
  "parameter_before": {"max_drawdown_percent": 5.0},
  "parameter_after": {"max_drawdown_percent": 7.5},
  "confidence_level": "high"
}
```

---

## 10. Emergency Procedures

### Critical Event Protocol

1. **Immediate Notification**: Critical events trigger immediate Telegram alerts
2. **15-Minute SLA**: Must be claimed within 15 minutes
3. **Escalation**: Auto-escalates after 30 minutes if unclaimed
4. **On-Call Rotation**: Designate 24/7 on-call coverage

### System Override

In extreme emergencies (system compromise, API failure), authorized administrators may:

1. SSH to production server
2. Execute emergency stop script
3. Document all actions in incident report
4. Submit post-hoc review event

```bash
# Emergency stop (requires admin credentials)
python scripts/emergency_stop.py --reason "Security incident" --operator "admin_01"
```

---

## Document Control

| Version | Date | Author | Changes |
|---------|------|--------|---------|
| 1.0 | 2024-01-15 | System | Initial governance framework |

**Last Review**: This document should be reviewed quarterly.

**Approval**: This governance framework requires approval from Risk Management before deployment.
