"""
Risk Budget Manager Module.

============================================================
INSTITUTIONAL-GRADE CRYPTO TRADING SYSTEM
Risk Budget Manager - Mandatory Trade Gatekeeper
============================================================

PURPOSE
-------
Enforce capital preservation and controlled risk exposure.
Act as mandatory gatekeeper between Signal Engine and Execution Engine.

The module controls WHETHER a trade is allowed based on remaining
risk budget. It does NOT generate trading signals.

DESIGN PHILOSOPHY
-----------------
1. Risk budget = maximum allowable loss (NOT position size)
2. All values expressed as percentage of account equity
3. Capital-agnostic: scales from $1,500 to any amount
4. Deterministic: rule-based, no ML, fully testable

RISK BUDGET DIMENSIONS
----------------------
1. Per-Trade Risk: Max loss allowed on single trade (0.5%)
2. Daily Risk: Cumulative risk per trading day (1.5%)
3. Open Position Risk: Total risk across open positions (1.0%)
4. Drawdown Limit: Emergency halt threshold (12%)

DEFAULT CONFIGURATION (1500 USD)
--------------------------------
- Max risk per trade: 0.5% = $7.50
- Max daily risk: 1.5% = $22.50
- Max open risk: 1.0% = $15.00
- Drawdown halt: 12% = $180

DECISION OUTCOMES
-----------------
For every trade request, returns ONE of:
- ALLOW_TRADE: Trade approved at requested size
- REDUCE_SIZE: Trade approved but size reduced
- REJECT_TRADE: Trade denied with reason

FAILURE HANDLING
----------------
On any failure (stale data, calculation error, inconsistent state):
- Reject ALL new trades
- Emit CRITICAL alert
- Escalate to System Risk Controller

============================================================
USAGE EXAMPLE
============================================================

```python
from risk_budget_manager import (
    RiskBudgetManager,
    TradeRiskRequest,
    EquityUpdate,
    get_default_config,
)

# Initialize with configuration
config = get_default_config()
manager = RiskBudgetManager(config)

# Provide equity data (from Account Monitor)
equity_update = EquityUpdate(
    account_equity=1500.00,
    available_balance=1500.00,
    unrealized_pnl=0.0,
    realized_pnl_today=0.0,
)
manager.update_equity(equity_update)

# Create trade request
request = TradeRiskRequest(
    symbol="BTC/USDT",
    exchange="binance",
    entry_price=50000.0,
    stop_loss_price=49500.0,  # 1% stop loss
    position_size=0.015,       # 0.015 BTC
    direction="LONG",
)

# Evaluate request
response = manager.evaluate_request(request)

if response.decision == TradeDecision.ALLOW_TRADE:
    # Proceed with trade at full size
    execute_trade(request.position_size)
    
elif response.decision == TradeDecision.REDUCE_SIZE:
    # Proceed with reduced size
    execute_trade(response.allowed_position_size)
    
else:  # REJECT_TRADE
    # Log rejection reason
    print(f"Trade rejected: {response.primary_reason.value}")

# After trade executes, register position
manager.register_position_opened(
    position_id="pos_123",
    symbol="BTC/USDT",
    exchange="binance",
    direction="LONG",
    entry_price=50000.0,
    stop_loss_price=49500.0,
    position_size=0.015,
)

# When position closes, release budget
manager.register_position_closed(
    position_id="pos_123",
    realized_pnl=15.00,  # Profit
)
```

============================================================
EDGE CASES HANDLED
============================================================

1. Stale Equity Data
   - Condition: No equity update within max_staleness_seconds (60s)
   - Action: REJECT_TRADE with STALE_EQUITY_DATA
   - Alert: CRITICAL

2. Drawdown Limit Breach
   - Condition: Current drawdown >= max_drawdown_pct (12%)
   - Action: REJECT_TRADE, HALT trading
   - Alert: EMERGENCY
   - Recovery: Manual resume required

3. Daily Budget Exhausted
   - Condition: Daily risk consumed >= daily limit
   - Action: REJECT_TRADE with DAILY_BUDGET_EXHAUSTED
   - Recovery: Resets at configured time (00:00 UTC)

4. Max Positions Reached
   - Condition: Open positions >= max_positions
   - Action: REJECT_TRADE with MAX_POSITIONS_REACHED

5. Duplicate Symbol Position
   - Condition: Position already open for symbol (if no pyramiding)
   - Action: REJECT_TRADE with DUPLICATE_SYMBOL_POSITION

6. Consecutive Losses
   - Condition: Consecutive losses >= hard_stop_after_losses
   - Action: REJECT_TRADE with DAILY_BUDGET_EXHAUSTED
   - Recovery: Resets on new trading day

7. Missing Stop Loss
   - Condition: Trade request without stop loss
   - Action: REJECT_TRADE with MISSING_STOP_LOSS

8. Invalid Stop Loss Direction
   - Condition: Stop loss on wrong side of entry
   - Action: REJECT_TRADE with INVALID_PARAMETERS

9. Minimum Trade Size
   - Condition: Reduced size below minimum
   - Action: REJECT_TRADE instead of REDUCE_SIZE

10. Calculation Error
    - Condition: Any unexpected error during evaluation
    - Action: REJECT_TRADE with CALCULATION_ERROR
    - Alert: CRITICAL, escalate after 3 consecutive

============================================================
COMPONENTS
============================================================

Types (types.py)
----------------
- TradeDecision: ALLOW_TRADE, REDUCE_SIZE, REJECT_TRADE
- RejectReason: All possible rejection reasons
- TradeRiskRequest: Input for trade evaluation
- TradeRiskResponse: Output with decision and details
- RiskBudgetSnapshot: Complete state snapshot

Configuration (config.py)
-------------------------
- CapitalTierConfig: Per-tier risk limits
- PerTradeConfig: Per-trade risk settings
- DailyBudgetConfig: Daily cumulative settings
- OpenPositionConfig: Open position settings
- DrawdownConfig: System-wide drawdown settings
- Presets: get_default_config(), get_conservative_config()

Tracker (tracker.py)
--------------------
- RiskTracker: Real-time risk consumption tracking
- Position registration and closure
- Daily budget management
- Drawdown calculation

Engine (engine.py)
------------------
- RiskBudgetManager: Main gatekeeper

Persistence (models.py, repository.py)
--------------------------------------
- RiskEvaluationRecord: Evaluation audit trail
- PositionRiskRecord: Position risk tracking
- DailyRiskRecord: Daily usage statistics
- DrawdownRecord: Drawdown history
- RiskBudgetRepository: Database operations

Alerting (alerting.py)
----------------------
- RiskAlertManager: Alert management
- Telegram integration
- Rate limiting and deduplication

============================================================
"""

# ============================================================
# TYPE EXPORTS
# ============================================================

from .types import (
    # Decision Outcomes
    TradeDecision,
    RejectReason,
    RiskBudgetDimension,
    
    # Status and Severity
    AlertSeverity,
    PositionStatus,
    BudgetResetPeriod,
    
    # Request Types
    TradeRiskRequest,
    EquityUpdate,
    
    # Response Types
    BudgetCheckResult,
    TradeRiskResponse,
    
    # Tracking Types
    OpenPositionRisk,
    DailyRiskUsage,
    RiskBudgetSnapshot,
    
    # Errors
    RiskBudgetError,
    EquityDataError,
    PositionStateError,
    BudgetCalculationError,
    ConfigurationError,
)

# ============================================================
# CONFIGURATION EXPORTS
# ============================================================

from .config import (
    # Individual Configs
    PerTradeConfig,
    DailyBudgetConfig,
    OpenPositionConfig,
    DrawdownConfig,
    EquityTrackingConfig,
    AlertingConfig,
    
    # Tier Config
    CapitalTierConfig,
    
    # Master Config
    RiskBudgetConfig,
    
    # Tier Factories
    create_tier_1500,
    create_tier_3000,
    create_tier_5000,
    create_tier_10000,
    
    # Config Presets
    get_default_config,
    get_conservative_config,
    get_aggressive_config,
    load_config_from_dict,
)

# ============================================================
# TRACKER EXPORTS
# ============================================================

from .tracker import (
    RiskTracker,
)

# ============================================================
# ENGINE EXPORTS
# ============================================================

from .engine import (
    RiskBudgetManager,
)

# ============================================================
# MODEL EXPORTS
# ============================================================

from .models import (
    RiskEvaluationRecord,
    PositionRiskRecord,
    DailyRiskRecord,
    DrawdownRecord,
    RiskAlertRecord,
    TradingHaltRecord,
    EquitySnapshotRecord,
)

# ============================================================
# REPOSITORY EXPORTS
# ============================================================

from .repository import (
    RiskBudgetRepository,
)

# ============================================================
# ALERTING EXPORTS
# ============================================================

from .alerting import (
    AlertMessage,
    RiskAlertManager,
    create_telegram_callback,
)


# ============================================================
# ALL EXPORTS
# ============================================================

__all__ = [
    # Types - Decisions
    "TradeDecision",
    "RejectReason",
    "RiskBudgetDimension",
    
    # Types - Status
    "AlertSeverity",
    "PositionStatus",
    "BudgetResetPeriod",
    
    # Types - Requests
    "TradeRiskRequest",
    "EquityUpdate",
    
    # Types - Responses
    "BudgetCheckResult",
    "TradeRiskResponse",
    
    # Types - Tracking
    "OpenPositionRisk",
    "DailyRiskUsage",
    "RiskBudgetSnapshot",
    
    # Types - Errors
    "RiskBudgetError",
    "EquityDataError",
    "PositionStateError",
    "BudgetCalculationError",
    "ConfigurationError",
    
    # Config - Individual
    "PerTradeConfig",
    "DailyBudgetConfig",
    "OpenPositionConfig",
    "DrawdownConfig",
    "EquityTrackingConfig",
    "AlertingConfig",
    
    # Config - Tier
    "CapitalTierConfig",
    
    # Config - Master
    "RiskBudgetConfig",
    
    # Config - Factories
    "create_tier_1500",
    "create_tier_3000",
    "create_tier_5000",
    "create_tier_10000",
    
    # Config - Presets
    "get_default_config",
    "get_conservative_config",
    "get_aggressive_config",
    "load_config_from_dict",
    
    # Tracker
    "RiskTracker",
    
    # Engine
    "RiskBudgetManager",
    
    # Models
    "RiskEvaluationRecord",
    "PositionRiskRecord",
    "DailyRiskRecord",
    "DrawdownRecord",
    "RiskAlertRecord",
    "TradingHaltRecord",
    "EquitySnapshotRecord",
    
    # Repository
    "RiskBudgetRepository",
    
    # Alerting
    "AlertMessage",
    "RiskAlertManager",
    "create_telegram_callback",
]


# ============================================================
# MODULE VERSION
# ============================================================

__version__ = "1.0.0"
