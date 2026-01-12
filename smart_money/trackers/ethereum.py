"""
Ethereum On-Chain Tracker - Etherscan API integration.

Uses Etherscan free tier API for transaction tracking.
Free tier: 5 requests/second, 100k requests/day.
We use conservative limits to avoid hitting rate limits.
"""

import asyncio
import logging
from datetime import datetime
from typing import Any, Optional

import aiohttp

from ..config import ChainConfig, SmartMoneyConfig, get_config
from ..exceptions import APIError, RateLimitError
from ..models import ActivityType, Chain, WalletActivity
from .base import BaseOnChainTracker


logger = logging.getLogger(__name__)


# Common token addresses for labeling
TOKEN_LABELS: dict[str, str] = {
    "0xdac17f958d2ee523a2206206994597c13d831ec7": "USDT",
    "0xa0b86991c6218b36c1d19d4a2e9eb0ce3606eb48": "USDC",
    "0x6b175474e89094c44da98b954eedeac495271d0f": "DAI",
    "0x2260fac5e5542a773aa44fbcfedf7c193bc2c599": "WBTC",
    "0xc02aaa39b223fe8d0a0e5c4f27ead9083c756cc2": "WETH",
    "0x7d1afa7b718fb893db30a3abc0cfc608aacfebb0": "MATIC",
    "0x514910771af9ca656af840dff83e8264ecf986ca": "LINK",
    "0x1f9840a85d5af5bf1d1762f925bdaddc4201f984": "UNI",
    "0x7fc66500c84a76ad7e9c93437bfc5ac33e2ddae9": "AAVE",
}


class EthereumTracker(BaseOnChainTracker):
    """
    Ethereum on-chain tracker using Etherscan API V2.
    
    As of August 2025, Etherscan V1 is deprecated.
    V2 uses unified endpoint with chainid parameter.
    
    Free tier constraints:
    - 5 requests/second max (we use 0.2 = 1 per 5 seconds)
    - 100,000 requests/day
    - API key required for V2
    
    Extensibility:
    - Can be replaced with Arkham API or Nansen without interface changes
    """
    
    # Etherscan V2 API endpoint
    V2_API_URL = "https://api.etherscan.io/v2/api"
    CHAIN_ID = 1  # Ethereum mainnet
    
    def __init__(
        self,
        config: Optional[SmartMoneyConfig] = None,
        api_key: Optional[str] = None,
    ) -> None:
        config = config or get_config()
        chain_config = config.get_chain_config(Chain.ETHEREUM)
        super().__init__(config, chain_config)
        
        self.api_key = api_key or (
            chain_config.explorer_api_key if chain_config else None
        )
        # Use V2 API
        self.base_url = self.V2_API_URL
        
        self._session: Optional[aiohttp.ClientSession] = None
    
    @property
    def chain(self) -> Chain:
        return Chain.ETHEREUM
    
    async def _get_session(self) -> aiohttp.ClientSession:
        """Get or create aiohttp session."""
        if self._session is None or self._session.closed:
            timeout = aiohttp.ClientTimeout(total=15)
            self._session = aiohttp.ClientSession(timeout=timeout)
        return self._session
    
    async def _fetch_transactions(
        self,
        address: str,
        start_block: Optional[int] = None,
        end_block: Optional[int] = None,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        """
        Fetch normal transactions from Etherscan V2 API.
        
        API: https://api.etherscan.io/v2/api?chainid=1&module=account&action=txlist
        """
        session = await self._get_session()
        
        params = {
            "chainid": str(self.CHAIN_ID),
            "module": "account",
            "action": "txlist",
            "address": address,
            "startblock": start_block or 0,
            "endblock": end_block or 99999999,
            "page": 1,
            "offset": min(limit, 100),
            "sort": "desc",
        }
        
        if self.api_key:
            params["apikey"] = self.api_key
        
        try:
            async with session.get(self.base_url, params=params) as response:
                if response.status == 429:
                    raise RateLimitError(
                        "Etherscan rate limit exceeded",
                        chain=Chain.ETHEREUM,
                        retry_after_seconds=60,
                    )
                
                data = await response.json()
                
                if data.get("status") == "0":
                    message = data.get("message", "")
                    if "rate limit" in message.lower():
                        raise RateLimitError(
                            f"Etherscan rate limit: {message}",
                            chain=Chain.ETHEREUM,
                        )
                    # No transactions is not an error
                    if "no transactions" in message.lower():
                        return []
                    logger.warning(f"Etherscan API error: {message}")
                    return []
                
                return data.get("result", [])
                
        except aiohttp.ClientError as e:
            raise APIError(
                f"Network error: {e}",
                chain=Chain.ETHEREUM,
                api_name="etherscan",
            )
    
    async def _fetch_token_transfers(
        self,
        address: str,
        start_block: Optional[int] = None,
        end_block: Optional[int] = None,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        """
        Fetch ERC-20 token transfers from Etherscan V2 API.
        
        API: https://api.etherscan.io/v2/api?chainid=1&module=account&action=tokentx
        """
        session = await self._get_session()
        
        params = {
            "chainid": str(self.CHAIN_ID),
            "module": "account",
            "action": "tokentx",
            "address": address,
            "startblock": start_block or 0,
            "endblock": end_block or 99999999,
            "page": 1,
            "offset": min(limit, 100),
            "sort": "desc",
        }
        
        if self.api_key:
            params["apikey"] = self.api_key
        
        try:
            # Rate limit delay
            await asyncio.sleep(0.5)  # Be conservative
            
            async with session.get(self.base_url, params=params) as response:
                if response.status == 429:
                    raise RateLimitError(
                        "Etherscan rate limit exceeded",
                        chain=Chain.ETHEREUM,
                        retry_after_seconds=60,
                    )
                
                data = await response.json()
                
                if data.get("status") == "0":
                    message = data.get("message", "")
                    if "no transactions" in message.lower():
                        return []
                    return []
                
                return data.get("result", [])
                
        except aiohttp.ClientError as e:
            raise APIError(
                f"Network error: {e}",
                chain=Chain.ETHEREUM,
                api_name="etherscan",
            )
    
    def _parse_transaction(
        self,
        raw: dict[str, Any],
        wallet_address: str,
    ) -> Optional[WalletActivity]:
        """Parse Etherscan transaction into WalletActivity."""
        try:
            tx_hash = raw.get("hash", "")
            from_addr = raw.get("from", "").lower()
            to_addr = raw.get("to", "").lower()
            wallet_lower = wallet_address.lower()
            
            # Determine direction
            if from_addr == wallet_lower:
                direction = "out"
                counterparty = to_addr
            elif to_addr == wallet_lower:
                direction = "in"
                counterparty = from_addr
            else:
                direction = "unknown"
                counterparty = None
            
            # Parse timestamp
            timestamp_str = raw.get("timeStamp", "0")
            timestamp = datetime.fromtimestamp(int(timestamp_str))
            
            # Parse value
            if "tokenDecimal" in raw:
                # Token transfer
                decimals = int(raw.get("tokenDecimal", 18))
                value = float(raw.get("value", 0)) / (10 ** decimals)
                token_symbol = raw.get("tokenSymbol", "UNKNOWN")
                token_address = raw.get("contractAddress", "").lower()
                activity_type = ActivityType.TRANSFER
            else:
                # Native ETH transfer
                value = float(raw.get("value", 0)) / 1e18
                token_symbol = "ETH"
                token_address = None
                
                # Detect activity type
                if raw.get("input", "0x") != "0x":
                    activity_type = ActivityType.CONTRACT_INTERACTION
                else:
                    activity_type = ActivityType.TRANSFER
            
            # Estimate USD value (simplified - would use price feed in production)
            value_usd = self._estimate_usd_value(token_symbol, value)
            
            return WalletActivity(
                tx_hash=tx_hash,
                wallet_address=wallet_address,
                chain=Chain.ETHEREUM,
                timestamp=timestamp,
                activity_type=activity_type,
                direction=direction,
                token_symbol=token_symbol,
                token_address=token_address,
                amount=value,
                value_usd=value_usd,
                counterparty_address=counterparty,
                block_number=int(raw.get("blockNumber", 0)),
                gas_used=int(raw.get("gasUsed", 0)),
                gas_price_gwei=float(raw.get("gasPrice", 0)) / 1e9,
            )
            
        except Exception as e:
            logger.warning(f"Failed to parse transaction: {e}")
            return None
    
    def _estimate_usd_value(self, token_symbol: str, amount: float) -> float:
        """
        Estimate USD value of token amount.
        
        Simplified - in production, use real-time price feed.
        """
        # Approximate prices (would be from price feed)
        prices = {
            "ETH": 2500.0,
            "WETH": 2500.0,
            "USDT": 1.0,
            "USDC": 1.0,
            "DAI": 1.0,
            "WBTC": 45000.0,
            "LINK": 15.0,
            "UNI": 8.0,
            "AAVE": 100.0,
            "MATIC": 0.8,
        }
        
        price = prices.get(token_symbol.upper(), 0.0)
        return amount * price
    
    async def get_eth_balance(self, address: str) -> Optional[float]:
        """Get ETH balance for an address."""
        session = await self._get_session()
        
        params = {
            "module": "account",
            "action": "balance",
            "address": address,
            "tag": "latest",
        }
        
        if self.api_key:
            params["apikey"] = self.api_key
        
        try:
            async with session.get(self.base_url, params=params) as response:
                data = await response.json()
                
                if data.get("status") == "1":
                    balance_wei = int(data.get("result", 0))
                    return balance_wei / 1e18
                
                return None
                
        except Exception as e:
            logger.warning(f"Failed to get ETH balance: {e}")
            return None
    
    async def close(self) -> None:
        """Close the aiohttp session."""
        if self._session and not self._session.closed:
            await self._session.close()
