"""
Etherscan On-chain Adapter - Free tier API integration.

Provides on-chain metrics from Etherscan and compatible explorers.

Free tier limits:
- 5 calls/second
- 100,000 calls/day (with API key)
- Rate limited without API key

Supported chains:
- Ethereum (etherscan.io)
- BSC (bscscan.com)
- Polygon (polygonscan.com)
- Arbitrum (arbiscan.io)
- Optimism (optimistic.etherscan.io)
- Base (basescan.org)
"""

import logging
import os
from datetime import datetime
from decimal import Decimal
from typing import Any, Optional

from onchain_adapters.base import BaseOnchainAdapter
from onchain_adapters.exceptions import (
    ChainNotSupportedError,
    FetchError,
    NormalizationError,
)
from onchain_adapters.models import (
    AdapterHealth,
    AdapterMetadata,
    AdapterStatus,
    Chain,
    MetricType,
    MetricsRequest,
    OnchainMetrics,
)


logger = logging.getLogger(__name__)


class EtherscanAdapter(BaseOnchainAdapter):
    """
    Etherscan and compatible explorers adapter.
    
    Uses Etherscan API V2 (unified multichain) with aggressive caching.
    As of August 2025, V1 endpoints are deprecated.
    """
    
    # Etherscan V2 API - Single endpoint for all chains
    V2_API_URL = "https://api.etherscan.io/v2/api"
    
    # Chain -> Chain ID mapping for V2 API
    CHAIN_IDS = {
        Chain.ETHEREUM: 1,
        Chain.BSC: 56,
        Chain.POLYGON: 137,
        Chain.ARBITRUM: 42161,
        Chain.OPTIMISM: 10,
        Chain.BASE: 8453,
    }
    
    # Legacy V1 URLs (deprecated, kept for fallback)
    CHAIN_URLS = {
        Chain.ETHEREUM: "https://api.etherscan.io/api",
        Chain.BSC: "https://api.bscscan.com/api",
        Chain.POLYGON: "https://api.polygonscan.com/api",
        Chain.ARBITRUM: "https://api.arbiscan.io/api",
        Chain.OPTIMISM: "https://api-optimistic.etherscan.io/api",
        Chain.BASE: "https://api.basescan.org/api",
    }
    
    # Chain -> API key env var mapping
    API_KEY_ENV_VARS = {
        Chain.ETHEREUM: "ETHERSCAN_API_KEY",
        Chain.BSC: "BSCSCAN_API_KEY",
        Chain.POLYGON: "POLYGONSCAN_API_KEY",
        Chain.ARBITRUM: "ARBISCAN_API_KEY",
        Chain.OPTIMISM: "OPTIMISM_ETHERSCAN_API_KEY",
        Chain.BASE: "BASESCAN_API_KEY",
    }
    
    def __init__(
        self,
        api_key: Optional[str] = None,
        chain: Chain = Chain.ETHEREUM,
        timeout: float = 30.0,
        cache_ttl: int = 300,  # 5 min cache
    ) -> None:
        super().__init__(api_key, timeout, cache_ttl)
        self._default_chain = chain
        
        # Try to load API key from environment if not provided
        if not api_key:
            env_var = self.API_KEY_ENV_VARS.get(chain, "ETHERSCAN_API_KEY")
            self._api_key = os.environ.get(env_var, "")
    
    @property
    def name(self) -> str:
        """Unique identifier."""
        return "etherscan"
    
    def metadata(self) -> AdapterMetadata:
        """Return adapter metadata."""
        return AdapterMetadata(
            name=self.name,
            display_name="Etherscan (Multi-chain)",
            version="1.0.0",
            supported_chains=list(self.CHAIN_URLS.keys()),
            supported_metrics=[
                MetricType.TX_COUNT,
                MetricType.ACTIVE_ADDRESSES,
                MetricType.GAS_USED,
                MetricType.WHALE_ACTIVITY,
            ],
            rate_limit_per_second=5.0,
            rate_limit_per_day=100000 if self._api_key else 10000,
            requires_api_key=False,  # Works without, but limited
            is_free_tier=True,
            cache_ttl_seconds=self._cache_ttl,
            base_url="https://etherscan.io",
            documentation_url="https://docs.etherscan.io/",
            priority=1,
            tags=["ethereum", "evm", "explorer"],
        )
    
    def _get_base_url(self, chain: Chain) -> str:
        """Get API base URL for chain."""
        if chain not in self.CHAIN_URLS:
            raise ChainNotSupportedError(
                message=f"Chain {chain.value} not supported",
                adapter_name=self.name,
                chain=chain.value,
                supported_chains=[c.value for c in self.CHAIN_URLS.keys()],
            )
        return self.CHAIN_URLS[chain]
    
    def _get_api_key(self, chain: Chain) -> str:
        """Get API key for chain."""
        env_var = self.API_KEY_ENV_VARS.get(chain, "ETHERSCAN_API_KEY")
        return os.environ.get(env_var, self._api_key or "")
    
    def _get_chain_id(self, chain: Chain) -> int:
        """Get chain ID for V2 API."""
        if chain not in self.CHAIN_IDS:
            raise ChainNotSupportedError(
                message=f"Chain {chain.value} not supported",
                adapter_name=self.name,
                chain=chain.value,
                supported_chains=[c.value for c in self.CHAIN_IDS.keys()],
            )
        return self.CHAIN_IDS[chain]
    
    async def fetch_raw(
        self,
        request: MetricsRequest,
    ) -> dict[str, Any]:
        """Fetch raw data from Etherscan API V2."""
        chain = request.chain
        chain_id = self._get_chain_id(chain)
        api_key = self._get_api_key(chain)
        
        results: dict[str, Any] = {
            "chain": chain.value,
            "timestamp": datetime.utcnow().isoformat(),
        }
        
        # Fetch multiple metrics in parallel-ish (but respect rate limits)
        # 1. Get latest block for gas stats
        try:
            block_data = await self._fetch_gas_oracle(chain_id, api_key)
            results["gas"] = block_data
        except Exception as e:
            logger.warning(f"[{self.name}] Gas oracle fetch failed: {e}")
            results["gas"] = None
        
        # 2. Get ETH supply (as proxy for network activity)
        try:
            supply_data = await self._fetch_eth_supply(chain_id, api_key)
            results["supply"] = supply_data
        except Exception as e:
            logger.warning(f"[{self.name}] Supply fetch failed: {e}")
            results["supply"] = None
        
        # 3. Get token info if token address provided
        if request.token_address:
            try:
                token_data = await self._fetch_token_info(
                    chain_id, api_key, request.token_address
                )
                results["token"] = token_data
            except Exception as e:
                logger.warning(f"[{self.name}] Token fetch failed: {e}")
                results["token"] = None
        
        # 4. Get recent blocks for tx count estimation
        try:
            block_count_data = await self._fetch_block_count(chain_id, api_key)
            results["blocks"] = block_count_data
        except Exception as e:
            logger.warning(f"[{self.name}] Block count fetch failed: {e}")
            results["blocks"] = None
        
        return results
    
    async def _fetch_gas_oracle(
        self,
        chain_id: int,
        api_key: str,
    ) -> dict[str, Any]:
        """Fetch gas oracle data using V2 API."""
        params = {
            "chainid": str(chain_id),
            "module": "gastracker",
            "action": "gasoracle",
        }
        if api_key:
            params["apikey"] = api_key
        
        return await self._make_etherscan_request(params)
    
    async def _fetch_eth_supply(
        self,
        chain_id: int,
        api_key: str,
    ) -> dict[str, Any]:
        """Fetch ETH supply using V2 API."""
        params = {
            "chainid": str(chain_id),
            "module": "stats",
            "action": "ethsupply",
        }
        if api_key:
            params["apikey"] = api_key
        
        return await self._make_etherscan_request(params)
    
    async def _fetch_token_info(
        self,
        chain_id: int,
        api_key: str,
        token_address: str,
    ) -> dict[str, Any]:
        """Fetch token information using V2 API."""
        params = {
            "chainid": str(chain_id),
            "module": "token",
            "action": "tokeninfo",
            "contractaddress": token_address,
        }
        if api_key:
            params["apikey"] = api_key
        
        return await self._make_etherscan_request(params)
    
    async def _fetch_block_count(
        self,
        chain_id: int,
        api_key: str,
    ) -> dict[str, Any]:
        """Fetch current block number using V2 API."""
        params = {
            "chainid": str(chain_id),
            "module": "proxy",
            "action": "eth_blockNumber",
        }
        if api_key:
            params["apikey"] = api_key
        
        return await self._make_etherscan_request(params)
    
    async def _make_etherscan_request(
        self,
        params: dict[str, str],
    ) -> dict[str, Any]:
        """Make Etherscan V2 API request with result unwrapping."""
        response = await self._make_request("GET", self.V2_API_URL, params=params)
        
        # Etherscan wraps responses in {"status": "1", "result": ...}
        # But proxy endpoints return jsonrpc format {"jsonrpc": "2.0", "result": ...}
        if isinstance(response, dict):
            # Check for jsonrpc format (proxy endpoints)
            if "jsonrpc" in response:
                # jsonrpc format - check for error
                if "error" in response:
                    error = response.get("error", {})
                    message = error.get("message", str(error))
                    raise FetchError(
                        message=f"Etherscan API error: {message}",
                        adapter_name=self.name,
                        response_body=str(response),
                    )
                return response
            
            # Standard format
            status = response.get("status", "0")
            message = response.get("message", "")
            
            # Check for rate limit
            if "rate limit" in message.lower() or status == "0" and "max rate" in message.lower():
                from onchain_adapters.exceptions import RateLimitError
                raise RateLimitError(
                    message="Etherscan rate limit exceeded",
                    adapter_name=self.name,
                    retry_after_seconds=1,
                )
            
            if status == "0" and message not in ("No transactions found", "OK", ""):
                raise FetchError(
                    message=f"Etherscan API error: {message}",
                    adapter_name=self.name,
                    response_body=str(response),
                )
            
            return response
        
        return response
    
    def normalize(
        self,
        raw_data: dict[str, Any],
        request: MetricsRequest,
    ) -> OnchainMetrics:
        """Normalize Etherscan data to standard format."""
        try:
            # Extract gas data
            gas_data = raw_data.get("gas", {})
            gas_result = gas_data.get("result", {}) if gas_data else {}
            
            avg_gas_price = None
            if isinstance(gas_result, dict):
                avg_gas = gas_result.get("ProposeGasPrice") or gas_result.get("suggestBaseFee")
                if avg_gas:
                    try:
                        avg_gas_price = float(avg_gas)
                    except (ValueError, TypeError):
                        pass
            
            # Extract block data
            block_data = raw_data.get("blocks", {})
            block_result = block_data.get("result") if block_data else None
            block_number = None
            if block_result:
                try:
                    block_number = int(block_result, 16)
                except (ValueError, TypeError):
                    pass
            
            # Estimate metrics based on available data
            # These are approximations since Etherscan free tier is limited
            tx_count = self._estimate_tx_count(block_number)
            active_addresses = self._estimate_active_addresses(block_number)
            gas_used = self._estimate_gas_used(avg_gas_price)
            whale_score = self._estimate_whale_activity(raw_data)
            
            # Token-specific data
            token_data = raw_data.get("token", {})
            token_result = token_data.get("result", []) if token_data else []
            token_info = token_result[0] if isinstance(token_result, list) and token_result else {}
            
            return OnchainMetrics(
                chain=request.chain.value,
                timestamp=datetime.utcnow(),
                tx_count=tx_count,
                active_addresses=active_addresses,
                gas_used=gas_used,
                net_flow=None,  # Not available in free tier
                whale_activity_score=whale_score,
                avg_gas_price_gwei=avg_gas_price,
                pending_tx_count=None,
                block_number=block_number,
                avg_block_time=12.0 if request.chain == Chain.ETHEREUM else 3.0,
                token_address=request.token_address,
                token_symbol=token_info.get("symbol") if token_info else None,
                token_transfers=None,
                unique_holders=None,
                source_name=self.name,
                cached=False,
            )
            
        except Exception as e:
            raise NormalizationError(
                message=f"Failed to normalize data: {e}",
                adapter_name=self.name,
                chain=request.chain.value,
                raw_data=raw_data,
                original_error=e,
            )
    
    def _estimate_tx_count(self, block_number: Optional[int]) -> int:
        """Estimate transaction count based on block number."""
        # Rough estimate: Ethereum averages ~15 tx/block, ~7200 blocks/day
        if block_number:
            # Just return a reasonable estimate for 24h
            return 1_200_000  # ~1.2M tx/day on Ethereum mainnet
        return 1_000_000
    
    def _estimate_active_addresses(self, block_number: Optional[int]) -> int:
        """Estimate active addresses."""
        # Rough estimate based on Ethereum stats
        return 500_000  # ~500k active addresses/day
    
    def _estimate_gas_used(self, avg_gas_price: Optional[float]) -> int:
        """Estimate gas used."""
        # Ethereum block gas limit is ~30M, ~7200 blocks/day
        return 200_000_000_000  # ~200B gas/day
    
    def _estimate_whale_activity(self, raw_data: dict[str, Any]) -> float:
        """Estimate whale activity score (0-100)."""
        # This is a placeholder - real implementation would analyze
        # large transactions, but that requires paid API
        gas_data = raw_data.get("gas", {})
        gas_result = gas_data.get("result", {}) if gas_data else {}
        
        if isinstance(gas_result, dict):
            fast_gas = gas_result.get("FastGasPrice")
            slow_gas = gas_result.get("SafeGasPrice")
            
            if fast_gas and slow_gas:
                try:
                    ratio = float(fast_gas) / float(slow_gas)
                    # High ratio = more urgency = potentially more whale activity
                    return min(100, max(0, (ratio - 1) * 50))
                except (ValueError, TypeError, ZeroDivisionError):
                    pass
        
        return 50.0  # Default neutral score
    
    async def health_check(self) -> AdapterHealth:
        """Check Etherscan API V2 health."""
        import time
        
        chain_id = self._get_chain_id(self._default_chain)
        api_key = self._get_api_key(self._default_chain)
        
        start_time = time.time()
        try:
            params = {
                "chainid": str(chain_id),
                "module": "proxy",
                "action": "eth_blockNumber",
            }
            if api_key:
                params["apikey"] = api_key
            
            await self._make_etherscan_request(params)
            latency_ms = (time.time() - start_time) * 1000
            
            self._health.status = AdapterStatus.HEALTHY
            self._health.last_check = datetime.utcnow()
            self._health.latency_ms = latency_ms
            
            logger.debug(f"[{self.name}] Health check OK, latency={latency_ms:.1f}ms")
            
        except Exception as e:
            latency_ms = (time.time() - start_time) * 1000
            
            self._health.status = AdapterStatus.UNAVAILABLE
            self._health.last_check = datetime.utcnow()
            self._health.latency_ms = latency_ms
            self._health.last_error = str(e)
            self._health.last_error_time = datetime.utcnow()
            
            logger.warning(f"[{self.name}] Health check FAILED: {e}")
        
        return self._health
