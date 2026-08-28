"""Explicit external Graphify adapter for disposable semantic overlays."""

from __future__ import annotations

import json
import os
from pathlib import Path, PurePosixPath, PureWindowsPath
import re
import shutil
import subprocess
from typing import Any, Callable, Mapping
from urllib.parse import urlparse
import uuid
import ipaddress

from .corpus import ReferenceCorpus
from .models import (
    CONTRACT_VERSION,
    GraphifyRequest,
    ReferenceError,
    atomic_write_json,
    canonical_json_bytes,
    confined_relative_path,
    hash_bytes,
    hash_file,
    load_json,
    write_json,
)


_SUPPORTED_BACKENDS = {"gemini", "kimi", "claude", "openai", "deepseek", "ollama"}
_VERSION = re.compile(r"\bgraphify\s+(\d+)\.(\d+)\.(\d+)(?:[-+][^\s]+)?\b", re.IGNORECASE)
_FINGERPRINT = re.compile(r"^[0-9a-f]{64}$")
_MAX_OVERLAY_FILES = 50_000
_MAX_OVERLAY_BYTES = 2 * 1024 * 1024 * 1024
_MAX_GRAPH_BYTES = 512 * 1024 * 1024
_MAX_GRAPH_NODES = 50_000
_MAX_GRAPH_EDGES = 250_000
_RUNTIME_ENVIRONMENT = frozenset(
    {
        "COMSPEC",
        "HOME",
        "HOMEDRIVE",
        "HOMEPATH",
        "LANG",
        "LC_ALL",
        "LC_CTYPE",
        "PATH",
        "PATHEXT",
        "REQUESTS_CA_BUNDLE",
        "SSL_CERT_DIR",
        "SSL_CERT_FILE",
        "SYSTEMROOT",
        "TEMP",
        "TMP",
        "TMPDIR",
        "TZ",
        "USERPROFILE",
        "WINDIR",
    }
)
_BACKEND_ENVIRONMENT = {
    "claude": frozenset(
        {
            "ANTHROPIC_API_KEY",
            "ANTHROPIC_BASE_URL",
            "ANTHROPIC_MODEL",
            "GRAPHIFY_CLAUDE_MODEL",
        }
    ),
    "deepseek": frozenset(
        {
            "DEEPSEEK_API_KEY",
            "DEEPSEEK_BASE_URL",
            "GRAPHIFY_DEEPSEEK_MODEL",
        }
    ),
    "gemini": frozenset(
        {
            "GEMINI_API_KEY",
            "GEMINI_BASE_URL",
            "GOOGLE_API_KEY",
            "GRAPHIFY_GEMINI_MODEL",
        }
    ),
    "kimi": frozenset(
        {
            "KIMI_BASE_URL",
            "KIMI_MODEL",
            "MOONSHOT_API_KEY",
        }
    ),
    "ollama": frozenset(
        {
            "OLLAMA_API_KEY",
            "OLLAMA_BASE_URL",
            "OLLAMA_HOST",
            "OLLAMA_MODEL",
        }
    ),
    "openai": frozenset(
        {
            "GRAPHIFY_OPENAI_MODEL",
            "OPENAI_API_KEY",
            "OPENAI_BASE_URL",
            "OPENAI_MODEL",
        }
    ),
}

Runner = Callable[..., subprocess.CompletedProcess[str]]


def _validate_request(request: GraphifyRequest) -> None:
    if not isinstance(request.executable, str) or not request.executable.strip():
        raise ReferenceError(
            "graphify_request_invalid",
            "Graphify executable must be a non-empty command or path",
        )
    if request.backend not in _SUPPORTED_BACKENDS:
        raise ReferenceError(
            "graphify_request_invalid",
            "Graphify backend is not supported by this adapter",
            {"backend": request.backend},
        )
    if request.processing_boundary not in {"local", "remote"}:
        raise ReferenceError(
            "graphify_processing_boundary_invalid",
            "processing_boundary must be local or remote",
        )
    if request.processing_boundary == "local" and request.backend != "ollama":
        raise ReferenceError(
            "graphify_processing_boundary_invalid",
            "The local boundary currently permits only the explicit ollama backend",
            {"backend": request.backend},
        )
    if request.processing_boundary == "local":
        endpoint = os.environ.get("OLLAMA_BASE_URL") or os.environ.get("OLLAMA_HOST")
        if endpoint and not _is_loopback_endpoint(endpoint):
            raise ReferenceError(
                "graphify_processing_boundary_invalid",
                "Local processing refused because Ollama is configured for a non-loopback host",
                {"environment": "OLLAMA_BASE_URL or OLLAMA_HOST"},
            )
    if request.processing_boundary == "remote" and not request.allow_remote:
        raise ReferenceError(
            "graphify_remote_not_authorized",
            "Remote semantic processing requires explicit --allow-remote authority",
            {"backend": request.backend},
        )
    if request.model is not None and (
        not isinstance(request.model, str)
        or not request.model.strip()
        or "\n" in request.model
        or "\r" in request.model
    ):
        raise ReferenceError(
            "graphify_request_invalid",
            "Graphify model must be a non-empty single-line value or null",
        )
    if (
        not isinstance(request.timeout_seconds, int)
        or not 1 <= request.timeout_seconds <= 86_400
        or not isinstance(request.max_concurrency, int)
        or not 1 <= request.max_concurrency <= 8
    ):
        raise ReferenceError(
            "graphify_request_invalid",
            "Graphify timeout or concurrency is outside the supported bounds",
        )


def _is_loopback_endpoint(value: str) -> bool:
    candidate = value.strip()
    if not candidate:
        return True
    if candidate.isdigit() or candidate.startswith(":"):
        return True
    parsed = urlparse(candidate if "://" in candidate else f"http://{candidate}")
    hostname = parsed.hostname
    if hostname is None:
        return False
    if hostname.casefold() == "localhost":
        return True
    try:
        return ipaddress.ip_address(hostname).is_loopback
    except ValueError:
        return False


def _subprocess_environment(backend: str | None = None) -> dict[str, str]:
    """Return only runtime and selected-provider values for Graphify."""

    allowed = set(_RUNTIME_ENVIRONMENT)
    if backend is not None:
        allowed.update(_BACKEND_ENVIRONMENT[backend])
    return {
        name: value
        for name in sorted(allowed)
        if (value := os.environ.get(name)) is not None
    }


def _run(
    runner: Runner,
    command: list[str],
    *,
    environment: Mapping[str, str],
    timeout: int,
    failure_code: str,
    failure_message: str,
) -> subprocess.CompletedProcess[str]:
    try:
        result = runner(
            command,
            capture_output=True,
            env=dict(environment),
            text=True,
            shell=False,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired as error:
        raise ReferenceError(
            "graphify_timeout",
            "Graphify exceeded the explicit timeout",
            {"timeout_seconds": timeout},
        ) from error
    except (OSError, ValueError) as error:
        raise ReferenceError(failure_code, failure_message) from error
    if result.returncode != 0:
        raise ReferenceError(
            failure_code,
            failure_message,
            {"exit_code": result.returncode},
        )
    return result


def _probe_version(request: GraphifyRequest, runner: Runner) -> str:
    result = _run(
        runner,
        [request.executable, "--version"],
        environment=_subprocess_environment(),
        timeout=min(request.timeout_seconds, 30),
        failure_code="graphify_unavailable",
        failure_message="Graphify version probe failed",
    )
    match = _VERSION.search(result.stdout or "")
    if match is None:
        raise ReferenceError(
            "graphify_version_unsupported",
            "Graphify did not report a parseable semantic version",
        )
    major, minor, patch = (int(part) for part in match.groups())
    if major != 0 or minor < 9:
        raise ReferenceError(
            "graphify_version_unsupported",
            "Supported Graphify versions are >=0.9.0 and <1.0.0",
            {"observed_version": f"{major}.{minor}.{patch}"},
        )
    return f"{major}.{minor}.{patch}"


def _portable_source_path(value: Any) -> bool:
    if not isinstance(value, str):
        return True
    return not PurePosixPath(value).is_absolute() and not PureWindowsPath(value).is_absolute()


def _validate_graph(path: Path) -> tuple[int, int, list[str]]:
    try:
        if path.stat().st_size > _MAX_GRAPH_BYTES:
            raise ReferenceError(
                "graphify_output_invalid",
                "Graphify graph exceeds the supported size",
            )
        graph = json.loads(path.read_text(encoding="utf-8"))
    except ReferenceError:
        raise
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise ReferenceError(
            "graphify_output_invalid",
            "Graphify did not produce a valid graph.json",
        ) from error
    if not isinstance(graph, dict) or not isinstance(graph.get("nodes"), list):
        raise ReferenceError(
            "graphify_output_invalid",
            "Graphify graph.json has an unsupported structure",
        )
    edges = graph.get("links", graph.get("edges"))
    if not isinstance(edges, list):
        raise ReferenceError(
            "graphify_output_invalid",
            "Graphify graph.json has no supported edge collection",
        )
    nodes = graph["nodes"]
    if len(nodes) > _MAX_GRAPH_NODES or len(edges) > _MAX_GRAPH_EDGES:
        raise ReferenceError(
            "graphify_output_invalid",
            "Graphify graph exceeds the supported node or edge bounds",
            {"nodes": len(nodes), "edges": len(edges)},
        )
    for node in nodes:
        if not isinstance(node, dict) or not _portable_source_path(node.get("source_file")):
            raise ReferenceError(
                "graphify_output_invalid",
                "Graphify graph contains an absolute or invalid source path",
            )
    warnings = ["visualization_may_be_large"] if len(nodes) > 5_000 else []
    return len(nodes), len(edges), warnings


def _artifact_inventory(snapshot: Path) -> list[dict[str, Any]]:
    artifacts: list[dict[str, Any]] = []
    total_bytes = 0
    for path in sorted(
        (item for item in snapshot.rglob("*") if item.is_file()),
        key=lambda item: item.relative_to(snapshot).as_posix(),
    ):
        if path.is_symlink():
            raise ReferenceError(
                "graphify_output_invalid",
                "Graphify output must not contain symbolic links",
            )
        relative = path.relative_to(snapshot).as_posix()
        if relative == "manifest.json":
            continue
        size = path.stat().st_size
        total_bytes += size
        if len(artifacts) >= _MAX_OVERLAY_FILES or total_bytes > _MAX_OVERLAY_BYTES:
            raise ReferenceError(
                "graphify_output_invalid",
                "Graphify output exceeds the supported file or byte bounds",
            )
        artifacts.append(
            {"byte_size": size, "path": relative, "sha256": hash_file(path)}
        )
    return artifacts


def _validate_overlay(
    snapshot: Path,
    overlay_fingerprint: str,
    *,
    manifest_sha256: str | None = None,
) -> dict[str, Any]:
    manifest_path = snapshot / "manifest.json"
    if manifest_sha256 is not None and (
        not manifest_path.is_file() or hash_file(manifest_path) != manifest_sha256
    ):
        raise ReferenceError(
            "graphify_output_invalid",
            "Overlay manifest hash does not match its pointer",
        )
    manifest = load_json(manifest_path, "graphify_output_invalid")
    if (
        not isinstance(manifest, dict)
        or manifest.get("contract_version") != CONTRACT_VERSION
        or manifest.get("complete") is not True
        or manifest.get("overlay_fingerprint") != overlay_fingerprint
        or manifest.get("evidence_class") != "semantic_overlay_inference"
    ):
        raise ReferenceError(
            "graphify_output_invalid",
            "Overlay manifest is incomplete or incompatible",
        )
    artifacts = manifest.get("artifacts")
    if not isinstance(artifacts, list):
        raise ReferenceError(
            "graphify_output_invalid",
            "Overlay artifact inventory is invalid",
        )
    expected_paths: set[str] = set()
    for artifact in artifacts:
        if (
            not isinstance(artifact, dict)
            or not isinstance(artifact.get("path"), str)
            or not isinstance(artifact.get("byte_size"), int)
            or not _FINGERPRINT.fullmatch(str(artifact.get("sha256", "")))
        ):
            raise ReferenceError(
                "graphify_output_invalid",
                "Overlay artifact entry is invalid",
            )
        relative = str(artifact["path"])
        expected_paths.add(relative)
        path = confined_relative_path(snapshot, relative)
        if (
            not path.is_file()
            or path.stat().st_size != artifact["byte_size"]
            or hash_file(path) != artifact["sha256"]
        ):
            raise ReferenceError(
                "graphify_output_invalid",
                "Overlay artifact hash is invalid",
                {"path": relative},
            )
    actual_paths = {
        path.relative_to(snapshot).as_posix()
        for path in snapshot.rglob("*")
        if path.is_file() and path.name != "manifest.json"
    }
    if expected_paths != actual_paths:
        raise ReferenceError(
            "graphify_output_invalid",
            "Overlay contains untracked or missing artifacts",
        )
    _validate_graph(snapshot / "graphify-out" / "graph.json")
    return manifest


def build_graphify_overlay(
    request: GraphifyRequest,
    *,
    runner: Runner = subprocess.run,
) -> dict[str, Any]:
    """Run Graphify only after explicit local/remote processing authority."""

    _validate_request(request)
    corpus = ReferenceCorpus.open(request.corpus_root)
    output = request.output_dir.expanduser().resolve()
    if (
        output == corpus.root
        or corpus.root in output.parents
        or output in corpus.root.parents
    ):
        raise ReferenceError(
            "graphify_request_invalid",
            "Overlay output and authoritative corpus must be separate directories",
        )
    version = _probe_version(request, runner)
    invocation = {
        "backend": request.backend,
        "input": "documents",
        "max_concurrency": request.max_concurrency,
        "model": request.model,
        "processing_boundary": request.processing_boundary,
    }
    identity = {
        "contract_version": CONTRACT_VERSION,
        "corpus_fingerprint": corpus.corpus_fingerprint,
        "invocation": invocation,
        "producer": {"name": "graphify", "version": version},
    }
    overlay_fingerprint = hash_bytes(canonical_json_bytes(identity))
    output.mkdir(parents=True, exist_ok=True)
    snapshots = output / "snapshots"
    snapshots.mkdir(exist_ok=True)
    final_snapshot = snapshots / overlay_fingerprint
    if final_snapshot.exists():
        manifest = _validate_overlay(final_snapshot, overlay_fingerprint)
        pointer = {
            "contract_version": CONTRACT_VERSION,
            "manifest_sha256": hash_file(final_snapshot / "manifest.json"),
            "overlay_fingerprint": overlay_fingerprint,
            "snapshot_path": f"snapshots/{overlay_fingerprint}",
        }
        atomic_write_json(output / "current.json", pointer)
        return _result(manifest, pointer, reused=True)

    staging = output / f".staging-{uuid.uuid4().hex}"
    staging.mkdir()
    try:
        command = [
            request.executable,
            "extract",
            str(corpus.snapshot / "documents"),
            "--out",
            str(staging),
            "--backend",
            request.backend,
            "--max-concurrency",
            str(request.max_concurrency),
            "--api-timeout",
            str(min(request.timeout_seconds, 3_600)),
        ]
        if request.model is not None:
            command.extend(["--model", request.model])
        _run(
            runner,
            command,
            environment=_subprocess_environment(request.backend),
            timeout=request.timeout_seconds,
            failure_code="graphify_execution_failed",
            failure_message="Graphify semantic extraction failed",
        )
        node_count, edge_count, warnings = _validate_graph(
            staging / "graphify-out" / "graph.json"
        )
        artifacts = _artifact_inventory(staging)
        manifest = {
            "artifacts": artifacts,
            "complete": True,
            "contract_version": CONTRACT_VERSION,
            "corpus_fingerprint": corpus.corpus_fingerprint,
            "counts": {"edges": edge_count, "nodes": node_count},
            "evidence_class": "semantic_overlay_inference",
            "invocation": invocation,
            "overlay_fingerprint": overlay_fingerprint,
            "producer": {
                "name": "graphify",
                "supported_range": ">=0.9.0,<1.0.0",
                "version": version,
            },
            "warnings": warnings,
        }
        write_json(staging / "manifest.json", manifest)
        _validate_overlay(staging, overlay_fingerprint)
        os.replace(staging, final_snapshot)
        pointer = {
            "contract_version": CONTRACT_VERSION,
            "manifest_sha256": hash_file(final_snapshot / "manifest.json"),
            "overlay_fingerprint": overlay_fingerprint,
            "snapshot_path": f"snapshots/{overlay_fingerprint}",
        }
        atomic_write_json(output / "current.json", pointer)
        return _result(manifest, pointer, reused=False)
    except ReferenceError:
        raise
    except (OSError, ValueError) as error:
        raise ReferenceError(
            "graphify_execution_failed",
            "Graphify overlay publication failed",
        ) from error
    finally:
        if staging.exists() and staging.parent == output:
            shutil.rmtree(staging)


def _result(
    manifest: Mapping[str, Any],
    pointer: Mapping[str, Any],
    *,
    reused: bool,
) -> dict[str, Any]:
    return {
        "contract_version": CONTRACT_VERSION,
        "corpus_fingerprint": manifest["corpus_fingerprint"],
        "counts": manifest["counts"],
        "evidence_class": "semantic_overlay_inference",
        "manifest_sha256": pointer["manifest_sha256"],
        "overlay_fingerprint": pointer["overlay_fingerprint"],
        "processing_boundary": manifest["invocation"]["processing_boundary"],
        "producer": manifest["producer"],
        "reused": reused,
        "snapshot_path": pointer["snapshot_path"],
        "warnings": manifest["warnings"],
    }
