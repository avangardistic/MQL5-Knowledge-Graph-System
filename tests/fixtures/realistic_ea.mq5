//+------------------------------------------------------------------+
//| realistic_ea.mq5 - Full EA for end-to-end testing               |
//+------------------------------------------------------------------+
#property copyright "Test"
#property version   "1.0"
#include "IncludeTest.mqh"

input double LotSize = 0.1;
input int    MagicNum = 12345;
input double TakeProfit = 50.0;
input double StopLoss = 30.0;

int g_maHandle;
double g_lastEquity;

int OnInit()
{
    g_maHandle = iMA(_Symbol, _Period, 20, 0, MODE_SMA, PRICE_CLOSE);
    g_lastEquity = AccountInfoDouble(ACCOUNT_EQUITY);
    return(INIT_SUCCEEDED);
}

void OnDeinit(const int reason)
{
    IndicatorRelease(g_maHandle);
}

void OnTick()
{
    double equity = AccountInfoDouble(ACCOUNT_EQUITY);
    if(equity < g_lastEquity * 0.95)
    {
        CloseAll();
        return;
    }

    if(ShouldBuy())
        OpenBuy();
    else if(ShouldSell())
        OpenSell();
}

bool ShouldBuy()
{
    double price = SymbolInfoDouble(_Symbol, SYMBOL_BID);
    return price > 0;
}

bool ShouldSell()
{
    double price = SymbolInfoDouble(_Symbol, SYMBOL_ASK);
    return price > 0;
}

void OpenBuy()
{
    MqlTradeRequest req = {};
    MqlTradeResult  res = {};
    req.action = TRADE_ACTION_DEAL;
    req.type   = ORDER_TYPE_BUY;
    req.volume = LotSize;
    OrderSend(req, res);
}

void OpenSell()
{
    MqlTradeRequest req = {};
    MqlTradeResult  res = {};
    req.action = TRADE_ACTION_DEAL;
    req.type   = ORDER_TYPE_SELL;
    req.volume = LotSize;
    OrderSend(req, res);
}

void CloseAll()
{
    for(int i = PositionsTotal() - 1; i >= 0; i--)
    {
        ulong ticket = PositionGetTicket(i);
        if(ticket > 0)
            CloseByTicket(ticket);
    }
}

bool CloseByTicket(ulong ticket)
{
    MqlTradeRequest req = {};
    MqlTradeResult  res = {};
    req.action   = TRADE_ACTION_DEAL;
    req.position = ticket;
    return OrderSend(req, res);
}

double GetEquity()
{
    return AccountInfoDouble(ACCOUNT_EQUITY);
}
