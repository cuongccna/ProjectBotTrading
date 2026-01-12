"""
Data Processing - Risk Keyword Detector.

============================================================
RESPONSIBILITY
============================================================
Detects risk-related keywords and phrases in text.

- Identifies high-risk terminology
- Categorizes risk by type
- Provides severity scoring
- Enables risk-based filtering

============================================================
DESIGN PRINCIPLES
============================================================
- Conservative detection (prefer false positives)
- Configurable keyword lists
- Context-aware matching where possible
- Regular updates to keyword lists
- DESCRIPTIVE only - no predictive scoring

============================================================
RISK CATEGORIES (DESCRIPTIVE)
============================================================
- regulatory_risk: SEC, ban, lawsuit, investigation
- security_risk: hack, exploit, vulnerability, breach
- liquidity_risk: insolvency, withdrawal halt, bank run
- market_risk: crash, dump, manipulation
- operational_risk: downtime, outage, failure

============================================================
"""

import re
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from typing import Dict, List, Optional, Set, Tuple


# ============================================================
# CONFIGURATION
# ============================================================


@dataclass
class RiskKeywordConfig:
    """Configuration for risk keyword detection."""
    
    # Risk categories to detect
    categories: List[str] = field(default_factory=lambda: [
        "regulatory_risk",
        "security_risk",
        "liquidity_risk",
        "market_risk",
        "operational_risk",
    ])
    
    # Context window (characters around keyword)
    context_window: int = 50
    
    # Detection method
    method: str = "pattern"  # exact, pattern
    
    # Version
    version: str = "1.0.0"


# ============================================================
# RESULT TYPES
# ============================================================


@dataclass
class RiskDetection:
    """A single risk keyword detection."""
    
    keyword: str
    category: str
    severity: Decimal  # 0.0 to 1.0
    context: str
    position: int


@dataclass
class RiskDetectionResult:
    """Result of risk keyword detection."""
    
    detections: List[RiskDetection]
    categories_detected: List[str]
    detected_at: datetime = field(default_factory=datetime.utcnow)
    method: str = "pattern"
    version: str = "1.0.0"
    
    @property
    def has_detections(self) -> bool:
        """Check if any risk keywords were detected."""
        return len(self.detections) > 0
    
    @property
    def detection_count(self) -> int:
        """Get total number of detections."""
        return len(self.detections)
    
    def get_by_category(self, category: str) -> List[RiskDetection]:
        """Get detections for a specific category."""
        return [d for d in self.detections if d.category == category]
    
    def get_keywords_by_category(self) -> Dict[str, List[str]]:
        """Get keywords grouped by category."""
        result: Dict[str, List[str]] = {}
        for detection in self.detections:
            if detection.category not in result:
                result[detection.category] = []
            if detection.keyword not in result[detection.category]:
                result[detection.category].append(detection.keyword)
        return result


# ============================================================
# KEYWORD DEFINITIONS
# ============================================================


# Risk keywords with severity weights (descriptive categories only)
RISK_KEYWORDS: Dict[str, Dict[str, float]] = {
    "regulatory_risk": {
        "sec investigation": 0.9,
        "sec lawsuit": 0.9,
        "sec charges": 0.9,
        "cftc lawsuit": 0.9,
        "criminal charges": 0.95,
        "indictment": 0.95,
        "ban": 0.8,
        "banned": 0.8,
        "prohibition": 0.8,
        "lawsuit": 0.7,
        "legal action": 0.7,
        "enforcement": 0.6,
        "regulatory action": 0.7,
        "investigation": 0.6,
        "subpoena": 0.7,
        "settlement": 0.5,
        "fine": 0.5,
        "penalty": 0.5,
        "compliance failure": 0.6,
        "license revoked": 0.8,
    },
    "security_risk": {
        "hack": 0.9,
        "hacked": 0.9,
        "exploit": 0.9,
        "exploited": 0.9,
        "vulnerability": 0.7,
        "breach": 0.8,
        "security breach": 0.9,
        "funds stolen": 0.95,
        "theft": 0.9,
        "drain": 0.9,
        "drained": 0.9,
        "rug pull": 0.95,
        "rugpull": 0.95,
        "rugged": 0.95,
        "attack": 0.7,
        "attacker": 0.7,
        "flash loan attack": 0.9,
        "oracle manipulation": 0.8,
        "compromised": 0.8,
        "malware": 0.7,
        "phishing": 0.6,
    },
    "liquidity_risk": {
        "insolvency": 0.95,
        "insolvent": 0.95,
        "bankruptcy": 0.95,
        "bankrupt": 0.95,
        "liquidation": 0.8,
        "liquidated": 0.8,
        "withdrawal halt": 0.9,
        "withdrawals paused": 0.9,
        "pause withdrawals": 0.9,
        "bank run": 0.9,
        "depeg": 0.8,
        "depegged": 0.8,
        "liquidity crisis": 0.9,
        "redemption halt": 0.9,
        "frozen funds": 0.8,
        "funds frozen": 0.8,
        "unable to withdraw": 0.8,
    },
    "market_risk": {
        "crash": 0.7,
        "crashed": 0.7,
        "plunge": 0.7,
        "plunged": 0.7,
        "collapse": 0.8,
        "collapsed": 0.8,
        "dump": 0.6,
        "dumped": 0.6,
        "manipulation": 0.7,
        "manipulated": 0.7,
        "wash trading": 0.7,
        "pump and dump": 0.8,
        "market manipulation": 0.8,
        "flash crash": 0.8,
        "delisting": 0.7,
        "delisted": 0.7,
        "trading halted": 0.8,
    },
    "operational_risk": {
        "outage": 0.7,
        "downtime": 0.6,
        "offline": 0.6,
        "down": 0.4,
        "failure": 0.6,
        "failed": 0.5,
        "bug": 0.5,
        "error": 0.4,
        "glitch": 0.5,
        "network congestion": 0.5,
        "transaction stuck": 0.5,
        "service unavailable": 0.6,
        "maintenance": 0.3,
        "emergency": 0.7,
        "emergency shutdown": 0.9,
    },
}


# ============================================================
# RISK KEYWORD DETECTOR
# ============================================================


class RiskKeywordDetector:
    """
    Detects risk-related keywords in text.
    
    ============================================================
    USAGE
    ============================================================
    ```python
    config = RiskKeywordConfig()
    detector = RiskKeywordDetector(config)
    
    result = detector.detect(text)
    for detection in result.detections:
        print(f"{detection.keyword}: {detection.category}")
    ```
    
    ============================================================
    """
    
    def __init__(self, config: Optional[RiskKeywordConfig] = None) -> None:
        """
        Initialize the risk keyword detector.
        
        Args:
            config: Detection configuration
        """
        self._config = config or RiskKeywordConfig()
        
        # Build detection patterns
        self._patterns = self._build_patterns()
    
    @property
    def version(self) -> str:
        """Get detector version."""
        return self._config.version
    
    def get_categories(self) -> List[str]:
        """Get list of risk categories."""
        return self._config.categories.copy()
    
    # =========================================================
    # PUBLIC API
    # =========================================================
    
    def detect(self, text: str) -> RiskDetectionResult:
        """
        Detect risk keywords in text.
        
        Args:
            text: Text to analyze
            
        Returns:
            RiskDetectionResult with detections
        """
        detections: List[RiskDetection] = []
        text_lower = text.lower()
        
        for category in self._config.categories:
            if category not in self._patterns:
                continue
            
            for pattern, severity in self._patterns[category]:
                for match in pattern.finditer(text_lower):
                    keyword = match.group()
                    position = match.start()
                    
                    # Extract context
                    context = self._extract_context(text, position, len(keyword))
                    
                    detections.append(RiskDetection(
                        keyword=keyword,
                        category=category,
                        severity=Decimal(str(severity)),
                        context=context,
                        position=position,
                    ))
        
        # Get unique categories
        categories_detected = list(set(d.category for d in detections))
        
        return RiskDetectionResult(
            detections=detections,
            categories_detected=categories_detected,
            method=self._config.method,
            version=self._config.version,
        )
    
    def detect_batch(self, texts: List[str]) -> List[RiskDetectionResult]:
        """
        Detect risk keywords in a batch of texts.
        
        Args:
            texts: List of texts to analyze
            
        Returns:
            List of RiskDetectionResult
        """
        return [self.detect(text) for text in texts]
    
    # =========================================================
    # INTERNAL METHODS
    # =========================================================
    
    def _build_patterns(self) -> Dict[str, List[Tuple[re.Pattern, float]]]:
        """Build regex patterns for each category."""
        patterns: Dict[str, List[Tuple[re.Pattern, float]]] = {}
        
        for category, keywords in RISK_KEYWORDS.items():
            if category not in self._config.categories:
                continue
            
            category_patterns = []
            for keyword, severity in keywords.items():
                # Escape special regex characters
                escaped = re.escape(keyword)
                # Create word boundary pattern
                pattern = re.compile(rf"\b{escaped}\b", re.IGNORECASE)
                category_patterns.append((pattern, severity))
            
            patterns[category] = category_patterns
        
        return patterns
    
    def _extract_context(
        self,
        text: str,
        position: int,
        keyword_length: int,
    ) -> str:
        """Extract context around a keyword match."""
        window = self._config.context_window
        
        start = max(0, position - window)
        end = min(len(text), position + keyword_length + window)
        
        context = text[start:end]
        
        # Add ellipsis if truncated
        if start > 0:
            context = "..." + context
        if end < len(text):
            context = context + "..."
        
        return context.strip()
    
    # =========================================================
    # KEYWORD MANAGEMENT
    # =========================================================
    
    def get_keywords_for_category(self, category: str) -> List[str]:
        """Get keywords for a specific category."""
        return list(RISK_KEYWORDS.get(category, {}).keys())
    
    def get_all_keywords(self) -> Dict[str, List[str]]:
        """Get all keywords grouped by category."""
        return {
            category: list(keywords.keys())
            for category, keywords in RISK_KEYWORDS.items()
        }
    
    def get_category_description(self, category: str) -> str:
        """Get description for a risk category."""
        descriptions = {
            "regulatory_risk": "Legal and regulatory compliance risks",
            "security_risk": "Security vulnerabilities and attacks",
            "liquidity_risk": "Liquidity and solvency risks",
            "market_risk": "Market manipulation and volatility risks",
            "operational_risk": "Technical and operational failures",
        }
        return descriptions.get(category, "Unknown category")
