"""
Graph Storage - Handles graph serialization and report generation.
"""

import json
from pathlib import Path
from typing import Dict, List, Any, Optional
from datetime import datetime


class GraphStorage:
    """Handles saving and loading knowledge graphs."""
    
    def __init__(self, output_dir: str = '.'):
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
    
    def save_graph(self, graph: Dict[str, Any], filename: str = 'graph.json') -> str:
        """Save graph to JSON file."""
        output_path = self.output_dir / filename
        
        # Prepare serializable graph
        serializable_graph = {
            'metadata': {
                'generated_at': datetime.now().isoformat(),
                'version': '1.0.0'
            },
            'statistics': graph.get('statistics', {}),
            'files': graph.get('files', {}),
            'symbols': graph.get('symbols', {}),
            'edges': graph.get('edges', []),
            'includes': graph.get('includes', {}),
            'dll_imports': graph.get('dll_imports', {})
        }
        
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(serializable_graph, f, indent=2, ensure_ascii=False)
        
        return str(output_path)
    
    def load_graph(self, filename: str = 'graph.json') -> Dict[str, Any]:
        """Load graph from JSON file."""
        input_path = self.output_dir / filename
        
        if not input_path.exists():
            raise FileNotFoundError(f'Graph file not found: {input_path}')
        
        with open(input_path, 'r', encoding='utf-8') as f:
            return json.load(f)
    
    def generate_report(self, graph: Dict[str, Any], filename: str = 'GRAPH_REPORT.md') -> str:
        """Generate human-readable Markdown report."""
        report_lines = [
            '# MQL5 Knowledge Graph Report',
            '',
            f'Generated: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}',
            '',
            '## Project Statistics',
            '',
        ]
        
        stats = graph.get('statistics', {})
        report_lines.extend([
            f'- **Total Symbols**: {stats.get("total_symbols", 0)}',
            f'- **Total Edges**: {stats.get("total_edges", 0)}',
            f'- **Total Files**: {stats.get("total_files", 0)}',
            '',
            '### Symbols by Type',
            '',
        ])
        
        by_type = stats.get('by_type', {})
        for symbol_type, count in sorted(by_type.items()):
            report_lines.append(f'- {symbol_type}: {count}')
        
        report_lines.extend([
            '',
            '## Files Overview',
            '',
        ])
        
        files = graph.get('files', {})
        for file_path, file_info in sorted(files.items()):
            report_lines.extend([
                f'### {file_info.get("name", file_path)}',
                '',
                f'- Path: `{file_path}`',
                f'- Lines: {file_info.get("lines", 0)}',
                f'- Size: {file_info.get("size", 0)} bytes',
                '',
            ])
            
            # List symbols in this file
            file_symbols = [s for s in graph.get('symbols', {}).values() 
                          if s.get('file') == file_path]
            if file_symbols:
                report_lines.append('**Symbols:**')
                report_lines.append('')
                by_symbol_type: Dict[str, List] = {}
                for sym in file_symbols:
                    sym_type = sym.get('type', 'unknown')
                    if sym_type not in by_symbol_type:
                        by_symbol_type[sym_type] = []
                    by_symbol_type[sym_type].append(sym)
                
                for sym_type, syms in sorted(by_symbol_type.items()):
                    report_lines.append(f'*{sym_type}s:*')
                    for sym in sorted(syms, key=lambda x: x.get('line_start', 0)):
                        report_lines.append(f'- `{sym.get("name", "unknown")}` (line {sym.get("line_start", "?")})')
                    report_lines.append('')
        
        # Dependencies section
        includes = graph.get('includes', {})
        if includes:
            report_lines.extend([
                '## File Dependencies',
                '',
            ])
            for file_path, deps in sorted(includes.items()):
                if deps:
                    report_lines.append(f'### {Path(file_path).name}')
                    report_lines.append('')
                    for dep in deps:
                        report_lines.append(f'- Includes: `{dep}`')
                    report_lines.append('')
        
        # DLL Imports section
        dll_imports = graph.get('dll_imports', {})
        has_dlls = any(dlls for dlls in dll_imports.values())
        if has_dlls:
            report_lines.extend([
                '## DLL Imports',
                '',
            ])
            for file_path, dlls in sorted(dll_imports.items()):
                if dlls:
                    report_lines.append(f'### {Path(file_path).name}')
                    report_lines.append('')
                    for dll in dlls:
                        report_lines.append(f'- ⚠️ Imports: `{dll}`')
                    report_lines.append('')
        
        # Event Handlers section
        event_handlers = [s for s in graph.get('symbols', {}).values() 
                        if s.get('is_event_handler')]
        if event_handlers:
            report_lines.extend([
                '## Event Handlers',
                '',
            ])
            for handler in sorted(event_handlers, key=lambda x: x.get('name', '')):
                report_lines.extend([
                    f'### {handler.get("name", "unknown")}',
                    '',
                    f'- File: `{handler.get("file", "unknown")}`',
                    f'- Line: {handler.get("line_start", "?")}',
                    '',
                ])
        
        # Call graph summary
        edges = graph.get('edges', [])
        call_edges = [e for e in edges if e.get('type') == 'CALLS']
        if call_edges:
            report_lines.extend([
                '## Call Graph Summary',
                '',
                f'Total function calls mapped: {len(call_edges)}',
                '',
                '### Top Called Functions',
                '',
            ])
            
            callee_counts: Dict[str, int] = {}
            for edge in call_edges:
                target = edge.get('target', '')
                callee_counts[target] = callee_counts.get(target, 0) + 1
            
            top_called = sorted(callee_counts.items(), key=lambda x: -x[1])[:20]
            for func_name, count in top_called:
                report_lines.append(f'- `{func_name}`: called {count} times')
            report_lines.append('')
        
        # Write report
        output_path = self.output_dir / filename
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write('\n'.join(report_lines))
        
        return str(output_path)
