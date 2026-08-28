"""Versioned reference-corpus contracts and deterministic I/O helpers."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import tempfile
import unicodedata
from typing import Any, Mapping


CONTRACT_VERSION = "1.0.0"
NORMALIZATION_VERSION = "1.0.0"
DEFAULT_MAX_PDF_BYTES = 512 * 1024 * 1024
DEFAULT_MAX_PAGES_PER_SOURCE = 20_000
DEFAULT_MAX_PAGES_PER_SECTION = 32
DEFAULT_SEARCH_LIMIT = 20
DEFAULT_EXCERPT_CHARS = 1_200
MAX_SEARCH_LIMIT = 50
MAX_QUERY_CHARS = 512
MIN_EXCERPT_CHARS = 80
MAX_EXCERPT_CHARS = 4_000
MAX_DIRECT_EXCERPT_CHARS = 8_000
AUTHORITY_RANK = {
    "normative": 300,
    "explanatory": 200,
    "specialist": 100,
    "unclassified": 0,
}

_SOURCE_ID = re.compile(r"^[a-z0-9](?:[a-z0-9-]{0,62}[a-z0-9])?$")
_SHA256 = re.compile(r"^[0-9a-f]{64}$")


class ReferenceError(RuntimeError):
    """Stable expected failure safe for CLI and local adapter clients."""

    __slots__ = ("code", "message", "details")

    def __init__(
        self,
        code: str,
        message: str,
        details: Mapping[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.details = dict(details or {})

    def to_dict(self) -> dict[str, Any]:
        return {
            "code": self.code,
            "message": self.message,
            "details": dict(sorted(self.details.items())),
        }


def _require_string(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ReferenceError(
            "invalid_source_manifest",
            f"{field} must be a non-empty string",
            {"field": field},
        )
    return value.strip()


@dataclass(frozen=True, slots=True)
class SourceDeclaration:
    """Operator-declared provenance and authority for one local PDF."""

    source_id: str
    filename: str
    title: str
    authority: str
    role: str
    official_url: str | None = None
    expected_sha256: str | None = None

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> SourceDeclaration:
        if not isinstance(value, Mapping):
            raise ReferenceError(
                "invalid_source_manifest",
                "Every source declaration must be an object",
            )
        source_id = _require_string(value.get("source_id"), "source_id")
        filename = _require_string(value.get("filename"), "filename")
        title = _require_string(value.get("title"), "title")
        authority = _require_string(value.get("authority"), "authority")
        role = _require_string(value.get("role"), "role")
        official_url = value.get("official_url")
        expected_sha256 = value.get("expected_sha256")
        declaration = cls(
            source_id=source_id,
            filename=filename,
            title=title,
            authority=authority,
            role=role,
            official_url=official_url,
            expected_sha256=expected_sha256,
        )
        declaration.validate()
        return declaration

    def validate(self) -> None:
        if not _SOURCE_ID.fullmatch(self.source_id):
            raise ReferenceError(
                "invalid_source_manifest",
                "source_id must be a portable lowercase slug",
                {"source_id": self.source_id},
            )
        filename = Path(self.filename)
        if (
            filename.name != self.filename
            or filename.suffix.casefold() != ".pdf"
            or "/" in self.filename
            or "\\" in self.filename
        ):
            raise ReferenceError(
                "invalid_source_manifest",
                "filename must be a PDF basename",
                {"filename": self.filename},
            )
        if self.authority not in AUTHORITY_RANK:
            raise ReferenceError(
                "invalid_source_manifest",
                "authority is not supported",
                {"authority": self.authority},
            )
        if self.official_url is not None and (
            not isinstance(self.official_url, str)
            or not self.official_url.startswith("https://")
        ):
            raise ReferenceError(
                "invalid_source_manifest",
                "official_url must be an HTTPS URL or null",
                {"source_id": self.source_id},
            )
        if self.expected_sha256 is not None and (
            not isinstance(self.expected_sha256, str)
            or not _SHA256.fullmatch(self.expected_sha256)
        ):
            raise ReferenceError(
                "invalid_source_manifest",
                "expected_sha256 must be lowercase SHA-256 or null",
                {"source_id": self.source_id},
            )

    def to_dict(self) -> dict[str, Any]:
        return {
            "authority": self.authority,
            "expected_sha256": self.expected_sha256,
            "filename": self.filename,
            "official_url": self.official_url,
            "role": self.role,
            "source_id": self.source_id,
            "title": self.title,
        }


@dataclass(frozen=True, slots=True)
class BuildRequest:
    """Validated operator request for one offline corpus build."""

    input_dir: Path
    output_dir: Path
    sources_path: Path | None = None
    max_pdf_bytes: int = DEFAULT_MAX_PDF_BYTES
    max_pages_per_source: int = DEFAULT_MAX_PAGES_PER_SOURCE
    max_pages_per_section: int = DEFAULT_MAX_PAGES_PER_SECTION

    def validate(self) -> None:
        if not self.input_dir.is_dir():
            raise ReferenceError(
                "invalid_reference_source",
                "Input directory is not an existing local directory",
            )
        if self.input_dir.is_symlink():
            raise ReferenceError(
                "invalid_reference_source",
                "Input directory must not be a symbolic link",
            )
        if self.sources_path is not None and (
            not self.sources_path.is_file() or self.sources_path.is_symlink()
        ):
            raise ReferenceError(
                "invalid_source_manifest",
                "Source manifest is not a regular local file",
            )
        try:
            input_root = self.input_dir.resolve()
            output_root = self.output_dir.resolve()
        except (OSError, RuntimeError) as error:
            raise ReferenceError(
                "invalid_reference_root",
                "Reference paths could not be resolved",
            ) from error
        if (
            input_root == output_root
            or input_root in output_root.parents
            or output_root in input_root.parents
        ):
            raise ReferenceError(
                "invalid_reference_root",
                "PDF input and corpus output directories must not overlap",
            )
        if self.max_pdf_bytes < 1 or self.max_pages_per_source < 1:
            raise ReferenceError(
                "reference_limit_exceeded",
                "PDF byte and page limits must be positive",
            )
        if not 1 <= self.max_pages_per_section <= 256:
            raise ReferenceError(
                "reference_limit_exceeded",
                "max_pages_per_section must be between 1 and 256",
            )


@dataclass(frozen=True, slots=True)
class GraphifyRequest:
    """Explicit request for a non-normative external semantic overlay."""

    corpus_root: Path
    output_dir: Path
    executable: str
    backend: str
    processing_boundary: str
    model: str | None = None
    allow_remote: bool = False
    timeout_seconds: int = 3_600
    max_concurrency: int = 1


def canonical_json_bytes(value: Any, *, pretty: bool = False) -> bytes:
    """Serialize stable UTF-8 JSON with one trailing LF."""

    if pretty:
        text = json.dumps(
            value,
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
    else:
        text = json.dumps(
            value,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        )
    return (text + "\n").encode("utf-8")


def write_json(path: Path, value: Any, *, pretty: bool = True) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(canonical_json_bytes(value, pretty=pretty))


def write_jsonl(path: Path, values: list[Mapping[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("wb") as stream:
        for value in values:
            stream.write(canonical_json_bytes(value))


def load_json(path: Path, code: str = "reference_integrity_failed") -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise ReferenceError(code, f"Could not read valid JSON: {path.name}") from error


def hash_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def hash_file(path: Path, *, chunk_size: int = 1024 * 1024) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(chunk_size):
            digest.update(chunk)
    return digest.hexdigest()


def atomic_write_json(path: Path, value: Any) -> None:
    """Flush and atomically replace one small publication pointer."""

    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        dir=path.parent,
        prefix=f".{path.name}.",
        suffix=".tmp",
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(canonical_json_bytes(value, pretty=True))
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        try:
            temporary.unlink()
        except FileNotFoundError:
            pass


def confined_relative_path(root: Path, value: str) -> Path:
    """Resolve a canonical POSIX relative path while rejecting traversal."""

    if not isinstance(value, str) or not value:
        raise ReferenceError(
            "reference_integrity_failed",
            "Canonical path must be a non-empty string",
        )
    portable = PurePosixPath(value)
    if portable.is_absolute() or ".." in portable.parts or "." in portable.parts:
        raise ReferenceError(
            "reference_snapshot_outside_root",
            "Canonical path escapes the reference root",
        )
    candidate = root.joinpath(*portable.parts)
    try:
        resolved_root = root.resolve()
        resolved_candidate = candidate.resolve()
    except (OSError, RuntimeError) as error:
        raise ReferenceError(
            "reference_integrity_failed",
            "Canonical path could not be resolved",
        ) from error
    if resolved_candidate != resolved_root and resolved_root not in resolved_candidate.parents:
        raise ReferenceError(
            "reference_snapshot_outside_root",
            "Canonical path escapes the reference root",
        )
    return resolved_candidate


def portable_slug(value: str, *, fallback: str = "section") -> str:
    normalized = unicodedata.normalize("NFKD", value)
    ascii_text = normalized.encode("ascii", "ignore").decode("ascii").casefold()
    slug = re.sub(r"[^a-z0-9]+", "-", ascii_text).strip("-")
    return (slug or fallback)[:64].rstrip("-")
