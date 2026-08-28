"""Shared fixtures and helpers for the MQL5 Knowledge Graph test suite."""

from pathlib import Path

import pytest

FIXTURES = Path(__file__).parent / "fixtures"
ADVERSARIAL = FIXTURES / "adversarial"


@pytest.fixture()
def fixtures_dir() -> Path:
    return FIXTURES


@pytest.fixture()
def adversarial_dir() -> Path:
    return ADVERSARIAL


@pytest.fixture()
def sample_source() -> str:
    """A compact MQL5 sample used by many tests."""
    return """\
#property copyright "Test"
#property version "1.0"
#include "IncludeTest.mqh"

input double RiskPercent = 1.5;

#define MAX_POSITIONS 10

enum TradingState
{
    STATE_IDLE,
    STATE_IN_TRADE
};

struct TradeResult
{
    bool success;
    double profit;
};

class RiskManager
{
public:
    RiskManager(double risk) { m_risk = risk; }
    bool CanTrade() { return PositionsTotal() < 5; }
private:
    double m_risk;
};

void OnTick()
{
    if(ShouldClose())
        CloseAll();
    string note = "OrderSend(fake)";
    // ClosePosition();
}

bool ShouldClose()
{
    return AccountInfoDouble(ACCOUNT_EQUITY) > 0;
}

void CloseAll()
{
    for(int i = 0; i < PositionsTotal(); i++)
        CloseByTicket(i);
}

void CloseByTicket(int ticket)
{
    RiskManager *rm = new RiskManager(RiskPercent);
    delete rm;
}
"""


@pytest.fixture()
def build_graph():
    """Return an analyzed canonical graph for a root path."""
    from mql5_kg.indexer import analyze_repository

    def _build(root: str | Path):
        return analyze_repository(str(root))

    return _build
