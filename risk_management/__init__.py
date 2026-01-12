"""
Risk Management Package.

This package implements the hierarchical risk management system.
Risk controls exist at system, strategy, and trade levels.

Modules:
- system_guard: System-level controls (can halt everything)
- strategy_guard: Strategy-level controls (can pause strategies)
- trade_guard: Trade-level controls (can veto trades)
- drawdown_monitor: Drawdown tracking and alerts
"""

# TODO: Export guard classes
# from .system_guard import SystemGuard, SystemHealthStatus
# from .strategy_guard import StrategyGuard, StrategyHealthStatus
# from .trade_guard import TradeGuard, TradeGuardResult
# from .drawdown_monitor import DrawdownMonitor, DrawdownStatus
