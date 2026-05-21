# Phase 2 Ontology Schema: Node-Centric Mixed Hierarchy

This document describes the final Phase 2 Ontology Schema for the Knowledge Graph. It utilizes a **node-centric mixed hierarchy** where the `Paper` root node is lightweight, and all rich semantic information is extracted into independent child nodes with their own vector embeddings. 

This design enables highly granular similarity search and reduces token retrieval costs.

---

## 1. Schema Overview

| Node Type | Level | Attributes | Data Format | Vector Embedding |
| :--- | :---: | :--- | :--- | :---: |
| **`Paper`** (Root) | L1 | `title` | String | ❌ **No** |
| **`Summary`** | L2 | `year`, `short_claim` | Strings | ✅ **Yes** |
| **`Keyword`** | L2 | `name` | String (Merged) | ✅ **Yes** |
| **`ResearchProblem`** | L2 | `summary` | String | ✅ **Yes** |
| ↳ **`PreviousLimitation`** | L3 | `limitation` | String | ✅ **Yes** |
| ↳ **`UnderlyingProblem`** | L3 | `detail` | String | ✅ **Yes** |
| **`Method`** | L2 | `high_level_description` | String | ✅ **Yes** |
| ↳ **`MethodDetail`** | L3 | `method_detail`, `method_section_pointer` | Strings | ✅ **Yes** |
| ↳ **`ReferredAlgorithm`** | L3 | `algorithms`, `description` | **List[String]**, String | ✅ **Yes** |
| **`Experiment`** | L2 | `result`, `experiment_section_pointer` | Strings | ✅ **Yes** |
| ↳ **`ExperimentAnalysis`** | L3 | `design`, `sota_comparison`, `ablation_study` | Strings | ✅ **Yes** |
| ↳ **`ComparedMethod`** | L3 | `name` | String (Shared Node) | ✅ **Yes** |
| ↳ **`Dataset`** | L3 | `name` | String (Shared Node) | ✅ **Yes** |


---

## 2. Complete Extraction Prompt

Here is the exact prompt used by the `DeepReaderAgent` to extract information from the parsed PDF into the schema outlined above.

```markdown
You are an expert AI academic researcher. Read the provided academic paper markdown and extract structured information according to the strict JSON schema below. 

Your extraction must be deeply analytical and capture the core essence of the paper, especially the logical progression from problem to method to experiment. 
Make sure your text is dense with information and uses terminology from the paper.

# Output Schema
You must output a single JSON object. Here is the field-by-field breakdown:

1. **paper.title**: The exact full title of the paper.

2. **summary**:
   - `year`: The publication year (e.g. "2023"). Use "Unknown" if not found.
   - `short_claim`: 1 sentence summarizing the core achievement/claim of the paper.

3. **keywords**: The paper's own listed keywords (exactly as written). 5-10 items.

4. **research_problem**:
   - `summary`: Short 1-2 sentence summary of the problem addressed.
   - `previous_limitation.limitation`: How does this paper's Introduction synthesize the limitations of prior work? Capture the specific bottleneck prior methods fail at — the motivation for this research.
   - `underlying_problem.detail`: Detailed explanation of the core research question being solved. 2-4 sentences.

7. **method**:
   - `high_level_description`: 1-3 sentence elevator pitch of the proposed approach.
   - `detail.method_detail`: Deep dive into how the method works. Formulas, architecture steps, modules, training objective. Extremely detailed.
   - `detail.method_section_pointer`: Section path, e.g. "Section 3: Methodology (3.1 Setup, 3.2 Optimization)".
   - `referred_algorithms.algorithms`: List of classic or prior algorithms this method is inspired by, builds upon, or utilizes (e.g., ["EM algorithm", "Data synthesis", "DTW", "LoRA", "MoE"]).
   - `referred_algorithms.description`: How are these algorithms used or adapted in this specific method?

8. **experiment**:
   - `result`: Comprehensive summary of what experiments were run, metrics, and key quantitative findings.
   - `experiment_section_pointer`: Section path, e.g. "Section 5: Experiments".
   - `analysis.design`: What was the experimental design? List the conducted experiments and what each aimed to prove.
   - `analysis.sota_comparison`: What were the conclusions from the SOTA comparison? Which models were beaten and on what metrics?
   - `analysis.ablation_study`: What did the ablation study prove? Specifically, which modules were shown to be effective?
   - `compared_methods`: List of all baseline/competing methods compared against.
   - `datasets`: List of all datasets used for evaluation.

# Rules
- Output MUST be valid JSON matching the schema exactly.
- Keywords must be taken verbatim from the paper's Keywords section.
- Extract datasets and baselines accurately. If there are many, list the top most prominent ones.
- ONLY output the JSON. Do not include markdown code block wrappers like ```json.
```

---

## 3. Real Dataset Example (RoG: Reasoning on Graphs)

Below is an actual verified extraction output using the current prompt for the paper *"REASONING ON GRAPHS: FAITHFUL AND INTERPRETABLE LARGE LANGUAGE MODEL REASONING"* (arXiv:2310.01061).

```json
{
  "paper": {
    "title": "REASONING ON GRAPHS: FAITHFUL AND INTERPRETABLE LARGE LANGUAGE MODEL REASONING"
  },
  "summary": {
    "year": "Unknown",
    "short_claim": "RoG grounds LLM planning in knowledge-graph relation paths and then retrieves and reasons over KG path instances, yielding faithful, interpretable reasoning and state-of-the-art KGQA performance."
  },
  "keywords": [],
  "research_problem": {
    "summary": "LLMs reason well but hallucinate and lack up-to-date factual knowledge; existing KG+LLM methods either produce non-executable logical queries or treat KGs only as text-like facts, ignoring KG structure. The paper addresses how to combine LLMs with KG structural information (relation paths) so LLM reasoning becomes faithful and interpretable.",
    "previous_limitation": {
      "limitation": "Prior approaches either (1) use semantic parsing to produce logical queries that are often non-executable due to syntax/semantic errors, or (2) use retrieval-augmented methods that treat KGs as flat factual contexts and ignore KG structural signals (relation paths). Additionally, vanilla LLM planning suffers from hallucinated reasoning steps and lack of KG-grounded relations, which motivates grounding plans in KG structure."
    },
    "underlying_problem": {
      "detail": "The core research question is how to make LLM-based reasoning faithful and interpretable by explicitly incorporating KG structure into the planning and reasoning loop. Concretely, the paper asks how to (1) make LLMs generate relation-path plans that are grounded in the target KG, (2) retrieve concrete KG reasoning-path instances that realize those plans, and (3) enable LLMs to reason over the retrieved paths to produce correct answers and human-interpretable explanations. The approach must also allow distillation of KG relational knowledge into LLMs and be usable as a plug-and-play planning module for arbitrary LLMs at inference."
    }
  },
  "method": {
    "high_level_description": "RoG is a planning–retrieval–reasoning pipeline: an instruction-tuned planning module prompts an LLM to generate KG-grounded relation-path plans; a constrained breadth-first search retrieves concrete reasoning-path instances in the KG that follow those relation paths; a fusion-in-decoder style reasoning module feeds retrieved paths into the LLM to generate answers and explanations. Training jointly optimizes a planning objective (minimizing KL to KG-derived shortest relation paths) and a retrieval-reasoning objective (maximizing answer likelihood).",
    "detail": {
      "method_detail": "Overall architecture and training: RoG comprises two tightly coupled components... (Abridged for brevity, but deeply detailed architecture breakdown in actual DB).",
      "method_section_pointer": "Section 4: Approach (4.1 Planning-Retrieval-Reasoning; 4.2 Optimization Framework; 4.3 Planning Module; 4.4 Retrieval-Reasoning Module)"
    },
    "referred_algorithms": {
      "algorithms": [
        "Fusion-in-Decoder (FiD)",
        "Variational inference / ELBO (KL divergence)",
        "Plan-and-solve / chain-of-thought planning",
        "Constrained breadth-first search (graph traversal)",
        "Beam search"
      ],
      "description": "FiD is adapted as the retrieval-reasoning backbone to fuse multiple retrieved reasoning-path instances into a single generative answer; variational inference / ELBO is used to decompose the objective into a planning optimization... "
    }
  },
  "experiment": {
    "result": "RoG is evaluated on two KGQA benchmarks (WebQuestionSP and Complex WebQuestions) using Freebase as the background KG and measured by Hits@1 and F1. Main quantitative results: WebQSP Hits@1 = 85.7 and F1 = 70.8 (RoG) versus DECAF (DECAF reported Hits@1 82.1) and UniKGQA (77.2 Hits@1); RoG improves Hits@1 over DECAF by 4.4% on WebQSP...",
    "experiment_section_pointer": "Section 5: Experiment (5.1 Experiment Settings; 5.2 RQ1: KGQA Performance Comparison; 5.3 RQ2: Plug-and-Play Planning; 5.4 RQ3: Faithful Reasoning)",
    "analysis": {
      "design": "Conducted experiments: (1) Main KGQA benchmark comparison against 21 baselines... (2) Ablation study comparing RoG, RoG w/o planning, RoG w/o reasoning... (3) Plug-and-play experiments... (4) Faithfulness analysis sweeping top-K... (5) Case studies showing interpretable explanations...",
      "sota_comparison": "Conclusions: RoG outperforms prior state-of-the-art methods on both benchmarks. On WebQSP RoG (Hits@1 85.7) exceeds DECAF (82.1) and UniKGQA (77.2). On CWQ RoG (Hits@1 62.6 / F1 56.2) substantially outperforms UniKGQA.",
      "ablation_study": "Ablation results show planning module and reasoning module are both essential: removing planning reduces precision and overall F1 dramatically (WebQSP F1 from 70.81 -> 49.69); removing reasoning increases recall but drops precision and F1 (WebQSP F1 -> 49.56), demonstrating reasoning module's ability to filter noisy retrieved paths..."
    },
    "compared_methods": [
      { "name": "KV-Mem" },
      { "name": "EmbedKGQA" },
      { "name": "NSM" },
      { "name": "ChatGPT" },
      { "name": "UniKGQA" },
      { "name": "DECAF" }
    ],
    "datasets": [
      { "name": "WebQuestionSP (WebQSP)" },
      { "name": "Complex WebQuestions (CWQ)" },
      { "name": "Freebase (background KG)" },
      { "name": "MetaQA-3hop (Wiki-Movies KG)" }
    ]
  }
}
```
