"""
Test script for CryptoNews API integration.

Validates:
1. API connectivity
2. News data fetching
3. Date parsing
4. Sentiment extraction
"""

import os
import requests
from datetime import datetime
from email.utils import parsedate_to_datetime
from dotenv import load_dotenv

# Load environment variables
load_dotenv()


def print_header(text: str) -> None:
    print(f"\n{'='*60}")
    print(f"  {text}")
    print("="*60)


def print_success(text: str) -> None:
    print(f"  [OK] {text}")


def print_warning(text: str) -> None:
    print(f"  [WARN] {text}")


def print_error(text: str) -> None:
    print(f"  [FAIL] {text}")


def test_cryptonews_api() -> bool:
    """Test CryptoNews API connectivity and data quality."""
    print_header("Test 1: CryptoNews API Connectivity")
    
    api_key = os.getenv("CRYPTO_NEWS_API_KEY")
    if not api_key:
        print_error("No API key configured (CRYPTO_NEWS_API_KEY)")
        print("  Set in .env: CRYPTO_NEWS_API_KEY=your_key")
        return False
    
    print(f"  API Key: {api_key[:10]}...")
    
    url = "https://cryptonews-api.com/api/v1/category"
    params = {
        "section": "alltickers",
        "tickers": "BTC,ETH",
        "items": 3,  # Trial plan limit
        "token": api_key,
    }
    
    try:
        resp = requests.get(url, params=params, timeout=15)
        
        if resp.status_code == 200:
            data = resp.json()
            items = data.get("data", [])
            print(f"  Status: {resp.status_code}")
            print(f"  Items fetched: {len(items)}")
            print_success("API connectivity OK")
            return True
        elif resp.status_code == 403:
            error = resp.json().get("message", "Access denied")
            print_error(f"Status: 403 - {error}")
            return False
        else:
            print_error(f"Status: {resp.status_code}")
            return False
            
    except Exception as e:
        print_error(f"Connection error: {e}")
        return False


def test_news_data_quality() -> bool:
    """Test news data structure and quality."""
    print_header("Test 2: News Data Quality")
    
    api_key = os.getenv("CRYPTO_NEWS_API_KEY")
    if not api_key:
        print_error("No API key")
        return False
    
    url = "https://cryptonews-api.com/api/v1/category"
    params = {
        "section": "alltickers",
        "tickers": "BTC,ETH,SOL",
        "items": 3,
        "token": api_key,
    }
    
    try:
        resp = requests.get(url, params=params, timeout=15)
        
        if resp.status_code != 200:
            print_error(f"API error: {resp.status_code}")
            return False
        
        data = resp.json()
        items = data.get("data", [])
        
        if not items:
            print_warning("No items returned")
            return False
        
        print(f"  Checking {len(items)} news items...\n")
        
        all_valid = True
        for i, item in enumerate(items):
            title = item.get("title", "")[:45]
            sentiment = item.get("sentiment", "N/A")
            source = item.get("source_name", "Unknown")
            tickers = item.get("tickers", [])
            date_str = item.get("date", "")
            
            # Parse date
            try:
                parsed_date = parsedate_to_datetime(date_str)
                date_ok = "[OK]"
                time_str = parsed_date.strftime("%Y-%m-%d %H:%M")
            except:
                date_ok = "[FAIL]"
                time_str = "Parse error"
                all_valid = False
            
            print(f"  {i+1}. {date_ok} [{sentiment}]")
            print(f"     Time: {time_str}")
            print(f"     Source: {source}")
            print(f"     Tickers: {tickers}")
            print(f"     {title}...")
            print()
        
        if all_valid:
            print_success("All news items valid")
        else:
            print_warning("Some items have parsing issues")
        
        return all_valid
        
    except Exception as e:
        print_error(f"Error: {e}")
        return False


def test_sentiment_distribution() -> bool:
    """Test sentiment values returned by API."""
    print_header("Test 3: Sentiment Analysis")
    
    api_key = os.getenv("CRYPTO_NEWS_API_KEY")
    if not api_key:
        print_error("No API key")
        return False
    
    url = "https://cryptonews-api.com/api/v1/category"
    params = {
        "section": "alltickers",
        "tickers": "BTC",
        "items": 3,
        "token": api_key,
    }
    
    try:
        resp = requests.get(url, params=params, timeout=15)
        
        if resp.status_code != 200:
            print_error(f"API error: {resp.status_code}")
            return False
        
        data = resp.json()
        items = data.get("data", [])
        
        sentiments = {}
        for item in items:
            sentiment = item.get("sentiment", "Unknown")
            sentiments[sentiment] = sentiments.get(sentiment, 0) + 1
        
        print("  Sentiment distribution:")
        for sentiment, count in sentiments.items():
            print(f"    {sentiment}: {count}")
        
        print_success("Sentiment data available")
        return True
        
    except Exception as e:
        print_error(f"Error: {e}")
        return False


def main():
    print_header("CRYPTONEWS API - TEST SUITE")
    print("  Trial Plan: max 3 items per request")
    print("  Upgrade at: https://cryptonews-api.com")
    
    results = []
    
    # Run tests
    results.append(("API Connectivity", test_cryptonews_api()))
    results.append(("Data Quality", test_news_data_quality()))
    results.append(("Sentiment", test_sentiment_distribution()))
    
    # Summary
    print_header("TEST SUMMARY")
    
    passed = 0
    for name, success in results:
        status = "[OK]" if success else "[FAIL]"
        print(f"  {status} {name}")
        if success:
            passed += 1
    
    print(f"\n  Total: {passed}/{len(results)} tests passed")
    
    if passed == len(results):
        print("\n  [OK] CryptoNews API is ready for bot input!")
        print("  Features available:")
        print("    - Real-time crypto news")
        print("    - Sentiment analysis (Positive/Negative/Neutral)")
        print("    - Ticker filtering (BTC, ETH, SOL, etc.)")
        return 0
    else:
        print("\n  Some tests failed. Check API key configuration.")
        return 1


if __name__ == "__main__":
    exit(main())
