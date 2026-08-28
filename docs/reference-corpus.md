# Reference Corpus

The reference subsystem (`mql5_kg/reference/`) ingests offline MQL5
documentation and books (PDFs) into an immutable, searchable local corpus.
It is a **separate subsystem** from the code graph — reference knowledge never
becomes code-graph truth (Invariant 10), and every reference result retains
citation evidence (`evidence_class: "reference_document"`).

## Conceptual separation

```
CodeGraph              ReferenceCorpus
   (source truth)          (documentation)
      ≠                        |
                               +→ every result cites
                                   source hash + physical pages
```

## Build a corpus

### Prerequisites

```bash
pip install -e ".[reference]"     # pypdf + pypdfium2
```

### Structure your inputs

Put PDFs in an input directory. The builder auto-declares known sources:

| Filename | source_id | authority |
|----------|-----------|-----------|
| `mql5.pdf` | `mql5-reference` | `normative` |
| `mql5book.pdf` | `mql5-programming-book` | `explanatory` |
| `neuronetworksbook.pdf` | `mql5-neural-networks-book` | `specialist` |

For other PDFs you can provide an explicit source manifest
(`contract_version: "1.0.0"` with a `sources` list of `source_id`,
`filename`, `title`, `authority` (`normative`/`explanatory`/`specialist`/
`unclassified`), `role`, optional `official_url` and `expected_sha256`).

### Build

```python
from pathlib import Path
from mql5_kg.reference import BuildRequest, ReferenceError, build_reference_corpus

try:
    result = build_reference_corpus(BuildRequest(
        input_dir=Path("/data/pdf-in"),
        output_dir=Path("/data/corpus"),
        # sources_path=Path("/data/sources.json"),   # optional explicit manifest
        # max_pdf_bytes=512*1024*1024,
        # max_pages_per_source=20000,
        # max_pages_per_section=32,
    ))
    print(result["corpus_fingerprint"], result["counts"])
except ReferenceError as error:
    print(error.code, error.message, error.details)
```

The build extracts text per physical page, organizes it into sections from
the PDF outline, validates every canonical byte and structural invariant, and
**atomically publishes** a snapshot under `output_dir/snapshots/<fingerprint>`
with a `current.json` pointer. Building identical input reuses the snapshot.

## Search

Reading and searching an existing corpus uses only the Python standard
library.

```python
from mql5_kg.reference import ReferenceCorpus, ReferenceError

corpus = ReferenceCorpus.open("/data/corpus")

hits = corpus.search("OrderSend", limit=20, max_excerpt_chars=1200)
for result in hits["results"]:
    print(result["source"]["title"],
          result["citation"]["physical_page_start"],
          result["excerpt"][:80])

excerpt = corpus.excerpt(hits["results"][0]["section"]["section_id"],
                         max_chars=1200)
```

Every result carries:

- `evidence_class: "reference_document"`
- `corpus_fingerprint`
- `citation` — physical page range and character offsets
- `source` — SHA-256, authority, title, official URL
- `score` — authority rank, exact vs phrase vs term match, occurrences

## Authority

Authorities rank results deterministically:
`normative` (300) > `explanatory` (200) > `specialist` (100) >
`unclassified` (0). Higher-authority matches sort first.

## Integrity & security

- Every snapshot file is content-addressed and hash-verified against the
  manifest; any mismatch fails validation.
- Canonical paths are confined to the corpus root — `..` traversal,
  absolute paths, and symlink escapes are rejected.
- Size limits are enforced (manifest, inventory, page lines, total bytes).
- Input and output directories must not overlap; source PDFs must be regular
  files (no symlinks).
- Build publication is atomic: a failed build never leaves a partial corpus as
  `current`.

## Limitations

- Requires the optional `reference` extra to *build* a corpus (reading does
  not).
- PDFs with no extractable text layer (image-only) produce `empty_or_image_only`
  / `extraction_failed` warnings; only the outline-derived section structure is
  guaranteed.
- The corpus is immutable per fingerprint; rebuilding with the same input is a
  no-op (reused pointer).