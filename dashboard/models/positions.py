"""
Dashboard Database Models - Positions & Execution.

============================================================
POSITIONS & EXECUTION TABLES
============================================================

Tables for tracking open positions, orders, and execution quality.
View-only - no order placement from dashboard.

Source: Position Manager, Execution Engine
Update Frequency: Real-time (on change)
Retention: 90 days for orders, indefinite for positions

============================================================
"""

from datetime import datetime
from enum import Enum
from typing import Optional, Dict, List
from dataclasses import dataclass, field


class PositionSide(str, Enum):
    """Position side."""
    LONG = "long"
    SHORT = "short"
    FLAT = "flat"


class OrderStatus(str, Enum):
    """Order status."""
    PENDING = "pending"
    SUBMITTED = "submitted"
    PARTIAL = "partial"
    FILLED = "filled"
    CANCELLED = "cancelled"
    REJECTED = "rejected"
    EXPIRED = "expired"


class OrderType(str, Enum):
    """Order type."""
    MARKET = "market"
    LIMIT = "limit"
    STOP = "stop"
    STOP_LIMIT = "stop_limit"


@dataclass
class CurrentPosition:
    """
    Current open position.
    
    Table: current_positions
    Primary Key: (asset, exchange)
    """
    asset: str
    exchange: str
    
    # Position details
    side: PositionSide
    size: float  # In asset units
    size_usd: float
    entry_price: float
    current_price: float
    
    # P&L
    unrealized_pnl: float
    unrealized_pnl_pct: float
    realized_pnl_today: float
    
    # Risk metrics
    position_pct_of_portfolio: float
    position_vs_risk_budget: float  # Actual vs allowed
    liquidation_price: Optional[float]
    margin_ratio: Optional[float]
    
    # Timing
    opened_at: datetime
    last_update: datetime
    hold_duration_hours: float
    
    # Strategy
    strategy_id: str
    signal_id: Optional[str]
    
    updated_at: datetime = field(default_factory=datetime.utcnow)
    
    # Source traceability
    source_module: str = "position_manager"
    update_frequency_seconds: int = 5
    
    def to_dict(self) -> dict:
        return {
            "asset": self.asset,
            "exchange": self.exchange,
            "side": self.side.value,
            "size": round(self.size, 8),
            "size_usd": round(self.size_usd, 2),
            "entry_price": self.entry_price,
            "current_price": self.current_price,
            "unrealized_pnl": round(self.unrealized_pnl, 2),
            "unrealized_pnl_pct": round(self.unrealized_pnl_pct, 2),
            "realized_pnl_today": round(self.realized_pnl_today, 2),
            "position_pct_of_portfolio": round(self.position_pct_of_portfolio, 2),
            "position_vs_risk_budget": round(self.position_vs_risk_budget, 2),
            "liquidation_price": self.liquidation_price,
            "margin_ratio": round(self.margin_ratio, 4) if self.margin_ratio else None,
            "opened_at": self.opened_at.isoformat(),
            "hold_duration_hours": round(self.hold_duration_hours, 1),
            "strategy_id": self.strategy_id,
            "updated_at": self.updated_at.isoformat(),
        }


@dataclass
class OpenOrder:
    """
    Open/pending order.
    
    Table: open_orders
    Primary Key: order_id
    """
    order_id: str
    exchange_order_id: Optional[str]
    exchange: str
    
    # Order details
    asset: str
    side: str  # buy, sell
    order_type: OrderType
    status: OrderStatus
    
    # Sizing
    quantity: float
    quantity_usd: float
    filled_quantity: float
    remaining_quantity: float
    
    # Pricing
    price: Optional[float]  # For limit orders
    stop_price: Optional[float]  # For stop orders
    avg_fill_price: Optional[float]
    
    # Timing
    created_at: datetime
    submitted_at: Optional[datetime]
    last_update: datetime
    
    # Strategy
    strategy_id: str
    decision_id: Optional[str]
    
    updated_at: datetime = field(default_factory=datetime.utcnow)
    
    # Source traceability
    source_module: str = "order_manager"
    
    def to_dict(self) -> dict:
        return {
            "order_id": self.order_id,
            "exchange_order_id": self.exchange_order_id,
            "exchange": self.exchange,
            "asset": self.asset,
            "side": self.side,
            "order_type": self.order_type.value,
            "status": self.status.value,
            "quantity": round(self.quantity, 8),
            "quantity_usd": round(self.quantity_usd, 2),
            "filled_quantity": round(self.filled_quantity, 8),
            "remaining_quantity": round(self.remaining_quantity, 8),
            "fill_pct": round(self.filled_quantity / max(0.00000001, self.quantity) * 100, 1),
            "price": self.price,
            "avg_fill_price": self.avg_fill_price,
            "created_at": self.created_at.isoformat(),
            "strategy_id": self.strategy_id,
            "updated_at": self.updated_at.isoformat(),
        }


@dataclass
class ExecutionMetrics:
    """
    Execution quality metrics.
    
    Table: execution_metrics
    Primary Key: (exchange, time_bucket)
    """
    exchange: str
    time_bucket: datetime  # Hourly
    
    # Volume
    orders_submitted: int
    orders_filled: int
    orders_cancelled: int
    orders_rejected: int
    
    # Latency
    avg_submission_latency_ms: float
    avg_fill_latency_ms: float
    p95_submission_latency_ms: float
    p95_fill_latency_ms: float
    
    # Slippage
    avg_slippage_bps: float  # Basis points
    max_slippage_bps: float
    positive_slippage_count: int  # Better than expected
    negative_slippage_count: int
    
    # Fill quality
    avg_fill_rate: float  # 0-1
    partial_fill_count: int
    
    # Cost
    total_fees_usd: float
    avg_fee_pct: float
    
    updated_at: datetime = field(default_factory=datetime.utcnow)
    
    # Source traceability
    source_module: str = "execution_monitor"
    update_frequency_seconds: int = 300
    
    def to_dict(self) -> dict:
        return {
            "exchange": self.exchange,
            "time_bucket": self.time_bucket.isoformat(),
            "orders_submitted": self.orders_submitted,
            "orders_filled": self.orders_filled,
            "fill_rate_pct": round(self.orders_filled / max(1, self.orders_submitted) * 100, 1),
            "avg_submission_latency_ms": round(self.avg_submission_latency_ms, 1),
            "avg_fill_latency_ms": round(self.avg_fill_latency_ms, 1),
            "avg_slippage_bps": round(self.avg_slippage_bps, 2),
            "max_slippage_bps": round(self.max_slippage_bps, 2),
            "total_fees_usd": round(self.total_fees_usd, 2),
            "updated_at": self.updated_at.isoformat(),
        }


@dataclass
class PortfolioSnapshot:
    """
    Portfolio snapshot.
    
    Table: portfolio_snapshots
    Primary Key: snapshot_id
    """
    snapshot_id: str
    timestamp: datetime
    
    # Value
    total_value_usd: float
    cash_balance_usd: float
    positions_value_usd: float
    
    # P&L
    total_pnl_today: float
    total_pnl_pct_today: float
    unrealized_pnl: float
    realized_pnl: float
    
    # Allocation
    position_count: int
    largest_position_pct: float
    cash_pct: float
    
    # Risk
    portfolio_beta: Optional[float]
    portfolio_volatility: Optional[float]
    var_95_usd: Optional[float]  # Value at Risk
    
    # Drawdown
    peak_value_usd: float
    current_drawdown_pct: float
    max_drawdown_pct: float
    
    # Source traceability
    source_module: str = "portfolio_manager"
    update_frequency_seconds: int = 60
    
    def to_dict(self) -> dict:
        return {
            "snapshot_id": self.snapshot_id,
            "timestamp": self.timestamp.isoformat(),
            "total_value_usd": round(self.total_value_usd, 2),
            "cash_balance_usd": round(self.cash_balance_usd, 2),
            "positions_value_usd": round(self.positions_value_usd, 2),
            "total_pnl_today": round(self.total_pnl_today, 2),
            "total_pnl_pct_today": round(self.total_pnl_pct_today, 2),
            "position_count": self.position_count,
            "current_drawdown_pct": round(self.current_drawdown_pct, 2),
            "max_drawdown_pct": round(self.max_drawdown_pct, 2),
        }


# =============================================================
# SQL TABLE DEFINITIONS
# =============================================================

CURRENT_POSITIONS_TABLE = """
CREATE TABLE IF NOT EXISTS current_positions (
    asset VARCHAR(20) NOT NULL,
    exchange VARCHAR(50) NOT NULL,
    side VARCHAR(10) NOT NULL,
    size FLOAT NOT NULL,
    size_usd FLOAT NOT NULL,
    entry_price FLOAT NOT NULL,
    current_price FLOAT NOT NULL,
    unrealized_pnl FLOAT DEFAULT 0,
    unrealized_pnl_pct FLOAT DEFAULT 0,
    realized_pnl_today FLOAT DEFAULT 0,
    position_pct_of_portfolio FLOAT DEFAULT 0,
    position_vs_risk_budget FLOAT DEFAULT 0,
    liquidation_price FLOAT,
    margin_ratio FLOAT,
    opened_at TIMESTAMP NOT NULL,
    last_update TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    hold_duration_hours FLOAT DEFAULT 0,
    strategy_id VARCHAR(100) NOT NULL,
    signal_id VARCHAR(100),
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    source_module VARCHAR(100) DEFAULT 'position_manager',
    PRIMARY KEY (asset, exchange)
);

CREATE INDEX IF NOT EXISTS idx_positions_side ON current_positions(side);
CREATE INDEX IF NOT EXISTS idx_positions_strategy ON current_positions(strategy_id);
"""

OPEN_ORDERS_TABLE = """
CREATE TABLE IF NOT EXISTS open_orders (
    order_id VARCHAR(100) PRIMARY KEY,
    exchange_order_id VARCHAR(100),
    exchange VARCHAR(50) NOT NULL,
    asset VARCHAR(20) NOT NULL,
    side VARCHAR(10) NOT NULL,
    order_type VARCHAR(20) NOT NULL,
    status VARCHAR(20) NOT NULL,
    quantity FLOAT NOT NULL,
    quantity_usd FLOAT NOT NULL,
    filled_quantity FLOAT DEFAULT 0,
    remaining_quantity FLOAT NOT NULL,
    price FLOAT,
    stop_price FLOAT,
    avg_fill_price FLOAT,
    created_at TIMESTAMP NOT NULL,
    submitted_at TIMESTAMP,
    last_update TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    strategy_id VARCHAR(100) NOT NULL,
    decision_id VARCHAR(100),
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    source_module VARCHAR(100) DEFAULT 'order_manager'
);

CREATE INDEX IF NOT EXISTS idx_orders_status ON open_orders(status);
CREATE INDEX IF NOT EXISTS idx_orders_asset ON open_orders(asset);
CREATE INDEX IF NOT EXISTS idx_orders_exchange ON open_orders(exchange);
"""

EXECUTION_METRICS_TABLE = """
CREATE TABLE IF NOT EXISTS execution_metrics (
    exchange VARCHAR(50) NOT NULL,
    time_bucket TIMESTAMP NOT NULL,
    orders_submitted INTEGER DEFAULT 0,
    orders_filled INTEGER DEFAULT 0,
    orders_cancelled INTEGER DEFAULT 0,
    orders_rejected INTEGER DEFAULT 0,
    avg_submission_latency_ms FLOAT DEFAULT 0,
    avg_fill_latency_ms FLOAT DEFAULT 0,
    p95_submission_latency_ms FLOAT DEFAULT 0,
    p95_fill_latency_ms FLOAT DEFAULT 0,
    avg_slippage_bps FLOAT DEFAULT 0,
    max_slippage_bps FLOAT DEFAULT 0,
    positive_slippage_count INTEGER DEFAULT 0,
    negative_slippage_count INTEGER DEFAULT 0,
    avg_fill_rate FLOAT DEFAULT 0,
    partial_fill_count INTEGER DEFAULT 0,
    total_fees_usd FLOAT DEFAULT 0,
    avg_fee_pct FLOAT DEFAULT 0,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    source_module VARCHAR(100) DEFAULT 'execution_monitor',
    PRIMARY KEY (exchange, time_bucket)
);

CREATE INDEX IF NOT EXISTS idx_exec_exchange ON execution_metrics(exchange);
CREATE INDEX IF NOT EXISTS idx_exec_time ON execution_metrics(time_bucket);
"""

PORTFOLIO_SNAPSHOTS_TABLE = """
CREATE TABLE IF NOT EXISTS portfolio_snapshots (
    snapshot_id VARCHAR(100) PRIMARY KEY,
    timestamp TIMESTAMP NOT NULL,
    total_value_usd FLOAT NOT NULL,
    cash_balance_usd FLOAT DEFAULT 0,
    positions_value_usd FLOAT DEFAULT 0,
    total_pnl_today FLOAT DEFAULT 0,
    total_pnl_pct_today FLOAT DEFAULT 0,
    unrealized_pnl FLOAT DEFAULT 0,
    realized_pnl FLOAT DEFAULT 0,
    position_count INTEGER DEFAULT 0,
    largest_position_pct FLOAT DEFAULT 0,
    cash_pct FLOAT DEFAULT 0,
    portfolio_beta FLOAT,
    portfolio_volatility FLOAT,
    var_95_usd FLOAT,
    peak_value_usd FLOAT,
    current_drawdown_pct FLOAT DEFAULT 0,
    max_drawdown_pct FLOAT DEFAULT 0,
    source_module VARCHAR(100) DEFAULT 'portfolio_manager'
);

CREATE INDEX IF NOT EXISTS idx_portfolio_time ON portfolio_snapshots(timestamp);
"""

ALL_POSITION_TABLES = [
    CURRENT_POSITIONS_TABLE,
    OPEN_ORDERS_TABLE,
    EXECUTION_METRICS_TABLE,
    PORTFOLIO_SNAPSHOTS_TABLE,
]
