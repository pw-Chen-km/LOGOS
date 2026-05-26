# LOGOS 2.0 替換式重構遷移清單

本文檔記錄從舊 LOGOS 遷移到 LOGOS 2.0 的清理決策。

## 遷移原則

1. **刪除優先**：舊 heavy parser、heavy ontology、預設 PeerReviewer、舊 UI 一律刪除
2. **邏輯遷移**：有用的 LangGraph 結構、trace 模式、Neo4j 連線模式搬到新架構
3. **不再相容**：LOGOS 2.0 不維護舊 schema，只做 artifact-first 新管線

---

## Phase 0：刪除清單

### 刪除：舊 Ingestion Scripts（Heavy Parser 預設管線）

| 檔案 | 處置 | 原因 |
|------|------|------|
| `scripts/run_phase2.py` | **DELETE** | 舊 heavy ingestion 主入口，含 DeepReader + PeerReviewer 預設流程 |
| `scripts/batch_process.py` | **DELETE** | batch 舊管線 |
| `scripts/batch_ingest_testing.py` | **DELETE** | 測試舊管線 |
| `scripts/test_new_extraction.py` | **DELETE** | 舊 extraction 測試 |
| `scripts/vectorize_entities.py` | **DELETE** | 舊 embedding 批次處理 |
| `scripts/run_phase3_qa.py` | **DELETE** | 舊 QA CLI，將由 logos2 workflow 取代 |
| `scripts/check_relations.py` | **DELETE** | 舊 relation 檢查 script |

### 刪除：舊 Core Agent（Heavy Parser / PeerReviewer）

| 檔案 | 處置 | 原因 |
|------|------|------|
| `src/core/agent/deep_reader.py` | **DELETE** | DeepReaderAgent，heavy LLM extraction，LOGOS 2.0 不再預設執行 |
| `src/core/agent/peer_reviewer.py` | **DELETE** | PeerReviewAgent，預設 pairwise verification，改為 optional verifier |
| `src/core/agent/legacy_agent.py` | **DELETE** | 舊 ReAct agent |
| `src/core/agent/schema.py` | **DELETE** | 舊 Pydantic schema（DeepReader 輸出），LOGOS 2.0 用新 schemas |
| `src/core/agent/qa_tools.py` | **MIGRATE** → 重寫 | 部分工具概念保留，但重寫為 skill-guided routing tools |
| `src/core/agent/multi_agent.py` | **MIGRATE** → 重寫 | LangGraph 結構保留，但搬到 `logos2/workflow/graph.py` |

### 刪除：舊 Graph Client（Heavy Ontology）

| 檔案 | 處置 | 原因 |
|------|------|------|
| `src/core/graph/neo4j_client.py` | **DELETE** | 11 vector indexes + heavy paper-internal nodes，改為 lightweight indexer |

### 刪除：舊 Extraction

| 檔案 | 處置 | 原因 |
|------|------|------|
| `src/core/extraction/docling_parser.py` | **DELETE** | PDF extraction 將由 paper-navigator 或外部 tool 處理，不在 LOGOS 2.0 預設管線 |

### 刪除：舊 UI

| 檔案 | 處置 | 原因 |
|------|------|------|
| `demo_app.py` | **DELETE** | Streamlit 舊 demo |
| `app.py` | **DELETE** | Streamlit 舊 QA UI |
| `ui_demo/api_server.py` | **DELETE** | Flask 舊 API |
| `ui_demo/index.html` | **DELETE** | 舊前端 |
| `ui_demo/app.js` | **DELETE** | 舊前端 |
| `ui_demo/style.css` | **DELETE** | 舊前端 |

### 刪除：目錄

| 目錄 | 處置 |
|------|------|
| `scripts/` | **DELETE** 整個目錄 |
| `src/core/` | **DELETE** 整個目錄 |
| `ui_demo/` | **DELETE** 整個目錄 |
| `docling/` | 檢查後決定（若只有快取則刪除）|

---

## 遷移邏輯：搬到 LOGOS 2.0

### 保留概念（重寫到新位置）

| 來源 | 目標 | 遷移內容 |
|------|------|----------|
| `multi_agent.py` 的 LangGraph 結構 | `src/logos2/workflow/graph.py` | scanner → planner → executor → synthesizer 流程 |
| `multi_agent.py` 的 trace logging | `src/logos2/workflow/trace.py` | QA trace 寫入 logs/qa_traces/ |
| `neo4j_client.py` 的連線模式 | `src/logos2/storage/neo4j_repository.py` | driver 建立、環境變數讀取 |
| `qa_tools.py` 的 properties reading 概念 | `src/logos2/nodes/qa_agent.py` | 但改為讀 paper_profile / SKILL.md / reference guides |
| `ontology_schema_v2.md` 的設計動機 | `README.md` 或 `docs/` | 保留 node-centric hierarchy 的設計理念說明 |

### 可重用的 snippets（搬進 utils 或參考實作）

```python
# multi_agent.py 中的 trace logging pattern
# 搬到 logos2/workflow/trace.py
def _log_trace(file_path: str, section_title: str, content: str):
    """Append steps to trace file"""
    if not file_path:
        return
    with open(file_path, "a", encoding="utf-8") as f:
        f.write(f"\n## {section_title} - {datetime.datetime.now().strftime('%H:%M:%S')}\n")
        f.write(f"```\n{content}\n```\n")
        f.write("-" * 40 + "\n")

# neo4j_client.py 中的 driver 模式
# 搬到 logos2/storage/neo4j_repository.py
from neo4j import GraphDatabase
class Neo4jClient:
    def __init__(self, uri, user, password):
        self.driver = GraphDatabase.driver(uri, auth=(user, password))
    def close(self):
        self.driver.close()
```

---

## 保留但不改動的檔案

| 檔案 | 原因 |
|------|------|
| `README.md` | 重寫為 LOGOS 2.0 描述，而非舊功能說明 |
| `requirements.txt` | 重寫為最小依賴 |
| `.git/` | 保留 git history |

---

## 新增檔案結構（LOGOS 2.0）

```
LOGOS/
├── README.md                     # 重寫：LOGOS 2.0 描述
├── requirements.txt              # 重寫：最小依賴
├── MIGRATION_LOGOS2.md           # 本文檔
├── src/
│   └── logos2/                   # 唯一主要程式碼路徑
│       ├── __init__.py
│       ├── schemas/              # Pydantic schemas
│       │   ├── research_request.py
│       │   ├── paper_navigator_reading.py
│       │   ├── survey_taxonomy.py
│       │   ├── paper_profile.py
│       │   ├── paper_skill_manifest.py
│       │   ├── candidate_edge.py
│       │   └── verified_edge.py
│       ├── adapters/             # EvoScientist adapters
│       │   └── evoscientist/
│       │       └── paper_navigator_adapter.py
│       ├── nodes/                # LangGraph nodes
│       │   ├── intent_intake.py
│       │   ├── survey_taxonomy.py
│       │   ├── profile_normalizer.py
│       │   ├── paper_skill_builder.py
│       │   ├── lightweight_graph_indexer.py
│       │   ├── qa_agent.py
│       │   └── edge_verifier.py
│       ├── storage/              # Storage layer
│       │   ├── neo4j_repository.py
│       │   └── skill_registry.py
│       ├── workflow/             # LangGraph workflow
│       │   ├── state.py
│       │   ├── graph.py
│       │   └── trace.py
│       └── cli/                  # CLI entry points
│           └── main.py
├── paper_skills/                 # 輸出：paper skill packs
├── paper_library/                # 輸入/快取：PDFs
├── logs/                         # QA traces
└── tests/                        # 測試
    └── fixtures/
        ├── paper_navigator_reading.json
        └── survey_taxonomy.json
```

---

## 執行順序

1. **建立新結構**：創建 `src/logos2/` 目錄與所有新檔案
2. **測試新結構**：確保新 code 可運行
3. **刪除舊入口**：刪除 `scripts/`、`src/core/`、`ui_demo/`
4. **重寫 README**：更新為 LOGOS 2.0 描述
5. **清理 requirements**：移除舊 heavy dependencies

---

## 確認檢查清單

- [ ] 新 `src/logos2/` 可獨立運行
- [ ] 舊 `scripts/run_phase2.py` 不再被引用
- [ ] 舊 `demo_app.py`, `app.py` 已刪除
- [ ] 舊 `src/core/` 已刪除
- [ ] README 已重寫
