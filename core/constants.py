"""
Core Module - Constants.

============================================================
RESPONSIBILITY
============================================================
Defines all system-wide constants.

- Provides single source of truth for magic values
- Enables consistent behavior across modules
- Documents the meaning of each constant
- Prevents hardcoding throughout codebase

============================================================
DESIGN PRINCIPLES
============================================================
- All constants are immutable
- Each constant is documented
- Related constants are grouped
- No business logic here

============================================================
"""

# TODO: Import typing, enum

# ============================================================
# SYSTEM CONSTANTS
# ============================================================

# TODO: Define system identification
#   SYSTEM_NAME = "crypto-trading-platform"
#   SYSTEM_VERSION = "0.1.0"

# TODO: Define time constants
#   SECONDS_PER_MINUTE = 60
#   SECONDS_PER_HOUR = 3600
#   SECONDS_PER_DAY = 86400

# ============================================================
# DATA QUALITY CONSTANTS
# ============================================================

# TODO: Define confidence thresholds
#   MIN_CONFIDENCE_SCORE = 0.0
#   MAX_CONFIDENCE_SCORE = 1.0
#   DEFAULT_CONFIDENCE_THRESHOLD = 0.6

# TODO: Define staleness thresholds
#   MAX_NEWS_STALENESS_SECONDS = 300
#   MAX_MARKET_DATA_STALENESS_SECONDS = 60
#   MAX_ONCHAIN_STALENESS_SECONDS = 600

# ============================================================
# RISK CONSTANTS
# ============================================================

# TODO: Define score ranges
#   MIN_RISK_SCORE = 0.0
#   MAX_RISK_SCORE = 1.0
#   RISK_SCORE_HIGH_THRESHOLD = 0.7
#   RISK_SCORE_CRITICAL_THRESHOLD = 0.9

# TODO: Define position limits
#   MAX_POSITION_SIZE_PERCENT = 10.0
#   MIN_POSITION_SIZE_USD = 10.0

# ============================================================
# EXECUTION CONSTANTS
# ============================================================

# TODO: Define order constants
#   ORDER_TYPE_MARKET = "market"
#   ORDER_TYPE_LIMIT = "limit"
#   ORDER_SIDE_BUY = "buy"
#   ORDER_SIDE_SELL = "sell"

# TODO: Define retry constants
#   DEFAULT_MAX_RETRIES = 3
#   DEFAULT_RETRY_BACKOFF_SECONDS = [1, 5, 15]

# ============================================================
# SENTIMENT CONSTANTS
# ============================================================

# TODO: Define sentiment ranges
#   SENTIMENT_VERY_NEGATIVE = -1.0
#   SENTIMENT_NEGATIVE = -0.5
#   SENTIMENT_NEUTRAL = 0.0
#   SENTIMENT_POSITIVE = 0.5
#   SENTIMENT_VERY_POSITIVE = 1.0

# ============================================================
# DATABASE CONSTANTS
# ============================================================

# TODO: Define table name prefixes
#   TABLE_PREFIX_RAW = "raw_"
#   TABLE_PREFIX_PROCESSED = "proc_"
#   TABLE_PREFIX_SIGNAL = "sig_"

# ============================================================
# MONITORING CONSTANTS
# ============================================================

# TODO: Define metric names
#   METRIC_PREFIX = "crypto_trading_"
#   METRIC_DATA_INGESTION_COUNT = "data_ingestion_count"
#   METRIC_TRADE_COUNT = "trade_count"

# TODO: DECISION POINT - Constants loading from config vs hardcoded
