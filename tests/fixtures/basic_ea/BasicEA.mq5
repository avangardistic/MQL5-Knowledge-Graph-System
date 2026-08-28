#property strict
#include "Risk.mqh"

CRiskManager risk_manager;

int OnInit()
  {
   EventSetTimer(10);
   return(INIT_SUCCEEDED);
  }

void OnTick()
  {
   const double lots = risk_manager.CalculateLots(1.0);
   SubmitOrder(lots);
  }

bool SubmitOrder(const double lots)
  {
   MqlTradeRequest request = {};
   MqlTradeResult result = {};
   return(OrderSend(request, result));
  }

void OnTradeTransaction(const MqlTradeTransaction &trans,
                        const MqlTradeRequest &request,
                        const MqlTradeResult &result)
  {
   Print(trans.type);
  }

void OnTimer()
  {
   // The string must not become a fake call: "GhostCall()"
   Print("timer");
  }
