"""
Solana On-Chain Tracker - Solana RPC integration.

Uses public Solana RPC for transaction tracking.
Rate limits vary by RPC provider - we use conservative limits.
"""

import asyncio
import base64
import logging
from datetime import datetime
from typing import Any, Optional

import aiohttp

from ..config import ChainConfig, SmartMoneyConfig, get_config
from ..exceptions import APIError, RateLimitError, RPCError
from ..models import ActivityType, Chain, WalletActivity
from .base import BaseOnChainTracker


logger = logging.getLogger(__name__)


# Known SPL token mints
TOKEN_MINTS: dict[str, str] = {
    "So11111111111111111111111111111111111111112": "SOL",  # Wrapped SOL
    "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v": "USDC",
    "Es9vMFrzaCERmJfrF4H2FYD4KCoNkY11McCe8BenwNYB": "USDT",
    "7vfCXTUXx5WJV5JADk17DUJ4ksgau7utNKj4b963voxs": "WETH",
    "9n4nbM75f5Ui33ZbPYXn59EwSgE8CGsHtAeTH5YFeJ9E": "WBTC",
    "mSoLzYCxHdYgdzU16g5QSh3i5K3z3KZK7ytfqcJm7So": "mSOL",
    "7dHbWXmci3dT8UFYWYZweBLXgycu7Y3iL6trKn1Y7ARj": "stSOL",
    "DezXAZ8z7PnrnRJjz3wXBoRgixCa6xjnB7YaB1pPB263": "BONK",
    "JUPyiwrYJFskUPiHa7hkeR8VUtAeFoSYbKedZNsDvCN": "JUP",
}


class SolanaTracker(BaseOnChainTracker):
    """
    Solana on-chain tracker using public RPC.
    
    RPC endpoints:
    - Mainnet: https://api.mainnet-beta.solana.com
    - Rate limits vary, we use conservative 0.5 req/s
    
    Extensibility:
    - Can be replaced with Helius, QuickNode, or premium RPC
    """
    
    def __init__(
        self,
        config: Optional[SmartMoneyConfig] = None,
        rpc_url: Optional[str] = None,
    ) -> None:
        config = config or get_config()
        chain_config = config.get_chain_config(Chain.SOLANA)
        super().__init__(config, chain_config)
        
        self.rpc_url = rpc_url or (
            chain_config.rpc_url if chain_config 
            else "https://api.mainnet-beta.solana.com"
        )
        
        self._session: Optional[aiohttp.ClientSession] = None
        self._request_id = 0
    
    @property
    def chain(self) -> Chain:
        return Chain.SOLANA
    
    async def _get_session(self) -> aiohttp.ClientSession:
        """Get or create aiohttp session."""
        if self._session is None or self._session.closed:
            timeout = aiohttp.ClientTimeout(total=20)
            headers = {"Content-Type": "application/json"}
            self._session = aiohttp.ClientSession(
                timeout=timeout,
                headers=headers,
            )
        return self._session
    
    def _next_request_id(self) -> int:
        """Get next JSON-RPC request ID."""
        self._request_id += 1
        return self._request_id
    
    async def _rpc_call(
        self,
        method: str,
        params: list[Any],
    ) -> Any:
        """Make a JSON-RPC call to Solana."""
        session = await self._get_session()
        
        payload = {
            "jsonrpc": "2.0",
            "id": self._next_request_id(),
            "method": method,
            "params": params,
        }
        
        try:
            async with session.post(self.rpc_url, json=payload) as response:
                if response.status == 429:
                    raise RateLimitError(
                        "Solana RPC rate limit exceeded",
                        chain=Chain.SOLANA,
                        retry_after_seconds=5,
                    )
                
                if response.status != 200:
                    raise RPCError(
                        f"RPC error: {response.status}",
                        chain=Chain.SOLANA,
                        rpc_url=self.rpc_url,
                        status_code=response.status,
                    )
                
                data = await response.json()
                
                if "error" in data:
                    error = data["error"]
                    raise RPCError(
                        f"RPC error: {error.get('message', 'Unknown')}",
                        chain=Chain.SOLANA,
                        details=error,
                    )
                
                return data.get("result")
                
        except aiohttp.ClientError as e:
            raise RPCError(
                f"Network error: {e}",
                chain=Chain.SOLANA,
                rpc_url=self.rpc_url,
            )
    
    async def _fetch_transactions(
        self,
        address: str,
        start_block: Optional[int] = None,
        end_block: Optional[int] = None,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        """
        Fetch transaction signatures for an address.
        
        Uses getSignaturesForAddress RPC method.
        """
        try:
            params = [
                address,
                {"limit": min(limit, 100)},
            ]
            
            signatures = await self._rpc_call("getSignaturesForAddress", params)
            
            if not signatures:
                return []
            
            # Fetch full transactions for each signature
            transactions = []
            for sig_info in signatures[:min(20, len(signatures))]:  # Limit detail fetches
                signature = sig_info.get("signature")
                if signature:
                    tx = await self._get_transaction(signature)
                    if tx:
                        transactions.append(tx)
                
                # Rate limit between requests
                await asyncio.sleep(0.2)
            
            return transactions
            
        except Exception as e:
            logger.warning(f"Failed to fetch Solana transactions: {e}")
            return []
    
    async def _fetch_token_transfers(
        self,
        address: str,
        start_block: Optional[int] = None,
        end_block: Optional[int] = None,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        """
        Fetch SPL token transfers.
        
        For Solana, token transfers are included in regular transactions.
        This method fetches token accounts and their recent activity.
        """
        # Token transfers are parsed from regular transactions in Solana
        # Return empty here as we handle them in _fetch_transactions
        return []
    
    async def _get_transaction(self, signature: str) -> Optional[dict[str, Any]]:
        """Get full transaction details."""
        try:
            params = [
                signature,
                {
                    "encoding": "jsonParsed",
                    "maxSupportedTransactionVersion": 0,
                },
            ]
            
            result = await self._rpc_call("getTransaction", params)
            
            if result:
                result["signature"] = signature
            
            return result
            
        except Exception as e:
            logger.debug(f"Failed to get transaction {signature[:20]}...: {e}")
            return None
    
    def _parse_transaction(
        self,
        raw: dict[str, Any],
        wallet_address: str,
    ) -> Optional[WalletActivity]:
        """Parse Solana transaction into WalletActivity."""
        try:
            signature = raw.get("signature", "")
            
            # Parse timestamp
            block_time = raw.get("blockTime", 0)
            if block_time:
                timestamp = datetime.fromtimestamp(block_time)
            else:
                timestamp = datetime.utcnow()
            
            # Parse meta
            meta = raw.get("meta", {})
            if meta.get("err"):
                return None  # Failed transaction
            
            # Get pre and post balances
            pre_balances = meta.get("preBalances", [])
            post_balances = meta.get("postBalances", [])
            
            # Get account keys
            transaction = raw.get("transaction", {})
            message = transaction.get("message", {})
            account_keys = message.get("accountKeys", [])
            
            # Find wallet index
            wallet_index = None
            for i, key in enumerate(account_keys):
                if isinstance(key, dict):
                    pubkey = key.get("pubkey", "")
                else:
                    pubkey = str(key)
                
                if pubkey == wallet_address:
                    wallet_index = i
                    break
            
            if wallet_index is None:
                return None
            
            # Calculate SOL balance change
            if wallet_index < len(pre_balances) and wallet_index < len(post_balances):
                pre_balance = pre_balances[wallet_index]
                post_balance = post_balances[wallet_index]
                balance_change = (post_balance - pre_balance) / 1e9  # lamports to SOL
            else:
                balance_change = 0
            
            # Determine direction
            if balance_change > 0:
                direction = "in"
            elif balance_change < 0:
                direction = "out"
            else:
                direction = "unknown"
            
            # Detect token transfers from inner instructions
            token_transfers = self._extract_token_transfers(meta, wallet_address)
            
            # Determine activity type
            instructions = message.get("instructions", [])
            activity_type = self._detect_activity_type(instructions)
            
            # Get counterparty (simplified)
            counterparty = None
            for i, key in enumerate(account_keys):
                if isinstance(key, dict):
                    pubkey = key.get("pubkey", "")
                else:
                    pubkey = str(key)
                
                if pubkey != wallet_address and i < 3:
                    counterparty = pubkey
                    break
            
            # Use token transfer if available, otherwise SOL
            if token_transfers:
                transfer = token_transfers[0]
                token_symbol = transfer.get("symbol", "UNKNOWN")
                amount = transfer.get("amount", 0)
            else:
                token_symbol = "SOL"
                amount = abs(balance_change)
            
            # Estimate USD value
            value_usd = self._estimate_usd_value(token_symbol, amount)
            
            return WalletActivity(
                tx_hash=signature,
                wallet_address=wallet_address,
                chain=Chain.SOLANA,
                timestamp=timestamp,
                activity_type=activity_type,
                direction=direction,
                token_symbol=token_symbol,
                token_address=None,
                amount=amount,
                value_usd=value_usd,
                counterparty_address=counterparty,
                block_number=raw.get("slot", 0),
            )
            
        except Exception as e:
            logger.warning(f"Failed to parse Solana transaction: {e}")
            return None
    
    def _extract_token_transfers(
        self,
        meta: dict[str, Any],
        wallet_address: str,
    ) -> list[dict[str, Any]]:
        """Extract SPL token transfers from transaction meta."""
        transfers = []
        
        # Check pre and post token balances
        pre_token = meta.get("preTokenBalances", [])
        post_token = meta.get("postTokenBalances", [])
        
        # Create balance maps
        pre_map: dict[str, float] = {}
        post_map: dict[str, float] = {}
        
        for balance in pre_token:
            owner = balance.get("owner", "")
            if owner == wallet_address:
                mint = balance.get("mint", "")
                amount = float(balance.get("uiTokenAmount", {}).get("uiAmount", 0) or 0)
                pre_map[mint] = amount
        
        for balance in post_token:
            owner = balance.get("owner", "")
            if owner == wallet_address:
                mint = balance.get("mint", "")
                amount = float(balance.get("uiTokenAmount", {}).get("uiAmount", 0) or 0)
                post_map[mint] = amount
        
        # Calculate changes
        all_mints = set(pre_map.keys()) | set(post_map.keys())
        for mint in all_mints:
            pre_amount = pre_map.get(mint, 0)
            post_amount = post_map.get(mint, 0)
            change = post_amount - pre_amount
            
            if abs(change) > 0.0001:
                symbol = TOKEN_MINTS.get(mint, "UNKNOWN")
                transfers.append({
                    "mint": mint,
                    "symbol": symbol,
                    "amount": abs(change),
                    "direction": "in" if change > 0 else "out",
                })
        
        return transfers
    
    def _detect_activity_type(
        self,
        instructions: list[dict[str, Any]],
    ) -> ActivityType:
        """Detect activity type from instructions."""
        for inst in instructions:
            program_id = inst.get("programId", "")
            
            # Common program IDs
            if program_id in [
                "JUP6LkbZbjS1jKKwapdHNy74zcZ3tLUZoi5QNyVTaV4",  # Jupiter
                "whirLbMiicVdio4qvUfM5KAg6Ct8VwpYzGff3uctyCc",   # Orca
            ]:
                return ActivityType.SWAP
            elif program_id == "11111111111111111111111111111111":  # System
                return ActivityType.TRANSFER
            elif program_id in [
                "Stake11111111111111111111111111111111111111",
            ]:
                return ActivityType.STAKE
        
        return ActivityType.CONTRACT_INTERACTION
    
    def _estimate_usd_value(self, token_symbol: str, amount: float) -> float:
        """Estimate USD value of token amount."""
        prices = {
            "SOL": 100.0,
            "USDC": 1.0,
            "USDT": 1.0,
            "WETH": 2500.0,
            "WBTC": 45000.0,
            "mSOL": 110.0,
            "stSOL": 110.0,
            "BONK": 0.00002,
            "JUP": 0.8,
        }
        
        price = prices.get(token_symbol.upper(), 0.0)
        return amount * price
    
    async def get_sol_balance(self, address: str) -> Optional[float]:
        """Get SOL balance for an address."""
        try:
            result = await self._rpc_call("getBalance", [address])
            
            if result and "value" in result:
                return result["value"] / 1e9
            
            return None
            
        except Exception as e:
            logger.warning(f"Failed to get SOL balance: {e}")
            return None
    
    async def close(self) -> None:
        """Close the aiohttp session."""
        if self._session and not self._session.closed:
            await self._session.close()
