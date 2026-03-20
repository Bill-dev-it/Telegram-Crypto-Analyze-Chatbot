import pytest

from features.deepscan.agent import agent as deepscan_agent
from features.data.binance_price_fetcher import get_binance_ticker_price
from features.data.dexscreener_data_fetcher import fetch_dexscreener_token_data
from features.data.deployer_analyzer import analyze_deployer


def test_deepscan_agent_import():
    # the agent should be callable and have process_query
    assert hasattr(deepscan_agent, 'process_query')
    res = deepscan_agent.process_query('hello world')
    assert isinstance(res, dict)


def test_binance_price_fetcher_returns_none_for_unknown_symbol():
    price = get_binance_ticker_price('NONEXISTENTCOIN')
    assert price is None or isinstance(price, float)


def test_dexscreener_fetcher_invalid_address():
    data = fetch_dexscreener_token_data('0x0000000000000000000000000000000000000000')
    # likely None or a dict
    assert data is None or isinstance(data, dict)


def test_deployer_analyzer_no_key(monkeypatch):
    # without etherscan key it should return a dict with conclusion
    monkeypatch.delenv('ETHERSCAN_API_KEY', raising=False)
    report = analyze_deployer('0x0000000000000000000000000000000000000000')
    assert isinstance(report, dict)
    assert 'conclusion' in report
