#import "kernel32.dll"
int    MessageBoxW(int hWnd, string lpText, string lpCaption, int uType);
int    GetTickCount();
#import

#import "user32.dll"
int    SendMessageW(int hWnd, int Msg, int wParam, int lParam);
#import

void UsesImports()
{
    int tick = GetTickCount();
    // MessageBoxW must be an imported_symbol node, not a call to user code
    string label = "GetTickCount()";
    Print(label);
}
