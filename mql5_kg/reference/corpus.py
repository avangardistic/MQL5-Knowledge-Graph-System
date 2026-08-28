"""Validated immutable reference-corpus reader and deterministic lexical search."""

from __future__ import annotations

from collections import Counter
import json
from pathlib import Path
import re
import unicodedata
from typing import Any, Iterable, Iterator, Mapping

from .models import (
    AUTHORITY_RANK,
    CONTRACT_VERSION,
    DEFAULT_EXCERPT_CHARS,
    DEFAULT_SEARCH_LIMIT,
    MAX_DIRECT_EXCERPT_CHARS,
    MAX_EXCERPT_CHARS,
    MAX_QUERY_CHARS,
    MAX_SEARCH_LIMIT,
    MIN_EXCERPT_CHARS,
    ReferenceError,
    canonical_json_bytes,
    confined_relative_path,
    hash_file,
    hash_bytes,
    load_json,
)


_FINGERPRINT = re.compile(r"^[0-9a-f]{64}$")
_TOKEN = re.compile(r"\w+", re.UNICODE)
_SPACED_IDENTIFIER = re.compile(
    r"(?<!\w)(?:[a-z]\s+){2,}[a-z0-9_]+(?!\w)",
    re.IGNORECASE,
)
_MAX_MANIFEST_BYTES = 16 * 1024 * 1024
_MAX_INVENTORY_FILES = 50_000
_MAX_CANONICAL_BYTES = 2 * 1024 * 1024 * 1024
_MAX_JSONL_LINE_CHARS = 64 * 1024 * 1024


def _iter_jsonl(path: Path) -> Iterator[dict[str, Any]]:
    try:
        with path.open("r", encoding="utf-8") as stream:
            for line_number, line in enumerate(stream, start=1):
                if len(line) > _MAX_JSONL_LINE_CHARS:
                    raise ReferenceError(
                        "reference_limit_exceeded",
                        "Reference record exceeds the supported line size",
                        {"path": path.name, "line": line_number},
                    )
                if not line.strip():
                    continue
                value = json.loads(line)
                if not isinstance(value, dict):
                    raise ValueError("record is not an object")
                yield value
    except ReferenceError:
        raise
    except (OSError, UnicodeError, json.JSONDecodeError, ValueError) as error:
        raise ReferenceError(
            "reference_integrity_failed",
            "Reference JSONL record is invalid",
            {"path": path.name},
        ) from error


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    return list(_iter_jsonl(path))


def validate_snapshot(
    snapshot: Path,
    expected_fingerprint: str,
    *,
    expected_manifest_sha256: str | None = None,
) -> tuple[dict[str, Any], list[dict[str, Any]], list[dict[str, Any]]]:
    """Validate all canonical bytes and structural page/section invariants."""

    manifest_path = snapshot / "manifest.json"
    try:
        if manifest_path.stat().st_size > _MAX_MANIFEST_BYTES:
            raise ReferenceError(
                "reference_limit_exceeded",
                "Reference manifest exceeds the supported size",
            )
    except OSError as error:
        raise ReferenceError(
            "reference_snapshot_incomplete",
            "Reference snapshot manifest is missing",
        ) from error
    actual_manifest_sha256 = hash_file(manifest_path)
    if (
        expected_manifest_sha256 is not None
        and actual_manifest_sha256 != expected_manifest_sha256
    ):
        raise ReferenceError(
            "reference_integrity_failed",
            "Reference manifest hash does not match current.json",
        )
    manifest = load_json(manifest_path)
    if (
        not isinstance(manifest, dict)
        or manifest.get("contract_version") != CONTRACT_VERSION
        or manifest.get("complete") is not True
        or manifest.get("corpus_fingerprint") != expected_fingerprint
    ):
        code = (
            "unsupported_reference_contract"
            if isinstance(manifest, dict)
            and manifest.get("contract_version") != CONTRACT_VERSION
            else "reference_snapshot_incomplete"
        )
        raise ReferenceError(
            code,
            "Reference snapshot manifest is incomplete or incompatible",
        )

    files = manifest.get("files")
    if not isinstance(files, list) or len(files) > _MAX_INVENTORY_FILES:
        raise ReferenceError(
            "reference_integrity_failed",
            "Reference snapshot file inventory is invalid",
        )
    inventory: set[str] = set()
    total_bytes = 0
    for item in files:
        if (
            not isinstance(item, dict)
            or not isinstance(item.get("path"), str)
            or not isinstance(item.get("byte_size"), int)
            or not _FINGERPRINT.fullmatch(str(item.get("sha256", "")))
        ):
            raise ReferenceError(
                "reference_integrity_failed",
                "Reference snapshot file entry is invalid",
            )
        relative = str(item["path"])
        if relative in inventory or relative == "manifest.json":
            raise ReferenceError(
                "reference_integrity_failed",
                "Reference snapshot file inventory contains a duplicate",
                {"path": relative},
            )
        inventory.add(relative)
        path = confined_relative_path(snapshot, relative)
        try:
            size = path.stat().st_size
        except OSError as error:
            raise ReferenceError(
                "reference_integrity_failed",
                "Reference snapshot file is missing",
                {"path": relative},
            ) from error
        total_bytes += size
        if total_bytes > _MAX_CANONICAL_BYTES:
            raise ReferenceError(
                "reference_limit_exceeded",
                "Reference snapshot exceeds the supported size",
            )
        if size != item["byte_size"] or hash_file(path) != item["sha256"]:
            raise ReferenceError(
                "reference_integrity_failed",
                "Reference snapshot file hash does not match the manifest",
                {"path": relative},
            )
    actual_files = {
        path.relative_to(snapshot).as_posix()
        for path in snapshot.rglob("*")
        if path.is_file() and path.name != "manifest.json"
    }
    if actual_files != inventory:
        raise ReferenceError(
            "reference_integrity_failed",
            "Reference snapshot contains untracked or missing canonical files",
        )

    sections = _read_jsonl(snapshot / "records" / "sections.jsonl")
    _validate_records(
        manifest,
        _iter_jsonl(snapshot / "records" / "pages.jsonl"),
        sections,
        inventory,
    )
    return manifest, [], sections


def _validate_records(
    manifest: Mapping[str, Any],
    pages: Iterable[dict[str, Any]],
    sections: list[dict[str, Any]],
    inventory: set[str],
) -> None:
    sources = manifest.get("sources")
    counts = manifest.get("counts")
    if not isinstance(sources, list) or not isinstance(counts, dict) or not sources:
        raise ReferenceError(
            "reference_integrity_failed",
            "Reference source or count metadata is invalid",
        )
    source_ids: list[str] = []
    page_counts: dict[str, int] = {}
    for source in sources:
        if not isinstance(source, dict):
            raise ReferenceError(
                "reference_integrity_failed",
                "Reference source metadata is invalid",
            )
        source_id = source.get("source_id")
        page_count = source.get("page_count")
        authority = source.get("authority")
        if (
            not isinstance(source_id, str)
            or source_id in page_counts
            or not isinstance(page_count, int)
            or page_count < 1
            or authority not in AUTHORITY_RANK
            or not isinstance(source.get("byte_size"), int)
            or source["byte_size"] < 0
            or not isinstance(source.get("filename"), str)
            or not isinstance(source.get("title"), str)
            or not isinstance(source.get("role"), str)
            or not _FINGERPRINT.fullmatch(str(source.get("sha256", "")))
            or (
                source.get("expected_sha256") is not None
                and not _FINGERPRINT.fullmatch(
                    str(source.get("expected_sha256"))
                )
            )
        ):
            raise ReferenceError(
                "reference_integrity_failed",
                "Reference source identity is invalid",
            )
        source_ids.append(source_id)
        page_counts[source_id] = page_count
    if source_ids != sorted(source_ids):
        raise ReferenceError(
            "reference_integrity_failed",
            "Reference sources are out of canonical order",
        )
    fingerprint_sources = [
        {
            "authority": source["authority"],
            "byte_size": source["byte_size"],
            "expected_sha256": source.get("expected_sha256"),
            "filename": source["filename"],
            "official_url": source.get("official_url"),
            "role": source["role"],
            "sha256": source["sha256"],
            "source_id": source["source_id"],
            "title": source["title"],
        }
        for source in sources
    ]
    expected_identity = {
        "configuration": manifest.get("configuration"),
        "contract_version": CONTRACT_VERSION,
        "sources": fingerprint_sources,
    }
    if hash_bytes(canonical_json_bytes(expected_identity)) != manifest.get(
        "corpus_fingerprint"
    ):
        raise ReferenceError(
            "reference_integrity_failed",
            "Reference corpus fingerprint does not match its canonical identity",
        )

    expected_pages = iter(
        (source_id, page_number)
        for source_id in source_ids
        for page_number in range(1, page_counts[source_id] + 1)
    )
    actual_page_count = 0
    for page in pages:
        source_id = page.get("source_id")
        physical_page = page.get("physical_page")
        if (
            not isinstance(source_id, str)
            or not isinstance(physical_page, int)
            or page.get("state") not in {"text", "empty", "extraction_failed"}
            or not isinstance(page.get("raw_text"), str)
            or not isinstance(page.get("normalized_text"), str)
            or not isinstance(page.get("warnings"), list)
        ):
            raise ReferenceError(
                "reference_integrity_failed",
                "Reference page record is invalid",
            )
        actual_page_count += 1
        try:
            expected_page = next(expected_pages)
        except StopIteration as error:
            raise ReferenceError(
                "reference_integrity_failed",
                "Reference pages contain unexpected extra records",
            ) from error
        if (source_id, physical_page) != expected_page:
            raise ReferenceError(
                "reference_integrity_failed",
                "Reference pages are incomplete, duplicated, or out of order",
            )
    try:
        next(expected_pages)
    except StopIteration:
        pass
    else:
        raise ReferenceError(
            "reference_integrity_failed",
            "Reference pages are incomplete, duplicated, or out of order",
        )

    seen_sections: set[str] = set()
    expected_section_order: list[tuple[int, int]] = []
    source_order = {source_id: index for index, source_id in enumerate(source_ids)}
    coverage: dict[str, list[int]] = {source_id: [] for source_id in source_ids}
    for section in sections:
        source_id = section.get("source_id")
        section_id = section.get("section_id")
        start = section.get("physical_page_start")
        end = section.get("physical_page_end")
        text = section.get("text")
        markdown_path = section.get("markdown_path")
        spans = section.get("page_spans")
        if (
            source_id not in page_counts
            or not isinstance(section_id, str)
            or section_id in seen_sections
            or not isinstance(start, int)
            or not isinstance(end, int)
            or not 1 <= start <= end <= page_counts[str(source_id)]
            or not isinstance(text, str)
            or not isinstance(markdown_path, str)
            or markdown_path not in inventory
            or not isinstance(spans, list)
            or not _FINGERPRINT.fullmatch(str(section.get("content_sha256", "")))
            or not isinstance(section.get("path"), list)
            or not isinstance(section.get("aliases"), list)
            or not isinstance(section.get("warnings"), list)
        ):
            raise ReferenceError(
                "reference_integrity_failed",
                "Reference section record is invalid",
            )
        seen_sections.add(section_id)
        expected_section_order.append((source_order[str(source_id)], start))
        coverage[str(source_id)].extend(range(start, end + 1))
        if len(spans) != end - start + 1:
            raise ReferenceError(
                "reference_integrity_failed",
                "Reference section page spans are incomplete",
            )
        previous_end = 0
        for offset, span in enumerate(spans):
            if (
                not isinstance(span, dict)
                or span.get("physical_page") != start + offset
                or not isinstance(span.get("start"), int)
                or not isinstance(span.get("end"), int)
                or not 0 <= span["start"] <= span["end"] <= len(text)
                or span["start"] < previous_end
            ):
                raise ReferenceError(
                    "reference_integrity_failed",
                    "Reference section page span is invalid",
                )
            previous_end = span["end"]
    if expected_section_order != sorted(expected_section_order):
        raise ReferenceError(
            "reference_integrity_failed",
            "Reference sections are out of canonical order",
        )
    for source_id, page_count in page_counts.items():
        if coverage[source_id] != list(range(1, page_count + 1)):
            raise ReferenceError(
                "reference_integrity_failed",
                "Reference section ranges do not cover every physical page exactly once",
                {"source_id": source_id},
            )
    if (
        counts.get("documents") != len(sources)
        or counts.get("pages") != actual_page_count
        or counts.get("sections") != len(sections)
    ):
        raise ReferenceError(
            "reference_integrity_failed",
            "Reference manifest counts do not match canonical records",
        )


def _search_form(value: str) -> str:
    normalized = unicodedata.normalize("NFKC", value).casefold()
    return _SPACED_IDENTIFIER.sub(
        lambda match: re.sub(r"\s+", "", match.group(0)),
        normalized,
    )


def _tokens(value: str) -> list[str]:
    return _TOKEN.findall(_search_form(value))


def _excerpt_bounds(text: str, query: str, tokens: Iterable[str], maximum: int) -> tuple[int, int]:
    lowered = unicodedata.normalize("NFKC", text).casefold()
    needle = unicodedata.normalize("NFKC", query).casefold()
    anchor = lowered.find(needle)
    if anchor < 0:
        positions: list[int] = []
        for token in tokens:
            position = lowered.find(token)
            if position < 0 and token.isalnum() and 3 <= len(token) <= 32:
                spaced = re.search(
                    r"\s*".join(re.escape(character) for character in token),
                    lowered,
                )
                position = spaced.start() if spaced is not None else -1
            if position >= 0:
                positions.append(position)
        anchor = min(positions) if positions else 0
    start = max(0, anchor - maximum // 3)
    end = min(len(text), start + maximum)
    if end - start < maximum:
        start = max(0, end - maximum)
    return start, end


def _citation_pages(
    section: Mapping[str, Any],
    start: int,
    end: int,
) -> tuple[int, int]:
    pages = [
        int(span["physical_page"])
        for span in section["page_spans"]
        if int(span["start"]) < end and int(span["end"]) > start
    ]
    if not pages:
        page = int(section["physical_page_start"])
        return page, page
    return min(pages), max(pages)


class ReferenceCorpus:
    """One fully validated immutable reference snapshot."""

    __slots__ = (
        "root",
        "snapshot",
        "pointer",
        "manifest",
        "pages",
        "sections",
        "_search_entries",
        "sources_by_id",
        "sections_by_id",
        "corpus_fingerprint",
    )

    def __init__(
        self,
        root: Path,
        snapshot: Path,
        pointer: dict[str, Any],
        manifest: dict[str, Any],
        pages: list[dict[str, Any]],
        sections: list[dict[str, Any]],
    ) -> None:
        self.root = root
        self.snapshot = snapshot
        self.pointer = pointer
        self.manifest = manifest
        self.pages = tuple(pages)
        self.sections = tuple(sections)
        self._search_entries = tuple(
            (
                section,
                (
                    _search_form(str(section["title"])),
                    *(
                        _search_form(str(alias))
                        for alias in section["aliases"]
                    ),
                ),
                _search_form(str(section["text"])),
            )
            for section in sections
        )
        self.sources_by_id = {
            str(source["source_id"]): source for source in manifest["sources"]
        }
        self.sections_by_id = {
            str(section["section_id"]): section for section in sections
        }
        self.corpus_fingerprint = str(pointer["corpus_fingerprint"])

    @classmethod
    def open(cls, root: str | Path) -> ReferenceCorpus:
        try:
            resolved = Path(root).expanduser().resolve()
        except (OSError, RuntimeError) as error:
            raise ReferenceError(
                "invalid_reference_root",
                "Reference corpus root could not be resolved",
            ) from error
        if not resolved.is_dir():
            raise ReferenceError(
                "invalid_reference_root",
                "Reference corpus root is not an existing directory",
            )
        pointer_path = resolved / "current.json"
        if not pointer_path.is_file() or pointer_path.is_symlink():
            raise ReferenceError(
                "reference_not_built",
                "Reference corpus has no published current.json",
            )
        try:
            if pointer_path.stat().st_size > 64 * 1024:
                raise ValueError("pointer too large")
            pointer = load_json(pointer_path, "invalid_reference_pointer")
        except (OSError, ValueError) as error:
            raise ReferenceError(
                "invalid_reference_pointer",
                "Reference corpus pointer is invalid",
            ) from error
        fingerprint = pointer.get("corpus_fingerprint") if isinstance(pointer, dict) else None
        expected_path = (
            f"snapshots/{fingerprint}"
            if isinstance(fingerprint, str)
            else None
        )
        if (
            not isinstance(pointer, dict)
            or pointer.get("contract_version") != CONTRACT_VERSION
            or not isinstance(fingerprint, str)
            or not _FINGERPRINT.fullmatch(fingerprint)
            or pointer.get("snapshot_path") != expected_path
            or not _FINGERPRINT.fullmatch(str(pointer.get("manifest_sha256", "")))
        ):
            raise ReferenceError(
                "invalid_reference_pointer",
                "Reference corpus pointer is invalid or incompatible",
            )
        snapshot = confined_relative_path(resolved, expected_path)
        if not snapshot.is_dir():
            raise ReferenceError(
                "reference_snapshot_incomplete",
                "Published reference snapshot directory is missing",
            )
        manifest, pages, sections = validate_snapshot(
            snapshot,
            fingerprint,
            expected_manifest_sha256=str(pointer["manifest_sha256"]),
        )
        return cls(resolved, snapshot, pointer, manifest, pages, sections)

    def status(self) -> dict[str, Any]:
        authorities = Counter(
            str(source["authority"]) for source in self.manifest["sources"]
        )
        warnings = sorted(
            {
                str(warning)
                for source in self.manifest["sources"]
                for warning in source.get("warnings", [])
            }
        )
        return {
            "authority_catalog": dict(sorted(authorities.items())),
            "contract_version": CONTRACT_VERSION,
            "corpus_fingerprint": self.corpus_fingerprint,
            "counts": self.manifest["counts"],
            "root": str(self.root),
            "snapshot_path": self.pointer["snapshot_path"],
            "sources": self.manifest["sources"],
            "status": "loaded",
            "warnings": warnings,
        }

    def search(
        self,
        query: str,
        *,
        limit: int = DEFAULT_SEARCH_LIMIT,
        max_excerpt_chars: int = DEFAULT_EXCERPT_CHARS,
    ) -> dict[str, Any]:
        if not isinstance(query, str) or not query.strip() or len(query) > MAX_QUERY_CHARS:
            raise ReferenceError(
                "invalid_reference_query",
                f"Query must contain 1 to {MAX_QUERY_CHARS} characters",
            )
        if not isinstance(limit, int) or not 1 <= limit <= MAX_SEARCH_LIMIT:
            raise ReferenceError(
                "invalid_reference_query",
                f"limit must be between 1 and {MAX_SEARCH_LIMIT}",
            )
        if (
            not isinstance(max_excerpt_chars, int)
            or not MIN_EXCERPT_CHARS <= max_excerpt_chars <= MAX_EXCERPT_CHARS
        ):
            raise ReferenceError(
                "invalid_reference_query",
                f"max_excerpt_chars must be between {MIN_EXCERPT_CHARS} and {MAX_EXCERPT_CHARS}",
            )
        normalized_query = query.strip()
        query_form = _search_form(normalized_query)
        query_tokens = list(dict.fromkeys(_tokens(normalized_query)))
        if not query_tokens:
            raise ReferenceError(
                "invalid_reference_query",
                "Query must contain at least one word or identifier",
            )
        token_patterns = {
            token: re.compile(rf"(?<!\w){re.escape(token)}(?!\w)")
            for token in query_tokens
        }

        candidates: list[tuple[tuple[Any, ...], dict[str, Any]]] = []
        for section, title_forms, text_form in self._search_entries:
            exact_alias = query_form in title_forms
            phrase_occurrences = sum(value.count(query_form) for value in [*title_forms, text_form])
            token_counts = {
                token: sum(
                    len(pattern.findall(value))
                    for value in (*title_forms, text_form)
                )
                for token, pattern in token_patterns.items()
            }
            matched_terms = sum(1 for count in token_counts.values() if count > 0)
            term_occurrences = sum(token_counts.values())
            if not exact_alias and not phrase_occurrences and not matched_terms:
                continue
            source = self.sources_by_id[str(section["source_id"])]
            score = {
                "authority_rank": AUTHORITY_RANK[str(source["authority"])],
                "exact_alias": exact_alias,
                "exact_phrase": phrase_occurrences > 0,
                "matched_query_terms": matched_terms,
                "phrase_occurrences": phrase_occurrences,
                "query_terms": len(query_tokens),
                "term_occurrences": term_occurrences,
            }
            start, end = _excerpt_bounds(
                str(section["text"]),
                normalized_query,
                query_tokens,
                max_excerpt_chars,
            )
            citation_start, citation_end = _citation_pages(section, start, end)
            result = {
                "citation": {
                    "character_end": end,
                    "character_start": start,
                    "physical_page_end": citation_end,
                    "physical_page_start": citation_start,
                },
                "contract_version": CONTRACT_VERSION,
                "corpus_fingerprint": self.corpus_fingerprint,
                "evidence_class": "reference_document",
                "excerpt": str(section["text"])[start:end],
                "score": score,
                "section": {
                    "content_sha256": section["content_sha256"],
                    "markdown_path": section["markdown_path"],
                    "path": section["path"],
                    "physical_page_end": section["physical_page_end"],
                    "physical_page_start": section["physical_page_start"],
                    "section_id": section["section_id"],
                    "title": section["title"],
                    "warnings": section["warnings"],
                },
                "source": {
                    "authority": source["authority"],
                    "official_url": source.get("official_url"),
                    "sha256": source["sha256"],
                    "source_id": source["source_id"],
                    "title": source["title"],
                },
            }
            sort_key = (
                -int(exact_alias),
                -int(phrase_occurrences > 0),
                -matched_terms,
                -score["authority_rank"],
                -phrase_occurrences,
                -term_occurrences,
                str(source["source_id"]),
                str(section["section_id"]),
            )
            candidates.append((sort_key, result))
        candidates.sort(key=lambda item: item[0])
        results = [item[1] for item in candidates[:limit]]
        return {
            "completion": {
                "candidate_count": len(candidates),
                "exhaustive": True,
                "limit": limit,
                "no_match": not candidates,
                "returned_count": len(results),
                "truncated": len(candidates) > limit,
            },
            "contract_version": CONTRACT_VERSION,
            "corpus_fingerprint": self.corpus_fingerprint,
            "evidence_class": "reference_document",
            "query": normalized_query,
            "results": results,
        }

    def excerpt(
        self,
        section_id: str,
        *,
        start: int = 0,
        max_chars: int = DEFAULT_EXCERPT_CHARS,
    ) -> dict[str, Any]:
        if not isinstance(section_id, str) or not section_id.strip():
            raise ReferenceError(
                "invalid_reference_query",
                "section_id must be a non-empty string",
            )
        section = self.sections_by_id.get(section_id)
        if section is None:
            raise ReferenceError(
                "reference_section_not_found",
                "Reference section does not exist in the active corpus",
                {"section_id": section_id},
            )
        text = str(section["text"])
        if (
            not isinstance(start, int)
            or start < 0
            or start > len(text)
            or not isinstance(max_chars, int)
            or not MIN_EXCERPT_CHARS <= max_chars <= MAX_DIRECT_EXCERPT_CHARS
        ):
            raise ReferenceError(
                "invalid_reference_query",
                "Excerpt bounds are outside the supported range",
            )
        end = min(len(text), start + max_chars)
        citation_start, citation_end = _citation_pages(section, start, end)
        source = self.sources_by_id[str(section["source_id"])]
        return {
            "citation": {
                "character_end": end,
                "character_start": start,
                "physical_page_end": citation_end,
                "physical_page_start": citation_start,
            },
            "complete_section": start == 0 and end == len(text),
            "contract_version": CONTRACT_VERSION,
            "corpus_fingerprint": self.corpus_fingerprint,
            "evidence_class": "reference_document",
            "excerpt": text[start:end],
            "section": {
                "content_sha256": section["content_sha256"],
                "markdown_path": section["markdown_path"],
                "path": section["path"],
                "physical_page_end": section["physical_page_end"],
                "physical_page_start": section["physical_page_start"],
                "section_id": section["section_id"],
                "title": section["title"],
                "warnings": section["warnings"],
            },
            "source": {
                "authority": source["authority"],
                "official_url": source.get("official_url"),
                "sha256": source["sha256"],
                "source_id": source["source_id"],
                "title": source["title"],
            },
            "truncated": end < len(text),
        }
