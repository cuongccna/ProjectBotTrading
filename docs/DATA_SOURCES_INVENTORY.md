# 📊 DATA SOURCES INVENTORY
## Crypto Trading Bot - Input Data Sources

**Last Updated:** January 11, 2026  
**Status:** Production Ready (Free Tier)

---

## 📋 SUMMARY

| Category | Sources | Status |
|----------|---------|--------|
| Market Data | 2 | ✅ Active |
| News & Sentiment | 3 | ⚠️ Partial |
| On-Chain Data | 4 | ✅ Active |
| Smart Money Tracking | 2 | ✅ Active |
| **TOTAL** | **11** | **8 Active** |

---

## 1️⃣ MARKET DATA SOURCES

### 1.1 Binance Futures
| Property | Value |
|----------|-------|
| **Status** | ✅ **ACTIVE** |
| **Type** | Exchange API (WebSocket + REST) |
| **Class** | `BinanceMarketSource` |
| **Location** | `data_sources/providers/binance.py` |
| **Features** | Real-time prices, orderbook, trades, klines |
| **Rate Limit** | 1200 requests/min (weight-based) |
| **API Key** | Not required for public data |
| **Integration** | ✅ Integrated in `SourceRegistry` |

### 1.2 OKX Swap
| Property | Value |
|----------|-------|
| **Status** | ✅ **ACTIVE** |
| **Type** | Exchange API (WebSocket + REST) |
| **Class** | `OKXMarketSource` |
| **Location** | `data_sources/providers/okx.py` |
| **Features** | Real-time prices, orderbook, trades, klines |
| **Rate Limit** | 20 requests/2 sec |
| **API Key** | Not required for public data |
| **Integration** | ✅ Integrated in `SourceRegistry` |

---

## 2️⃣ NEWS & SENTIMENT SOURCES

### 2.1 CryptoNews API ⚠️
| Property | Value |
|----------|-------|
| **Status** | ✅ **ACTIVE** |
| **Type** | REST API |
| **Class** | `CryptoNewsApiCollector` |
| **Location** | `data_ingestion/collectors/crypto_news_api.py` |
| **Features** | News articles, sentiment analysis, ticker filtering |
| **Endpoint** | `https://cryptonews-api.com/api/v1/category` |
| **API Key** | `CRYPTO_NEWS_API_KEY` in `.env` |
| **Integration** | ✅ Integrated in `IngestionService` |

> ⚠️ **LIMITATION - TRIAL PLAN:**
> - **Maximum 3 items per request**
> - To increase limit, upgrade to Premium at: https://cryptonews-api.com/pricing
> - Current code: `batch_size = min(self._news_config.batch_size, 3)`
> - **TODO:** Remove limit after upgrading to Premium plan

### 2.2 CryptoPanic
| Property | Value |
|----------|-------|
| **Status** | ❌ **BLOCKED** |
| **Type** | REST API |
| **Class** | `CryptoPanicSource` |
| **Location** | `sentiment/providers/cryptopanic.py` |
| **Features** | Aggregated news, votes, sentiment |
| **Endpoint** | `https://cryptopanic.com/api/v1` |
| **API Key** | `CRYPTOPANIC_API_KEY` in `.env` |
| **Issue** | Cloudflare protection (403/404) |
| **Integration** | ✅ Registered in `SentimentRegistry` |

> ❌ **ISSUE:** API blocked by Cloudflare. Need to contact CryptoPanic support or use alternative approach.

### 2.3 Twitter Scraper
| Property | Value |
|----------|-------|
| **Status** | ⚠️ **EXPERIMENTAL** |
| **Type** | Web Scraping |
| **Class** | `TwitterScraperSource` |
| **Location** | `sentiment/providers/twitter.py` |
| **Features** | Crypto-related tweets, hashtag sentiment |
| **API Key** | Not required |
| **Integration** | ✅ Registered in `SentimentRegistry` |

---

## 3️⃣ ON-CHAIN DATA SOURCES

### 3.1 Etherscan (V2 API)
| Property | Value |
|----------|-------|
| **Status** | ✅ **ACTIVE** |
| **Type** | Block Explorer API |
| **Class** | `OnChainCollector` (via Etherscan adapter) |
| **Location** | `data_ingestion/collectors/onchain_free_sources.py` |
| **Features** | Ethereum transactions, token transfers, contract data |
| **Endpoint** | `https://api.etherscan.io/v2/api?chainid=1` |
| **API Key** | `ETHERSCAN_API_KEY` in `.env` |
| **Rate Limit** | 5 calls/sec, 100,000 calls/day |
| **Integration** | ✅ Integrated in `IngestionService` |

> ℹ️ **NOTE:** Upgraded to V2 API (V1 deprecated August 2025)

### 3.2 BSCScan (V2 API)
| Property | Value |
|----------|-------|
| **Status** | ✅ **CONFIGURED** |
| **Type** | Block Explorer API |
| **Chain** | BNB Smart Chain |
| **API Key** | `BSC_ETHERSCAN_API_KEY` in `.env` |
| **Endpoint** | `https://api.etherscan.io/v2/api?chainid=56` |
| **Integration** | ✅ Integrated (same adapter as Etherscan) |

### 3.3 PolygonScan (V2 API)
| Property | Value |
|----------|-------|
| **Status** | ✅ **CONFIGURED** |
| **Type** | Block Explorer API |
| **Chain** | Polygon |
| **API Key** | `POLYGON_ETHERSCAN_API_KEY` in `.env` |
| **Endpoint** | `https://api.etherscan.io/v2/api?chainid=137` |
| **Integration** | ✅ Integrated (same adapter as Etherscan) |

### 3.4 CoinGecko
| Property | Value |
|----------|-------|
| **Status** | ✅ **ACTIVE** |
| **Type** | REST API |
| **Class** | `CoinGeckoCollector` |
| **Location** | `data_ingestion/collectors/coingecko.py` |
| **Features** | Market data, coin info, historical prices |
| **Endpoint** | `https://api.coingecko.com/api/v3` |
| **API Key** | Optional (free tier) |
| **Rate Limit** | 10-50 calls/min (free tier) |
| **Integration** | ✅ Integrated in `IngestionService` |

---

## 4️⃣ SMART MONEY / WHALE TRACKING

### 4.1 Ethereum Whale Tracker
| Property | Value |
|----------|-------|
| **Status** | ✅ **ACTIVE** |
| **Type** | On-chain Analysis |
| **Class** | `EthereumTracker` |
| **Location** | `smart_money/trackers/ethereum.py` |
| **Features** | Whale wallet tracking, large transactions |
| **Data Source** | Etherscan API (V2) |
| **Integration** | ✅ Integrated in `SmartMoneyManager` |

### 4.2 Solana Whale Tracker
| Property | Value |
|----------|-------|
| **Status** | ✅ **ACTIVE** |
| **Type** | On-chain Analysis |
| **Class** | `SolanaTracker` |
| **Location** | `smart_money/trackers/solana.py` |
| **Features** | Whale wallet tracking, DEX transactions |
| **Data Source** | Public Solana RPC |
| **Integration** | ✅ Integrated in `SmartMoneyManager` |

---

## 5️⃣ EXECUTION ADAPTERS (Output)

These are for trade execution, not data input:

| Adapter | Status | Location |
|---------|--------|----------|
| Binance | ✅ Active | `execution_engine/adapters/binance.py` |
| OKX | ✅ Active | `execution_engine/adapters/okx.py` |
| Bybit | ✅ Active | `execution_engine/adapters/bybit.py` |
| Mock | ✅ Active | `execution_engine/adapters/mock.py` |

---

## 📁 INTEGRATION POINTS

### Data Ingestion Service
**File:** `data_ingestion/ingestion_service.py`

```python
COLLECTOR_REGISTRY = {
    "crypto_news_api": CryptoNewsApiCollector,  # ✅
    "coingecko": CoinGeckoCollector,             # ✅
    "onchain": OnChainCollector,                 # ✅
}
```

### Sentiment Registry
**File:** `sentiment/registry.py`

```python
registry.register(CryptoPanicSource())   # ❌ Blocked
registry.register(TwitterScraperSource()) # ⚠️ Experimental
```

### Smart Money Manager
**File:** `smart_money/manager.py`

```python
trackers = {
    "ethereum": EthereumTracker(),  # ✅
    "solana": SolanaTracker(),      # ✅
}
```

### Market Data Registry
**File:** `data_sources/registry.py`

```python
sources = {
    "binance": BinanceMarketSource(),  # ✅
    "okx": OKXMarketSource(),          # ✅
}
```

---

## 🔑 API KEYS REQUIRED

| Source | Environment Variable | Status |
|--------|---------------------|--------|
| CryptoNews API | `CRYPTO_NEWS_API_KEY` | ✅ Configured |
| CryptoPanic | `CRYPTOPANIC_API_KEY` | ⚠️ Blocked |
| Etherscan | `ETHERSCAN_API_KEY` | ✅ Configured |
| BSCScan | `BSC_ETHERSCAN_API_KEY` | ✅ Configured |
| PolygonScan | `POLYGON_ETHERSCAN_API_KEY` | ✅ Configured |
| CoinGecko | `COINGECKO_API_KEY` | Optional |
| Telegram | `TELEGRAM_BOT_TOKEN` | ✅ Configured |

---

## ⚠️ KNOWN LIMITATIONS

### 1. CryptoNews API - Trial Plan
```python
# File: data_ingestion/collectors/crypto_news_api.py
# Line: ~75
batch_size = min(self._news_config.batch_size, 3)  # Trial Plan limit
```
**Action:** Upgrade to Premium plan at https://cryptonews-api.com/pricing

### 2. CryptoPanic - Cloudflare Block
**Issue:** API returns 403/404 due to Cloudflare protection
**Action:** Contact support or use CryptoNews API as alternative

### 3. Flipside - Connectivity Issues
**Issue:** Network connectivity problems
**Action:** May require VPN or alternative provider

---

## 📊 DATA FLOW DIAGRAM

```
┌─────────────────────────────────────────────────────────────┐
│                    BOT TRADING SYSTEM                        │
├─────────────────────────────────────────────────────────────┤
│                                                              │
│  ┌─────────────────┐  ┌─────────────────┐  ┌──────────────┐ │
│  │  MARKET DATA    │  │   SENTIMENT     │  │  ON-CHAIN    │ │
│  │  (Real-time)    │  │   (News/Social) │  │  (Whale)     │ │
│  ├─────────────────┤  ├─────────────────┤  ├──────────────┤ │
│  │ ✅ Binance      │  │ ✅ CryptoNews*  │  │ ✅ Etherscan │ │
│  │ ✅ OKX          │  │ ❌ CryptoPanic  │  │ ✅ CoinGecko │ │
│  │                 │  │ ⚠️ Twitter      │  │ ✅ BSCScan   │ │
│  └────────┬────────┘  └────────┬────────┘  └──────┬───────┘ │
│           │                    │                   │         │
│           └──────────┬─────────┴───────────────────┘         │
│                      │                                       │
│                      ▼                                       │
│           ┌─────────────────────┐                            │
│           │  ANALYSIS ENGINE    │                            │
│           │  - Signal Generator │                            │
│           │  - Risk Manager     │                            │
│           └──────────┬──────────┘                            │
│                      │                                       │
│                      ▼                                       │
│           ┌─────────────────────┐                            │
│           │ EXECUTION ENGINE    │                            │
│           │ Binance/OKX/Bybit   │                            │
│           └─────────────────────┘                            │
│                                                              │
│  * CryptoNews API: Limited to 3 items/request (Trial Plan)  │
└─────────────────────────────────────────────────────────────┘
```

---

## ✅ TODO - NEXT STEPS

1. [ ] **Upgrade CryptoNews API** to Premium plan (remove 3-item limit)
2. [ ] **Fix CryptoPanic** - contact support about Cloudflare block
3. [ ] **Add Arkham Intelligence** API for smart money labels
4. [ ] **Add Nansen** API for wallet attribution
5. [ ] **Add Dune Analytics** for custom on-chain queries
6. [ ] **Test Flipside** connectivity with VPN

---

*Document generated for project documentation purposes.*
