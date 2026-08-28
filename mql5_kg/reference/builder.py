"""Offline PDF-to-reference-corpus builder."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from importlib import metadata
import json
import os
from pathlib import Path
import shutil
import unicodedata
import uuid
from typing import Any, Iterable, Mapping

from .models import (
    CONTRACT_VERSION,
    NORMALIZATION_VERSION,
    BuildRequest,
    ReferenceError,
    SourceDeclaration,
    atomic_write_json,
    canonical_json_bytes,
    hash_bytes,
    hash_file,
    load_json,
    portable_slug,
    write_json,
)


KNOWN_SOURCES: dict[str, dict[str, str]] = {
    "mql5.pdf": {
        "source_id": "mql5-reference",
        "title": "MQL5 Reference",
        "authority": "normative",
        "role": "language_reference",
        "official_url": "https://www.mql5.com/files/docs/mql5.pdf",
    },
    "mql5book.pdf": {
        "source_id": "mql5-programming-book",
        "title": "MQL5 Programming for Traders",
        "authority": "explanatory",
        "role": "programming_book",
        "official_url": "https://www.mql5.com/files/book/mql5book.pdf",
    },
    "neuronetworksbook.pdf": {
        "source_id": "mql5-neural-networks-book",
        "title": "Neural Networks for Algorithmic Trading with MQL5",
        "authority": "specialist",
        "role": "specialist_neural_networks",
        "official_url": "https://www.mql5.com/files/book/neuronetworksbook.pdf",
    },
}


@dataclass(frozen=True, slots=True)
class _SourceInput:
    declaration: SourceDeclaration
    path: Path
    sha256: str
    byte_size: int


def _load_pdf_extractors() -> tuple[Any, Any, dict[str, dict[str, str]]]:
    try:
        from pypdf import PdfReader
        from pypdfium2 import PdfDocument
    except ImportError as error:
        raise ReferenceError(
            "reference_dependency_missing",
            "Building a PDF corpus requires the 'reference' extra",
            {"install": "mql5-codegraph[reference]"},
        ) from error
    versions: dict[str, dict[str, str]] = {}
    for role, package in (("structure", "pypdf"), ("text", "pypdfium2")):
        try:
            version = metadata.version(package)
        except metadata.PackageNotFoundError:
            version = "unknown"
        versions[role] = {"name": package, "version": version}
    return PdfReader, PdfDocument, versions


def _source_defaults(path: Path) -> SourceDeclaration:
    known = KNOWN_SOURCES.get(path.name.casefold())
    if known is not None:
        return SourceDeclaration(
            source_id=known["source_id"],
            filename=path.name,
            title=known["title"],
            authority=known["authority"],
            role=known["role"],
            official_url=known["official_url"],
        )
    return SourceDeclaration(
        source_id=portable_slug(path.stem, fallback="reference"),
        filename=path.name,
        title=path.stem.replace("_", " ").replace("-", " ").strip() or path.name,
        authority="unclassified",
        role="supplemental_reference",
    )


def _load_declarations(request: BuildRequest) -> list[SourceDeclaration]:
    if request.sources_path is None:
        candidates = sorted(
            (
                path
                for path in request.input_dir.iterdir()
                if path.suffix.casefold() == ".pdf"
            ),
            key=lambda path: path.name.casefold(),
        )
        if not candidates:
            raise ReferenceError(
                "invalid_reference_source",
                "Input directory contains no PDF files",
            )
        for path in candidates:
            if path.is_symlink() or not path.is_file():
                raise ReferenceError(
                    "invalid_reference_source",
                    "PDF sources must be regular files, not symbolic links",
                    {"filename": path.name},
                )
        declarations = [_source_defaults(path) for path in candidates]
    else:
        payload = load_json(request.sources_path, "invalid_source_manifest")
        if not isinstance(payload, dict) or payload.get("contract_version") != CONTRACT_VERSION:
            raise ReferenceError(
                "invalid_source_manifest",
                "Source manifest contract_version must be 1.0.0",
            )
        source_values = payload.get("sources")
        if not isinstance(source_values, list) or not source_values:
            raise ReferenceError(
                "invalid_source_manifest",
                "Source manifest must contain at least one source",
            )
        declarations = [SourceDeclaration.from_dict(value) for value in source_values]

    source_ids = [item.source_id for item in declarations]
    filenames = [item.filename.casefold() for item in declarations]
    if len(source_ids) != len(set(source_ids)) or len(filenames) != len(set(filenames)):
        raise ReferenceError(
            "invalid_source_manifest",
            "Source IDs and filenames must be unique",
        )
    return sorted(declarations, key=lambda item: item.source_id)


def _prepare_sources(request: BuildRequest) -> list[_SourceInput]:
    sources: list[_SourceInput] = []
    for declaration in _load_declarations(request):
        path = request.input_dir / declaration.filename
        if path.is_symlink() or not path.is_file():
            raise ReferenceError(
                "invalid_reference_source",
                "Declared PDF is not a regular local file",
                {"filename": declaration.filename},
            )
        size = path.stat().st_size
        if size > request.max_pdf_bytes:
            raise ReferenceError(
                "reference_limit_exceeded",
                "PDF exceeds the configured byte limit",
                {"filename": declaration.filename, "byte_size": size},
            )
        digest = hash_file(path)
        if declaration.expected_sha256 is not None and declaration.expected_sha256 != digest:
            raise ReferenceError(
                "invalid_reference_source",
                "PDF does not match expected_sha256",
                {"filename": declaration.filename, "actual_sha256": digest},
            )
        sources.append(_SourceInput(declaration, path, digest, size))
    return sources


def _raw_text(value: str | None) -> str:
    text = "" if value is None else str(value)
    text = unicodedata.normalize("NFC", text.replace("\r\n", "\n").replace("\r", "\n"))
    return text.replace("\x00", "\ufffd").strip("\n")


def _normalized_text(value: str) -> str:
    lines = [line.expandtabs(4).rstrip() for line in value.splitlines()]
    output: list[str] = []
    empty_run = 0
    for line in lines:
        if line:
            empty_run = 0
            output.append(line)
        else:
            empty_run += 1
            if empty_run <= 2:
                output.append("")
    return "\n".join(output).strip()


def _outline_title(value: Any) -> str:
    title = " ".join(str(value or "").split())
    return unicodedata.normalize("NFC", title) or "Untitled section"


def _flatten_outline(reader: Any, source_id: str) -> tuple[list[dict[str, Any]], list[str]]:
    warnings: list[str] = []
    try:
        tree = reader.outline
    except Exception:  # pypdf exposes heterogeneous malformed PDF exceptions.
        return [], ["outline_unreadable"]

    records: list[dict[str, Any]] = []

    def walk(items: Iterable[Any], ancestors: tuple[str, ...]) -> None:
        parent_path = ancestors
        for item in items:
            if isinstance(item, list):
                walk(item, parent_path)
                continue
            title = _outline_title(getattr(item, "title", item))
            path = (*ancestors, title)
            try:
                page_index = reader.get_destination_page_number(item)
            except Exception:
                page_index = None
            physical_page = (
                page_index + 1
                if isinstance(page_index, int) and page_index >= 0
                else None
            )
            identity = {
                "order": len(records),
                "path": list(path),
                "physical_page": physical_page,
                "source_id": source_id,
            }
            records.append(
                {
                    "depth": len(path) - 1,
                    "order": len(records),
                    "outline_id": (
                        f"{source_id}-outline-{hash_bytes(canonical_json_bytes(identity))[:16]}"
                    ),
                    "path": list(path),
                    "physical_page": physical_page,
                    "source_id": source_id,
                    "state": "resolved" if physical_page is not None else "unresolved",
                    "title": title,
                }
            )
            if physical_page is None:
                warnings.append("outline_destination_unresolved")
            parent_path = path

    if isinstance(tree, list):
        walk(tree, ())
    return records, sorted(set(warnings))


def _page_labels(reader: Any, page_count: int) -> tuple[list[str | None], list[str]]:
    try:
        labels = list(reader.page_labels)
    except Exception:
        return [None] * page_count, ["page_labels_unreadable"]
    if len(labels) != page_count:
        return [None] * page_count, ["page_labels_incomplete"]
    return [str(label) if label is not None else None for label in labels], []


def _open_reader(source: _SourceInput, PdfReader: Any) -> Any:
    try:
        reader = PdfReader(source.path, strict=False)
        if reader.is_encrypted and reader.decrypt("") == 0:
            raise ReferenceError(
                "invalid_reference_source",
                "Encrypted PDF cannot be opened with an empty password",
                {"filename": source.declaration.filename},
            )
        return reader
    except ReferenceError:
        raise
    except Exception as error:
        raise ReferenceError(
            "invalid_reference_source",
            "PDF could not be opened",
            {"filename": source.declaration.filename},
        ) from error


def _section_plans(
    source_id: str,
    page_count: int,
    outlines: list[dict[str, Any]],
    max_pages: int,
) -> list[dict[str, Any]]:
    by_page: dict[int, list[dict[str, Any]]] = {}
    for entry in outlines:
        physical_page = entry["physical_page"]
        if isinstance(physical_page, int) and 1 <= physical_page <= page_count:
            by_page.setdefault(physical_page, []).append(entry)
    starts: dict[int, tuple[str, list[str], list[str], int]] = {}
    for page_number, entries in by_page.items():
        chosen = max(entries, key=lambda entry: (entry["depth"], entry["order"]))
        aliases = sorted(
            {
                str(entry["title"])
                for entry in entries
                if entry is not chosen and entry["title"] != chosen["title"]
            },
            key=str.casefold,
        )
        starts[page_number] = (
            str(chosen["title"]),
            [str(part) for part in chosen["path"]],
            aliases,
            int(chosen["depth"]),
        )
    if 1 not in starts:
        starts[1] = ("Front matter", ["Front matter"], [], 0)

    plans: list[dict[str, Any]] = []
    ordered_starts = sorted(starts)
    occurrence = 0
    for index, start in enumerate(ordered_starts):
        end = (
            ordered_starts[index + 1] - 1
            if index + 1 < len(ordered_starts)
            else page_count
        )
        chunk_start = start
        part = 1
        while chunk_start <= end:
            chunk_end = min(end, chunk_start + max_pages - 1)
            title, path, aliases, depth = starts[start]
            if chunk_start != start or chunk_end != end:
                title = f"{title} (part {part})"
            identity = {
                "occurrence": occurrence,
                "path": path,
                "physical_page_end": chunk_end,
                "physical_page_start": chunk_start,
                "source_id": source_id,
            }
            digest = hash_bytes(canonical_json_bytes(identity))[:12]
            section_id = (
                f"{source_id}-{portable_slug(title)[:32]}-"
                f"p{chunk_start}-p{chunk_end}-{digest}"
            )
            plans.append(
                {
                    "aliases": list(aliases),
                    "depth": depth,
                    "markdown_path": (
                        f"documents/{source_id}/sections/{section_id}.md"
                    ),
                    "path": list(path),
                    "physical_page_end": chunk_end,
                    "physical_page_start": chunk_start,
                    "section_id": section_id,
                    "source_id": source_id,
                    "title": title,
                }
            )
            occurrence += 1
            chunk_start = chunk_end + 1
            part += 1
    return plans


def _materialize_section(
    plan: Mapping[str, Any],
    pages: list[dict[str, Any]],
) -> dict[str, Any]:
    text_parts: list[str] = []
    spans: list[dict[str, int]] = []
    warnings: set[str] = set()
    length = 0
    for page in pages:
        if text_parts:
            text_parts.append("\n\n")
            length += 2
        page_text = str(page["normalized_text"])
        start = length
        text_parts.append(page_text)
        length += len(page_text)
        spans.append(
            {
                "end": length,
                "physical_page": int(page["physical_page"]),
                "start": start,
            }
        )
        warnings.update(str(item) for item in page["warnings"])
    text = "".join(text_parts)
    content_envelope = {
        "aliases": plan["aliases"],
        "page_spans": spans,
        "path": plan["path"],
        "physical_page_end": plan["physical_page_end"],
        "physical_page_start": plan["physical_page_start"],
        "source_id": plan["source_id"],
        "text": text,
        "title": plan["title"],
        "warnings": sorted(warnings),
    }
    return {
        **dict(plan),
        "content_sha256": hash_bytes(canonical_json_bytes(content_envelope)),
        "page_spans": spans,
        "text": text,
        "warnings": sorted(warnings),
    }


def _yaml_string(value: str) -> str:
    return json.dumps(value, ensure_ascii=False)


def _markdown_section(
    section: Mapping[str, Any],
    pages: list[Mapping[str, Any]],
    source: Mapping[str, Any],
    fingerprint: str,
    previous_section: Mapping[str, Any] | None,
    next_section: Mapping[str, Any] | None,
) -> str:
    start = int(section["physical_page_start"])
    end = int(section["physical_page_end"])
    lines = [
        "---",
        f"reference_contract: {_yaml_string(CONTRACT_VERSION)}",
        f"corpus_fingerprint: {_yaml_string(fingerprint)}",
        f"source_id: {_yaml_string(str(source['source_id']))}",
        f"source_sha256: {_yaml_string(str(source['sha256']))}",
        f"authority: {_yaml_string(str(source['authority']))}",
        f"section_id: {_yaml_string(str(section['section_id']))}",
        f"physical_pages: [{start}, {end}]",
        'evidence_class: "reference_document"',
        "---",
        "",
        f"# {section['title']}",
        "",
        f"Breadcrumb: {' / '.join(str(item) for item in section['path'])}",
        "",
    ]
    navigation: list[str] = ["[Document index](../index.md)"]
    if previous_section is not None:
        previous_name = Path(str(previous_section["markdown_path"])).name
        navigation.append(f"[Previous]({previous_name})")
    if next_section is not None:
        next_name = Path(str(next_section["markdown_path"])).name
        navigation.append(f"[Next]({next_name})")
    lines.extend([" · ".join(navigation), ""])
    pages_by_number = {int(page["physical_page"]): page for page in pages}
    for page_number in range(start, end + 1):
        page = pages_by_number[page_number]
        label = page.get("printed_label")
        suffix = f" (label {label})" if label and str(label) != str(page_number) else ""
        lines.extend([f"## Physical PDF page {page_number}{suffix}", ""])
        page_warnings = page.get("warnings", [])
        if page_warnings:
            lines.extend(
                [
                    f"> Extraction warning: {', '.join(str(item) for item in page_warnings)}",
                    "",
                ]
            )
        text = str(page.get("normalized_text", ""))
        lines.extend([text if text else "_No extractable text._", ""])
    return "\n".join(lines).rstrip() + "\n"


def _initialize_streamed_snapshot(staging: Path) -> None:
    records = staging / "records"
    records.mkdir(parents=True, exist_ok=True)
    for name in ("pages.jsonl", "outlines.jsonl", "sections.jsonl"):
        (records / name).write_bytes(b"")


def _append_jsonl(path: Path, values: Iterable[Mapping[str, Any]]) -> None:
    with path.open("ab") as stream:
        for value in values:
            stream.write(canonical_json_bytes(value))


def _write_source_index(
    staging: Path,
    source: Mapping[str, Any],
    sections: list[dict[str, Any]],
) -> None:
    source_id = str(source["source_id"])
    lines = [
        f"# {source['title']}",
        "",
        f"- Authority: `{source['authority']}`",
        f"- Source SHA-256: `{source['sha256']}`",
        f"- Physical pages: {source['page_count']}",
        f"- [Corpus index](../../index.md)",
        "",
        "## Sections",
        "",
    ]
    for section in sections:
        indent = "  " * int(section["depth"])
        filename = Path(str(section["markdown_path"])).name
        lines.append(
            f"{indent}- [{section['title']}](sections/{filename}) "
            f"(physical pages {section['physical_page_start']}–{section['physical_page_end']})"
        )
    source_index = staging / "documents" / source_id / "index.md"
    source_index.parent.mkdir(parents=True, exist_ok=True)
    source_index.write_text(
        "\n".join(lines).rstrip() + "\n",
        encoding="utf-8",
        newline="\n",
    )


def _extract_source_streamed(
    source: _SourceInput,
    PdfReader: Any,
    PdfDocument: Any,
    max_pages: int,
    max_section_pages: int,
    staging: Path,
    fingerprint: str,
) -> tuple[dict[str, Any], int]:
    reader = _open_reader(source, PdfReader)
    try:
        page_count = len(reader.pages)
    except Exception as error:
        raise ReferenceError(
            "invalid_reference_source",
            "PDF page tree could not be read",
            {"filename": source.declaration.filename},
        ) from error
    if page_count < 1:
        raise ReferenceError(
            "invalid_reference_source",
            "PDF contains no physical pages",
            {"filename": source.declaration.filename},
        )
    if page_count > max_pages:
        raise ReferenceError(
            "reference_limit_exceeded",
            "PDF exceeds the configured page limit",
            {"filename": source.declaration.filename, "page_count": page_count},
        )
    labels, source_warnings = _page_labels(reader, page_count)
    outlines, outline_warnings = _flatten_outline(reader, source.declaration.source_id)
    source_warnings.extend(outline_warnings)
    plans = _section_plans(
        source.declaration.source_id,
        page_count,
        outlines,
        max_section_pages,
    )
    del reader
    _append_jsonl(staging / "records" / "outlines.jsonl", outlines)

    source_for_markdown = {
        **source.declaration.to_dict(),
        "page_count": page_count,
        "sha256": source.sha256,
    }
    states: Counter[str] = Counter()
    warning_count = len(set(source_warnings))
    plan_index = 0
    page_buffer: list[dict[str, Any]] = []
    page_records_path = staging / "records" / "pages.jsonl"
    section_records_path = staging / "records" / "sections.jsonl"
    try:
        text_document = PdfDocument(source.path)
        if len(text_document) != page_count:
            raise ReferenceError(
                "invalid_reference_source",
                "PDF extractors disagree about the physical page count",
                {"filename": source.declaration.filename},
            )
    except ReferenceError:
        raise
    except Exception as error:
        raise ReferenceError(
            "invalid_reference_source",
            "PDF text layer could not be opened",
            {"filename": source.declaration.filename},
        ) from error
    try:
        with page_records_path.open("ab") as page_stream, section_records_path.open(
            "ab"
        ) as section_stream:
            for page_index in range(page_count):
                warnings: list[str] = []
                page_handle = None
                text_handle = None
                try:
                    page_handle = text_document[page_index]
                    text_handle = page_handle.get_textpage()
                    raw = _raw_text(text_handle.get_text_bounded())
                    normalized = _normalized_text(raw)
                    if normalized == raw:
                        raw = normalized
                    state = "text" if normalized else "empty"
                    if not normalized:
                        warnings.append("empty_or_image_only")
                except Exception:
                    raw = ""
                    normalized = ""
                    state = "extraction_failed"
                    warnings.append("page_extraction_failed")
                finally:
                    if text_handle is not None:
                        text_handle.close()
                    if page_handle is not None:
                        page_handle.close()
                states[state] += 1
                warning_count += len(warnings)
                page = {
                    "normalized_text": normalized,
                    "physical_page": page_index + 1,
                    "printed_label": labels[page_index],
                    "raw_text": raw,
                    "source_id": source.declaration.source_id,
                    "state": state,
                    "warnings": warnings,
                }
                page_stream.write(canonical_json_bytes(page))
                page_buffer.append(page)
                plan = plans[plan_index]
                if page_index + 1 == int(plan["physical_page_end"]):
                    section = _materialize_section(plan, page_buffer)
                    section_stream.write(canonical_json_bytes(section))
                    content = _markdown_section(
                        section,
                        page_buffer,
                        source_for_markdown,
                        fingerprint,
                        plans[plan_index - 1] if plan_index else None,
                        plans[plan_index + 1]
                        if plan_index + 1 < len(plans)
                        else None,
                    )
                    markdown = staging / str(section["markdown_path"])
                    markdown.parent.mkdir(parents=True, exist_ok=True)
                    markdown.write_text(content, encoding="utf-8", newline="\n")
                    page_buffer = []
                    plan_index += 1
    finally:
        text_document.close()
    if page_buffer or plan_index != len(plans):
        raise ReferenceError(
            "reference_build_failed",
            "Section streaming did not account for every physical page",
            {"filename": source.declaration.filename},
        )

    metadata_value = source.declaration.to_dict()
    metadata_value.update(
        {
            "byte_size": source.byte_size,
            "outline_entries": len(outlines),
            "page_count": page_count,
            "page_states": {
                state: states.get(state, 0)
                for state in ("text", "empty", "extraction_failed")
            },
            "section_count": len(plans),
            "sha256": source.sha256,
            "warnings": sorted(set(source_warnings)),
        }
    )
    _write_source_index(staging, metadata_value, plans)
    return metadata_value, warning_count


def _write_root_index(
    staging: Path,
    fingerprint: str,
    sources: list[dict[str, Any]],
) -> None:
    lines = [
        "# Authoritative MQL5 Reference Corpus",
        "",
        f"Corpus fingerprint: `{fingerprint}`",
        "",
        "> Generated local derivative. Cite document hashes and physical PDF pages.",
        "",
        "## Documents",
        "",
    ]
    for source in sources:
        source_id = str(source["source_id"])
        lines.append(
            f"- [{source['title']}](documents/{source_id}/index.md) "
            f"— `{source['authority']}`, {source['page_count']} pages"
        )
    (staging / "index.md").write_text(
        "\n".join(lines).rstrip() + "\n",
        encoding="utf-8",
        newline="\n",
    )


def _finalize_streamed_snapshot(
    staging: Path,
    fingerprint: str,
    configuration: Mapping[str, Any],
    sources: list[dict[str, Any]],
    *,
    pages: int,
    sections: int,
    warnings: int,
) -> dict[str, Any]:
    files: list[dict[str, Any]] = []
    for path in sorted(
        (item for item in staging.rglob("*") if item.is_file()),
        key=lambda item: item.relative_to(staging).as_posix(),
    ):
        files.append(
            {
                "byte_size": path.stat().st_size,
                "path": path.relative_to(staging).as_posix(),
                "sha256": hash_file(path),
            }
        )
    manifest = {
        "complete": True,
        "configuration": dict(configuration),
        "contract_version": CONTRACT_VERSION,
        "corpus_fingerprint": fingerprint,
        "counts": {
            "documents": len(sources),
            "pages": pages,
            "sections": sections,
            "warnings": warnings,
        },
        "files": files,
        "sources": sources,
    }
    write_json(staging / "manifest.json", manifest)
    return manifest


def build_reference_corpus(request: BuildRequest) -> dict[str, Any]:
    """Build and atomically publish one complete local corpus snapshot."""

    request.validate()
    PdfReader, PdfDocument, extractors = _load_pdf_extractors()
    sources = _prepare_sources(request)
    configuration = {
        "extractors": extractors,
        "max_pages_per_section": request.max_pages_per_section,
        "max_pages_per_source": request.max_pages_per_source,
        "max_pdf_bytes": request.max_pdf_bytes,
        "normalization_version": NORMALIZATION_VERSION,
    }
    identity = {
        "configuration": configuration,
        "contract_version": CONTRACT_VERSION,
        "sources": [
            {
                **source.declaration.to_dict(),
                "byte_size": source.byte_size,
                "sha256": source.sha256,
            }
            for source in sources
        ],
    }
    fingerprint = hash_bytes(canonical_json_bytes(identity))

    output = request.output_dir.resolve()
    output.mkdir(parents=True, exist_ok=True)
    snapshots = output / "snapshots"
    snapshots.mkdir(exist_ok=True)
    final_snapshot = snapshots / fingerprint
    if final_snapshot.exists():
        from .corpus import validate_snapshot

        manifest, _, _ = validate_snapshot(final_snapshot, fingerprint)
        pointer = {
            "contract_version": CONTRACT_VERSION,
            "corpus_fingerprint": fingerprint,
            "manifest_sha256": hash_file(final_snapshot / "manifest.json"),
            "snapshot_path": f"snapshots/{fingerprint}",
        }
        atomic_write_json(output / "current.json", pointer)
        return _build_result(manifest, pointer, reused=True)

    staging = output / f".staging-{uuid.uuid4().hex}"
    staging.mkdir()
    try:
        _initialize_streamed_snapshot(staging)
        source_records: list[dict[str, Any]] = []
        page_count = 0
        section_count = 0
        warning_count = 0
        for source in sources:
            metadata_value, source_warning_count = _extract_source_streamed(
                source,
                PdfReader,
                PdfDocument,
                request.max_pages_per_source,
                request.max_pages_per_section,
                staging,
                fingerprint,
            )
            if (
                source.path.stat().st_size != source.byte_size
                or hash_file(source.path) != source.sha256
            ):
                raise ReferenceError(
                    "reference_source_changed",
                    "PDF changed while the corpus was being built",
                    {"filename": source.declaration.filename},
                )
            source_records.append(metadata_value)
            page_count += int(metadata_value["page_count"])
            section_count += int(metadata_value["section_count"])
            warning_count += source_warning_count

        _verify_sources_unchanged(sources)
        _write_root_index(staging, fingerprint, source_records)
        manifest = _finalize_streamed_snapshot(
            staging,
            fingerprint,
            configuration,
            source_records,
            pages=page_count,
            sections=section_count,
            warnings=warning_count,
        )
        _verify_sources_unchanged(sources)
        from .corpus import validate_snapshot

        validate_snapshot(staging, fingerprint)
        os.replace(staging, final_snapshot)
        pointer = {
            "contract_version": CONTRACT_VERSION,
            "corpus_fingerprint": fingerprint,
            "manifest_sha256": hash_file(final_snapshot / "manifest.json"),
            "snapshot_path": f"snapshots/{fingerprint}",
        }
        atomic_write_json(output / "current.json", pointer)
        return _build_result(manifest, pointer, reused=False)
    except ReferenceError:
        raise
    except (OSError, ValueError) as error:
        raise ReferenceError(
            "reference_build_failed",
            "Reference corpus build failed",
            {"reason": str(error)},
        ) from error
    finally:
        if staging.exists() and staging.parent == output:
            shutil.rmtree(staging)


def _verify_sources_unchanged(sources: Iterable[_SourceInput]) -> None:
    for source in sources:
        try:
            unchanged = (
                source.path.stat().st_size == source.byte_size
                and hash_file(source.path) == source.sha256
            )
        except OSError:
            unchanged = False
        if not unchanged:
            raise ReferenceError(
                "reference_source_changed",
                "PDF changed while the corpus was being built",
                {"filename": source.declaration.filename},
            )


def _build_result(
    manifest: Mapping[str, Any],
    pointer: Mapping[str, Any],
    *,
    reused: bool,
) -> dict[str, Any]:
    warnings = sorted(
        {
            str(warning)
            for source in manifest["sources"]
            for warning in source.get("warnings", [])
        }
    )
    return {
        "contract_version": CONTRACT_VERSION,
        "corpus_fingerprint": pointer["corpus_fingerprint"],
        "counts": manifest["counts"],
        "manifest_sha256": pointer["manifest_sha256"],
        "reused": reused,
        "snapshot_path": pointer["snapshot_path"],
        "sources": manifest["sources"],
        "warnings": warnings,
    }
