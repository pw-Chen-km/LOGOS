from typing import List, Dict
from langchain_core.prompts import ChatPromptTemplate
from langchain_openai import ChatOpenAI

from src.core.agent.schema import (
    ProblemReviewOutput,
    BenchmarkReviewOutput,
    BaselineReviewOutput,
)


class PeerReviewAgent:
    """
    Dual-track peer review agent.

    Track A: Problem similarity → TACKLES_SIMILAR_PROBLEM edge.
    Track B-1: Dataset overlap → EVALUATED_ON_SAME_BENCHMARK edge.
    Track B-2: Baseline overlap → HAS_COMMON_BASELINE edge.
    """

    def __init__(self, api_key: str, model_name: str = "gpt-5-mini-2025-08-07"):
        llm = ChatOpenAI(model=model_name, api_key=api_key, temperature=0.1)

        # ── Track A ──────────────────────────────────────────────
        self._problem_chain = ChatPromptTemplate.from_messages([
            ("system", """You are a senior AI researcher performing rigorous peer review.
Your task: determine if a NEW paper and each CANDIDATE paper fundamentally attack the SAME core research problem.

Focus on:
- The underlying_problem (deep technical root cause)
- The prior_limitation (specific bottleneck prior methods fail at)
- The method high-level description (how they each solve it)

Be strict: surface-level topic similarity is NOT enough. 
The core problem must be essentially identical — same failure mode or same unsolved question.
"""),
            ("user", """# NEW PAPER
Title: {new_title}
Underlying Problem: {new_up}
Prior Limitation: {new_pl}
Method: {new_method}

# CANDIDATE PAPERS
{candidates}

For each candidate, evaluate strictly and output a structured list.""")
        ]) | llm.with_structured_output(ProblemReviewOutput)

        # ── Track B-1 ─────────────────────────────────────────────
        self._benchmark_chain = ChatPromptTemplate.from_messages([
            ("system", """You are a senior AI researcher comparing experimental evaluations.
Your task: determine if a NEW paper and each CANDIDATE paper were evaluated on the SAME benchmark dataset(s).

Confirm semantic equivalence carefully:
- "WebQSP" and "WebQuestionSP" refer to the same benchmark → match.
- "Freebase" used as background KG vs. "Freebase" as evaluation set may differ → verify from context.

If they share at least one benchmark, write a 2-3 sentence micro-comparison report describing who performed better and on which metrics.
"""),
            ("user", """# NEW PAPER
Title: {new_title}
Experiment Result: {new_result}
Analysis: {new_analysis}
Datasets: {new_datasets}

# CANDIDATE PAPERS
{candidates}

For each candidate, confirm match and write the micro-comparison report.""")
        ]) | llm.with_structured_output(BenchmarkReviewOutput)

        # ── Track B-2 ─────────────────────────────────────────────
        self._baseline_chain = ChatPromptTemplate.from_messages([
            ("system", """You are a senior AI researcher comparing experimental evaluations.
Your task: determine if a NEW paper and each CANDIDATE paper are compared against the SAME baseline methods.

Confirm semantic equivalence:
- "ChatGPT" and "GPT-3.5-turbo" may refer to the same model → match if used in the same timeframe.
- "LLaMA-2-7B" and "LLaMA2-Chat-7B" are different variants → only match if the same model.

If they share at least one baseline, write a 1-2 sentence summary of who outperformed on those baselines.
"""),
            ("user", """# NEW PAPER
Title: {new_title}
Baselines Used: {new_baselines}
Analysis: {new_analysis}

# CANDIDATE PAPERS
{candidates}

For each candidate, confirm match and summarize who won.""")
        ]) | llm.with_structured_output(BaselineReviewOutput)

    # ── Private Formatters ────────────────────────────────────────

    @staticmethod
    def _fmt_problem_candidates(candidates: List[Dict]) -> str:
        blocks = []
        for i, c in enumerate(candidates):
            ctx = c.get("context", {})
            blocks.append(
                f"--- Candidate {i+1} ---\n"
                f"Title: {c['title']}\n"
                f"Underlying Problem: {ctx.get('underlying_problem', 'N/A')}\n"
                f"Prior Limitation: {ctx.get('prior_limitation', 'N/A')}\n"
                f"Method: {ctx.get('method', 'N/A')}\n"
            )
        return "\n".join(blocks)

    @staticmethod
    def _fmt_experiment_candidates(candidates: List[Dict]) -> str:
        blocks = []
        for i, c in enumerate(candidates):
            ctx = c.get("context", {})
            blocks.append(
                f"--- Candidate {i+1} ---\n"
                f"Title: {c['title']}\n"
                f"Datasets: {ctx.get('datasets', [])}\n"
                f"Baselines: {ctx.get('baselines', [])}\n"
                f"Design: {ctx.get('design', 'N/A')}\n"
                f"Analysis: {(ctx.get('comprehensive_analysis') or '')[:300]}...\n"
                f"Result: {(ctx.get('result') or '')[:300]}...\n"
            )
        return "\n".join(blocks)

    # ── Public run methods ────────────────────────────────────────

    def run_problem_review(
        self,
        new_title: str,
        new_ctx: Dict,
        problem_candidates: List[Dict],
    ) -> ProblemReviewOutput:
        if not problem_candidates:
            return ProblemReviewOutput(insights=[])
        print(f"[PeerReview-A] Reviewing {len(problem_candidates)} problem candidates...")
        return self._problem_chain.invoke({
            "new_title": new_title,
            "new_up": new_ctx.get("underlying_problem", "N/A"),
            "new_pl": new_ctx.get("prior_limitation", "N/A"),
            "new_method": new_ctx.get("method", "N/A"),
            "candidates": self._fmt_problem_candidates(problem_candidates),
        })

    def run_benchmark_review(
        self,
        new_title: str,
        new_exp_ctx: Dict,
        dataset_candidates: List[Dict],
    ) -> BenchmarkReviewOutput:
        if not dataset_candidates:
            return BenchmarkReviewOutput(insights=[])
        print(f"[PeerReview-B1] Reviewing {len(dataset_candidates)} dataset candidates...")
        return self._benchmark_chain.invoke({
            "new_title": new_title,
            "new_result": (new_exp_ctx.get("result") or "")[:400],
            "new_analysis": new_exp_ctx.get("comprehensive_analysis", "N/A"),
            "new_datasets": new_exp_ctx.get("datasets", []),
            "candidates": self._fmt_experiment_candidates(dataset_candidates),
        })

    def run_baseline_review(
        self,
        new_title: str,
        new_exp_ctx: Dict,
        baseline_candidates: List[Dict],
    ) -> BaselineReviewOutput:
        if not baseline_candidates:
            return BaselineReviewOutput(insights=[])
        print(f"[PeerReview-B2] Reviewing {len(baseline_candidates)} baseline candidates...")
        return self._baseline_chain.invoke({
            "new_title": new_title,
            "new_baselines": new_exp_ctx.get("baselines", []),
            "new_analysis": new_exp_ctx.get("comprehensive_analysis", "N/A"),
            "candidates": self._fmt_experiment_candidates(baseline_candidates),
        })
