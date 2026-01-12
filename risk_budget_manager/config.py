"""
Risk Budget Manager - Configuration.

============================================================
PURPOSE
============================================================
Configuration system for the Risk Budget Manager with support
for multiple capital tiers and externally configurable limits.

============================================================
CAPITAL SCALING PHILOSOPHY
============================================================
Risk limits are expressed as PERCENTAGES, not absolute values.
This ensures:
- Same logic works from 1500 USD to any capital level
- No code changes required when scaling
- Historical performance remains comparable

Capital tiers allow ADJUSTING percentages for different account sizes:
- Smaller accounts may need tighter limits (less room for error)
- Larger accounts may afford slightly wider limits

============================================================
DEFAULT CONFIGURATION (1500 USD TIER)
============================================================
- Max risk per trade: 0.5% of equity ($7.50)
- Max daily risk: 1.5% of equity ($22.50)
- Max open risk: 1.0% of equity ($15.00)
- Drawdown halt: 12% ($180)

============================================================
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any


# ============================================================
# INDIVIDUAL CONFIGURATIONS
# ============================================================

@dataclass
class PerTradeConfig:
    """
    Per-trade risk budget configuration.
    
    Controls the maximum risk allowed on any single trade.
    """
    
    max_risk_pct: float = 0.5
    """
    Maximum risk per trade as percentage of equity.
    Default: 0.5% (e.g., $7.50 on $1500 account)
    
    RATIONALE:
    - Conservative limit ensures no single trade can
      significantly damage the account
    - At 0.5%, need 200 consecutive losers for ruin
    - Allows for drawdown recovery
    """
    
    min_risk_pct: float = 0.1
    """
    Minimum risk per trade as percentage of equity.
    Trades with less risk may not be worth the overhead.
    """
    
    reduce_when_drawdown_pct: float = 5.0
    """
    Reduce per-trade risk when drawdown exceeds this level.
    Risk will be reduced by the reduction_factor.
    """
    
    reduction_factor: float = 0.5
    """
    Factor to multiply risk limit when in drawdown.
    Example: 0.5% * 0.5 = 0.25% during drawdown
    """


@dataclass
class DailyBudgetConfig:
    """
    Daily cumulative risk budget configuration.
    
    Controls total risk that can be taken in a single trading day.
    """
    
    max_risk_pct: float = 1.5
    """
    Maximum cumulative daily risk as percentage of equity.
    Default: 1.5% (e.g., $22.50 on $1500 account)
    
    RATIONALE:
    - Limits damage from bad trading days
    - At 1.5%/day, worst case is 7.5% weekly drawdown
    - Psychological benefit of knowing daily max loss
    """
    
    reset_hour_utc: int = 0
    """Hour (0-23 UTC) when daily budget resets."""
    
    reset_minute_utc: int = 0
    """Minute (0-59) when daily budget resets."""
    
    warning_threshold_pct: float = 75.0
    """
    Percentage of daily budget used that triggers a warning.
    Example: At 75% of 1.5% = 1.125% used
    """
    
    hard_stop_after_losses: int = 3
    """
    Number of consecutive losses that triggers daily halt.
    Prevents revenge trading behavior.
    """


@dataclass
class OpenPositionConfig:
    """
    Open position risk budget configuration.
    
    Controls total risk across all currently open positions.
    """
    
    max_risk_pct: float = 1.0
    """
    Maximum total open position risk as percentage of equity.
    Default: 1.0% (e.g., $15.00 on $1500 account)
    
    RATIONALE:
    - Limits concurrent exposure
    - If all positions hit stop loss simultaneously,
      maximum loss is 1.0%
    - Lower than daily limit to allow recovery trades
    """
    
    max_positions: int = 3
    """
    Maximum number of concurrent open positions.
    Even if risk budget allows, limits position count.
    """
    
    max_risk_per_symbol_pct: float = 0.5
    """
    Maximum risk on any single symbol.
    Prevents overconcentration.
    """
    
    allow_pyramiding: bool = False
    """
    Whether to allow multiple entries on same symbol.
    If False, only one position per symbol allowed.
    """
    
    correlation_limit: float = 0.7
    """
    Maximum correlation between open positions.
    Highly correlated positions (>0.7) count as one.
    """


@dataclass
class DrawdownConfig:
    """
    System-wide drawdown configuration.
    
    Controls the emergency halt threshold and recovery rules.
    """
    
    max_drawdown_pct: float = 12.0
    """
    Maximum drawdown before full trading halt.
    Default: 12% (e.g., $180 on $1500 account)
    
    RATIONALE:
    - Protects capital from catastrophic loss
    - 12% drawdown requires 13.6% gain to recover
    - Provides psychological safety net
    """
    
    warning_threshold_pct: float = 8.0
    """
    Drawdown level that triggers warning alerts.
    """
    
    reduce_risk_threshold_pct: float = 5.0
    """
    Drawdown level that triggers automatic risk reduction.
    """
    
    risk_reduction_factor: float = 0.5
    """
    Factor applied to all risk limits during drawdown.
    """
    
    recovery_threshold_pct: float = 3.0
    """
    Drawdown must recover to this level before
    resuming normal risk limits.
    """
    
    halt_duration_hours: int = 24
    """
    Minimum hours to remain halted after hitting limit.
    Prevents emotional resumption of trading.
    """
    
    require_manual_resume: bool = True
    """
    Whether manual intervention is required to resume
    after hitting drawdown limit.
    """


@dataclass
class EquityTrackingConfig:
    """
    Configuration for equity data tracking and validation.
    """
    
    max_staleness_seconds: int = 60
    """
    Maximum age of equity data before considered stale.
    Stale data triggers trade rejection.
    """
    
    update_interval_seconds: int = 30
    """
    Expected interval between equity updates.
    """
    
    min_equity_usd: float = 100.0
    """
    Minimum equity required for trading.
    Below this, all trades are rejected.
    """
    
    peak_equity_persistence: bool = True
    """
    Whether to persist peak equity across sessions.
    Required for accurate drawdown calculation.
    """


@dataclass
class AlertingConfig:
    """
    Configuration for alerting and notifications.
    """
    
    enabled: bool = True
    """Whether alerting is enabled."""
    
    telegram_enabled: bool = True
    """Whether to send Telegram alerts."""
    
    # Alert Thresholds
    daily_usage_warning_pct: float = 75.0
    """Daily budget usage that triggers warning."""
    
    drawdown_warning_pct: float = 8.0
    """Drawdown that triggers warning."""
    
    consecutive_rejections: int = 5
    """Consecutive rejections that triggers alert."""
    
    # Rate Limiting
    min_alert_interval_seconds: int = 300
    """Minimum time between similar alerts."""
    
    max_alerts_per_hour: int = 10
    """Maximum alerts per hour (prevents spam)."""


# ============================================================
# CAPITAL TIER CONFIGURATION
# ============================================================

@dataclass
class CapitalTierConfig:
    """
    Configuration for a specific capital tier.
    
    Each tier can have different risk limits appropriate
    for that capital level.
    """
    
    tier_name: str
    """Human-readable tier name."""
    
    min_equity_usd: float
    """Minimum equity for this tier (inclusive)."""
    
    max_equity_usd: float
    """Maximum equity for this tier (exclusive)."""
    
    per_trade: PerTradeConfig = field(default_factory=PerTradeConfig)
    """Per-trade risk configuration."""
    
    daily: DailyBudgetConfig = field(default_factory=DailyBudgetConfig)
    """Daily risk configuration."""
    
    open_position: OpenPositionConfig = field(default_factory=OpenPositionConfig)
    """Open position risk configuration."""
    
    drawdown: DrawdownConfig = field(default_factory=DrawdownConfig)
    """Drawdown configuration."""
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "tier_name": self.tier_name,
            "min_equity_usd": self.min_equity_usd,
            "max_equity_usd": self.max_equity_usd,
            "per_trade": {
                "max_risk_pct": self.per_trade.max_risk_pct,
                "min_risk_pct": self.per_trade.min_risk_pct,
                "reduce_when_drawdown_pct": self.per_trade.reduce_when_drawdown_pct,
                "reduction_factor": self.per_trade.reduction_factor,
            },
            "daily": {
                "max_risk_pct": self.daily.max_risk_pct,
                "reset_hour_utc": self.daily.reset_hour_utc,
                "warning_threshold_pct": self.daily.warning_threshold_pct,
                "hard_stop_after_losses": self.daily.hard_stop_after_losses,
            },
            "open_position": {
                "max_risk_pct": self.open_position.max_risk_pct,
                "max_positions": self.open_position.max_positions,
                "max_risk_per_symbol_pct": self.open_position.max_risk_per_symbol_pct,
                "allow_pyramiding": self.open_position.allow_pyramiding,
            },
            "drawdown": {
                "max_drawdown_pct": self.drawdown.max_drawdown_pct,
                "warning_threshold_pct": self.drawdown.warning_threshold_pct,
                "reduce_risk_threshold_pct": self.drawdown.reduce_risk_threshold_pct,
                "require_manual_resume": self.drawdown.require_manual_resume,
            },
        }


# ============================================================
# MASTER CONFIGURATION
# ============================================================

@dataclass
class RiskBudgetConfig:
    """
    Master configuration for the Risk Budget Manager.
    
    Aggregates all configuration sections and provides
    capital tier lookup.
    """
    
    capital_tiers: List[CapitalTierConfig] = field(default_factory=list)
    """List of capital tier configurations."""
    
    equity_tracking: EquityTrackingConfig = field(
        default_factory=EquityTrackingConfig
    )
    """Equity tracking configuration."""
    
    alerting: AlertingConfig = field(default_factory=AlertingConfig)
    """Alerting configuration."""
    
    # Fallback Configuration (used if no tier matches)
    default_per_trade: PerTradeConfig = field(default_factory=PerTradeConfig)
    """Default per-trade config if no tier matches."""
    
    default_daily: DailyBudgetConfig = field(default_factory=DailyBudgetConfig)
    """Default daily config if no tier matches."""
    
    default_open_position: OpenPositionConfig = field(
        default_factory=OpenPositionConfig
    )
    """Default open position config if no tier matches."""
    
    default_drawdown: DrawdownConfig = field(default_factory=DrawdownConfig)
    """Default drawdown config if no tier matches."""
    
    def get_tier_for_equity(self, equity: float) -> Optional[CapitalTierConfig]:
        """
        Get the appropriate tier for an equity amount.
        
        Args:
            equity: Current account equity in USD
        
        Returns:
            Matching CapitalTierConfig or None if no match
        """
        for tier in self.capital_tiers:
            if tier.min_equity_usd <= equity < tier.max_equity_usd:
                return tier
        return None
    
    def get_per_trade_config(self, equity: float) -> PerTradeConfig:
        """Get per-trade config for equity level."""
        tier = self.get_tier_for_equity(equity)
        return tier.per_trade if tier else self.default_per_trade
    
    def get_daily_config(self, equity: float) -> DailyBudgetConfig:
        """Get daily config for equity level."""
        tier = self.get_tier_for_equity(equity)
        return tier.daily if tier else self.default_daily
    
    def get_open_position_config(self, equity: float) -> OpenPositionConfig:
        """Get open position config for equity level."""
        tier = self.get_tier_for_equity(equity)
        return tier.open_position if tier else self.default_open_position
    
    def get_drawdown_config(self, equity: float) -> DrawdownConfig:
        """Get drawdown config for equity level."""
        tier = self.get_tier_for_equity(equity)
        return tier.drawdown if tier else self.default_drawdown
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "capital_tiers": [tier.to_dict() for tier in self.capital_tiers],
            "equity_tracking": {
                "max_staleness_seconds": self.equity_tracking.max_staleness_seconds,
                "min_equity_usd": self.equity_tracking.min_equity_usd,
            },
            "alerting": {
                "enabled": self.alerting.enabled,
                "telegram_enabled": self.alerting.telegram_enabled,
            },
        }


# ============================================================
# PRESET FACTORIES
# ============================================================

def create_tier_1500() -> CapitalTierConfig:
    """
    Create configuration for $1500 capital tier.
    
    This is the starting tier with conservative limits.
    
    Risk Limits:
    - Per Trade: 0.5% = $7.50
    - Daily: 1.5% = $22.50
    - Open: 1.0% = $15.00
    - Drawdown Halt: 12% = $180
    """
    return CapitalTierConfig(
        tier_name="STARTER_1500",
        min_equity_usd=1000.0,
        max_equity_usd=2500.0,
        per_trade=PerTradeConfig(
            max_risk_pct=0.5,
            min_risk_pct=0.1,
            reduce_when_drawdown_pct=5.0,
            reduction_factor=0.5,
        ),
        daily=DailyBudgetConfig(
            max_risk_pct=1.5,
            reset_hour_utc=0,
            warning_threshold_pct=75.0,
            hard_stop_after_losses=3,
        ),
        open_position=OpenPositionConfig(
            max_risk_pct=1.0,
            max_positions=2,  # Conservative for small account
            max_risk_per_symbol_pct=0.5,
            allow_pyramiding=False,
        ),
        drawdown=DrawdownConfig(
            max_drawdown_pct=12.0,
            warning_threshold_pct=8.0,
            reduce_risk_threshold_pct=5.0,
            risk_reduction_factor=0.5,
            recovery_threshold_pct=3.0,
            require_manual_resume=True,
        ),
    )


def create_tier_3000() -> CapitalTierConfig:
    """
    Create configuration for $3000 capital tier.
    
    Slightly more room to operate with increased position count.
    
    Risk Limits:
    - Per Trade: 0.5% = $15.00
    - Daily: 1.5% = $45.00
    - Open: 1.0% = $30.00
    - Drawdown Halt: 12% = $360
    """
    return CapitalTierConfig(
        tier_name="GROWTH_3000",
        min_equity_usd=2500.0,
        max_equity_usd=4500.0,
        per_trade=PerTradeConfig(
            max_risk_pct=0.5,
            min_risk_pct=0.1,
            reduce_when_drawdown_pct=5.0,
            reduction_factor=0.5,
        ),
        daily=DailyBudgetConfig(
            max_risk_pct=1.5,
            reset_hour_utc=0,
            warning_threshold_pct=75.0,
            hard_stop_after_losses=3,
        ),
        open_position=OpenPositionConfig(
            max_risk_pct=1.0,
            max_positions=3,  # Can handle more positions
            max_risk_per_symbol_pct=0.5,
            allow_pyramiding=False,
        ),
        drawdown=DrawdownConfig(
            max_drawdown_pct=12.0,
            warning_threshold_pct=8.0,
            reduce_risk_threshold_pct=5.0,
            risk_reduction_factor=0.5,
            recovery_threshold_pct=3.0,
            require_manual_resume=True,
        ),
    )


def create_tier_5000() -> CapitalTierConfig:
    """
    Create configuration for $5000 capital tier.
    
    More established account with room for additional positions.
    
    Risk Limits:
    - Per Trade: 0.5% = $25.00
    - Daily: 1.5% = $75.00
    - Open: 1.0% = $50.00
    - Drawdown Halt: 12% = $600
    """
    return CapitalTierConfig(
        tier_name="ESTABLISHED_5000",
        min_equity_usd=4500.0,
        max_equity_usd=10000.0,
        per_trade=PerTradeConfig(
            max_risk_pct=0.5,
            min_risk_pct=0.1,
            reduce_when_drawdown_pct=5.0,
            reduction_factor=0.5,
        ),
        daily=DailyBudgetConfig(
            max_risk_pct=1.5,
            reset_hour_utc=0,
            warning_threshold_pct=75.0,
            hard_stop_after_losses=4,  # More tolerance
        ),
        open_position=OpenPositionConfig(
            max_risk_pct=1.2,  # Slightly higher capacity
            max_positions=4,
            max_risk_per_symbol_pct=0.5,
            allow_pyramiding=False,
        ),
        drawdown=DrawdownConfig(
            max_drawdown_pct=12.0,
            warning_threshold_pct=8.0,
            reduce_risk_threshold_pct=5.0,
            risk_reduction_factor=0.5,
            recovery_threshold_pct=3.0,
            require_manual_resume=True,
        ),
    )


def create_tier_10000() -> CapitalTierConfig:
    """
    Create configuration for $10000+ capital tier.
    
    Larger account with more flexibility.
    
    Risk Limits:
    - Per Trade: 0.5% = $50.00
    - Daily: 2.0% = $200.00
    - Open: 1.5% = $150.00
    - Drawdown Halt: 10% = $1000
    """
    return CapitalTierConfig(
        tier_name="ADVANCED_10000",
        min_equity_usd=10000.0,
        max_equity_usd=float('inf'),
        per_trade=PerTradeConfig(
            max_risk_pct=0.5,
            min_risk_pct=0.1,
            reduce_when_drawdown_pct=4.0,
            reduction_factor=0.5,
        ),
        daily=DailyBudgetConfig(
            max_risk_pct=2.0,  # Slightly more daily capacity
            reset_hour_utc=0,
            warning_threshold_pct=75.0,
            hard_stop_after_losses=5,
        ),
        open_position=OpenPositionConfig(
            max_risk_pct=1.5,
            max_positions=5,
            max_risk_per_symbol_pct=0.5,
            allow_pyramiding=True,  # Allow scaling in
        ),
        drawdown=DrawdownConfig(
            max_drawdown_pct=10.0,  # Tighter drawdown control
            warning_threshold_pct=6.0,
            reduce_risk_threshold_pct=4.0,
            risk_reduction_factor=0.5,
            recovery_threshold_pct=2.0,
            require_manual_resume=True,
        ),
    )


def get_default_config() -> RiskBudgetConfig:
    """
    Get default configuration with all capital tiers.
    
    Returns:
        Complete RiskBudgetConfig with tier support
    """
    return RiskBudgetConfig(
        capital_tiers=[
            create_tier_1500(),
            create_tier_3000(),
            create_tier_5000(),
            create_tier_10000(),
        ],
        equity_tracking=EquityTrackingConfig(
            max_staleness_seconds=60,
            update_interval_seconds=30,
            min_equity_usd=100.0,
            peak_equity_persistence=True,
        ),
        alerting=AlertingConfig(
            enabled=True,
            telegram_enabled=True,
            daily_usage_warning_pct=75.0,
            drawdown_warning_pct=8.0,
            consecutive_rejections=5,
            min_alert_interval_seconds=300,
            max_alerts_per_hour=10,
        ),
        # Fallback defaults (same as 1500 tier)
        default_per_trade=PerTradeConfig(),
        default_daily=DailyBudgetConfig(),
        default_open_position=OpenPositionConfig(),
        default_drawdown=DrawdownConfig(),
    )


def get_conservative_config() -> RiskBudgetConfig:
    """
    Get conservative configuration with reduced limits.
    
    Suitable for:
    - New systems in testing
    - High volatility periods
    - Capital preservation priority
    """
    config = get_default_config()
    
    # Reduce all risk limits by 50%
    for tier in config.capital_tiers:
        tier.per_trade.max_risk_pct *= 0.5
        tier.daily.max_risk_pct *= 0.5
        tier.open_position.max_risk_pct *= 0.5
        tier.open_position.max_positions = max(1, tier.open_position.max_positions - 1)
        tier.drawdown.max_drawdown_pct *= 0.75  # 25% reduction
    
    return config


def get_aggressive_config() -> RiskBudgetConfig:
    """
    Get aggressive configuration with higher limits.
    
    WARNING: Only for proven systems with track record.
    
    Suitable for:
    - Established profitable systems
    - Lower volatility periods
    - Growth priority
    """
    config = get_default_config()
    
    # Increase limits by 25%
    for tier in config.capital_tiers:
        tier.per_trade.max_risk_pct = min(1.0, tier.per_trade.max_risk_pct * 1.25)
        tier.daily.max_risk_pct = min(3.0, tier.daily.max_risk_pct * 1.25)
        tier.open_position.max_risk_pct = min(2.0, tier.open_position.max_risk_pct * 1.25)
        tier.open_position.max_positions += 1
    
    return config


# ============================================================
# CONFIGURATION LOADING
# ============================================================

def load_config_from_dict(data: Dict[str, Any]) -> RiskBudgetConfig:
    """
    Load configuration from a dictionary.
    
    Useful for loading from JSON/YAML files or environment.
    
    Args:
        data: Configuration dictionary
    
    Returns:
        RiskBudgetConfig instance
    """
    config = get_default_config()
    
    # Override capital tiers if provided
    if "capital_tiers" in data:
        config.capital_tiers = []
        for tier_data in data["capital_tiers"]:
            tier = CapitalTierConfig(
                tier_name=tier_data.get("tier_name", "CUSTOM"),
                min_equity_usd=tier_data.get("min_equity_usd", 0),
                max_equity_usd=tier_data.get("max_equity_usd", float('inf')),
            )
            
            if "per_trade" in tier_data:
                pt = tier_data["per_trade"]
                tier.per_trade = PerTradeConfig(
                    max_risk_pct=pt.get("max_risk_pct", 0.5),
                    min_risk_pct=pt.get("min_risk_pct", 0.1),
                    reduce_when_drawdown_pct=pt.get("reduce_when_drawdown_pct", 5.0),
                    reduction_factor=pt.get("reduction_factor", 0.5),
                )
            
            if "daily" in tier_data:
                d = tier_data["daily"]
                tier.daily = DailyBudgetConfig(
                    max_risk_pct=d.get("max_risk_pct", 1.5),
                    reset_hour_utc=d.get("reset_hour_utc", 0),
                    warning_threshold_pct=d.get("warning_threshold_pct", 75.0),
                    hard_stop_after_losses=d.get("hard_stop_after_losses", 3),
                )
            
            if "open_position" in tier_data:
                op = tier_data["open_position"]
                tier.open_position = OpenPositionConfig(
                    max_risk_pct=op.get("max_risk_pct", 1.0),
                    max_positions=op.get("max_positions", 3),
                    max_risk_per_symbol_pct=op.get("max_risk_per_symbol_pct", 0.5),
                    allow_pyramiding=op.get("allow_pyramiding", False),
                )
            
            if "drawdown" in tier_data:
                dd = tier_data["drawdown"]
                tier.drawdown = DrawdownConfig(
                    max_drawdown_pct=dd.get("max_drawdown_pct", 12.0),
                    warning_threshold_pct=dd.get("warning_threshold_pct", 8.0),
                    reduce_risk_threshold_pct=dd.get("reduce_risk_threshold_pct", 5.0),
                    require_manual_resume=dd.get("require_manual_resume", True),
                )
            
            config.capital_tiers.append(tier)
    
    # Override equity tracking if provided
    if "equity_tracking" in data:
        et = data["equity_tracking"]
        config.equity_tracking = EquityTrackingConfig(
            max_staleness_seconds=et.get("max_staleness_seconds", 60),
            update_interval_seconds=et.get("update_interval_seconds", 30),
            min_equity_usd=et.get("min_equity_usd", 100.0),
            peak_equity_persistence=et.get("peak_equity_persistence", True),
        )
    
    # Override alerting if provided
    if "alerting" in data:
        a = data["alerting"]
        config.alerting = AlertingConfig(
            enabled=a.get("enabled", True),
            telegram_enabled=a.get("telegram_enabled", True),
            daily_usage_warning_pct=a.get("daily_usage_warning_pct", 75.0),
            drawdown_warning_pct=a.get("drawdown_warning_pct", 8.0),
            consecutive_rejections=a.get("consecutive_rejections", 5),
            min_alert_interval_seconds=a.get("min_alert_interval_seconds", 300),
            max_alerts_per_hour=a.get("max_alerts_per_hour", 10),
        )
    
    return config
