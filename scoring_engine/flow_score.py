"""
Scoring Engine - Flow Score.

============================================================
RESPONSIBILITY
============================================================
Computes flow scores based on smart money indicators.

- Analyzes whale movements
- Tracks exchange flows
- Identifies accumulation/distribution
- Produces normalized flow score (-1 to 1)

============================================================
DESIGN PRINCIPLES
============================================================
- Conservative interpretation
- Multiple confirmation required
- Clear signal vs noise threshold
- Lag is acceptable for accuracy

============================================================
FLOW INDICATORS
============================================================
1. Whale activity: Large holder movements
2. Exchange flow: Inflow/outflow ratio
3. Accumulation: Long-term holder behavior
4. Smart money: Known address activity

Score interpretation:
- Positive: Net accumulation
- Negative: Net distribution
- Near zero: Neutral/unclear

============================================================
"""

# TODO: Import typing, dataclasses

# TODO: Define FlowScoreConfig dataclass
#   - whale_threshold_usd: float
#   - exchange_flow_weight: float
#   - whale_activity_weight: float
#   - lookback_hours: int

# TODO: Define FlowScoreComponents dataclass
#   - whale_activity_score: float
#   - exchange_flow_score: float
#   - accumulation_score: float

# TODO: Define FlowScore dataclass
#   - asset: str
#   - score: float (-1 to 1)
#   - components: FlowScoreComponents
#   - confidence: float
#   - computed_at: datetime
#   - version: str

# TODO: Implement FlowScorer class
#   - __init__(config, clock)
#   - compute(asset, onchain_data) -> FlowScore
#   - compute_batch(items) -> list[FlowScore]

# TODO: Implement component scoring
#   - compute_whale_activity(transactions) -> float
#   - compute_exchange_flow(flows) -> float
#   - compute_accumulation(holder_data) -> float

# TODO: Implement flow aggregation
#   - Weighted combination
#   - Confidence adjustment
#   - Noise filtering

# TODO: Implement flow interpretation
#   - Strong accumulation signal
#   - Strong distribution signal
#   - Neutral/unclear signal

# TODO: DECISION POINT - Whale threshold per asset
# TODO: DECISION POINT - Exchange address identification
