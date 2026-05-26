# LOGOS 2.0 專案說明

LOGOS 2.0 是一個 **paper-skill-centered research management system**。它的核心目標不是把每篇論文拆成大量 Neo4j 節點，而是把每篇 paper 轉成一個可導航、可檢索、可 fallback 到原始 evidence 的 **Paper Skill Pack**。

開源整理後，LOGOS 2.0 的預設配置是 artifact/direct-first，方便在沒有 API key、沒有 EvoScientist runtime 的環境下安裝與測試。EvoScientist survey agent 仍是正式支援的進階整合，透過 `configs/logos2.survey-agent.yaml` 和 optional dependency 邊界啟用。

一句話定位：

> LOGOS 2.0 turns research intent and paper-navigator artifacts into paper profiles, paper skill packs, a lightweight Neo4j routing graph, and a skill-guided QA runtime.

## 核心設計

LOGOS 2.0 的儲存責任分成三層：

1. `Paper Skill Pack` 是單篇 paper 的 canonical knowledge entry。
2. `Neo4j` 只作為 lightweight research map / routing index。
3. `original.pdf` / `document.md` / `figures/` / `tables/` 是最終 evidence source。

因此，LOGOS 2.0 不做舊版那種 heavy paper-internal Neo4j graph。以下內容不預設進 Neo4j：

- Claim
- Evidence
- Figure
- Table
- Result
- Metric
- Experiment
- ResearchProblem
- MethodDetail

這些細節保存在 file-based skill pack 與 Docling extraction output 裡。

## 目前目錄結構

```text
LOGOS/
  src/
    logos2/
      adapters/
        evoscientist/
          paper_navigator_adapter.py

      extraction/
        docling_parser.py
        section_indexer.py
        evidence_indexer.py

      nodes/
        survey_taxonomy.py
        profile_normalizer.py
        paper_skill_builder.py
        lightweight_graph_indexer.py
        qa_agent.py
        edge_verifier.py
        deep_reader.py

      schemas/
        research_request.py
        paper_navigator_reading.py
        survey_taxonomy.py
        paper_profile.py
        paper_skill_manifest.py
        candidate_edge.py
        verified_edge.py

      storage/
        neo4j_repository.py
        skill_registry.py

      workflow/
        state.py
        graph.py
        trace.py

      cli/
        main.py

  artifacts/
  paper_library/
  paper_skills/
  docs/
  tests/
```

## 資料來源

LOGOS 2.0 目前有三種主要輸入。

### 1. Paper Navigator Reading Artifacts

來源：`artifacts/` 或外部 EvoScientist / EvoSkills `paper-navigator`。

schema：`PaperNavigatorReading`

用途：

- paper id
- title
- tldr
- problem statement
- main contribution
- method intuition
- benchmarks
- datasets
- baselines
- reading level
- confidence
- missing fields

目前 MVP 是 artifact-first，也就是先讀本地 JSON，不直接在 LOGOS 裡實作 paper discovery。

### 2. Survey Taxonomy

來源：`SurveyTaxonomyGenerator`

schema：`SurveyTaxonomy`

用途：

- themes
- subthemes
- paper taxonomy assignments
- method families
- problem clusters
- benchmark matrix
- dataset matrix
- baseline matrix
- candidate paper relations

MVP 目前可以用 heuristic / deterministic grouping。完整版本可改接 research-survey 類 agent。

### 3. Docling Extraction Output

來源：`DoclingExtractor`

輸出位置：

```text
paper_library/<paper_id>/
  original.pdf
  document.md
  tables/
  figures/
  extraction_meta.json
```

用途：

- `document.md` 提供 parsed sections。
- `tables/` 提供 table CSV evidence。
- `figures/` 提供 figure image evidence。
- `extraction_meta.json` 提供 extraction 統計與來源資訊。

Docling 在 LOGOS 2.0 裡只負責 **evidence extraction**，不負責 LLM reasoning，也不負責寫 Neo4j heavy nodes。

## 完整流程

目前的主要流程如下：

```text
User Research Intent
  ↓
ResearchIntentAgent / simplified intake
  ↓
PaperNavigatorAdapter
  ↓
SurveyTaxonomyGenerator
  ↓
ProfileNormalizer
  ↓
DoclingExtractor / SectionIndexer / EvidenceIndexer
  ↓
PaperSkillBuilderAgent
  ↓
LightweightGraphIndexer
  ↓
QAAgent
  ↓
Optional EdgeVerifierAgent
  ↓
Optional OnDemandDeepReaderAgent
```

## 各階段說明

### 1. Intent Intake

實作位置：

- `src/logos2/workflow/graph.py`

目前 MVP 是 rule-based intake：

- 從 user input 建立 `request_id`
- 保留 `raw_user_input`
- 建立簡化版 `research_request`
- 嘗試抽取 paper count / year range

完整版本可以改成 LLM-based `ResearchIntentAgent`。

### 2. Paper Discovery / Reading Artifact Loading

實作位置：

- `src/logos2/adapters/evoscientist/paper_navigator_adapter.py`

目前行為：

- 從 `artifacts/` 載入 `PaperNavigatorReading`
- 驗證 schema
- 不偽造 discovery 結果

未來行為：

- adapter 後面接 EvoScientist / EvoSkills `paper-navigator`
- 由 paper-navigator 做 search、citation traversal、PDF acquisition、L1/L2/L3 reading

### 3. Survey Taxonomy Generation

實作位置：

- `src/logos2/nodes/survey_taxonomy.py`

輸入：

- `List[PaperNavigatorReading]`

輸出：

- `SurveyTaxonomy`

功能：

- 建立 themes / subthemes
- 建立 method families
- 建立 benchmark / dataset / baseline matrix
- 產生 candidate relations

注意：

- Candidate relations 是 cheap edges。
- 預設不做 expensive verification。

### 4. Profile Normalization

實作位置：

- `src/logos2/nodes/profile_normalizer.py`

輸入：

- `PaperNavigatorReading`
- `SurveyTaxonomy`
- optional metadata

輸出：

- `paper_profile.json`
- `PaperProfile`

責任：

- 合併 reading artifact 與 taxonomy assignment。
- 產生單篇 paper 的 canonical lightweight profile。
- 不呼叫 LLM。
- 不啟動 heavy parser。
- 缺漏只寫入 `missing_fields`。

### 5. Docling Evidence Extraction

實作位置：

- `src/logos2/extraction/docling_parser.py`
- `src/logos2/extraction/section_indexer.py`
- `src/logos2/extraction/evidence_indexer.py`

Docling extraction 產生：

```text
paper_library/<paper_id>/
  document.md
  tables/table_001.csv
  figures/figure_001.png
  extraction_meta.json
```

`SectionIndexer` 會從 `document.md` 解析 markdown headers，產生：

```text
section_index.json
```

`EvidenceIndexer` 會從 `figures/` 與 `tables/` 建立：

```text
evidence_index.json
```

注意：

- Docling 是 Python 套件，需透過 `pip install docling` 或 `pip install -r requirements.txt` 安裝。
- 目前 Docling extraction module 已存在。
- 目前 workflow 尚未自動在 skill build 前跑 `DoclingExtractor.extract()`；需要在下一步把 extraction 串進 pipeline。

### 6. Paper Skill Building

實作位置：

- `src/logos2/nodes/paper_skill_builder.py`

輸入：

- `PaperProfile`
- optional `extraction_dir`

輸出：

```text
paper_skills/<paper_id>/
  SKILL.md
  metadata.json
  paper_profile.json
  section_index.json
  evidence_index.json
  references/
    problem_and_motivation.md
    method_guide.md
    experiment_guide.md
    benchmark_and_baselines.md
    figures_and_tables.md
    limitations.md
```

`SKILL.md` 不是完整摘要，而是 routing manual。它負責告訴 QA agent：

- 哪些問題讀 `paper_profile.json`
- 哪些問題讀 `references/problem_and_motivation.md`
- 哪些問題讀 `references/method_guide.md`
- 哪些問題讀 `references/experiment_guide.md`
- 哪些問題讀 `references/figures_and_tables.md`
- 什麼情況 fallback 到 `document.md` / `original.pdf`

如果有 Docling extraction output，`PaperSkillBuilder` 會使用真實 section / figure / table 結構建立 index。

如果沒有 Docling extraction output，會退回 placeholder section / evidence index。

### 7. Lightweight Neo4j Indexing

實作位置：

- `src/logos2/storage/neo4j_repository.py`
- `src/logos2/nodes/lightweight_graph_indexer.py`

Neo4j 寫入：

```text
Paper
Theme
MethodFamily
Benchmark
Dataset
Baseline
```

Edges：

```text
Paper -[:BELONGS_TO_THEME]-> Theme
Paper -[:USES_METHOD_FAMILY]-> MethodFamily
Paper -[:EVALUATED_ON]-> Benchmark
Paper -[:USES_DATASET]-> Dataset
Paper -[:COMPARES_WITH]-> Baseline
Paper -[:RELATED_TO {status, source, confidence, verified}]-> Paper
```

Neo4j 不保存 paper 內部 evidence。它只保存 routing metadata：

- `paper_id`
- `title`
- `tldr`
- `theme`
- `method_family`
- `skill_path`
- `profile_path`
- `pdf_path`

### 8. QA Runtime

實作位置：

- `src/logos2/nodes/qa_agent.py`
- `src/logos2/nodes/deep_reader.py`
- `src/logos2/storage/skill_registry.py`

QA 流程：

```text
User question
  ↓
QAAgent._classify_query()
  ↓
Neo4j full-text / theme search
  ↓
SkillRegistry 找到 paper skill
  ↓
讀 paper_profile.json
  ↓
根據 query type 讀 reference guide
  ↓
如果 reference guide 不夠，呼叫 OnDemandDeepReaderAgent
  ↓
OnDemandDeepReaderAgent 讀 document.md / tables / figures
  ↓
回傳答案與 files_read trace
```

目前 query type 是 rule-based：

- `single_paper_summary`
- `single_paper_problem`
- `method_intuition`
- `technical_detail`
- `experiment_evidence`
- `benchmark_comparison`
- `table_or_figure_question`
- `cross_paper_comparison`
- `survey_landscape`

目前答案 synthesis 是 template-based。完整版本可加入 LLM synthesizer，但輸入必須只來自已讀 evidence。

### 9. Optional Edge Verification

實作位置：

- `src/logos2/nodes/edge_verifier.py`

用途：

- 將 candidate edge 升級成 verified / weak_verified / rejected。

觸發時機：

- 使用者要求驗證兩篇 paper 關係。
- QA answer 依賴某條 candidate edge。
- 需要高可信 related-work graph。

預設：

- 不跑。
- 不對所有 candidate edge 做 pairwise verification。

## Agent Runtime 怎麼運作

目前 runtime 是 **step-based workflow runtime**，不是完整 LangGraph execution runtime。

入口：

- `src/logos2/workflow/graph.py`
- class：`LogosResearchWorkflow`

初始化時會建立：

```python
self.tracer = WorkflowTracer()
self.navigator = PaperNavigatorAdapter(...)
self.taxonomy_generator = SurveyTaxonomyGenerator(...)
self.normalizer = ProfileNormalizer(...)
self.skill_builder = PaperSkillBuilder(...)
self.repository = Neo4jRepository(...)
self.skill_registry = SkillRegistry(...)
self.indexer = LightweightGraphIndexer(...)
self.qa_agent = QAAgent(...)
self.edge_verifier = EdgeVerifier(...)
```

### Research Pipeline Runtime

呼叫：

```python
state = workflow.run_research_pipeline(user_input)
```

執行順序：

```text
_intent_intake(state)
_paper_discovery(state)
_taxonomy_generation(state)
_profile_normalization(state)
_skill_building(state)
_graph_indexing(state)
```

每個 step 都讀寫同一個 `LogosResearchState`。

`WorkflowTracer` 會寫 trace：

```text
logs/workflow_traces/trace_<timestamp>_<id>.md
```

### QA Runtime

呼叫：

```python
answer = workflow.run_qa(query, state)
```

內部流程：

```text
QAAgent.answer(query)
  ↓
_classify_query(query)
  ↓
_search_papers(query, query_type)
  ↓
_route_and_answer(query, query_type, paper_id)
  ↓
_read_file(...)
  ↓
_read_pdf_section(...) if fallback needed
  ↓
OnDemandDeepReaderAgent.find_and_read(...)
```

QA trace 會寫入：

- `state.qa_trace`
- `WorkflowTracer`

如果 query 是 cross-paper comparison，`QAAgent` 會標記 `needs_verification=True`，workflow 可進一步觸發 optional edge verification。

## State Model

核心狀態定義：

- `src/logos2/workflow/state.py`

重要欄位：

```text
user_request
research_request
paper_candidates
paper_navigator_readings
survey_taxonomy
paper_profiles
paper_skill_paths
neo4j_index_status
qa_trace
candidate_edges
verified_edges
rejected_edges
errors
current_phase
workflow_complete
trace_file
```

Runtime 的每個 step 只應更新自己負責的 state 欄位。

## Agent 權限邊界

完整 agent 職責定義在：

- `docs/AGENTS.md`

簡化版如下：

| Agent / Node | LLM | Tools | State mutation | Default |
|---|---:|---|---|---|
| `PaperNavigatorAdapter` | No | local artifacts | discovery fields | Yes |
| `SurveyTaxonomyAgent` | Optional | local artifacts | taxonomy fields | Yes |
| `ProfileNormalizer` | No | file write | profile fields | Yes |
| `PaperSkillBuilderAgent` | Optional | Docling output + file write | skill fields | Yes |
| `LightweightGraphIndexer` | No | Neo4j write | graph status | Yes |
| `QAAgent` | Optional | Neo4j read + files | QA trace | Yes |
| `EdgeVerifierAgent` | Optional | files + Neo4j update | verified edges | No |
| `OnDemandDeepReaderAgent` | Optional | document.md/tables/figures/PDF | QA evidence trace | No |

## 目前已實作與尚未完整接上的部分

已實作：

- Pydantic schemas
- artifact-first `PaperNavigatorAdapter`
- heuristic `SurveyTaxonomyGenerator`
- `ProfileNormalizer`
- Docling wrapper `DoclingExtractor`
- `SectionIndexer`
- `EvidenceIndexer`
- `PaperSkillBuilder`
- lightweight Neo4j repository
- skill registry
- rule-based `QAAgent`
- `OnDemandDeepReaderAgent` 讀 `document.md` / tables / figures
- optional `EdgeVerifier`
- step-based workflow runtime
- CLI skeleton

尚未完整接上：

- `run_research_pipeline()` 目前尚未自動對 PDF 執行 `DoclingExtractor.extract()`。
- `PaperNavigatorAdapter` 目前讀本地 artifacts，尚未直接呼叫 EvoSkills `paper-navigator`。
- `SurveyTaxonomyGenerator` 目前不是完整 LLM survey agent。
- QA synthesis 目前是 template-based，不是 LLM-based final answer synthesis。
- full PDF page extraction 仍是 placeholder；已支援從 Docling 的 `document.md` 讀 section。
- workflow runtime 目前是 step-based，不是正式 LangGraph graph execution。

## 推薦下一步

1. 在 `_skill_building()` 前新增 extraction phase：

```text
_docling_extraction(state)
```

負責：

- 找到每篇 paper 的 PDF path
- 執行 `DoclingExtractor.extract()`
- 產生 `paper_library/<paper_id>/`
- 建立 `extraction_map`
- 傳給 `PaperSkillBuilder.build_batch(profiles, extraction_map)`

2. 強化 `PaperNavigatorAdapter`：

- 從 artifact 裡保留 `pdf_path`
- 支援 metadata + PDF path mapping
- 未來接 EvoSkills paper-navigator

3. 強化 `QAAgent`：

- 改成讀 `SKILL.md` routing policy，而不是只靠 hardcoded query type map
- 引入 LLM answer synthesizer，但只允許使用 routed evidence

4. 強化 `OnDemandDeepReaderAgent`：

- 支援 PDF page range extraction
- 支援 table CSV summarization
- 支援 figure caption + image reference routing

