# Institutional Trading Dashboard Architecture

This document outlines the architecture for the Monitoring & Decision Dashboard.

## 1. Backend API (FastAPI)

The backend is structured as a modular FastAPI application reading directly from the `crypto_trading` PostgreSQL database.

### API Endpoints

| Panel | Endpoint | Method | Purpose |
|-------|----------|--------|---------|
| **System Health** | `/health/system` | GET | Module status, error rates, freshness. |
| **Data Pipeline** | `/pipeline/stats` | GET | Ingestion counts, latency, stale data detection. |
| **Risk State** | `/risk/state` | GET | Current global risk score, components breakdown. |
| **Decision Trace** | `/decisions/latest` | GET | Audit log of recent trade decisions (ALLOW/BLOCK). |
| **Positions** | `/positions/monitor` | GET | Current open positions and recent execution metrics. |
| **Alerts** | `/alerts/active` | GET | Active critical warnings and errors. |

### Running the Backend

```bash
cd ProjectBotTrading
# (Ensure venv is active)
uvicorn dashboard.main:app --host 0.0.0.0 --port 8000 --reload
```

## 2. Frontend Component Structure (React/TypeScript)

Recommended directory structure for the frontend application:

```
src/
├── components/
│   ├── common/
│   │   ├── StatusBadge.tsx       # UP/DOWN/DEGRADED indicators
│   │   ├── MetricCard.tsx        # Standard stat display
│   │   └── DataTable.tsx         # Reusable table with sorting
│   ├── panels/
│   │   ├── SystemHealthPanel.tsx # Consumes /health/system
│   │   ├── PipelinePanel.tsx     # Consumes /pipeline/stats
│   │   ├── RiskGaugePanel.tsx    # Consumes /risk/state
│   │   ├── DecisionLogPanel.tsx  # Consumes /decisions/latest
│   │   ├── PositionTable.tsx     # Consumes /positions/monitor
│   │   └── AlertFeed.tsx         # Consumes /alerts/active
│   └── layout/
│       ├── DashboardGrid.tsx     # CSS Grid layout for panels
│       └── Navbar.tsx            # Navigation and Global Status
├── hooks/
│   ├── useAutoRefresh.ts         # Polling logic (every 5s)
│   └── useApi.ts                 # Generic fetch wrapper
├── types/
│   └── api.ts                    # TypeScript interfaces matching Pydantic schemas
└── App.tsx
```

## 3. Data Mapping (Module → DB → UI)

| UI Metrics | Database Source | Module Origin |
|------------|-----------------|---------------|
| **Module Status** | `system_monitoring` (latest heartbeat) | All Modules |
| **News Count** | `raw_news` (count last 24h) | `data_ingestion` |
| **Sentiment Status** | `sentiment_scores` (freshness) | `sentiment_analysis` |
| **Risk Score** | `risk_state.global_risk_score` | `risk_scoring` |
| **Trade Decision** | `entry_decision.decision` | `decision_engine` |
| **Slippage** | `execution_records.slippage_percent` | `execution` |

## 4. Security & Access Control

*   **Read-Only**: The API performs `SELECT` queries only. No `INSERT/UPDATE/DELETE` capabilities are exposed via these endpoints.
*   **Networking**: The Dashboard API should run on a restricted port/network, separate from the core trading bot loop.
*   **Auth**: For production, wrap the `get_db` dependency with an OAuth2 token verification function.

## 5. Extensibility

To add a new panel:
1.  Define the table in `database/models.py`.
2.  Add retrieval logic in `dashboard/services.py`.
3.  Create a Pydantic schema in `dashboard/schemas.py`.
4.  Add a new router in `dashboard/routers/`.
5.  Create the React component in `src/components/panels/`.
