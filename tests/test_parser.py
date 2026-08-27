"""
Tests for the MQL5 parser — covers symbol extraction, return types, and false CALLS detection.
"""

import pytest
from pathlib import Path
from mql5_kg.parser import MQL5Parser

FIXTURES = Path(__file__).parent / "fixtures"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def parse_fixture(name: str) -> MQL5Parser:
    p = MQL5Parser()
    p.parse_file(str(FIXTURES / name))
    return p


def calls_targets(parser: MQL5Parser, source: str):
    """Return the set of targets called by *source* in CALLS edges."""
    return {e['target'] for e in parser.edges
            if e['type'] == 'CALLS' and e['source'] == source}


# ---------------------------------------------------------------------------
# Control-flow keyword tests (Phase 4)
# ---------------------------------------------------------------------------

class TestFalseCallsEdges:
    """CALLS edges must never be created for control-flow keywords."""

    KEYWORDS = {'if', 'for', 'while', 'switch', 'else', 'case', 'default', 'do'}

    def test_no_keyword_in_any_calls_target(self):
        p = parse_fixture("control_flow_test.mq5")
        targets = {e['target'] for e in p.edges if e['type'] == 'CALLS'}
        bad = targets & self.KEYWORDS
        assert not bad, f"Control-flow keywords found as CALLS targets: {bad}"

    def test_no_keyword_in_audit_fixture(self):
        p = parse_fixture("audit_test.mq5")
        targets = {e['target'] for e in p.edges if e['type'] == 'CALLS'}
        bad = targets & self.KEYWORDS
        assert not bad, f"Keywords in audit fixture CALLS: {bad}"

    def test_no_keyword_in_realistic_ea(self):
        p = parse_fixture("realistic_ea.mq5")
        targets = {e['target'] for e in p.edges if e['type'] == 'CALLS'}
        bad = targets & self.KEYWORDS
        assert not bad, f"Keywords in realistic_ea CALLS: {bad}"


# ---------------------------------------------------------------------------
# Symbol extraction tests (Phase 5)
# ---------------------------------------------------------------------------

class TestSymbolExtraction:
    """Numeric/boolean literals and keyword tokens must NOT be symbols."""

    FORBIDDEN_SYMBOLS = {'0', '1', '2', 'false', 'true', 'null', 'NULL',
                         'lots', 'if', 'for', 'while', 'switch'}

    def test_no_literal_symbols_in_audit(self):
        p = parse_fixture("audit_test.mq5")
        bad = set(p.symbols.keys()) & self.FORBIDDEN_SYMBOLS
        assert not bad, f"Forbidden symbols found: {bad}"

    def test_no_literal_symbols_in_control_flow(self):
        p = parse_fixture("control_flow_test.mq5")
        bad = set(p.symbols.keys()) & self.FORBIDDEN_SYMBOLS
        assert not bad, f"Forbidden symbols: {bad}"

    def test_event_handlers_extracted(self):
        p = parse_fixture("audit_test.mq5")
        assert 'OnInit' in p.symbols
        assert 'OnTick' in p.symbols
        assert 'OnDeinit' in p.symbols

    def test_event_handler_type(self):
        p = parse_fixture("audit_test.mq5")
        assert p.symbols['OnInit']['type'] == 'event_handler'
        assert p.symbols['OnTick']['type'] == 'event_handler'

    def test_user_functions_extracted(self):
        p = parse_fixture("audit_test.mq5")
        assert 'OpenBuyOrder' in p.symbols
        assert 'CloseAllPositions' in p.symbols
        assert 'GetCurrentState' in p.symbols

    def test_enum_extracted(self):
        p = parse_fixture("audit_test.mq5")
        assert 'TradingState' in p.symbols
        assert p.symbols['TradingState']['type'] == 'enum'

    def test_struct_extracted(self):
        p = parse_fixture("audit_test.mq5")
        assert 'TradeResult' in p.symbols
        assert p.symbols['TradeResult']['type'] == 'struct'

    def test_class_extracted(self):
        p = parse_fixture("audit_test.mq5")
        assert 'RiskManager' in p.symbols
        assert p.symbols['RiskManager']['type'] == 'class'

    def test_input_variables_extracted(self):
        p = parse_fixture("audit_test.mq5")
        assert 'RiskPercent' in p.symbols
        assert p.symbols['RiskPercent']['type'] == 'input_variable'

    def test_defines_extracted(self):
        p = parse_fixture("audit_test.mq5")
        assert 'MAX_POSITIONS' in p.symbols
        assert p.symbols['MAX_POSITIONS']['type'] == 'define'

    def test_no_symbol_from_comments(self):
        """Tokens appearing only in comments must not become symbols."""
        p = MQL5Parser()
        # Create a minimal MQL5 snippet where "FakeFunc" is only in a comment
        import tempfile, os
        content = "// FakeFunc is mentioned here but not defined\nvoid OnTick() { }\n"
        with tempfile.NamedTemporaryFile(mode='w', suffix='.mq5', delete=False, encoding='utf-8') as f:
            f.write(content)
            fname = f.name
        try:
            p.parse_file(fname)
        finally:
            os.unlink(fname)
        assert 'FakeFunc' not in p.symbols


# ---------------------------------------------------------------------------
# Return type detection tests (Phase 6)
# ---------------------------------------------------------------------------

class TestReturnTypeDetection:
    def test_double_return_type(self):
        p = parse_fixture("return_type_test.mq5")
        assert 'CalculateLotSize' in p.symbols
        assert p.symbols['CalculateLotSize']['return_type'] == 'double', \
            f"Expected 'double', got {p.symbols['CalculateLotSize']['return_type']!r}"

    def test_int_return_type(self):
        p = parse_fixture("return_type_test.mq5")
        assert 'CountPositions' in p.symbols
        assert p.symbols['CountPositions']['return_type'] == 'int'

    def test_bool_return_type(self):
        p = parse_fixture("return_type_test.mq5")
        assert 'IsMarketOpen' in p.symbols
        assert p.symbols['IsMarketOpen']['return_type'] == 'bool'

    def test_string_return_type(self):
        p = parse_fixture("return_type_test.mq5")
        assert 'GetStatusString' in p.symbols
        assert p.symbols['GetStatusString']['return_type'] == 'string'

    def test_void_return_type(self):
        p = parse_fixture("return_type_test.mq5")
        assert 'DoNothing' in p.symbols
        assert p.symbols['DoNothing']['return_type'] == 'void'

    def test_audit_fixture_return_types(self):
        p = parse_fixture("audit_test.mq5")
        # ShouldClosePosition returns bool
        if 'ShouldClosePosition' in p.symbols:
            assert p.symbols['ShouldClosePosition']['return_type'] == 'bool'
        # GetAccountEquity returns double
        if 'GetAccountEquity' in p.symbols:
            assert p.symbols['GetAccountEquity']['return_type'] == 'double'


# ---------------------------------------------------------------------------
# Graph integrity tests (Phase 11)
# ---------------------------------------------------------------------------

class TestGraphIntegrity:
    def test_defined_in_edges_reference_existing_files(self):
        p = parse_fixture("audit_test.mq5")
        file_keys = set(p.files.keys())
        for edge in p.edges:
            if edge['type'] == 'DEFINED_IN':
                assert edge['target'] in file_keys, \
                    f"DEFINED_IN target {edge['target']!r} not in files"

    def test_calls_source_and_target_are_symbols(self):
        p = parse_fixture("audit_test.mq5")
        sym_keys = set(p.symbols.keys())
        for edge in p.edges:
            if edge['type'] == 'CALLS':
                assert edge['source'] in sym_keys, \
                    f"CALLS source {edge['source']!r} not in symbols"
                assert edge['target'] in sym_keys, \
                    f"CALLS target {edge['target']!r} not in symbols"

    def test_realistic_ea_calls_edges_are_user_functions(self):
        p = parse_fixture("realistic_ea.mq5")
        sym_keys = set(p.symbols.keys())
        for edge in p.edges:
            if edge['type'] == 'CALLS':
                assert edge['target'] in sym_keys

    def test_no_numeric_node_names(self):
        p = parse_fixture("audit_test.mq5")
        for name in p.symbols:
            assert not name.replace('.', '', 1).isdigit(), \
                f"Numeric node name found: {name!r}"

    def test_reset_clears_state(self):
        p = parse_fixture("audit_test.mq5")
        assert len(p.symbols) > 0
        p.reset()
        assert len(p.symbols) == 0
        assert len(p.edges) == 0
        assert len(p.files) == 0
