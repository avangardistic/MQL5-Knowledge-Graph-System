//+------------------------------------------------------------------+
//| return_type_test.mq5 - Tests return type detection              |
//+------------------------------------------------------------------+
#property copyright "Test"

double CalculateLotSize(double risk, double sl)
{
    if(sl <= 0) return 0.01;
    return NormalizeDouble(risk / sl, 2);
}

int CountPositions()
{
    return PositionsTotal();
}

bool IsMarketOpen()
{
    return (bool)SymbolInfoInteger(_Symbol, SYMBOL_TRADE_MODE);
}

string GetStatusString()
{
    return "OK";
}

void DoNothing() { }

int OnInit() { return(INIT_SUCCEEDED); }
void OnDeinit(const int reason) { }
void OnTick() { }
