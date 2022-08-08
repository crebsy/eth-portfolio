
import abc
from dataclasses import dataclass, field
from decimal import Decimal
from functools import cached_property
from typing import (DefaultDict, Dict, Iterable, Literal, Optional, Tuple,
                    TypedDict, TypeVar, Union)

from checksum_dict import DefaultChecksumDict
from y.datatypes import Address, Block

_T = TypeVar('_T')

TransactionData = Dict # TODO define TypedDict
InternalTransferData = Dict # TODO define TypedDict

TokenTransferData = TypedDict('TokenTransferData', {
    'chainId': int,
    'blockNumber': Block,
    'transactionIndex': int,
    'hash': str,
    'log_index': int,
    'token': Optional[str],
    'token_address': Address,
    'from': Address,
    'to': Address,
    'value': Decimal,
})

ProtocolLabel = str

Addresses = Union[Address, Iterable[Address]]
TokenAddress = TypeVar('TokenAddress', bound=Address)


class _SummableNonNumeric(metaclass=abc.ABCMeta):
    @abc.abstractmethod
    def __add__(self: _T, other: Union[_T, Literal[0]]) -> _T:
        ...
    def __radd__(self: _T, other: Union[_T, Literal[0]]) -> _T:
        if other == 0:
            return self
        return self.__add__(other)  # type: ignore


@dataclass
class Balance(Dict[Literal["balance", "usd_value"], Decimal], _SummableNonNumeric):
    balance: Decimal = field(default=Decimal())
    usd_value: Decimal = field(default=Decimal())
    
    def __post_init__(self):
        """ This just supports legacy code that uses key lookup and will eventually be removed. """
        self['balance'] = self.balance
        self['usd_value'] = self.usd_value
    
    @property
    def usd(self) -> Decimal:
        ''' An alias for usd_value. ''' 
        return self.usd_value

    def __repr__(self) -> str:
        return f"_BalanceItem{str(dict(self))}"
    
    def __add__(self, other: Union['Balance', Literal[0]]) -> 'Balance':
        """ It is on you to ensure the two BalanceItems are for the same token. """
        assert isinstance(other, Balance), f"{other} is not a BalanceItem"
        try:
            return Balance(self['balance'] + other['balance'], self['usd_value'] + other['usd_value'])
        except Exception as e:
            raise e.__class__(f"Cannot add {self} and {other}: {e}")
    
    def __sub__(self, other: Union['Balance', Literal[0]]) -> 'Balance':
        """ It is on you to ensure the two BalanceItems are for the same token. """
        assert isinstance(other, Balance), f"{other} is not a BalanceItem"
        try:
            return Balance(self['balance'] - other['balance'], self['usd_value'] - other['usd_value'])
        except Exception as e:
            raise e.__class__(f"Cannot subtract {self} and {other}: {e}")
    
    def __bool__(self) -> bool:
        return self.balance != 0 or self.usd_value != 0


_TBSeed = Union[Dict[Address, Balance], Iterable[Tuple[Address, Balance]]]

class TokenBalances(DefaultChecksumDict[Balance], _SummableNonNumeric):
    """
    Keyed: ``token -> balance``
    """ 
    def __init__(self, seed: Optional[_TBSeed] = None) -> None:
        super().__init__(Balance)
        if seed is None:
            return
        if isinstance(seed, dict):
            seed = seed.items()
        if isinstance(seed, Iterable):
            for token, balance in seed:
                self[token] += balance
        else:
            raise TypeError(f"{seed} is not a valid input for TokenBalances")
    
    def sum_usd(self) -> Decimal:
        return Decimal(sum(balance.usd for balance in self.values()))
    
    def __bool__(self) -> bool:
        return any(self.values())

    def __repr__(self) -> str:
        return f"TokenBalances{str(dict(self))}"
    
    def __add__(self, other: Union['TokenBalances', Literal[0]]) -> 'TokenBalances':
        assert isinstance(other, TokenBalances), f"{other} is not a TokenBalances object"
        # NOTE We need a new object to avoid mutating the inputs
        combined: TokenBalances = TokenBalances()
        for token, balance in self.items():
            if balance:
                combined._setattr_nochecksum(token, Balance(balance.balance, balance.usd_value))
        for token, balance in other.items():
            if balance:
                if token in combined:
                    combined._setattr_nochecksum(token, combined.__getattr_nochecksum(token) + balance)
                else:
                    combined._setattr_nochecksum(token, Balance(balance.balance, balance.usd_value))
        return combined
    
    def __sub__(self, other: Union['TokenBalances', Literal[0]]) -> 'TokenBalances':
        assert isinstance(other, TokenBalances), f"{other} is not a TokenBalances object"
        # We need a new object to avoid mutating the inputs
        subtracted: TokenBalances = TokenBalances(self)
        for token, balance in other.items():
            subtracted[token] -= balance
        for token, balance in subtracted.items():
            if not balance:
                del subtracted[token]
        return subtracted

CategoryLabel = Literal["assets", "debt"]

_WBSeed = Union[Dict[CategoryLabel, TokenBalances], Iterable[Tuple[CategoryLabel, TokenBalances]]]

class WalletBalances(DefaultDict[CategoryLabel, TokenBalances], _SummableNonNumeric):
    """
    Keyed: ``category -> token -> balance``
    """
    def __init__(self, seed: Optional[_WBSeed] = None) -> None:
        super().__init__(TokenBalances)
        if seed is None:
            return
        if isinstance(seed, dict):
            seed = seed.items()
        if isinstance(seed, Iterable):
            for category, balances in seed:  # type: ignore
                self[category] += balances
        else:
            raise TypeError(f"{seed} is not a valid input for WalletBalances")
        
    @property
    def assets(self) -> TokenBalances:
        return self['assets']
    
    @property
    def debt(self) -> TokenBalances:
        return self['debt']
    
    def sum_usd(self) -> Decimal:
        return self.assets.sum_usd() - self.debt.sum_usd()
    
    def __bool__(self) -> bool:
        return any(self.values())
    
    def __repr__(self) -> str:
        return f"WalletBalances {str(dict(self))}"

    def __add__(self, other: Union['WalletBalances', Literal[0]]) -> 'WalletBalances':
        assert isinstance(other, WalletBalances), f"{other} is not a WalletBalances object"
        # NOTE We need a new object to avoid mutating the inputs
        combined: WalletBalances = WalletBalances()
        for category, balances in self.items():
            if balances:
                combined[category] += balances
        for category, balances in other.items():
            if balances:
                combined[category] += balances
        return combined
    
    def __sub__(self, other: Union['WalletBalances', Literal[0]]) -> 'WalletBalances':
        assert isinstance(other, WalletBalances), f"{other} is not a WalletBalances object"
        # We need a new object to avoid mutating the inputs
        subtracted: WalletBalances = WalletBalances(self)
        for category, balances in other.items():
            subtracted[category] -= balances
        for category, balances in subtracted.items():
            if not balances:
                del subtracted[category]
        return subtracted
    
    def __getitem__(self, key: CategoryLabel) -> TokenBalances:
        self.__validateitem(key)
        return super().__getitem__(key)

    def __setitem__(self, key: CategoryLabel, value: TokenBalances) -> None:
        self.__validateitem(key)
        return super().__setitem__(key, value)
    
    def __validateitem(self, key: CategoryLabel) -> None:
        if key not in ['assets', 'debt']:
            raise KeyError(f"{key} is not a valid key for WalletBalances. Valid keys are 'assets' and 'debt'")


RemoteTokenBalances = Dict[ProtocolLabel, TokenBalances]

_PBSeed = Union[Dict[Address, WalletBalances], Iterable[Tuple[Address, WalletBalances]]]

class PortfolioBalances(DefaultChecksumDict[WalletBalances], _SummableNonNumeric):
    """
    Keyed: ``wallet -> category -> token -> balance``
    """ 
    def __init__(self, seed: Optional[_PBSeed] = None) -> None:
        super().__init__(WalletBalances)
        if seed is None:
            return
        if isinstance(seed, dict):
            seed = seed.items()
        if isinstance(seed, Iterable):
            for wallet, balances in seed:
                self[wallet] += balances
        else:
            raise TypeError(f"{seed} is not a valid input for PortfolioBalances")
    
    def sum_usd(self) -> Decimal:
        return sum(balances.sum_usd() for balances in self.values())  # type: ignore
    
    @cached_property
    def inverted(self) -> "PortfolioBalancesByCategory":
        inverted = PortfolioBalancesByCategory()
        for wallet, wbalances in self.items():
            for label, tbalances in wbalances.items():
                if tbalances:
                    inverted[label][wallet] += tbalances
        return inverted
    
    def __bool__(self) -> bool:
        return any(self.values())

    def __repr__(self) -> str:
        return f"WalletBalances{str(dict(self))}"
    
    def __add__(self, other: Union['PortfolioBalances', Literal[0]]) -> 'PortfolioBalances':
        assert isinstance(other, PortfolioBalances), f"{other} is not a WalletBalances object"
        # NOTE We need a new object to avoid mutating the inputs
        combined: PortfolioBalances = PortfolioBalances()
        for wallet, balance in self.items():
            if balance:
                combined._setattr_nochecksum(wallet, combined.__getattr_nochecksum(wallet) + balance)
        for wallet, balance in other.items():
            if balance:
                combined._setattr_nochecksum(wallet, combined.__getattr_nochecksum(wallet) + balance)
        return combined
    
    def __sub__(self, other: Union['PortfolioBalances', Literal[0]]) -> 'PortfolioBalances':
        assert isinstance(other, PortfolioBalances), f"{other} is not a WalletBalances object"
        # We need a new object to avoid mutating the inputs
        subtracted: PortfolioBalances = PortfolioBalances(self)
        for protocol, balances in other.items():
            subtracted[protocol] -= balances
        for protocol, balances in subtracted.items():
            if not balances:
                del subtracted[protocol]
        return subtracted


_WTBInput = Union[Dict[Address, TokenBalances], Iterable[Tuple[Address, TokenBalances]]]

class WalletBalancesRaw(DefaultChecksumDict[TokenBalances], _SummableNonNumeric):
    """
    Since PortfolioBalances key lookup is:    ``wallet   -> category -> token    -> balance``
    and WalletBalances key lookup is:         ``category -> token    -> balance``
    We need a new structure for key pattern:  ``wallet   -> token    -> balance``

    WalletBalancesRaw fills this role.
    """ 
    def __init__(self, seed: Optional[_WTBInput] = None) -> None:
        super().__init__(TokenBalances)
        if seed is None:
            return
        if isinstance(seed, dict):
            seed = seed.items()
        if isinstance(seed, Iterable):
            for wallet, balances in seed:
                self[wallet] += balances
        else:
            raise TypeError(f"{seed} is not a valid input for WalletBalancesRaw")
    
    def __bool__(self) -> bool:
        return any(self.values())

    def __repr__(self) -> str:
        return f"WalletBalances{str(dict(self))}"
    
    def __add__(self, other: Union['WalletBalancesRaw', Literal[0]]) -> 'WalletBalancesRaw':
        assert isinstance(other, WalletBalancesRaw), f"{other} is not a WalletBalancesRaw object"
        # NOTE We need a new object to avoid mutating the inputs
        combined: WalletBalancesRaw = WalletBalancesRaw()
        for wallet, balance in self.items():
            if balance:
                combined._setattr_nochecksum(wallet, combined.__getattr_nochecksum(wallet) + balance)
        for wallet, balance in other.items():
            if balance:
                combined._setattr_nochecksum(wallet, combined.__getattr_nochecksum(wallet) + balance)
        return combined
    
    def __sub__(self, other: Union['WalletBalancesRaw', Literal[0]]) -> 'WalletBalancesRaw':
        assert isinstance(other, WalletBalancesRaw), f"{other} is not a WalletBalancesRaw object"
        # We need a new object to avoid mutating the inputs
        subtracted: WalletBalancesRaw = WalletBalancesRaw(self)
        for wallet, balances in other.items():
            if balances:
                subtracted[wallet] -= balances
        for wallet, balances in subtracted.items():
            if not balances:
                del subtracted[wallet]
        return subtracted

_CBInput = Union[Dict[CategoryLabel, WalletBalancesRaw], Iterable[Tuple[CategoryLabel, WalletBalancesRaw]]]

class PortfolioBalancesByCategory(DefaultDict[CategoryLabel, WalletBalancesRaw], _SummableNonNumeric):
    """
    Keyed: ``category -> wallet -> token -> balance``
    """ 
    def __init__(self, seed: Optional[_CBInput] = None) -> None:
        super().__init__(WalletBalancesRaw)
        if seed is None:
            return
        if isinstance(seed, dict):
            seed = seed.items()
        if isinstance(seed, Iterable):
            for label, balances in seed:  # type: ignore
                self[label] += balances
        else:
            raise TypeError(f"{seed} is not a valid input for PortfolioBalancesByCategory")

    @property
    def assets(self) -> WalletBalancesRaw:
        return self['assets']
    
    @property
    def debt(self) -> WalletBalancesRaw:
        return self['debt']
    
    def invert(self) -> "PortfolioBalances":
        inverted = PortfolioBalances()
        for label, wtbalances in self.items():
            for wallet, tbalances in wtbalances.items():
                if tbalances:
                    inverted[wallet][label] += tbalances
        return inverted
    
    def __bool__(self) -> bool:
        return any(self.values())

    def __repr__(self) -> str:
        return f"PortfolioBalancesByCategory{str(dict(self))}"
    
    def __add__(self, other: Union['PortfolioBalancesByCategory', Literal[0]]) -> 'PortfolioBalancesByCategory':
        assert isinstance(other, PortfolioBalancesByCategory), f"{other} is not a PortfolioBalancesByCategory object"
        # NOTE We need a new object to avoid mutating the inputs
        combined: PortfolioBalancesByCategory = PortfolioBalancesByCategory()
        for protocol, balances in self.items():
            if balances:
                combined[protocol] += balances
        for protocol, balances in other.items():
            if balances:
                combined[protocol] += balances
        return combined
    
    def __sub__(self, other: Union['PortfolioBalancesByCategory', Literal[0]]) -> 'PortfolioBalancesByCategory':
        assert isinstance(other, PortfolioBalancesByCategory), f"{other} is not a PortfolioBalancesByCategory object"
        # We need a new object to avoid mutating the inputs
        subtracted: PortfolioBalancesByCategory = PortfolioBalancesByCategory(self)
        for protocol, balances in other.items():
            subtracted[protocol] -= balances
        for protocol, balances in subtracted.items():
            if not balances:
                del subtracted[protocol]
        return subtracted
