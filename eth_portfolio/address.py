
import asyncio
import logging
from decimal import Decimal, InvalidOperation
from typing import TYPE_CHECKING, Dict, Optional

import eth_retry
from y import convert, get_price
from y.constants import EEE_ADDRESS, weth
from y.datatypes import Address, Block
from y.utils.dank_mids import dank_w3

from eth_portfolio._decorators import await_if_sync
from eth_portfolio._ledgers.address import (AddressInternalTransfersLedger,
                                            AddressTokenTransfersLedger,
                                            AddressTransactionsLedger,
                                            PandableLedgerEntryList)
from eth_portfolio.protocols import _external
from eth_portfolio.protocols.lending import _lending
from eth_portfolio.typing import (Balance, RemoteTokenBalances, TokenBalances,
                                  WalletBalances)
from eth_portfolio.utils import _get_price

if TYPE_CHECKING:
    from eth_portfolio.portfolio import Portfolio

logger = logging.getLogger(__name__)


@eth_retry.auto_retry
async def _get_eth_balance(address: Address, block: Optional[Block]) -> Decimal:
    return Decimal(await dank_w3.eth.get_balance(address, block_identifier=block)) / Decimal(1e18)

def _calc_value(balance, price) -> Decimal:
    if price is None:
        return Decimal(0)
    # NOTE If balance * price returns a Decimal with precision < 18, rounding is both impossible and unnecessary.
    value = Decimal(balance) * Decimal(price)
    try:
        return round(value, 18)
    except InvalidOperation:
        return value

class PortfolioAddress:
    def __init__(self, address: Address, portfolio: "Portfolio") -> None: # type: ignore
        self.address = convert.to_address(address)
        self.portfolio = portfolio
        self.transactions = AddressTransactionsLedger(self)
        self.internal_transfers = AddressInternalTransfersLedger(self)
        self.token_transfers = AddressTokenTransfersLedger(self)

    @property
    def asynchronous(self) -> bool:
        return self.portfolio.asynchronous

    @property
    def load_prices(self) -> bool:
        return self.portfolio.load_prices
    
    def __str__(self) -> str:
        return self.address

    def __repr__(self) -> str:
        return f"<PortfolioAddress: {self.address}>"
    
    def __eq__(self, other: object) -> bool:
        if isinstance(other, PortfolioAddress):
            return self.address == other.address
        elif isinstance(other, str):
            return self.address == convert.to_address(other)
        return False
    
    def __hash__(self) -> int:
        return hash(self.address)
    
    # Primary functions

    @await_if_sync
    def describe(self, block: int) -> WalletBalances:
        return self._describe_async(block=block) # type: ignore
    
    async def _describe_async(self, block: int) -> WalletBalances:
        assert block, "You must provide a valid block number"
        assert isinstance(block, int), f"Block must be an integer. You passed {type(block)} {block}"
        fns = [self._assets_async, self._debt_async, self._external_balances_async]
        balances = WalletBalances()
        balances['assets'], balances['debt'], balances['external'] = await asyncio.gather(*[fn(block) for fn in fns])
        return balances
    
    @await_if_sync
    def assets(self, block: Optional[Block] = None) -> TokenBalances:
        return self._assets_async(block) # type: ignore
    
    async def _assets_async(self, block: Optional[Block] = None) -> TokenBalances:
        return await self._balances_async(block=block)

    @await_if_sync
    def debt(self, block: Optional[Block] = None) -> RemoteTokenBalances:
        return self._debt_async(block) # type: ignore
    
    async def _debt_async(self, block: Optional[Block] = None) -> RemoteTokenBalances:
        return await _lending._debt_async(self.address, block=block)
    
    @await_if_sync
    def external_balances(self, block: Optional[Block] = None) -> RemoteTokenBalances:
        return self._external_balances_async(block) # type: ignore
    
    async def _external_balances_async(self, block: Optional[Block] = None) -> RemoteTokenBalances:
        staked, collateral = await asyncio.gather(
            self._staking_async(block),
            self._collateral_async(block)
        )
        return staked + collateral

    # Assets

    @await_if_sync
    def balances(self, block: Optional[Block]) -> TokenBalances:
        return self._balances_async(block) # type: ignore
    
    async def _balances_async(self, block: Optional[Block]) -> TokenBalances:
        eth_balance, token_balances = await asyncio.gather(
            self._eth_balance_async(block),
            self._token_balances_async(block),
        )
        token_balances[EEE_ADDRESS] = eth_balance
        return token_balances
    
    @await_if_sync
    def eth_balance(self, block: Optional[Block]) -> Balance:
        return self._eth_balance_async(block) # type: ignore

    async def _eth_balance_async(self, block: Optional[Block]) -> Balance:
        balance, price = await asyncio.gather(
            _get_eth_balance(self.address, block),
            get_price(weth, block, sync=False),
        )
        value = round(balance * Decimal(price), 18)
        return Balance(balance, value)
    
    @await_if_sync
    def token_balances(self, block: Optional[Block]) -> TokenBalances:
        return self._token_balances_async(block) # type: ignore
    
    async def _token_balances_async(self, block) -> TokenBalances:
        tokens = await self.token_transfers._list_tokens_at_block_async(block=block)
        token_balances, token_prices = await asyncio.gather(
            asyncio.gather(*[token.balance_of_readable(self.address, block, sync=False) for token in tokens]),
            asyncio.gather(*[_get_price(token, block) for token in tokens]),
        )
        token_balances = [
            Balance(Decimal(balance), _calc_value(balance, price))
            for balance, price in zip(token_balances, token_prices)
        ]
        return TokenBalances(zip(tokens, token_balances))
    
    @await_if_sync
    def collateral(self, block: Optional[Block] = None) -> RemoteTokenBalances:
        return self._collateral_async(block) # type: ignore
    
    async def _collateral_async(self, block: Optional[Block] = None) -> RemoteTokenBalances:
        return await _lending._collateral_async(self.address, block=block)
    
    @await_if_sync
    def staking(self, block: Optional[Block] = None) -> RemoteTokenBalances:
        return self._staking_async(block) # type: ignore
    
    async def _staking_async(self, block: Optional[Block] = None) -> RemoteTokenBalances:
        return await _external._balances_async(self.address, block=block)
    
    # Ledger Entries

    @await_if_sync
    def all(self, load_prices: bool = False) -> Dict[str, PandableLedgerEntryList]:
        return self._all_async(load_prices=load_prices) # type: ignore
    
    async def _all_async(self, start_block: Block, end_block: Block) -> Dict[str, PandableLedgerEntryList]:
        transactions, internal_transactions, token_transfers = await asyncio.gather(
            self.transactions._get_async(start_block, end_block),
            self.internal_transfers._get_async(start_block, end_block),
            self.token_transfers._get_async(start_block, end_block),
        )
        return {
            "transactions": transactions,
            "internal_transactions": internal_transactions,
            "token_transfers": token_transfers,
        }
