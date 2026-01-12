# Crypto Trading Platform

## Institutional-Grade Crypto Trading System

This is a modular, risk-first, data-centric crypto trading platform designed for institutional use.

---

## Core Philosophy

- **Data quality over prediction accuracy**
- **Risk management over profit maximization**
- **Stability over frequency**
- **Auditability over speed of development**

---

## Architecture Layers

1. **Data Ingestion Layer** — Collects raw inputs, no business logic
2. **Processing & Scoring Layer** — Cleans, normalizes, labels, scores
3. **Decision & Risk Layer** — Trade guards, vetoes, approval states
4. **Execution Layer** — Defensive, idempotent, fail-safe
5. **Monitoring & Reporting Layer** — Telegram-first observability
6. **Data Warehouse** — Historical replay and audit capability

---

## Project Structure

```
crypto-trading-platform/
├── config/              # All configuration files (YAML)
├── core/                # System clock, state, orchestration
├── data_ingestion/      # Collectors and normalizers
├── data_processing/     # Cleaning, labeling, sentiment
├── scoring_engine/      # Risk, flow, sentiment, composite scores
├── decision_engine/     # Trade eligibility and veto logic
├── risk_management/     # System, strategy, trade guards
├── execution_engine/    # Exchange client, order management
├── monitoring/          # Health checks, metrics, alerts
├── reporting/           # Daily, incident, performance reports
├── storage/             # Database and repositories
├── backtesting/         # Replay and parity validation
├── dashboard/           # API and views
├── chaos_testing/       # Fault injection and scenarios
├── data_products/       # Anonymization and export
└── scripts/             # Operational scripts
```

---

## Non-Negotiable Rules

- Never assume prediction accuracy
- Never overfit to backtest results
- Never skip database persistence
- Never bypass the risk layer
- Never allow execution without explicit approval state
- Never hardcode secrets
- Never mix module responsibilities
- Never silently fail

---

## Setup

```bash
# TODO: Add setup instructions
```

---

## Configuration

All configuration is managed via YAML files in the `config/` directory.
Secrets are managed via environment variables (see `.env.example`).

---

## License

Proprietary — All rights reserved.
