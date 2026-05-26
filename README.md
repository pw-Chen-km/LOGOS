# LOGOS 2.0: Paper-Skill-Centered Research Management

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

**LOGOS 2.0** is a paper-skill-centered research management system. It turns a research direction or paper-discovery artifact into a **paper pool**, **survey taxonomy**, **paper skill packs**, a **lightweight research graph**, and a **graph-guided QA runtime**.

Unlike the original LOGOS, which fragmented papers into heavy Neo4j nodes, LOGOS 2.0 uses **progressive disclosure**: the graph stores lightweight routing metadata, while detailed knowledge lives in **paper skill packs** that guide QA agents on what to read when.

---

## Key Highlights

### Paper Skill Packs
Each paper becomes a navigable skill pack containing:
- `SKILL.md`: Routing manual for QA agents
- `paper_profile.json`: Lightweight canonical knowledge
- `references/*.md`: Progressive disclosure guides (problem, method, experiments)
- `original.pdf`: Primary source (fallback)

### Lightweight Graph Index
SQLite is the open-source default. Neo4j is available as an optional backend.
The graph stores only:
- **Paper nodes**: `paper_id`, `title`, `theme`, `skill_path`
- **Index nodes**: Theme, MethodFamily, Benchmark, Dataset, Baseline
- **Candidate edges**: `RELATED_TO {status: candidate, confidence}`

No heavy paper-internal graph (no Claim, Evidence, Figure, Table nodes).

### Skill-Guided QA
```
User question
    ↓
Graph search → find relevant papers
    ↓
Read SKILL.md → understand routing policy
    ↓
Read paper_profile or reference guide
    ↓
Fallback to original.pdf only if necessary
```

---

## Architecture

```
User Research Intent
    ↓
[1] Research Intent Intake Agent
    ↓
[2] Paper Navigator Adapter (artifact-first or direct mode)
    ↓
[3] Survey Taxonomy Generator
    ↓
[4] LOGOS Profile Normalizer
    ↓
[5] Paper Skill Builder Agent
    ↓
[6] Lightweight Graph Index Builder
    ↓
[7] QA Agent (skill-guided)
    ↓
[8] Optional Cross-Paper Edge Verifier
```

---

## Quick Start

### Prerequisites
- Python 3.10+
- No API key required for fixture/offline tests
- Optional: EvoScientist for the full survey-agent integration
- Optional: Neo4j for a graph backend beyond the default SQLite index

### Installation

```bash
# Core install
pip install -e .

# Development tools
pip install -e .[dev]

# Optional full EvoScientist survey integration
pip install -e .[evoscientist]
```

### Usage

```bash
# Run research pipeline
logos2 research "GraphRAG latest methods"

# Ask questions about the knowledge base
logos2 qa "What is MRAG?"

# Check knowledge base status
logos2 status
```

The default config at `configs/logos2.yaml` keeps the project runnable without
EvoScientist or API keys. To enable the full EvoScientist survey agent:

```bash
pip install -e .[evoscientist]
cp .env.example .env
logos2 --config configs/logos2.survey-agent.yaml research "GraphRAG latest methods"
```

### Python API

```python
from logos2 import LogosResearchWorkflow

# Initialize workflow
workflow = LogosResearchWorkflow(
    paper_skills_dir="paper_skills",
    artifacts_dir="artifacts",
)

# Run research pipeline
state = workflow.run_research_pipeline(
    user_input="GraphRAG latest methods"
)

# Ask questions
answer = workflow.run_qa("How does MRAG work?", state)
print(answer)

workflow.close()
```

---

## Directory Structure

```
LOGOS/
├── pyproject.toml              # Python package metadata
├── src/logos2/                 # Main LOGOS 2.0 code
│   ├── schemas/                # Pydantic schemas
│   ├── adapters/               # EvoScientist adapters
│   ├── nodes/                    # Workflow nodes
│   ├── storage/                  # Neo4j & file storage
│   ├── workflow/                 # LangGraph workflow
│   └── cli/                      # CLI entry points
├── examples/fixtures/          # Small synthetic fixtures safe for git
├── paper_skills/               # Runtime output, ignored by git
├── artifacts/                  # Runtime artifacts, ignored by git
├── paper_library/              # Runtime PDF/cache storage, ignored by git
├── tests/                      # Tests and fixtures
└── logs/                       # QA traces and workflow logs
```

---

## Integration with EvoScientist

LOGOS 2.0 keeps EvoScientist survey support as a first-class optional integration.
The core package does not require EvoScientist at import time, but the full
survey workflow can be enabled explicitly when you need EvoScientist's research
agent runtime.

### Default Mode
- Loads local artifacts or uses direct paper-navigator filesystem integration
- Keeps CI and local development independent of API keys
- Uses SQLite as the default graph backend

### Survey-Agent Mode
- Uses `configs/logos2.survey-agent.yaml`
- Runs the full EvoScientist survey agent through `EvoSurveyAgentAdapter`
- Produces LOGOS-compatible paper candidates, readings, taxonomy, reports, and paper skill packs
- Remains behind an explicit config and optional dependency boundary

See [MIGRATION_LOGOS2.md](MIGRATION_LOGOS2.md) for migration from LOGOS 1.0.

---

## Testing

```bash
pytest tests/
```

---

## Open-Source Hygiene

The repository intentionally ignores local runtime outputs:

- `.env`
- `runs/`
- `logs/`
- `artifacts/`
- `paper_skills/`
- `paper_library/`
- `graph_index.sqlite`
- local `skills/` installs

Commit small fixtures under `tests/fixtures/` or `examples/fixtures/` instead
of committing real run outputs.

---

## Original LOGOS

This is a complete rewrite of the original LOGOS system:

- **LOGOS 1.0**: Heavy Neo4j ontology, pre-extracted paper anatomy, Streamlit UI
- **LOGOS 2.0**: Paper-skill-centered, lightweight index, artifact-first MVP

See [MIGRATION_LOGOS2.md](MIGRATION_LOGOS2.md) for details on what was removed and why.

---

## License

MIT License - See [LICENSE](LICENSE) for details.

## Acknowledgments

LOGOS 2.0 builds on concepts from the original LOGOS paper:
> "LOGOS: Logic-Oriented Graph Ontology Synthesis for Interactive Literature Navigation" by Pi-Wei Chen, Zih-Ching Chen, Rafał Cupek, and Jerry Chun-Wei Lin.
