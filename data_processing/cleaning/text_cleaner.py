"""
Data Processing - Text Cleaner.

============================================================
RESPONSIBILITY
============================================================
Cleans and preprocesses text data for analysis.

- Removes noise (HTML, special characters, etc.)
- Normalizes whitespace and encoding
- Handles multi-language text
- Prepares text for NLP processing

============================================================
DESIGN PRINCIPLES
============================================================
- Reversible operations where possible
- Preserve semantic meaning
- Language-agnostic core functions
- Configurable cleaning pipeline

============================================================
CLEANING PIPELINE
============================================================
1. Decode HTML entities
2. Remove HTML tags
3. Normalize unicode
4. Remove URLs (optionally extract)
5. Remove special characters
6. Normalize whitespace
7. Lowercase (optional)

============================================================
"""

import html
import re
import unicodedata
from dataclasses import dataclass, field
from datetime import datetime
from typing import List, Optional, Tuple


# ============================================================
# CONFIGURATION
# ============================================================


@dataclass
class TextCleanerConfig:
    """Configuration for text cleaning."""
    
    # HTML handling
    remove_html: bool = True
    decode_html_entities: bool = True
    
    # URL handling
    remove_urls: bool = False
    extract_urls: bool = True
    
    # Normalization
    normalize_unicode: bool = True
    unicode_form: str = "NFKC"  # NFC, NFKC, NFD, NFKD
    
    # Case
    lowercase: bool = False
    
    # Whitespace
    normalize_whitespace: bool = True
    
    # Special characters
    remove_control_chars: bool = True
    remove_zero_width: bool = True
    
    # Length
    min_length: int = 0
    max_length: int = 100000
    
    # Version
    version: str = "1.0.0"


# ============================================================
# RESULT TYPES
# ============================================================


@dataclass
class CleanedText:
    """Result of text cleaning."""
    
    original: str
    cleaned: str
    extracted_urls: List[str] = field(default_factory=list)
    cleaning_operations: List[str] = field(default_factory=list)
    characters_removed: int = 0
    cleaned_at: datetime = field(default_factory=datetime.utcnow)
    version: str = "1.0.0"


# ============================================================
# TEXT CLEANER
# ============================================================


class TextCleaner:
    """
    Cleans and preprocesses text data.
    
    ============================================================
    USAGE
    ============================================================
    ```python
    config = TextCleanerConfig()
    cleaner = TextCleaner(config)
    
    result = cleaner.clean(raw_text)
    print(result.cleaned)
    print(result.extracted_urls)
    ```
    
    ============================================================
    """
    
    # URL regex pattern
    URL_PATTERN = re.compile(
        r"https?://(?:[-\w.]|(?:%[\da-fA-F]{2}))+[/\w\-.~:/?#\[\]@!$&'()*+,;=%]*",
        re.IGNORECASE
    )
    
    # HTML tag pattern
    HTML_TAG_PATTERN = re.compile(r"<[^>]+>", re.IGNORECASE)
    
    # Control characters pattern (except newlines and tabs)
    CONTROL_CHAR_PATTERN = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
    
    # Zero-width characters
    ZERO_WIDTH_PATTERN = re.compile(r"[\u200b-\u200f\u2028-\u202f\u2060\ufeff]")
    
    # Multiple whitespace pattern
    WHITESPACE_PATTERN = re.compile(r"\s+")
    
    def __init__(self, config: TextCleanerConfig) -> None:
        """
        Initialize the text cleaner.
        
        Args:
            config: Cleaning configuration
        """
        self._config = config
    
    @property
    def version(self) -> str:
        """Get cleaner version."""
        return self._config.version
    
    # =========================================================
    # PUBLIC API
    # =========================================================
    
    def clean(self, text: str) -> CleanedText:
        """
        Clean a single text string.
        
        Args:
            text: Raw text to clean
            
        Returns:
            CleanedText with cleaned content and metadata
        """
        original = text
        operations: List[str] = []
        extracted_urls: List[str] = []
        
        # Track length changes
        initial_length = len(text)
        
        # 1. Decode HTML entities
        if self._config.decode_html_entities:
            text = self._decode_html_entities(text)
            operations.append("decode_html_entities")
        
        # 2. Remove HTML tags
        if self._config.remove_html:
            text = self._remove_html_tags(text)
            operations.append("remove_html")
        
        # 3. Extract URLs (before removal)
        if self._config.extract_urls:
            extracted_urls = self._extract_urls(text)
            if extracted_urls:
                operations.append("extract_urls")
        
        # 4. Remove URLs
        if self._config.remove_urls:
            text = self._remove_urls(text)
            operations.append("remove_urls")
        
        # 5. Normalize unicode
        if self._config.normalize_unicode:
            text = self._normalize_unicode(text)
            operations.append("normalize_unicode")
        
        # 6. Remove control characters
        if self._config.remove_control_chars:
            text = self._remove_control_chars(text)
            operations.append("remove_control_chars")
        
        # 7. Remove zero-width characters
        if self._config.remove_zero_width:
            text = self._remove_zero_width_chars(text)
            operations.append("remove_zero_width")
        
        # 8. Normalize whitespace
        if self._config.normalize_whitespace:
            text = self._normalize_whitespace(text)
            operations.append("normalize_whitespace")
        
        # 9. Lowercase
        if self._config.lowercase:
            text = text.lower()
            operations.append("lowercase")
        
        # 10. Trim to max length
        if self._config.max_length and len(text) > self._config.max_length:
            text = text[:self._config.max_length]
            operations.append("truncate")
        
        characters_removed = initial_length - len(text)
        
        return CleanedText(
            original=original,
            cleaned=text,
            extracted_urls=extracted_urls,
            cleaning_operations=operations,
            characters_removed=max(0, characters_removed),
            version=self._config.version,
        )
    
    def clean_batch(self, texts: List[str]) -> List[CleanedText]:
        """
        Clean a batch of texts.
        
        Args:
            texts: List of raw texts
            
        Returns:
            List of CleanedText results
        """
        return [self.clean(text) for text in texts]
    
    # =========================================================
    # CLEANING OPERATIONS
    # =========================================================
    
    def _decode_html_entities(self, text: str) -> str:
        """
        Decode HTML entities.
        
        Examples:
            &amp; -> &
            &lt; -> <
            &nbsp; -> (space)
        """
        return html.unescape(text)
    
    def _remove_html_tags(self, text: str) -> str:
        """Remove HTML tags from text."""
        return self.HTML_TAG_PATTERN.sub("", text)
    
    def _extract_urls(self, text: str) -> List[str]:
        """Extract URLs from text."""
        return self.URL_PATTERN.findall(text)
    
    def _remove_urls(self, text: str) -> str:
        """Remove URLs from text."""
        return self.URL_PATTERN.sub("", text)
    
    def _normalize_unicode(self, text: str) -> str:
        """
        Normalize unicode characters.
        
        NFKC normalization:
        - Compatibility decomposition
        - Canonical composition
        """
        return unicodedata.normalize(self._config.unicode_form, text)
    
    def _remove_control_chars(self, text: str) -> str:
        """Remove control characters (except newlines and tabs)."""
        return self.CONTROL_CHAR_PATTERN.sub("", text)
    
    def _remove_zero_width_chars(self, text: str) -> str:
        """Remove zero-width characters."""
        return self.ZERO_WIDTH_PATTERN.sub("", text)
    
    def _normalize_whitespace(self, text: str) -> str:
        """
        Normalize whitespace.
        
        - Replace multiple spaces with single space
        - Trim leading/trailing whitespace
        """
        return self.WHITESPACE_PATTERN.sub(" ", text).strip()
    
    # =========================================================
    # SPECIALIZED CLEANERS
    # =========================================================
    
    def clean_title(self, title: str) -> str:
        """
        Clean a title string.
        
        More aggressive cleaning for titles.
        """
        # Basic cleaning
        result = self.clean(title)
        text = result.cleaned
        
        # Remove leading/trailing quotes
        text = text.strip("\"'")
        
        # Remove common prefixes
        prefixes = ["BREAKING:", "UPDATE:", "EXCLUSIVE:", "[BREAKING]", "[UPDATE]"]
        for prefix in prefixes:
            if text.upper().startswith(prefix):
                text = text[len(prefix):].strip()
        
        return text
    
    def clean_for_hash(self, text: str) -> str:
        """
        Clean text for hash comparison.
        
        Very aggressive normalization for deduplication.
        """
        # Basic cleaning
        result = self.clean(text)
        text = result.cleaned
        
        # Lowercase
        text = text.lower()
        
        # Remove all non-alphanumeric except spaces
        text = re.sub(r"[^\w\s]", "", text)
        
        # Normalize whitespace again
        text = self._normalize_whitespace(text)
        
        return text
    
    def extract_text_from_html(self, html_content: str) -> str:
        """
        Extract readable text from HTML content.
        
        More sophisticated HTML handling.
        """
        # Decode entities
        text = self._decode_html_entities(html_content)
        
        # Replace block elements with newlines
        block_elements = r"</?(p|div|br|li|h[1-6]|tr|article|section)[^>]*>"
        text = re.sub(block_elements, "\n", text, flags=re.IGNORECASE)
        
        # Remove remaining tags
        text = self._remove_html_tags(text)
        
        # Normalize whitespace
        text = self._normalize_whitespace(text)
        
        return text
    
    # =========================================================
    # VALIDATION
    # =========================================================
    
    def is_valid_content(self, text: str) -> Tuple[bool, Optional[str]]:
        """
        Check if content is valid for processing.
        
        Returns:
            Tuple of (is_valid, error_message)
        """
        if not text:
            return False, "Empty content"
        
        if len(text) < self._config.min_length:
            return False, f"Content too short ({len(text)} < {self._config.min_length})"
        
        if len(text) > self._config.max_length:
            return False, f"Content too long ({len(text)} > {self._config.max_length})"
        
        # Check for mostly non-text content
        if self._is_mostly_special_chars(text):
            return False, "Content is mostly special characters"
        
        return True, None
    
    def _is_mostly_special_chars(self, text: str, threshold: float = 0.7) -> bool:
        """Check if text is mostly special characters."""
        if not text:
            return True
        
        alphanumeric = sum(1 for c in text if c.isalnum() or c.isspace())
        ratio = alphanumeric / len(text)
        
        return ratio < (1 - threshold)
