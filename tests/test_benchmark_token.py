"""Token-efficiency benchmark test: run and record real measurements."""

import json

from mql5_kg.benchmarks.token_efficiency import benchmark_context, run_benchmarks

from conftest import FIXTURES


def _synthetic_repo(tmp_path, files: int = 40, functions_per_file: int = 90) -> str:
    """Generate a synthetic multi-file MQL5 project (~450 KB, representative)."""

    for index in range(files):
        lines = [f'#property copyright "Synth {index}"']
        lines.append(f"input double RiskPercent{index} = 1.5;")
        for function_index in range(functions_per_file):
            name = f"Synth{index}Func{function_index}"
            lines.append(f"double {name}(double x) {{")
            lines.append(f"    if(x > {function_index}) return x * 2.0;")
            lines.append(f"    double local = x + {function_index};")
            lines.append(f"    return Helper{index}(local);")
            lines.append("}")
        lines.append("void OnTick() { Synth%dFunc0(1.0); }" % index)
        (tmp_path / f"module_{index:03d}.mq5").write_text(
            "\n".join(lines), encoding="utf-8"
        )
    return str(tmp_path)


# Representative project (~450 KB) needs a larger analysis work budget than the
# conservative default; the benchmark measures, so it is allowed to raise it.
_MAX_WORK = 5_000_000


def test_benchmark_records_measurements(tmp_path):
    root = _synthetic_repo(tmp_path)
    result = benchmark_context(root, "Synth0Func0", context_units=60, max_work=_MAX_WORK)
    measurements = result["measurements"]
    assert measurements["whole_repository"]["bytes"] > 0
    assert measurements["whole_repository"]["estimated_tokens"] > 0
    assert measurements["graph_context_package"]["estimated_tokens"] > 0
    assert result["latency_seconds"]["index"] >= 0
    assert result["latency_seconds"]["context_package"] >= 0
    assert result["graph_summary"]["nodes"] > 0


def test_graph_context_is_dramatically_smaller_than_repo(tmp_path):
    root = _synthetic_repo(tmp_path)
    result = benchmark_context(root, "Synth0Func0", context_units=60, max_work=_MAX_WORK)
    measurements = result["measurements"]
    repo_tokens = measurements["whole_repository"]["estimated_tokens"]
    graph_tokens = measurements["graph_context_package"]["estimated_tokens"]
    # Measured claim: a fixed-budget structural context package is dramatically
    # smaller than the raw source of a representative multi-file codebase.
    assert graph_tokens < repo_tokens / 10, (
        f"graph context ({graph_tokens}) should be <10% of repo ({repo_tokens})"
    )


def test_benchmark_serializes(tmp_path):
    root = _synthetic_repo(tmp_path, files=3, functions_per_file=5)
    payload = run_benchmarks(root, ["OnTick"], str(tmp_path / "bench.json"))
    assert payload["symbols"][0]["symbol"] == "OnTick"
    json.loads((tmp_path / "bench.json").read_text(encoding="utf-8"))
