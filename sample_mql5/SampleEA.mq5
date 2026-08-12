//+------------------------------------------------------------------+
//|                                              SampleEA.mq5        |
//|                                  Sample Expert Advisor           |
//+------------------------------------------------------------------+
#property copyright "Sample"
#property version   "1.00"

input double LotSize = 0.1;
input int StopLoss = 50;
input int TakeProfit = 100;
input bool UseTrailingStop = true;

int handleMA;
double maBuffer[];

//+------------------------------------------------------------------+
//| Expert initialization function                                   |
//+------------------------------------------------------------------+
int OnInit()
{
    handleMA = iMA(_Symbol, _Period, 20, 0, MODE_SMA, PRICE_CLOSE);
    if(handleMA == INVALID_HANDLE)
    {
        Print("Error creating MA handle");
        return(INIT_FAILED);
    }
    
    ArraySetAsSeries(maBuffer, true);
    Print("Expert Advisor initialized successfully");
    return(INIT_SUCCEEDED);
}

//+------------------------------------------------------------------+
//| Expert deinitialization function                                 |
//+------------------------------------------------------------------+
void OnDeinit(const int reason)
{
    IndicatorRelease(handleMA);
    Print("Expert Advisor deinitialized");
}

//+------------------------------------------------------------------+
//| Expert tick function                                             |
//+------------------------------------------------------------------+
void OnTick()
{
    if(CopyBuffer(handleMA, 0, 0, 3, maBuffer) < 3)
        return;
    
    double currentPrice = SymbolInfoDouble(_Symbol, SYMBOL_BID);
    double maCurrent = maBuffer[0];
    double maPrevious = maBuffer[1];
    
    if(currentPrice > maCurrent && currentPrice < maPrevious)
    {
        CloseAllPositions();
    }
    
    if(currentPrice < maCurrent && currentPrice > maPrevious)
    {
        if(CountPositions() == 0)
        {
            OpenBuyOrder();
        }
    }
    
    if(UseTrailingStop)
    {
        TrailPositions();
    }
}

//+------------------------------------------------------------------+
//| Open a buy order                                                 |
//+------------------------------------------------------------------+
void OpenBuyOrder()
{
    MqlTradeRequest request = {};
    MqlTradeResult result = {};
    
    request.action = TRADE_ACTION_DEAL;
    request.symbol = _Symbol;
    request.volume = LotSize;
    request.type = ORDER_TYPE_BUY;
    request.price = SymbolInfoDouble(_Symbol, SYMBOL_ASK);
    request.sl = request.price - StopLoss * _Point;
    request.tp = request.price + TakeProfit * _Point;
    request.deviation = 10;
    request.magic = 123456;
    
    if(!OrderSend(request, result))
    {
        Print("OrderSend error: ", GetLastError());
    }
    else
    {
        Print("Buy order opened at ", request.price);
    }
}

//+------------------------------------------------------------------+
//| Close all positions                                              |
//+------------------------------------------------------------------+
void CloseAllPositions()
{
    for(int i = PositionsTotal() - 1; i >= 0; i--)
    {
        ulong ticket = PositionGetTicket(i);
        if(ticket > 0)
        {
            ClosePosition(ticket);
        }
    }
}

//+------------------------------------------------------------------+
//| Close a single position                                          |
//+------------------------------------------------------------------+
void ClosePosition(ulong ticket)
{
    MqlTradeRequest request = {};
    MqlTradeResult result = {};
    
    if(!PositionSelectByTicket(ticket))
        return;
    
    request.action = TRADE_ACTION_DEAL;
    request.position = ticket;
    request.symbol = PositionGetString(POSITION_SYMBOL);
    request.volume = PositionGetDouble(POSITION_VOLUME);
    request.type = (PositionGetInteger(POSITION_TYPE) == POSITION_TYPE_BUY) ? ORDER_TYPE_SELL : ORDER_TYPE_BUY;
    request.price = (request.type == ORDER_TYPE_SELL) ? 
                    SymbolInfoDouble(_Symbol, SYMBOL_BID) : 
                    SymbolInfoDouble(_Symbol, SYMBOL_ASK);
    request.deviation = 10;
    
    if(!OrderSend(request, result))
    {
        Print("ClosePosition error: ", GetLastError());
    }
}

//+------------------------------------------------------------------+
//| Count open positions                                             |
//+------------------------------------------------------------------+
int CountPositions()
{
    return PositionsTotal();
}

//+------------------------------------------------------------------+
//| Trail stop losses                                                |
//+------------------------------------------------------------------+
void TrailPositions()
{
    for(int i = PositionsTotal() - 1; i >= 0; i--)
    {
        if(PositionSelectByTicket(PositionGetTicket(i)))
        {
            double openPrice = PositionGetDouble(POSITION_PRICE_OPEN);
            double currentSL = PositionGetDouble(POSITION_SL);
            double currentPrice = PositionGetDouble(POSITION_PRICE_CURRENT);
            
            if(PositionGetInteger(POSITION_TYPE) == POSITION_TYPE_BUY)
            {
                double newSL = currentPrice - StopLoss * _Point;
                if(newSL > currentSL && newSL > openPrice)
                {
                    ModifyPositionSL(PositionGetTicket(i), newSL);
                }
            }
        }
    }
}

//+------------------------------------------------------------------+
//| Modify position stop loss                                        |
//+------------------------------------------------------------------+
void ModifyPositionSL(ulong ticket, double newSL)
{
    MqlTradeRequest request = {};
    MqlTradeResult result = {};
    
    request.action = TRADE_ACTION_SLTP;
    request.position = ticket;
    request.symbol = PositionGetString(POSITION_SYMBOL);
    request.sl = newSL;
    
    if(!OrderSend(request, result))
    {
        Print("ModifyPositionSL error: ", GetLastError());
    }
}
