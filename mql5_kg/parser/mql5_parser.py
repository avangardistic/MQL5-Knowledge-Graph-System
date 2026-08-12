"""
MQL5 Parser - Parses MQL5 files and extracts symbols and relationships.
Uses regex-based parsing with optimized patterns for MQL5 syntax.
"""

import re
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple, Any


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
        # Function definitions (including return types)
        self.pattern_function = re.compile(
            r'^\s*(?:static\s+)?(?:virtual\s+)?(?:extern\s+)?'
            r'(?:\w+(?:\s*\*)?\s+|\w+\s*&\s*)'  # return type
            r'(\w+)\s*\(([^)]*)\)\s*(?:const)?\s*[;{]',
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
            r'^\s*(\w+)\s*(?:=\s*[^,]+)?\s*,',
            re.MULTILINE
        )
        
        # Input variables
        self.pattern_input = re.compile(
            r'^\s*input\s+(\w+(?:\s*\[\s*\d+\s*\])?(?:\s*&)?)(?:\s+(\w+))?\s*;',
            re.MULTILINE
        )
        
        # Global variables
        self.pattern_global_var = re.compile(
            r'^\s*(?:static\s+)?(?:extern\s+)?(\w+(?:\s*\[\s*\d+\s*\])?(?:\s*&)?)(?:\s+(\w+))?\s*;',
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
        
        # Function calls (for relationship mapping)
        self.pattern_function_call = re.compile(
            r'\b(\w+)\s*\(',
            re.MULTILINE
        )
        
        # Property statements
        self.pattern_property = re.compile(
            r'#property\s+(\w+)\s+(.+)',
            re.MULTILINE
        )
        
        # Define statements
        self.pattern_define = re.compile(
            r'#define\s+(\w+)(?:\s+(.+))?',
            re.MULTILINE
        )
    
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
        
        # Extract includes
        includes = self.pattern_include.findall(content)
        self.includes[relative_path] = includes
        
        # Extract DLL imports
        dll_imports = self.pattern_dll_import.findall(content)
        self.dll_imports[relative_path] = dll_imports
        
        # Extract symbols
        self._extract_functions(content, relative_path)
        self._extract_classes(content, relative_path)
        self._extract_structs(content, relative_path)
        self._extract_enums(content, relative_path)
        self._extract_inputs(content, relative_path)
        self._extract_global_vars(content, relative_path)
        self._extract_properties(content, relative_path)
        self._extract_defines(content, relative_path)
        
        # Build relationships
        self._build_relationships(content, relative_path)
        
        return {
            'file': relative_path,
            'symbols_count': len([s for s in self.symbols.values() if s.get('file') == relative_path]),
            'includes': includes,
            'dll_imports': dll_imports
        }
    
    def _extract_functions(self, content: str, file_path: str):
        """Extract function definitions from content."""
        for match in self.pattern_function.finditer(content):
            func_name = match.group(1)
            params = match.group(2).strip() if match.group(2) else ''
            
            # Get line number
            line_start = content[:match.start()].count('\n') + 1
            
            # Determine if it's an event handler
            is_event_handler = func_name in self.EVENT_HANDLERS
            symbol_type = 'event_handler' if is_event_handler else 'function'
            
            # Extract return type (simplified)
            before_name = content[max(0, match.start()-50):match.start()]
            return_type_match = re.search(r'(\w+(?:\s*\*)?)\s*$', before_name)
            return_type = return_type_match.group(1).strip() if return_type_match else 'void'
            
            self.symbols[func_name] = {
                'name': func_name,
                'type': symbol_type,
                'file': file_path,
                'line_start': line_start,
                'return_type': return_type,
                'parameters': params,
                'is_event_handler': is_event_handler
            }
    
    def _extract_classes(self, content: str, file_path: str):
        """Extract class definitions from content."""
        for match in self.pattern_class.finditer(content):
            class_name = match.group(1)
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
                    if member_name not in ['if', 'else', 'for', 'while', 'switch']:  # Filter keywords
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
            var_name = match.group(2).strip() if match.group(2) else f'input_{len(self.symbols)}'
            line_start = content[:match.start()].count('\n') + 1
            
            self.symbols[var_name] = {
                'name': var_name,
                'type': 'input_variable',
                'file': file_path,
                'line_start': line_start,
                'data_type': var_type
            }
    
    def _extract_global_vars(self, content: str, file_path: str):
        """Extract global variables from content."""
        lines = content.split('\n')
        for i, line in enumerate(lines, 1):
            line = line.strip()
            # Skip if inside function or class
            if line.startswith(('input ', 'enum ', 'struct ', 'class ', '//', '#', '*')):
                continue
            # Match simple global variable declarations
            match = re.match(r'^(?:static\s+)?(?:extern\s+)?(\w+)\s+(\w+)\s*;', line)
            if match:
                var_type = match.group(1)
                var_name = match.group(2)
                if var_name not in self.symbols:
                    self.symbols[var_name] = {
                        'name': var_name,
                        'type': 'global_variable',
                        'file': file_path,
                        'line_start': i,
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
        
        # Find function calls (CALLS edges)
        functions_in_file = [name for name, info in self.symbols.items() 
                           if info.get('file') == file_path and info.get('type') in ('function', 'event_handler')]
        
        for func_name in functions_in_file:
            func_info = self.symbols[func_name]
            # Get function body (simplified - just look after the definition)
            func_start_line = func_info.get('line_start', 0)
            lines = content.split('\n')
            
            # Simple approach: look at lines after function definition
            # In a more sophisticated parser, we'd track braces
            start_idx = sum(len(l) + 1 for l in lines[:func_start_line])
            end_idx = min(start_idx + 5000, len(content))  # Limit search scope
            func_body = content[start_idx:end_idx]
            
            for call_match in self.pattern_function_call.finditer(func_body):
                called_func = call_match.group(1)
                if called_func in self.symbols and called_func != func_name:
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
