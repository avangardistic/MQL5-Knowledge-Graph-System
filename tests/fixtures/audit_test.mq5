//+------------------------------------------------------------------+
//|                                         audit_test.mq5             |
//|                                  Comprehensive MQL5 Test Fixture   |
//+------------------------------------------------------------------+
#property copyright "Test Copyright"
#property version   "2.0.0"
#property description "Comprehensive test file for MQL5 Knowledge Graph parser"

// Input variables
input double RiskPercent = 1.5;           // Risk percentage per trade
input int    StopLossPoints = 100;        // Stop loss in points
input bool   UseTrailingStop = true;      // Enable trailing stop
input string CommentPrefix = "TestEA";    // Trade comment prefix
input int    MagicNumber = 999888;        // Magic number for orders

// Global variables
int g_maHandle;
double g_maBuffer[];
bool g_initialized = false;
datetime g_lastBarTime = 0;

// Define macros
#define MAX_POSITIONS 10
#define MIN_LOT_SIZE 0.01

// Enum for trading states
enum TradingState
{
    STATE_IDLE,
    STATE_WAITING_ENTRY,
    STATE_IN_TRADE,
    STATE_CLOSING
};

// Enum members test
enum OrderType
{
    ORDER_BUY,
    ORDER_SELL,
    ORDER_PENDING
};

// Struct definition
struct TradeResult
{
    bool success;
    ulong ticket;
    double profit;
    string message;
};

// Class definition
class RiskManager
{
private:
    double m_maxRisk;
    int m_maxPositions;
    
public:
    // Constructor
    RiskManager(double risk, int maxPos)
    {
        m_maxRisk = risk;
        m_maxPositions = maxPos;
    }
    
    // Method to check if we can trade
    bool CanTrade()
    {
        return PositionsTotal() < m_maxPositions;
    }
    
    // Method to calculate lot size
    double CalculateLot(double stopLoss)
    {
        double balance = AccountInfoDouble(ACCOUNT_BALANCE);
        double riskAmount = balance * (m_maxRisk / 100.0);
        double tickValue = SymbolInfoDouble(_Symbol, SYMBOL_TRADE_TICK_VALUE);
        
        if(stopLoss <= 0 || tickValue == 0)
            return 0;
        
        return NormalizeDouble(riskAmount / (stopLoss * tickValue), 2);
    }
    
    // Virtual method example
    virtual void OnRiskWarning(string msg)
    {
        Print("Risk Warning: ", msg);
    }
};

// Static function
static void LogMessage(string msg)
{
    Print("[", CommentPrefix, "] ", msg);
}

//+------------------------------------------------------------------+
//| Expert initialization function                                   |
//+------------------------------------------------------------------+
int OnInit()
{
    // Initialize indicator
    g_maHandle = iMA(_Symbol, _Period, 20, 0, MODE_SMA, PRICE_CLOSE);
    
    if(g_maHandle == INVALID_HANDLE)
    {
        LogMessage("Failed to create MA handle");
        return(INIT_FAILED);
    }
    
    ArraySetAsSeries(g_maBuffer, true);
    
    // Create risk manager instance
    RiskManager *rm = new RiskManager(RiskPercent, MAX_POSITIONS);
    delete rm;
    
    g_initialized = true;
    LogMessage("Initialization complete");
    
    return(INIT_SUCCEEDED);
}

//+------------------------------------------------------------------+
//| Expert deinitialization function                                 |
//+------------------------------------------------------------------+
void OnDeinit(const int reason)
{
    IndicatorRelease(g_maHandle);
    LogMessage("Deinitialized, reason: " + IntegerToString(reason));
}

//+------------------------------------------------------------------+
//| Expert tick function                                             |
//+------------------------------------------------------------------+
void OnTick()
{
    // Skip if not initialized
    if(!g_initialized)
        return;
    
    // Check for new bar
    datetime currentBarTime = iTime(_Symbol, _Period, 0);
    if(currentBarTime == g_lastBarTime)
        return;
    g_lastBarTime = currentBarTime;
    
    // Copy indicator buffer
    if(CopyBuffer(g_maHandle, 0, 0, 3, g_maBuffer) < 3)
        return;
    
    double price = SymbolInfoDouble(_Symbol, SYMBOL_BID);
    double maCurrent = g_maBuffer[0];
    double maPrev = g_maBuffer[1];
    
    // Trading logic with switch statement
    TradingState state = GetCurrentState();
    
    switch(state)
    {
        case STATE_IDLE:
            HandleIdleState(price, maCurrent, maPrev);
            break;
        case STATE_WAITING_ENTRY:
            HandleWaitingState(price, maCurrent);
            break;
        case STATE_IN_TRADE:
            HandleInTradeState(price);
            break;
        case STATE_CLOSING:
            CloseAllPositions();
            break;
    }
    
    // Trailing stop logic
    if(UseTrailingStop)
    {
        TrailAllStops();
    }
}

//+------------------------------------------------------------------+
//| Get current trading state                                        |
//+------------------------------------------------------------------+
TradingState GetCurrentState()
{
    if(PositionsTotal() == 0)
        return STATE_IDLE;
    
    if(PositionSelect(_Symbol))
        return STATE_IN_TRADE;
    
    return STATE_WAITING_ENTRY;
}

//+------------------------------------------------------------------+
//| Handle idle state                                                |
//+------------------------------------------------------------------+
void HandleIdleState(double price, double maCurrent, double maPrev)
{
    // Look for entry signal
    if(price > maCurrent && price < maPrev)
    {
        OpenBuyOrder();
    }
    else if(price < maCurrent && price > maPrev)
    {
        OpenSellOrder();
    }
}

//+------------------------------------------------------------------+
//| Handle waiting state                                             |
//+------------------------------------------------------------------+
void HandleWaitingState(double price, double maLevel)
{
    // Wait for confirmation
    if(MathAbs(price - maLevel) < 0.0001)
    {
        LogMessage("Price at MA level, waiting...");
    }
}

//+------------------------------------------------------------------+
//| Handle in-trade state                                            |
//+------------------------------------------------------------------+
void HandleInTradeState(double price)
{
    // Check if we should close
    if(ShouldClosePosition(price))
    {
        ClosePositionBySymbol(_Symbol);
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
    request.volume = 0.1;
    request.type = ORDER_TYPE_BUY;
    request.price = SymbolInfoDouble(_Symbol, SYMBOL_ASK);
    request.sl = request.price - StopLossPoints * _Point;
    request.tp = request.price + StopLossPoints * 2 * _Point;
    request.deviation = 10;
    request.magic = MagicNumber;
    request.comment = CommentPrefix + "_BUY";
    
    if(!OrderSend(request, result))
    {
        LogMessage("Buy order failed: " + IntegerToString(result.retcode));
    }
}

//+------------------------------------------------------------------+
//| Open a sell order                                                |
//+------------------------------------------------------------------+
void OpenSellOrder()
{
    MqlTradeRequest request = {};
    MqlTradeResult result = {};
    
    request.action = TRADE_ACTION_DEAL;
    request.symbol = _Symbol;
    request.volume = 0.1;
    request.type = ORDER_TYPE_SELL;
    request.price = SymbolInfoDouble(_Symbol, SYMBOL_BID);
    request.sl = request.price + StopLossPoints * _Point;
    request.tp = request.price - StopLossPoints * 2 * _Point;
    request.deviation = 10;
    request.magic = MagicNumber;
    request.comment = CommentPrefix + "_SELL";
    
    if(!OrderSend(request, result))
    {
        LogMessage("Sell order failed: " + IntegerToString(result.retcode));
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
            ClosePositionByTicket(ticket);
        }
    }
}

//+------------------------------------------------------------------+
//| Close position by symbol                                         |
//+------------------------------------------------------------------+
void ClosePositionBySymbol(string symbol)
{
    if(PositionSelect(symbol))
    {
        ulong ticket = PositionGetInteger(POSITION_TICKET);
        ClosePositionByTicket(ticket);
    }
}

//+------------------------------------------------------------------+
//| Close position by ticket                                         |
//+------------------------------------------------------------------+
void ClosePositionByTicket(ulong ticket)
{
    MqlTradeRequest request = {};
    MqlTradeResult result = {};
    
    if(!PositionSelectByTicket(ticket))
        return;
    
    request.action = TRADE_ACTION_DEAL;
    request.position = ticket;
    request.symbol = PositionGetString(POSITION_SYMBOL);
    request.volume = PositionGetDouble(POSITION_VOLUME);
    
    long posType = PositionGetInteger(POSITION_TYPE);
    if(posType == POSITION_TYPE_BUY)
    {
        request.type = ORDER_TYPE_SELL;
        request.price = SymbolInfoDouble(_Symbol, SYMBOL_BID);
    }
    else
    {
        request.type = ORDER_TYPE_BUY;
        request.price = SymbolInfoDouble(_Symbol, SYMBOL_ASK);
    }
    
    request.deviation = 10;
    
    if(!OrderSend(request, result))
    {
        LogMessage("Close failed: " + IntegerToString(result.retcode));
    }
}

//+------------------------------------------------------------------+
//| Check if position should be closed                               |
//+------------------------------------------------------------------+
bool ShouldClosePosition(double currentPrice)
{
    // Simple logic: close if we have profit
    double openPrice = PositionGetDouble(POSITION_PRICE_OPEN);
    double profit = currentPrice - openPrice;
    
    while(profit < 0)
    {
        // Still in loss, don't close
        return false;
    }
    
    // In profit, check if we hit target
    if(profit > 50 * _Point)
    {
        return true;
    }
    
    return false;
}

//+------------------------------------------------------------------+
//| Trail all stop losses                                            |
//+------------------------------------------------------------------+
void TrailAllStops()
{
    int trailed = 0;
    
    for(int i = 0; i < PositionsTotal(); i++)
    {
        if(PositionSelectByTicket(PositionGetTicket(i)))
        {
            if(TrailSinglePosition())
            {
                trailed++;
            }
        }
    }
    
    if(trailed > 0)
    {
        LogMessage("Trailed " + IntegerToString(trailed) + " positions");
    }
}

//+------------------------------------------------------------------+
//| Trail single position                                            |
//+------------------------------------------------------------------+
bool TrailSinglePosition()
{
    double openPrice = PositionGetDouble(POSITION_PRICE_OPEN);
    double currentSL = PositionGetDouble(POSITION_SL);
    double currentPrice = PositionGetDouble(POSITION_PRICE_CURRENT);
    
    if(PositionGetInteger(POSITION_TYPE) == POSITION_TYPE_BUY)
    {
        double newSL = currentPrice - StopLossPoints * _Point;
        if(newSL > currentSL && newSL > openPrice)
        {
            return ModifyPositionSL(PositionGetTicket(i), newSL);
        }
    }
    
    return false;
}

//+------------------------------------------------------------------+
//| Modify position stop loss                                        |
//+------------------------------------------------------------------+
bool ModifyPositionSL(ulong ticket, double newSL)
{
    MqlTradeRequest request = {};
    MqlTradeResult result = {};
    
    request.action = TRADE_ACTION_SLTP;
    request.position = ticket;
    request.sl = newSL;
    
    return OrderSend(request, result);
}

//+------------------------------------------------------------------+
//| Count positions by type                                          |
//+------------------------------------------------------------------+
int CountPositionsByType(ENUM_POSITION_TYPE type)
{
    int count = 0;
    
    for(int i = 0; i < PositionsTotal(); i++)
    {
        if(PositionSelectByTicket(PositionGetTicket(i)))
        {
            if(PositionGetInteger(POSITION_TYPE) == type)
            {
                count++;
            }
        }
    }
    
    return count;
}

//+------------------------------------------------------------------+
//| Get account equity                                               |
//+------------------------------------------------------------------+
double GetAccountEquity()
{
    return AccountInfoDouble(ACCOUNT_EQUITY);
}

//+------------------------------------------------------------------+
//| Check daily profit                                               |
//+------------------------------------------------------------------+
bool CheckDailyProfit(double targetProfit)
{
    double dailyProfit = 0;
    
    // Historical data check would go here
    // For now just check current floating profit
    
    for(int i = 0; i < PositionsTotal(); i++)
    {
        if(PositionSelectByTicket(PositionGetTicket(i)))
        {
            dailyProfit += PositionGetDouble(POSITION_PROFIT);
        }
    }
    
    return dailyProfit >= targetProfit;
}
