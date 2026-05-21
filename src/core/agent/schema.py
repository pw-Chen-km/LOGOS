from pydantic import BaseModel, Field
from typing import List, Optional

# ==========================================
# L1: Paper Root (title only)
# ==========================================
class PaperRoot(BaseModel):
    title: str = Field(..., description="Full title of the paper.")

# ==========================================
# L2: Direct Children of Paper
# ==========================================

class SummaryNode(BaseModel):
    year: str = Field(..., description="Publication year. Use 'Unknown' if not found.")
    short_claim: str = Field(..., description="One punchy sentence summarizing the core contribution.")

class KeywordNode(BaseModel):
    name: str = Field(..., description="A keyword exactly as listed in the paper's Keywords section.")

# --- Research Problem Branch (3 flat siblings under Paper) ---

class PreviousLimitationNode(BaseModel):
    limitation: str = Field(
        ...,
        description=(
            "How the paper's Introduction synthesizes the limitations of prior work. "
            "Capture the specific technical or logical bottleneck that prior methods fail at, "
            "as highlighted by the authors to motivate their research."
        )
    )

class UnderlyingProblemNode(BaseModel):
    detail: str = Field(
        ...,
        description="Detailed explanation of the core research problem to be solved. 2-4 sentences."
    )

class ResearchProblemNode(BaseModel):
    summary: str = Field(..., description="Short 1-2 sentence summary of the research problem this paper addresses.")
    previous_limitation: PreviousLimitationNode
    underlying_problem: UnderlyingProblemNode


# --- Method Branch ---

class ReferredAlgorithmNode(BaseModel):
    algorithms: List[str] = Field(
        ...,
        description=(
            "List of classic algorithms, architectures, or techniques that the proposed method "
            "is directly inspired by or builds upon. E.g. ['MoE', 'LoRA', 'EM Algorithm']. "
            "Only include techniques central to the method's design, not general background."
        )
    )
    description: str = Field(
        ...,
        description="Brief explanation of how/why these algorithms were referenced or adapted in this paper's method."
    )

class MethodDetailNode(BaseModel):
    method_detail: str = Field(
        ...,
        description="Detailed step-by-step explanation of the full architecture and methodology."
    )
    method_section_pointer: str = Field(
        ...,
        description="Section path, e.g. 'Section 3: Methodology'."
    )

class MethodNode(BaseModel):
    high_level_description: str = Field(
        ...,
        description="1-3 sentence elevator pitch of the proposed approach."
    )
    detail: MethodDetailNode
    referred_algorithms: ReferredAlgorithmNode

# --- Experiment Branch ---

class ComparedMethodNode(BaseModel):
    name: str = Field(..., description="Name of a baseline or competing method.")

class DatasetNode(BaseModel):
    name: str = Field(..., description="Name of a dataset used in experiments.")

class ConductedExperiment(BaseModel):
    name: str = Field(..., description="實驗名稱或類型，例如 'Main Results', 'Ablation Study'")
    purpose: str = Field(..., description="這個實驗具體想證明什麼特性或解決什麼問題？")
    conclusion: str = Field(..., description="實驗的具體結論是什麼？")
    reference_element: str = Field(..., description="對應的圖表編號，如 'Table 1', 'Figure 2'. 無明確圖表則填 'None'")

class ExperimentAnalysisNode(BaseModel):
    design_overview: str = Field(
        ...,
        description="整個評估階段的總體設計思路與使用的 Metric。"
    )
    experiments: List[ConductedExperiment] = Field(
        ..., 
        description="所有的具體實驗清單。"
    )
    comprehensive_analysis: str = Field(
        default="", 
        description="系統自動掛載的豐富 Markdown 內容，無需 LLM 填寫。"
    )

class ExperimentNode(BaseModel):
    result: str = Field(
        ...,
        description="Comprehensive summary of experiments: what each tests, metrics used, and key quantitative findings."
    )
    experiment_section_pointer: str = Field(
        ...,
        description="Section path, e.g. 'Section 5: Experiments'."
    )
    analysis: ExperimentAnalysisNode
    compared_methods: List[ComparedMethodNode] = Field(default_factory=list)
    datasets: List[DatasetNode] = Field(default_factory=list)


# ==========================================
# Root Extraction Output
# ==========================================
class DeepReadingOutput(BaseModel):
    paper: PaperRoot
    summary: SummaryNode
    keywords: List[KeywordNode] = Field(default_factory=list)
    research_problem: ResearchProblemNode
    method: MethodNode
    experiment: ExperimentNode


# ==========================================
# Peer Review Schema (Dual-Track)
# ==========================================

# --- Track A: Problem Similarity ---
class ProblemReviewInsight(BaseModel):
    target_paper_title: str = Field(..., description="Title of the candidate paper.")
    is_match: bool = Field(..., description="True if both papers are fundamentally attacking the same core problem.")
    shared_core_issue: str = Field(..., description="One sentence summarizing the shared underlying problem.")
    approach_contrast: str = Field(..., description="One sentence capturing how the two methods differ in solving it.")

class ProblemReviewOutput(BaseModel):
    insights: List[ProblemReviewInsight] = Field(default_factory=list)

# --- Track B-1: Benchmark (Dataset) Similarity ---
class BenchmarkReviewInsight(BaseModel):
    target_paper_title: str = Field(..., description="Title of the candidate paper.")
    is_match: bool = Field(..., description="True if both papers are evaluated on a genuinely shared benchmark.")
    shared_datasets: List[str] = Field(default_factory=list, description="List of confirmed shared dataset names.")
    micro_comparison_report: str = Field(..., description="2-3 sentence structured comparison of their performance on the shared benchmark. Who won and on what metrics?")

class BenchmarkReviewOutput(BaseModel):
    insights: List[BenchmarkReviewInsight] = Field(default_factory=list)

# --- Track B-2: Common Baseline Similarity ---
class BaselineReviewInsight(BaseModel):
    target_paper_title: str = Field(..., description="Title of the candidate paper.")
    is_match: bool = Field(..., description="True if both papers compared against a meaningfully shared set of baseline methods.")
    shared_baselines: List[str] = Field(default_factory=list, description="List of confirmed shared baseline method names.")
    who_won: str = Field(..., description="1-2 sentence summary of which paper outperformed on shared baselines and by how much.")

class BaselineReviewOutput(BaseModel):
    insights: List[BaselineReviewInsight] = Field(default_factory=list)

# Legacy – kept for backward compat
class RelationInsight(BaseModel):
    target_paper_title: str = Field(..., description="Title of the historical paper being compared against.")
    relation_type: str = Field(..., description="One of: 'IMPROVES_UPON', 'SOLVES_SAME_PROBLEM', 'CONCEPTUALLY_SIMILAR_TO'.")
    reason: str = Field(..., description="One highly condensed sentence explaining the relationship.")

class PeerReviewOutput(BaseModel):
    insights: List[RelationInsight] = Field(default_factory=list)
