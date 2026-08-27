//+------------------------------------------------------------------+
//| control_flow_test.mq5 - Tests that if/for/while/switch are NOT  |
//| extracted as function calls.                                     |
//+------------------------------------------------------------------+
#property copyright "Test"
#property version   "1.0"

int OnInit()
{
    // if should NOT become a CALLS edge
    if(true) { }

    // for should NOT become a CALLS edge
    for(int i = 0; i < 10; i++) { }

    // while should NOT become a CALLS edge
    while(false) { }

    // switch should NOT become a CALLS edge
    int x = 1;
    switch(x)
    {
        case 1:
            break;
        default:
            break;
    }

    return(INIT_SUCCEEDED);
}

void OnTick() { }

double CalculateValue(double input)
{
    if(input > 0)
        return input * 2.0;
    return 0.0;
}
