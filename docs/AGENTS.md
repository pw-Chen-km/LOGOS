# LOGOS 2.0 Agent Architecture

LOGOS 2.0 uses a schema-constrained multi-agent workflow.
Agents are not free-form autonomous workers. Each agent has a bounded role,
typed input, typed output, explicit state transition, and a defined failure
policy.

## Core Principle

Paper Skill Pack is the canonical per-paper knowledge entry.
Neo4j is only a lightweight routing index.
Original PDF or parsed sections are the final evidence source, but they are
read only by an explicit on-demand reader path.

## Agent Types

### Adapter Nodes

Adapter nodes do not reason. They normalize external artifacts, validate
schemas, and write storage.

- `PaperNavigatorAdapter`
- `ProfileNormalizer`
- `LightweightGraphIndexer`

### Worker Agents

Worker agents may use LLM reasoning, but must produce structured artifacts.

- `ResearchIntentAgent`
- `SurveyTaxonomyAgent`
- `PaperSkillBuilderAgent`
- `QAAgent`

### Optional High-Cost Agents

These agents are not part of the default research pipeline.

- `EdgeVerifierAgent`
- `OnDemandDeepReaderAgent`

## Agent Definitions

### ResearchIntentAgent

Purpose:
Convert a natural language research idea into `ResearchRequest`.

Input:
- `raw_user_input: str`

Output:
- `ResearchRequest`

Agency level:
- Medium

LLM:
- Yes, when enabled.
- MVP currently uses simplified rule-based intake in `LogosResearchWorkflow`.

Tools:
- No external tools by default.

State mutation:
- May write `research_request`, `request_id`, and intake trace fields.

Failure policy:
- If intent clarification fails, preserve `raw_user_input` and emit a minimal
  `ResearchRequest` with missing fields marked or left empty.

Default:
- Optional for artifact-first MVP.

### PaperNavigatorAdapter

Purpose:
Load paper-navigator reading artifacts and validate them.

Input:
- Artifact path or artifact directory.

Output:
- `List[PaperNavigatorReading]`

Agency level:
- Low

LLM:
- No.

Tools:
- File system read only.
- Future production mode may call EvoScientist / EvoSkills externally, but
  that must stay behind the adapter boundary.

State mutation:
- May write `paper_candidates`, `paper_navigator_readings`, and discovery
  status fields.

Failure policy:
- If artifacts are missing or invalid, fail explicitly. Do not fabricate paper
  discovery results.

Default:
- Yes.

### SurveyTaxonomyAgent

Purpose:
Build survey taxonomy, method families, benchmark matrix, dataset matrix,
baseline matrix, and candidate relations.

Input:
- `List[PaperNavigatorReading]`
- `ResearchRequest`

Output:
- `SurveyTaxonomy`

Agency level:
- Medium

LLM:
- Yes in full mode.
- MVP may use deterministic or heuristic grouping.

Tools:
- No network tools by default.
- May read local artifacts.

State mutation:
- May write `survey_taxonomy`, `taxonomy_id`, `candidate_edges`, and taxonomy
  status fields.

Failure policy:
- If taxonomy generation fails, preserve validated paper readings and record a
  failed taxonomy status. Do not continue to graph indexing with malformed
  taxonomy.

Default:
- Yes.

### ProfileNormalizer

Purpose:
Merge paper-navigator reading output and survey taxonomy into `PaperProfile`.

Input:
- `PaperNavigatorReading`
- `SurveyTaxonomy`
- optional paper metadata

Output:
- `PaperProfile`
- `paper_profile.json`

Agency level:
- Low

LLM:
- No by default.

Tools:
- File system write for profile artifacts.

State mutation:
- May write `paper_profiles` and profile status fields.

Failure policy:
- Missing details must be recorded in `missing_fields`.
- It must not silently call a heavy parser.

Default:
- Yes.

### PaperSkillBuilderAgent

Purpose:
Generate a progressive-disclosure paper skill pack.

Input:
- `PaperProfile`
- optional Docling extraction directory (`paper_library/{paper_id}/`)
  - `document.md` - parsed markdown from PDF
  - `tables/` - CSV files
  - `figures/` - PNG files
  - `extraction_meta.json` - metadata

Output:
- `PaperSkillManifest`
- `SKILL.md`
- `metadata.json`
- `paper_profile.json`
- `section_index.json` (from actual document sections if available)
- `evidence_index.json` (from actual figures/tables if available)
- `references/*.md`

Agency level:
- High

LLM:
- Yes in full mode.
- MVP currently generates reference guides from profile fields.
- If Docling extraction is available, uses actual document structure for indexes.

Tools:
- File system read (Docling extraction output).
- File system write (skill pack generation).
- No Neo4j writes.

State mutation:
- May write `paper_skill_paths` and skill-build status fields.

Failure policy:
- If a reference guide cannot be generated, keep the skill pack but mark the
  missing section in `metadata.json` and `missing_fields`.
- If Docling extraction is missing, generates placeholder section/evidence index.

Default:
- Yes.

Current implementation note:
- Uses `SectionIndexer` to parse `document.md` headers into accurate section index.
- Uses `EvidenceIndexer` to index actual `figures/` and `tables/` directories.
- Falls back to placeholder index if Docling extraction not available.

### LightweightGraphIndexer

Purpose:
Write lightweight routing metadata to Neo4j.

Input:
- `PaperProfile`
- `PaperSkillManifest`
- `SurveyTaxonomy`
- candidate relations

Output:
- `GraphWriteReport`
- Neo4j nodes and edges

Agency level:
- Low

LLM:
- No.

Tools:
- Neo4j write access.

State mutation:
- May write `neo4j_index_status` and indexing status fields.

Failure policy:
- Failed graph writes must return a structured error report.
- It must not mutate paper skill packs.

Default:
- Yes when Neo4j is configured.

### QAAgent

Purpose:
Answer user questions by routing through the lightweight Neo4j index and paper
skill packs.

Input:
- `UserQuery`
- Neo4j lightweight index
- `PaperSkillPack`

Output:
- `Answer`
- `RoutingTrace`
- files read
- source paper IDs

Agency level:
- High

LLM:
- Yes in full mode.
- MVP currently uses rule-based query classification and template synthesis.

Tools:
- Neo4j read access.
- File system read access for `paper_profile.json`, `SKILL.md`, reference
  guides, `section_index.json`, `evidence_index.json`, and parsed sections.

State mutation:
- May write `qa_trace`, `qa_answer`, and QA status fields.

Failure policy:
- If skill references are insufficient, route to `OnDemandDeepReaderAgent`.
- If the on-demand reader is unavailable, return an explicit insufficient
  evidence answer instead of hallucinating.

Default:
- Yes.

Current implementation note:
- The current `QAAgent` can route to `paper_profile.json` and reference guide
  files.
- PDF fallback uses `OnDemandDeepReaderAgent` which reads actual sections from
  Docling extraction output (`document.md`).
- Section matching uses `section_index.json` to find correct page/anchor.

### EdgeVerifierAgent

Purpose:
Verify candidate cross-paper relations using paper skills and original PDFs if
necessary.

Input:
- `CandidateEdge` or `CandidateRelation`

Output:
- `VerifiedEdge`

Agency level:
- High

LLM:
- Yes in full mode.
- MVP currently uses profile/reference-guide evidence and heuristic matching.

Tools:
- File system read access to paper skill packs.
- Neo4j write access to update relation status.
- May call `OnDemandDeepReaderAgent` only when evidence is insufficient.

State mutation:
- May write `verified_edges`, `rejected_edges`, and verification status fields.

Failure policy:
- Candidate edges must remain candidates unless sufficient evidence supports
  verification.
- Verification failure must not delete the original candidate edge.

Default:
- No.

### OnDemandDeepReaderAgent

Purpose:
Read original PDF sections or parsed sections when paper profile and skill
references are insufficient.

Input:
- user question
- `PaperSkillPack`
- `section_index.json`
- `evidence_index.json`
- original PDF path
- optional parsed markdown section path

Output:
- `DeepReadingResult`
- cited section/page/table/figure evidence

Agency level:
- High

LLM:
- Yes.

Tools:
- File system read access.
- PDF/text extraction tools.
- Optional OCR/table/figure extraction tools.

State mutation:
- May append evidence to QA trace.
- Must not rewrite canonical `paper_profile.json` unless an explicit
  enrichment workflow is requested.

Failure policy:
- If exact PDF/section evidence cannot be read, return `insufficient_evidence`
  with the intended file and section target.

Default:
- No.

Current implementation note:
- **IMPLEMENTED** in `src/logos2/nodes/deep_reader.py`.
- Can read sections from `document.md` using `section_index.json`.
- Can read figure/table metadata from `evidence_index.json` and files from
  `figures/`, `tables/` directories.
- Returns `DeepReadingResult` with content and citation info.
- Full PDF page extraction (not just Docling output) is still a placeholder.

## State Mutation Rules

- Adapter nodes may only normalize or write validated artifacts.
- Worker agents may update only their assigned workflow state fields.
- Optional high-cost agents must be explicitly triggered.
- No agent may silently invoke heavy parsing during default ingestion.
- No agent may write heavyweight paper-internal Neo4j nodes.

## Fallback Policy

Default QA order:

1. Search lightweight Neo4j index.
2. Read `paper_profile.json`.
3. Read `SKILL.md`.
4. Read the routed reference guide.
5. Read `section_index.json` and `evidence_index.json`.
6. Call `OnDemandDeepReaderAgent` for parsed sections or original PDF.
7. If evidence is still missing, answer with insufficient evidence.

## PDF and Section Parsing Policy

LOGOS 2.0 does not require Docling as the default parser.

The expected source of parsed paper structure is:

1. `paper-navigator` reading artifacts.
2. `section_index.json` emitted by paper-navigator or a lightweight section
   indexer.
3. `evidence_index.json` emitted from parsed markdown, PDF metadata, or a
   dedicated on-demand reader.
4. Original PDF as the final evidence source.

If Docling is not used, the system must still receive or generate:

- section boundaries
- page ranges
- figure/table captions
- figure/table page locations
- optional markdown anchors

These fields belong in `section_index.json` and `evidence_index.json`, not in
Neo4j.

