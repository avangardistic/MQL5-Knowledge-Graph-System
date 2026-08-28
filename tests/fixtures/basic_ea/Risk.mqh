#pragma once

class CRiskManager
  {
public:
   double CalculateLots(const double risk)
     {
      return(NormalizeDouble(risk * 0.10, 2));
     }
  };
