"""
MQL5 Parser - Parses MQL5 files and extracts symbols and relationships.
Uses regex-based parsing with optimized patterns for MQL5 syntax.
"""

import re
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple, Any


# Control-flow keywords — must never appear as function calls or symbol names
_CONTROL_FLOW_KEYWORDS: Set[str] = {
    'if', 'else', 'for', 'while', 'switch', 'case', 'default', 'do',
    'break', 'continue', 'return', 'new', 'delete',
}

# All MQL5/C++ reserved words — must never become user-defined symbol names
_MQL5_KEYWORDS: Set[str] = _CONTROL_FLOW_KEYWORDS | {
    'class', 'struct', 'enum', 'public', 'private', 'protected',
    'static', 'virtual', 'extern', 'const',
    'void', 'int', 'double', 'float', 'long', 'bool',
    'string', 'datetime', 'color', 'ulong', 'uint', 'uchar', 'ushort',
    'short', 'char', 'true', 'false', 'null', 'NULL', 'this', 'input',
    'sinput', 'template', 'typename', 'sizeof', 'typeof', 'operator',
    'namespace', 'using', 'include', 'define', 'property', 'import',
    'ifdef', 'ifndef', 'endif', 'undef',
}

# MQL5 primitive types — variable declarations with these as the type should
# not be stored as symbols themselves.
_PRIMITIVE_TYPES: Set[str] = {
    'void', 'int', 'double', 'float', 'long', 'bool', 'string', 'datetime',
    'color', 'ulong', 'uint', 'uchar', 'ushort', 'short', 'char',
}

# Return types we explicitly recognise for MQL5 functions
_KNOWN_RETURN_TYPES: Set[str] = _PRIMITIVE_TYPES | {
    'ENUM_INIT_RETCODE', 'MqlRates', 'MqlTick', 'MqlTradeRequest',
    'MqlTradeResult', 'MqlTradeCheckResult',
}

# Pattern: a valid C/MQL5 identifier
_IDENT_RE = re.compile(r'^[A-Za-z_]\w*$')


def _is_valid_identifier(name: str) -> bool:
    """Return True iff name is a legal C/MQL5 identifier and not a reserved keyword.

    Used for user-defined symbol names (function names, variable names, etc.).
    All MQL5 keywords — including type keywords like 'int', 'void' — are excluded
    so they never become user symbol entries.
    """
    if not name or not _IDENT_RE.match(name):
        return False
    if name in _MQL5_KEYWORDS:
        return False
    # Reject pure numeric literals
    try:
        float(name)
        return False
    except ValueError:
        pass
    return True


class MQL5Parser:
    """Parser for MQL5 files that extracts symbols and relationships."""

    # MQL5 event handlers
    EVENT_HANDLERS = {
        'OnInit', 'OnDeinit', 'OnTick', 'OnTimer', 'OnTrade', 'OnTradeTransaction',
        'OnBookEvent', 'OnChartEvent', 'OnTester', 'OnTesterInit', 'OnTesterDeinit',
        'OnTesterPass', 'OnCalculate', 'OnStart'
    }

    # MQL5 trading functions
    TRADING_FUNCTIONS = {
        'OrderSend', 'OrderCheck', 'PositionSelect', 'PositionGetDouble',
        'PositionGetInteger', 'PositionGetString', 'OrderSelect', 'OrderGetDouble',
        'OrderGetInteger', 'OrderGetString', 'DealSelect', 'DealGetDouble',
        'DealGetInteger', 'DealGetString', 'HistorySelect', 'HistoryDealSelect',
        'HistoryOrderSelect', 'HistoryDealGetDouble', 'HistoryDealGetInteger',
        'HistoryOrderGetDouble', 'HistoryOrderGetInteger'
    }

    # Indicator functions
    INDICATOR_FUNCTIONS = {
        'iMA', 'iEMA', 'iSMA', 'iLMAs', 'iRSI', 'iMACD', 'iBands', 'iATR',
        'iCCI', 'iStochastic', 'iADX', 'iMomentum', 'iForce', 'iAO', 'iAC',
        'iBWMFI', 'iFractals', 'iAlligator', 'iGator', 'iEnvelopes', 'iStdDev',
        'iCustom', 'iVolumes', 'iOBV', 'iWPR', 'iVIDYA'
    }

    def __init__(self):
        self.symbols: Dict[str, Dict[str, Any]] = {}
        self.edges: List[Dict[str, Any]] = []
        self.files: Dict[str, Dict[str, Any]] = {}
        self.includes: Dict[str, List[str]] = {}
        self.dll_imports: Dict[str, List[str]] = {}

        # Regex patterns
        self._compile_patterns()

    def _compile_patterns(self):
        """Compile regex patterns for MQL5 parsing."""
        # Function definitions — captures (return_type, func_name, params)
        # Handles: [static] [virtual] [extern] ReturnType FuncName(params) [const] {
        self.pattern_function = re.compile(
            r'^\s*'
            r'(?:(?:static|virtual|extern)\s+)*'           # optional modifiers
            r'([A-Za-z_]\w*(?:\s*\*|\s*&)?)\s+'            # GROUP 1: return type
            r'([A-Za-z_]\w*)\s*'                            # GROUP 2: function name
            r'\(([^)]*)\)\s*'                               # GROUP 3: params
            r'(?:const\s*)?[;{]',
            re.MULTILINE
        )

        # Class definitions
        self.pattern_class = re.compile(
            r'^\s*class\s+(\w+)\s*(?::\s*(?:public|private|protected)\s+\w+)?\s*[{]',
            re.MULTILINE
        )

        # Struct definitions
        self.pattern_struct = re.compile(
            r'^\s*struct\s+(\w+)\s*[{]',
            re.MULTILINE
        )

        # Enum definitions
        self.pattern_enum = re.compile(
            r'^\s*enum\s+(\w+)\s*[{]',
            re.MULTILINE
        )

        # Enum members
        self.pattern_enum_member = re.compile(
            r'^\s*([A-Za-z_]\w*)\s*(?:=\s*[^,\n]+)?\s*,',
            re.MULTILINE
        )

        # Input variables: "input TYPE NAME;"
        self.pattern_input = re.compile(
            r'^\s*(?:sinput\s+|input\s+)'
            r'([A-Za-z_]\w*(?:\s*\[\s*\d+\s*\])?(?:\s*&)?)\s+'
            r'([A-Za-z_]\w*)\s*(?:=\s*[^;]+)?\s*;',
            re.MULTILINE
        )

        # Include statements
        self.pattern_include = re.compile(
            r'#include\s*[<"]([^>"]+)[>"]',
            re.MULTILINE
        )

        # DLL imports
        self.pattern_dll_import = re.compile(
            r'#import\s+"([^"]+)"',
            re.MULTILINE
        )

        # Function calls — only identifiers followed by '('
        # We'll filter keywords in _build_relationships
        self.pattern_function_call = re.compile(
            r'\b([A-Za-z_]\w*)\s*\(',
            re.MULTILINE
        )

        # Property statements
        self.pattern_property = re.compile(
            r'#property\s+(\w+)\s+(.+)',
            re.MULTILINE
        )

        # Define statements
        self.pattern_define = re.compile(
            r'#define\s+([A-Za-z_]\w*)(?:\s+(.+))?',
            re.MULTILINE
        )

        # Strip single-line comments
        self._re_line_comment = re.compile(r'//[^\n]*')
        # Strip block comments
        self._re_block_comment = re.compile(r'/\*.*?\*/', re.DOTALL)
        # Strip string literals
        self._re_string_literal = re.compile(r'"(?:[^"\\]|\\.)*"')

    def _strip_comments_and_strings(self, content: str) -> str:
        """Remove comments and string literals so we don't extract symbols from them."""
        content = self._re_block_comment.sub(lambda m: '\n' * m.group().count('\n'), content)
        content = self._re_line_comment.sub('', content)
        content = self._re_string_literal.sub('""', content)
        return content

    def parse_file(self, file_path: str) -> Dict[str, Any]:
        """Parse a single MQL5 file and extract symbols."""
        path = Path(file_path)
        if not path.exists():
            return {'error': f'File not found: {file_path}'}

        try:
            content = path.read_text(encoding='utf-8')
        except Exception as e:
            return {'error': f'Error reading file: {e}'}

        relative_path = str(path)

        # Store file info
        self.files[relative_path] = {
            'path': relative_path,
            'name': path.name,
            'size': len(content),
            'lines': content.count('\n') + 1
        }

        # Work on comment/string-stripped content for symbol extraction
        clean = self._strip_comments_and_strings(content)

        # Extract includes (from raw content — #include is not in strings)
        includes = self.pattern_include.findall(content)
        self.includes[relative_path] = includes

        # Extract DLL imports
        dll_imports = self.pattern_dll_import.findall(content)
        self.dll_imports[relative_path] = dll_imports

        # Extract symbols from clean content
        self._extract_functions(clean, relative_path)
        self._extract_classes(clean, relative_path)
        self._extract_structs(clean, relative_path)
        self._extract_enums(clean, relative_path)
        self._extract_inputs(clean, relative_path)
        self._extract_global_vars(clean, relative_path)
        self._extract_properties(clean, relative_path)
        self._extract_defines(clean, relative_path)

        # Build relationships
        self._build_relationships(clean, relative_path)

        return {
            'file': relative_path,
            'symbols_count': len([s for s in self.symbols.values() if s.get('file') == relative_path]),
            'includes': includes,
            'dll_imports': dll_imports
        }

    def _extract_functions(self, content: str, file_path: str):
        """Extract function definitions from content."""
        for match in self.pattern_function.finditer(content):
            return_type = match.group(1).strip().rstrip('*&').strip()
            func_name = match.group(2)
            params = match.group(3).strip() if match.group(3) else ''

            # Skip if func_name is a keyword or invalid
            if not _is_valid_identifier(func_name):
                continue
            # Skip if the "return type" is a control-flow keyword
            # (e.g., `for (` captured as return_type=for, func_name=something)
            if return_type in _CONTROL_FLOW_KEYWORDS:
                continue

            line_start = content[:match.start()].count('\n') + 1

            is_event_handler = func_name in self.EVENT_HANDLERS
            symbol_type = 'event_handler' if is_event_handler else 'function'

            # return_type is now captured directly from GROUP 1
            clean_return_type = return_type if return_type else 'void'

            self.symbols[func_name] = {
                'name': func_name,
                'type': symbol_type,
                'file': file_path,
                'line_start': line_start,
                'return_type': clean_return_type,
                'parameters': params,
                'is_event_handler': is_event_handler
            }

    def _extract_classes(self, content: str, file_path: str):
        """Extract class definitions from content."""
        for match in self.pattern_class.finditer(content):
            class_name = match.group(1)
            if not _is_valid_identifier(class_name):
                continue
            line_start = content[:match.start()].count('\n') + 1
            self.symbols[class_name] = {
                'name': class_name,
                'type': 'class',
                'file': file_path,
                'line_start': line_start
            }

    def _extract_structs(self, content: str, file_path: str):
        """Extract struct definitions from content."""
        for match in self.pattern_struct.finditer(content):
            struct_name = match.group(1)
            if not _is_valid_identifier(struct_name):
                continue
            line_start = content[:match.start()].count('\n') + 1
            self.symbols[struct_name] = {
                'name': struct_name,
                'type': 'struct',
                'file': file_path,
                'line_start': line_start
            }

    def _extract_enums(self, content: str, file_path: str):
        """Extract enum definitions and members from content."""
        for match in self.pattern_enum.finditer(content):
            enum_name = match.group(1)
            if not _is_valid_identifier(enum_name):
                continue
            line_start = content[:match.start()].count('\n') + 1
            self.symbols[enum_name] = {
                'name': enum_name,
                'type': 'enum',
                'file': file_path,
                'line_start': line_start
            }

            # Extract enum members within this enum block
            enum_block_start = match.end()
            enum_block_end = content.find('}', enum_block_start)
            if enum_block_end != -1:
                enum_block = content[enum_block_start:enum_block_end]
                for member_match in self.pattern_enum_member.finditer(enum_block):
                    member_name = member_match.group(1)
                    if not _is_valid_identifier(member_name):
                        continue
                    full_member_name = f"{enum_name}.{member_name}"
                    self.symbols[full_member_name] = {
                        'name': member_name,
                        'type': 'enum_member',
                        'parent': enum_name,
                        'file': file_path,
                        'line_start': line_start + enum_block[:member_match.start()].count('\n')
                    }

    def _extract_inputs(self, content: str, file_path: str):
        """Extract input variables from content."""
        for match in self.pattern_input.finditer(content):
            var_type = match.group(1).strip() if match.group(1) else 'unknown'
            var_name = match.group(2).strip() if match.group(2) else ''
            if not var_name or not _is_valid_identifier(var_name):
                continue
            line_start = content[:match.start()].count('\n') + 1
            self.symbols[var_name] = {
                'name': var_name,
                'type': 'input_variable',
                'file': file_path,
                'line_start': line_start,
                'data_type': var_type
            }

    def _extract_global_vars(self, content: str, file_path: str):
        """Extract global variables from content.

        Only recognises declarations at the top level that look like:
            [static] [extern] KnownType varName;
        where KnownType is a recognised primitive or ENUM_/MQL type name.
        This avoids picking up arbitrary tokens as variable names.
        """
        # Pattern: optional modifiers + known-looking type + identifier + semicolon
        # We restrict to lines that are clearly declarations (not function bodies)
        pattern = re.compile(
            r'^(?:static\s+|extern\s+)*'
            r'([A-Za-z_]\w*(?:\s*\[\s*\d*\s*\])?)\s+'   # type (group 1)
            r'([A-Za-z_]\w*)\s*'                           # name (group 2)
            r'(?:=\s*[^;]*)?\s*;',                        # optional initialiser
            re.MULTILINE
        )
        # Known type prefixes that indicate a real declaration
        _type_indicators = _PRIMITIVE_TYPES | {
            'MqlRates', 'MqlTick', 'MqlTradeRequest', 'MqlTradeResult',
            'MqlTradeCheckResult', 'MqlBookInfo', 'MqlDateTime', 'ENUM_',
        }

        for match in pattern.finditer(content):
            var_type = match.group(1).strip()
            var_name = match.group(2).strip()

            # Only accept if type is a primitive or starts with known prefix
            is_known_type = (
                var_type in _PRIMITIVE_TYPES
                or var_type.startswith('ENUM_')
                or var_type.startswith('Mql')
            )
            if not is_known_type:
                continue
            if not _is_valid_identifier(var_name):
                continue
            if var_name in self.symbols:
                continue

            line_start = content[:match.start()].count('\n') + 1
            self.symbols[var_name] = {
                'name': var_name,
                'type': 'global_variable',
                'file': file_path,
                'line_start': line_start,
                'data_type': var_type
            }

    def _extract_properties(self, content: str, file_path: str):
        """Extract #property statements."""
        for match in self.pattern_property.finditer(content):
            prop_type = match.group(1)
            prop_value = match.group(2).strip()
            line_start = content[:match.start()].count('\n') + 1
            prop_name = f"property_{prop_type}"
            self.symbols[prop_name] = {
                'name': prop_name,
                'type': 'property',
                'file': file_path,
                'line_start': line_start,
                'property_type': prop_type,
                'value': prop_value
            }

    def _extract_defines(self, content: str, file_path: str):
        """Extract #define statements."""
        for match in self.pattern_define.finditer(content):
            define_name = match.group(1)
            define_value = match.group(2).strip() if match.group(2) else ''
            if not _is_valid_identifier(define_name):
                continue
            line_start = content[:match.start()].count('\n') + 1
            self.symbols[define_name] = {
                'name': define_name,
                'type': 'define',
                'file': file_path,
                'line_start': line_start,
                'value': define_value
            }

    def _build_relationships(self, content: str, file_path: str):
        """Build relationships between symbols."""
        # Add DEFINED_IN edges for all symbols in this file
        for symbol_name, symbol_info in self.symbols.items():
            if symbol_info.get('file') == file_path:
                self.edges.append({
                    'source': symbol_name,
                    'target': file_path,
                    'type': 'DEFINED_IN'
                })

        # Add INCLUDES edges
        for include in self.includes.get(file_path, []):
            self.edges.append({
                'source': file_path,
                'target': include,
                'type': 'INCLUDES'
            })

        # Add DEPENDS_ON edges for DLL imports
        for dll in self.dll_imports.get(file_path, []):
            self.edges.append({
                'source': file_path,
                'target': dll,
                'type': 'DEPENDS_ON'
            })

        # Find function calls (CALLS edges) — only between known user-defined symbols
        functions_in_file = [
            name for name, info in self.symbols.items()
            if info.get('file') == file_path and info.get('type') in ('function', 'event_handler')
        ]

        for func_name in functions_in_file:
            func_info = self.symbols[func_name]
            func_start_line = func_info.get('line_start', 0)
            lines = content.split('\n')

            start_idx = sum(len(l) + 1 for l in lines[:func_start_line])
            end_idx = min(start_idx + 5000, len(content))
            func_body = content[start_idx:end_idx]

            seen_calls: Set[str] = set()
            for call_match in self.pattern_function_call.finditer(func_body):
                called_func = call_match.group(1)

                # CRITICAL: Skip control-flow keywords (if/for/while/switch/etc.)
                if called_func in _MQL5_KEYWORDS:
                    continue
                # Also skip pure numeric literals (safety net)
                try:
                    float(called_func)
                    continue
                except ValueError:
                    pass
                # Only create CALLS edges to user-defined symbols
                if called_func in self.symbols and called_func != func_name:
                    if called_func not in seen_calls:
                        seen_calls.add(called_func)
                        self.edges.append({
                            'source': func_name,
                            'target': called_func,
                            'type': 'CALLS'
                        })

    def get_graph(self) -> Dict[str, Any]:
        """Return the complete graph structure."""
        return {
            'symbols': self.symbols,
            'edges': self.edges,
            'files': self.files,
            'includes': self.includes,
            'dll_imports': self.dll_imports,
            'statistics': {
                'total_symbols': len(self.symbols),
                'total_edges': len(self.edges),
                'total_files': len(self.files),
                'by_type': self._count_by_type()
            }
        }

    def _count_by_type(self) -> Dict[str, int]:
        """Count symbols by type."""
        counts: Dict[str, int] = {}
        for symbol in self.symbols.values():
            symbol_type = symbol.get('type', 'unknown')
            counts[symbol_type] = counts.get(symbol_type, 0) + 1
        return counts

    def reset(self):
        """Reset the parser state."""
        self.symbols.clear()
        self.edges.clear()
        self.files.clear()
        self.includes.clear()
        self.dll_imports.clear()
