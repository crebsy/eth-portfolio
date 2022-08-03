
from typing import Callable

import eth_portfolio.lending
import eth_portfolio.staking
import pytest
from eth_portfolio.address import PortfolioAddress
from eth_portfolio.portfolio import Ledger, Portfolio

"""
Test sync-async completeness.
"""

exposed_classes = [Portfolio, Ledger, PortfolioAddress]
exposed_classes.extend(obj for submodule in [eth_portfolio.lending, eth_portfolio.staking] for _, obj in submodule.__dict__.items() if isinstance(obj, type) and obj.__module__.startswith("eth_portfolio."))
functions = [(cls, name) for cls in exposed_classes for name, obj in cls.__dict__.items() if isinstance(obj, Callable)]

user_facing_functions = [(cls, method_name) for cls, method_name in functions if not method_name.startswith("_")]

@pytest.mark.parametrize("cls, method_name", user_facing_functions)
def test_user_facing_function_has_async_counterpart(cls, method_name):
    assert "_" + method_name + "_async" in cls.__dict__

internal_async_versions_of_user_facing_functions = [(cls, method_name) for cls, method_name in functions if method_name.endswith("async")]
@pytest.mark.parametrize(['cls','method_name'], internal_async_versions_of_user_facing_functions)
def test_async_internal_version_of_user_facing_fn_has_sync_counterpart(cls, method_name):
    # Ensure async internal versions of sync functions actually have their sync counterpart
    print(method_name)
    assert method_name[1:-6] in cls.__dict__        
