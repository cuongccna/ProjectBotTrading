# Dashboard Module → Metric → UI Mapping

This document provides complete traceability from source modules to database tables to dashboard UI components.

## Data Contract Rules

Every metric displayed on the dashboard must satisfy:

| Rule | Requirement |
|------|-------------|
| **Source Module** | Must map to a real Python module in the codebase |
| **Database Table** | Must read from a defined PostgreSQL table |
| **Update Frequency** | Must specify how often data is refreshed |
| **Retention Policy** | Must specify how long data is kept |

---

## Panel 1: System Health

| UI Metric | Database Table | Column(s) | Source Module | Update Frequency | Retention |
|-----------|----------------|-----------|---------------|------------------|-----------|
| Module Status (UP/DEGRADED/DOWN) | `system_monitoring` | `module_name`, `event_time`, `severity` | All modules | On each module heartbeat | 30 days |
| Error Count (1h) | `system_monitoring` | `severity = 'error'` count | All modules | Computed on request | 30 days |
| Last Heartbeat | `system_monitoring` | `MAX(event_time) per module` | All modules | Per event | 30 days |

**API Endpoint:** `GET /health/system`

**Logic:**
- Module is `UP` if last heartbeat < 30 minutes ago AND errors < 5/hour
- Module is `DEGRADED` if errors >= 5/hour
- Module is `DOWN` if last heartbeat > 30 minutes ago

---

## Panel 2: Data Pipeline Visibility

| UI Metric | Database Table | Column(s) | Source Module | Update Frequency | Retention |
|-----------|----------------|-----------|---------------|------------------|-----------|
| Raw News Count (24h) | `raw_news` | `COUNT(*) WHERE created_at > NOW()-24h` | `data_ingestion` | Per ingestion cycle | 90 days |
| Cleaned News Count (24h) | `cleaned_news` | `COUNT(*) WHERE created_at > NOW()-24h` | `data_processing` | Per processing cycle | 90 days |
| Sentiment Scores Count (24h) | `sentiment_scores` | `COUNT(*) WHERE created_at > NOW()-24h` | `sentiment_analysis` | Per batch | 90 days |
| On-chain Events Count (24h) | `onchain_flow_raw` | `COUNT(*) WHERE event_time > NOW()-24h` | `onchain_collector` | Per collection cycle | 90 days |

**API Endpoint:** `GET /pipeline/stats`

**Status Logic:**
- `HEALTHY`: count > 0 AND last_update < 1 hour ago
- `STALE`: count = 0 OR last_update > 1 hour ago

---

## Panel 3: Risk State (CRITICAL)

| UI Metric | Database Table | Column(s) | Source Module | Update Frequency | Retention |
|-----------|----------------|-----------|---------------|------------------|-----------|
| Global Risk Score | `risk_state` | `global_risk_score` | `risk_scoring` | Per pipeline cycle | 180 days |
| Risk Level | `risk_state` | `risk_level` | `risk_scoring` | Per pipeline cycle | 180 days |
| Trading Allowed | `risk_state` | `trading_allowed` | `risk_scoring` | Per pipeline cycle | 180 days |
| Blocked Reason | `risk_state` | `trading_blocked_reason` | `risk_scoring` | Per pipeline cycle | 180 days |
| Sentiment Risk (Raw) | `risk_state` | `sentiment_risk_raw` | `risk_scoring` | Per pipeline cycle | 180 days |
| Sentiment Risk (Normalized) | `risk_state` | `sentiment_risk_normalized` | `risk_scoring` | Per pipeline cycle | 180 days |
| Flow Risk (Raw) | `risk_state` | `flow_risk_raw` | `risk_scoring` | Per pipeline cycle | 180 days |
| Flow Risk (Normalized) | `risk_state` | `flow_risk_normalized` | `risk_scoring` | Per pipeline cycle | 180 days |
| Smart Money Risk (Raw) | `risk_state` | `smart_money_risk_raw` | `risk_scoring` | Per pipeline cycle | 180 days |
| Smart Money Risk (Normalized) | `risk_state` | `smart_money_risk_normalized` | `risk_scoring` | Per pipeline cycle | 180 days |
| Market Condition Risk (Raw) | `risk_state` | `market_condition_risk_raw` | `risk_scoring` | Per pipeline cycle | 180 days |
| Market Condition Risk (Normalized) | `risk_state` | `market_condition_risk_normalized` | `risk_scoring` | Per pipeline cycle | 180 days |
| Component Weights | `risk_state` | `weights` (JSONB) | `risk_scoring` | Per pipeline cycle | 180 days |

**API Endpoint:** `GET /risk/state`

**Component Breakdown:**
Each risk component shows:
- `name`: Component identifier (sentiment, flow, smart_money, market_condition)
- `raw_score`: Original unprocessed value
- `normalized_score`: Value after normalization (0-1 or 0-100)
- `weight`: Contribution weight to final score
- `risk_contribution`: normalized_score × weight

---

## Panel 4: Decision Trace

| UI Metric | Database Table | Column(s) | Source Module | Update Frequency | Retention |
|-----------|----------------|-----------|---------------|------------------|-----------|
| Decision (ALLOW/BLOCK) | `entry_decision` | `decision` | `decision_engine` | Per decision | 365 days |
| Token | `entry_decision` | `token` | `decision_engine` | Per decision | 365 days |
| Direction | `entry_decision` | `direction` | `decision_engine` | Per decision | 365 days |
| Reason Code | `entry_decision` | `reason_code` | `decision_engine` | Per decision | 365 days |
| Reason Details | `entry_decision` | `reason_details` | `decision_engine` | Per decision | 365 days |
| Sentiment Score | `entry_decision` | `sentiment_score` | `decision_engine` | Per decision | 365 days |
| Flow Score | `entry_decision` | `flow_score` | `decision_engine` | Per decision | 365 days |
| Smart Money Score | `entry_decision` | `smart_money_score` | `decision_engine` | Per decision | 365 days |
| Risk Score | `entry_decision` | `risk_score` | `decision_engine` | Per decision | 365 days |
| Trade Guard Intervention | `entry_decision` | `trade_guard_intervention` | `trade_guard` | Per decision | 365 days |
| Trade Guard Rule ID | `entry_decision` | `trade_guard_rule_id` | `trade_guard` | Per decision | 365 days |

**API Endpoint:** `GET /decisions/latest?limit=50`

**Audit Trail:**
Every decision links to:
1. Risk state at time of decision (via `correlation_id`)
2. Trade Guard rule that intervened (if any)
3. All input scores that influenced the decision

---

## Panel 5: Position & Execution Monitor

| UI Metric | Database Table | Column(s) | Source Module | Update Frequency | Retention |
|-----------|----------------|-----------|---------------|------------------|-----------|
| Order ID | `execution_records` | `order_id` | `execution` | Per order | 365 days |
| Token | `execution_records` | `token` | `execution` | Per order | 365 days |
| Side (buy/sell) | `execution_records` | `side` | `execution` | Per order | 365 days |
| Status | `execution_records` | `status` | `execution` | Per order update | 365 days |
| Executed Size | `execution_records` | `executed_size` | `execution` | Per fill | 365 days |
| Executed Price | `execution_records` | `executed_price` | `execution` | Per fill | 365 days |
| Slippage % | `execution_records` | `slippage_percent` | `execution` | Per fill | 365 days |
| Latency (ms) | `execution_records` | `latency_ms` | `execution` | Per order | 365 days |
| Position Size | `position_sizing` | `final_size` | `position_sizing` | Per sizing calculation | 365 days |
| Position USD Value | `position_sizing` | `final_size_usd` | `position_sizing` | Per sizing calculation | 365 days |

**API Endpoint:** `GET /positions/monitor`

**Note:** This panel is VIEW-ONLY. No order placement capability.

---

## Panel 6: Alerts & Incidents

| UI Metric | Database Table | Column(s) | Source Module | Update Frequency | Retention |
|-----------|----------------|-----------|---------------|------------------|-----------|
| Alert Severity | `system_monitoring` | `severity` (warning/error/critical) | Various | Per event | 90 days |
| Alert Module | `system_monitoring` | `module_name` | Various | Per event | 90 days |
| Alert Message | `system_monitoring` | `message` | Various | Per event | 90 days |
| Alert Timestamp | `system_monitoring` | `event_time` | Various | Per event | 90 days |
| Alert Details | `system_monitoring` | `details` (JSONB) | Various | Per event | 90 days |

**API Endpoint:** `GET /alerts/active?limit=50`

**Alert Sources:**
- `trade_guard`: Trade blocking events
- `risk_scoring`: Risk threshold breaches
- `execution`: Order failures, high slippage
- `data_ingestion`: Data source failures
- `monitoring`: System health degradations

---

## Database Schema Summary

| Table | Primary Module | Records | Purpose |
|-------|----------------|---------|---------|
| `raw_news` | `data_ingestion` | Raw news articles | Input data |
| `cleaned_news` | `data_processing` | Processed news | Cleaned data |
| `sentiment_scores` | `sentiment_analysis` | Sentiment results | Analysis output |
| `market_data` | `market_data_collector` | OHLCV candles | Market input |
| `onchain_flow_raw` | `onchain_collector` | Blockchain events | On-chain input |
| `flow_scores` | `flow_scoring` | Aggregated flows | Flow analysis |
| `market_state` | `market_analyzer` | Market regime | State assessment |
| `risk_state` | `risk_scoring` | Risk assessment | **CRITICAL** |
| `entry_decision` | `decision_engine` | Trade decisions | **AUDIT LOG** |
| `position_sizing` | `position_sizing` | Size calculations | Position management |
| `execution_records` | `execution` | Order executions | Trade records |
| `system_monitoring` | All | Health/alerts | System observability |

---

## API Endpoint Summary

| Endpoint | Method | Panel | Data Source |
|----------|--------|-------|-------------|
| `/health/system` | GET | System Health | `system_monitoring` |
| `/pipeline/stats` | GET | Pipeline Visibility | `raw_news`, `cleaned_news`, etc. |
| `/risk/state` | GET | Risk State | `risk_state` |
| `/decisions/latest` | GET | Decision Trace | `entry_decision` |
| `/positions/monitor` | GET | Position & Execution | `execution_records`, `position_sizing` |
| `/alerts/active` | GET | Alerts & Incidents | `system_monitoring` |

---

## Security Model

| Aspect | Implementation |
|--------|----------------|
| Read-Only | All endpoints are GET only |
| No API Keys Exposed | Database credentials never sent to frontend |
| CORS | Configured in FastAPI middleware |
| Authentication | TODO: Add OAuth2/JWT for production |
| Role-Based Access | TODO: Add viewer/admin roles |

---

## Extensibility

To add a new metric:

1. **Database**: Add column to existing table or create new table in `database/models.py`
2. **Service**: Add query method in `dashboard/services.py`
3. **Schema**: Add Pydantic model in `dashboard/schemas.py`
4. **Router**: Add endpoint in appropriate `dashboard/routers/*.py`
5. **Frontend**: Add UI component in Streamlit or React

No architectural changes required for new metrics.
