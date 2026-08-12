//+------------------------------------------------------------------+
//|                                         RiskManager.mqh          |
//|                                  Risk Management Library         |
//+------------------------------------------------------------------+

input double MaxRiskPercent = 2.0;
input int MaxDailyLoss = 500;
input int MaxOpenPositions = 5;

double dailyStartBalance = 0;
int todayTrades = 0;

//+------------------------------------------------------------------+
//| Calculate lot size based on risk                                 |
//+------------------------------------------------------------------+
double CalculateLotSize(double stopLossPoints)
{
    double balance = AccountInfoDouble(ACCOUNT_BALANCE);
    double riskAmount = balance * (MaxRiskPercent / 100.0);
    double tickValue = SymbolInfoDouble(_Symbol, SYMBOL_TRADE_TICK_VALUE);
    
    if(stopLossPoints <= 0 || tickValue == 0)
        return 0;
    
    double lots = riskAmount / (stopLossPoints * tickValue);
    
    double minLot = SymbolInfoDouble(_Symbol, SYMBOL_VOLUME_MIN);
    double maxLot = SymbolInfoDouble(_Symbol, SYMBOL_VOLUME_MAX);
    double step = SymbolInfoDouble(_Symbol, SYMBOL_VOLUME_STEP);
    
    lots = MathFloor(lots / step) * step;
    lots = MathMax(minLot, MathMin(maxLot, lots));
    
    return lots;
}

//+------------------------------------------------------------------+
//| Check if we can open a new position                              |
//+------------------------------------------------------------------+
bool CanOpenPosition()
{
    if(PositionsTotal() >= MaxOpenPositions)
        return false;
    
    if(IsDailyLimitReached())
        return false;
    
    return true;
}

//+------------------------------------------------------------------+
//| Check if daily loss limit is reached                             |
//+------------------------------------------------------------------+
bool IsDailyLimitReached()
{
    MqlDateTime currentTime;
    TimeToStruct(TimeCurrent(), currentTime);
    
    MqlDateTime todayStart = currentTime;
    todayStart.hour = 0;
    todayStart.min = 0;
    todayStart.sec = 0;
    
    datetime todayStartDT = StructToTime(todayStart);
    
    double totalProfit = 0;
    for(int i = HistorySelect(todayStartDT, TimeCurrent()); i > 0; i--)
    {
        if(HistoryDealGetTicket(i) > 0)
        {
            totalProfit += HistoryDealGetDouble(i, DEAL_PROFIT);
        }
    }
    
    double currentBalance = AccountInfoDouble(ACCOUNT_BALANCE);
    
    if(dailyStartBalance == 0)
        dailyStartBalance = currentBalance;
    
    double dailyChange = currentBalance - dailyStartBalance;
    
    if(dailyChange < -MaxDailyLoss)
    {
        Print("Daily loss limit reached: ", dailyChange);
        return true;
    }
    
    return false;
}

//+------------------------------------------------------------------+
//| Reset daily statistics                                           |
//+------------------------------------------------------------------+
void ResetDailyStats()
{
    dailyStartBalance = AccountInfoDouble(ACCOUNT_BALANCE);
    todayTrades = 0;
}

//+------------------------------------------------------------------+
//| Get current risk percentage                                      |
//+------------------------------------------------------------------+
double GetCurrentRiskPercent()
{
    double balance = AccountInfoDouble(ACCOUNT_BALANCE);
    if(balance == 0)
        return 0;
    
    double equity = AccountInfoDouble(ACCOUNT_EQUITY);
    double floatingPL = equity - balance;
    
    return (floatingPL / balance) * 100.0;
}

//+------------------------------------------------------------------+
//| Check if account is in danger zone                               |
//+------------------------------------------------------------------+
bool IsAccountInDanger(double thresholdPercent)
{
    double currentRisk = GetCurrentRiskPercent();
    return currentRisk < -thresholdPercent;
}
