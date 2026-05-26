# LOGOS 2.0 Recovery Plan: Re-integrate Docling as Evidence Extractor

## Problem

Docling was incorrectly removed entirely. It should be retained as a **lightweight evidence extraction tool** that feeds into the paper skill pack system, not as a heavy ontology builder.

## Solution

Re-introduce Docling as the **Section/Figure/Table Extractor** that:
1. Parses PDF → markdown sections, figures, tables
2. Generates `section_index.json` and `evidence_index.json`
3. Feeds extracted content into `PaperSkillBuilder`
4. Supports `OnDemandDeepReaderAgent` for PDF section fallback

## What Docling Actually Does (Correct Usage)

```
PDF URL
  ↓
Docling Parser (extraction only, no LLM reasoning)
  ↓
├─ document.md (parsed sections)
├─ tables/ (CSV files)
├─ figures/ (PNG files)
└─ section_index.json (section → page mapping)
  ↓
PaperSkillBuilder reads these to generate reference guides
```

## Architecture Changes

### 1. Re-add `src/logos2/extraction/` (NEW, not old)

Create lightweight extraction module:

```
src/logos2/extraction/
├── __init__.py
├── docling_parser.py      # Wrapper around Docling
├── section_indexer.py     # Generate section_index.json
└── evidence_indexer.py    # Generate evidence_index.json
```

Key difference from old LOGOS:
- Old: Docling → DeepReader → heavy Neo4j nodes (Claim, Evidence, Figure nodes)
- New: Docling → file-based index → PaperSkillPack (no heavy Neo4j)

### 2. Modify `PaperSkillBuilder`

Current (placeholder):
- Creates basic `section_index.json` with hardcoded sections
- `evidence_index.json` from `missing_fields` (wrong!)

New (using Docling output):
- Read `document.md` to get actual sections
- Read tables/figures directories to index evidence
- Generate accurate `section_index.json` with real page numbers
- Generate accurate `evidence_index.json` with real figure/table info
- Create reference guides that cite actual extracted sections

### 3. Create `OnDemandDeepReaderAgent`

Missing component that uses Docling output:

```
Input: user question + section_index + evidence_index + original PDF
Output: DeepReadingResult with actual section content

Capabilities:
- Read specific section from document.md
- Extract figure/table based on evidence_index
- Read specific PDF page range (if needed)
```

### 4. Update `QAAgent` fallback

Current:
```python
_read_pdf_section() → returns "[PDF content from {path}]"  # placeholder
```

New:
```python
_read_pdf_section() → calls OnDemandDeepReaderAgent with section_index
```

## Implementation Plan

### Phase 1: Re-add Docling Extraction (Lightweight)

**Files to create:**

1. `src/logos2/extraction/__init__.py`
2. `src/logos2/extraction/docling_parser.py`
   - Thin wrapper around Docling
   - Extract: document.md, tables/, figures/
   - No LLM processing, no Neo4j writes
3. `src/logos2/extraction/section_indexer.py`
   - Parse document.md → section_index.json
   - Map sections to page numbers
4. `src/logos2/extraction/evidence_indexer.py`
   - Index figures/tables from Docling output
   - Generate evidence_index.json

### Phase 2: Update PaperSkillBuilder

**Files to modify:**

1. `src/logos2/nodes/paper_skill_builder.py`
   - Accept optional Docling output path
   - Read actual section structure
   - Generate accurate indexes
   - Create reference guides with real section references

### Phase 3: Create OnDemandDeepReaderAgent

**Files to create:**

1. `src/logos2/nodes/deep_reader.py`
   - Read document.md sections
   - Read figure/table files
   - Optional: read PDF directly for un-extracted content

### Phase 4: Update QAAgent Fallback

**Files to modify:**

1. `src/logos2/nodes/qa_agent.py`
   - Replace placeholder _read_pdf_section()
   - Integrate OnDemandDeepReaderAgent
   - Use actual section_index/evidence_index

## Directory Structure After Recovery

```
LOGOS/
├── src/logos2/
│   ├── extraction/              # NEW: Docling-based extraction
│   │   ├── docling_parser.py
│   │   ├── section_indexer.py
│   │   └── evidence_indexer.py
│   ├── adapters/
│   ├── nodes/
│   │   ├── deep_reader.py       # NEW: OnDemandDeepReaderAgent
│   │   └── qa_agent.py          # UPDATED: real fallback
│   └── ...
├── paper_library/               # NEW: Docling output goes here
│   └── {paper_id}/
│       ├── original.pdf
│       ├── document.md          # Docling output
│       ├── tables/
│       ├── figures/
│       └── extraction_meta.json
└── ...
```

## Usage Flow

### Full Pipeline with Docling

```
User input: "Survey GraphRAG methods"
  ↓
PaperNavigatorAdapter loads artifacts
  ↓
SurveyTaxonomyAgent generates taxonomy
  ↓
ProfileNormalizer creates profiles
  ↓
For each new paper not yet extracted:
  DoclingExtractor.extract(pdf_path) → paper_library/{id}/
  ↓
PaperSkillBuilder uses extraction output to build skill pack
  ↓
LightweightGraphIndexer writes to Neo4j (no heavy nodes)
  ↓
QA ready
```

### QA with Docling Evidence

```
User: "What does Figure 3 show in the MRAG paper?"
  ↓
QAAgent routes to figures_and_tables.md
  ↓
Content insufficient → fallback to PDF
  ↓
OnDemandDeepReaderAgent:
  1. Check evidence_index.json → "fig_3: page 5, caption '...'"
  2. Read figures/figure_3.png or PDF page 5
  3. Return actual content
  ↓
Answer with real figure content
```

## Key Principles (Don't Repeat Old Mistakes)

1. **Docling is extraction-only**: No LLM reasoning, no ontology building
2. **Output is file-based**: document.md, CSV, PNG, JSON indexes
3. **Neo4j stays lightweight**: Only Paper/Theme/Benchmark nodes, no Figure/Table/Claim nodes
4. **PaperSkillPack owns the structure**: Indexes point to files, Neo4j points to skill packs
5. **OnDemandDeepReader is optional**: Only invoked when skill pack insufficient

## Files to Delete (None - we already cleaned)

The old heavy ontology files are already removed and stay removed:
- Old `src/core/` (DeepReaderAgent with heavy extraction) ✓ already deleted
- Old `scripts/run_phase2.py` (heavy pipeline) ✓ already deleted

## Files to Modify

1. `src/logos2/nodes/paper_skill_builder.py`
2. `src/logos2/nodes/qa_agent.py`
3. `requirements.txt` (re-add Docling dependency)

## Files to Create

1. `src/logos2/extraction/docling_parser.py`
2. `src/logos2/extraction/section_indexer.py`
3. `src/logos2/extraction/evidence_indexer.py`
4. `src/logos2/nodes/deep_reader.py` (OnDemandDeepReaderAgent)
5. `src/logos2/extraction/__init__.py`

## Dependencies to Add

```
# In requirements.txt
docling>=1.0.0
```

## Success Criteria

1. PaperSkillBuilder generates accurate section_index.json from actual PDF structure
2. EvidenceIndex includes real figure/table captions and page numbers
3. QAAgent can read actual PDF sections via OnDemandDeepReaderAgent
4. No heavy Neo4j nodes created (Paper node only stores skill_path)
5. Original PDF and Docling outputs stay in paper_library/ (file-based)
