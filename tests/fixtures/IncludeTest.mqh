//+------------------------------------------------------------------+
//|                                         IncludeTest.mqh            |
//|                                  Test include file for parser      |
//+------------------------------------------------------------------+

// Additional input variables for include testing
input int IncludeTestValue = 42;
input bool EnableFeature = false;

// Global variables in include file
int g_includeCounter = 0;
string g_lastMessage = "";

// Define in include
#define INCLUDE_VERSION "1.0"
#define MAX_RETRIES 5

// Enum in include
enum IncludeStatus
{
    STATUS_OK,
    STATUS_ERROR,
    STATUS_PENDING
};

// Helper function in include file
void LogInclude(string msg)
{
    g_includeCounter++;
    g_lastMessage = msg;
    Print("[IncludeTest] ", msg, " (count: ", g_includeCounter, ")");
}

// Calculate helper
double CalculateHelper(double base, double factor)
{
    if(factor <= 0)
        return base;
    
    return base * factor;
}

// Check status function
IncludeStatus CheckStatus()
{
    if(g_includeCounter > 100)
        return STATUS_ERROR;
    
    return STATUS_OK;
}

// Template class for include testing
class IncludeHelper
{
private:
    int m_value;
    
public:
    IncludeHelper(int val)
    {
        m_value = val;
    }
    
    int GetValue()
    {
        return m_value;
    }
    
    void SetValue(int newVal)
    {
        m_value = newVal;
    }
};
