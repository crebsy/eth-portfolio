
import asyncio
from typing import Optional

from async_lru import alru_cache
from brownie import chain
from eth_abi import encode_single
from eth_portfolio.decorators import await_if_sync
from eth_portfolio.lending.base import LendingProtocolWithLockedCollateral
from eth_portfolio.typing import TokenBalances
from y import Network, get_price_async
from y.constants import dai
from y.contracts import Contract
from y.datatypes import Address, Block

yfi = "0x0bc529c00C6401aEF6D220BE8C6Ea1667F6Ad93e"

class Maker(LendingProtocolWithLockedCollateral):
    def __init__(self, asynchronous: bool = False) -> None:
        self.asynchronous = bool(asynchronous)
        self.proxy_registry = Contract('0x4678f0a6958e4D2Bc4F1BAF7Bc52E8F3564f3fE4')
        self.cdp_manager = Contract('0x5ef30b9986345249bc32d8928B7ee64DE9435E39')
        self.vat = Contract('0x35D1b3F3D7966A1DFe207aa4514C12a259A0492B')
    
    @await_if_sync 
    def collateral(self, address: Address, block: Optional[Block] = None) -> TokenBalances:
        return self._collateral_async(address, block) # type: ignore
    
    async def _collateral_async(self, address: Address, block: Optional[Block] = None) -> TokenBalances:
        ilk = encode_single('bytes32', b'YFI-A')
        urn = await self._urn(address)
        ink = (await self.vat.urns.coroutine(ilk, urn, block_identifier=block)).dict()["ink"]
        if ink:
            return {
                yfi: {
                    'balance': ink / 1e18,
                    'usd value': ink / 1e18 * await get_price_async(yfi, block) if ink > 0 else 0,
                }
            }
        return {}
    
    @await_if_sync
    def debt(self, address: Address, block: int = None) -> TokenBalances:
        return self._debt_async(address, block=block) # type: ignore
    
    async def _debt_async(self, address: Address, block: int = None) -> TokenBalances:
        ilk = encode_single('bytes32', b'YFI-A')
        urn = await self._urn(address)
        urns, ilks = await asyncio.gather(
            self.vat.urns.coroutine(ilk, urn, block_identifier=block),
            self.vat.ilks.coroutine(ilk, block_identifier=block),
        )
        art = urns.dict()["art"]
        rate = ilks.dict()["rate"]
        debt = art * rate / 1e45
        return {dai.address: {'balance': debt, 'usd value': debt}}

    @alru_cache
    async def _proxy(self, address: Address) -> Address:
        return await self.proxy_registry.proxies.coroutine(address)
    
    @alru_cache
    async def _cdp(self, address: Address) -> Address:
        proxy = await self._proxy(address)
        return await self.cdp_manager.first.coroutine(proxy)
    
    @alru_cache
    async def _urn(self, address: Address) -> Address:
        cdp = await self._cdp(address)
        return await self.cdp_manager.urns.coroutine(cdp)

maker = Maker(asynchronous=True) if chain.id == Network.Mainnet else None
