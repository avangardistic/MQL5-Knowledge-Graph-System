// Adversarial fixture: broken and partially edited source must not crash the parser.
#property copyright "Adversarial"
// Unclosed block comment below:
/* this comment never closes
void NeverSeen() { }

// Code-looking strings and comments must never create relationships
string s1 = "OrderSend(foo); ClosePosition(1);";
string s2 = 'OnTick()';
// CloseAllPositions();
/* OrderSend(bar); */

// Missing semicolon
int g_broken = 1
double g_after = 2.0;

// Unclosed brace
void BrokenFunction(int a)
{
    if(a > 0)
    {
        return;
    // no closing brace for the if block

// Partially edited declaration
double PartiallyEdited(
    return 0.0;
}

// Duplicate names across scopes
double Compute(double x) { return x * 2.0; }
double Compute(double x, double y) { return x + y; }

// Misleading nested scope with same variable names
void ScopeTrap()
{
    int value = 1;
    {
        int value = 2;
        Print(value);
    }
    Print(value);
}
