"""Paper Skill Builder

Module 5: Paper Skill Builder Agent

將每篇 paper 打包成一個符合 progressive disclosure 原則的 paper skill pack。

不是單純摘要 paper，而是為 QA agent 建立一份 paper navigation guide。

要回答：
- 什麼問題看 paper_profile.json 就夠？
- 什麼問題要讀 problem guide？
- 什麼問題要讀 method guide？
- 什麼問題要讀 experiment guide？
- 什麼問題要看 table / figure？
- 什麼問題必須回到 original.pdf？
"""

import json
from pathlib import Path
from typing import List, Optional, Dict, Any
from datetime import datetime

from ..schemas import (
    PaperProfile,
    PaperSkillManifest,
    ReferenceGuideInfo,
    RoutingPolicy,
    SectionIndex,
    EvidenceIndex,
)
from ..extraction import (
    DoclingExtractor,
    SectionIndexer,
    EvidenceIndexer,
    index_sections_from_markdown,
    index_evidence_from_docling_output,
)
from .paper_reference_pack_builder import PaperReferencePackBuilder, ReferencePack
from .profile_normalizer import paper_title_slug


class PaperSkillBuilder:
    """Paper Skill Builder
    
    為每篇論文生成：
    - SKILL.md (routing manual)
    - metadata.json
    - references/*.md (problem, method, experiment, benchmark, figures, limitations)
    - section_index.json
    - evidence_index.json
    """
    
    def __init__(self, paper_skills_dir: str = "paper_skills"):
        """
        Args:
            paper_skills_dir: paper skill packs 輸出根目錄
        """
        self.paper_skills_dir = Path(paper_skills_dir)
        self.paper_skills_dir.mkdir(parents=True, exist_ok=True)
    
    def build(
        self,
        profile: PaperProfile,
        extraction_dir: Optional[Path] = None
    ) -> PaperSkillManifest:
        """為單篇論文建立 paper skill pack
        
        Args:
            profile: 論文 profile
            extraction_dir: 可選的 Docling extraction 輸出目錄。
                         如果提供，會從 document.md 產生準確的 section/evidence index。
            
        Returns:
            PaperSkillManifest: skill pack manifest
        """
        paper_id = profile.paper_id
        safe_id = paper_title_slug(profile.title, paper_id)
        skill_dir = self.paper_skills_dir / safe_id
        
        # 建立目錄結構
        skill_dir.mkdir(parents=True, exist_ok=True)
        refs_dir = skill_dir / "references"
        refs_dir.mkdir(exist_ok=True)
        
        # 1. 建立 progressive-disclosure reference pack from original paper text.
        document_md_path = None
        reference_pack = None
        if extraction_dir and extraction_dir.exists():
            doc_path = extraction_dir / "document.md"
            if doc_path.exists():
                document_md_path = doc_path
                reference_pack = PaperReferencePackBuilder().build(extraction_dir, skill_dir)
        
        if reference_pack and reference_pack.sections:
            reference_guides = self._create_reference_guides_from_pack(reference_pack)
        else:
            reference_guides = self._create_reference_guides(
                profile, refs_dir, document_md_path
            )
        
        # 2. 建立 section index（使用 Docling 輸出）
        section_index = self._create_section_index(profile, extraction_dir)
        
        # 3. 建立 evidence index（使用 Docling 輸出）
        evidence_index = self._create_evidence_index(profile, extraction_dir)
        
        # 4. 建立 routing policies
        routing_policies = self._create_routing_policies(reference_pack)
        
        # 5. 建立 SKILL.md
        if reference_pack and reference_pack.sections:
            skill_md_content = self._create_progressive_skill_md(
                profile,
                reference_pack,
                routing_policies,
            )
        else:
            skill_md_content = self._create_skill_md(profile, reference_guides, routing_policies)
        skill_md_path = skill_dir / "SKILL.md"
        with open(skill_md_path, "w", encoding="utf-8") as f:
            f.write(skill_md_content)
        
        # 6. 建立 metadata.json
        metadata = self._create_metadata(profile, reference_guides, extraction_dir)
        if reference_pack:
            metadata["reference_pack"] = reference_pack.model_dump()
        metadata_path = skill_dir / "metadata.json"
        with open(metadata_path, "w", encoding="utf-8") as f:
            json.dump(metadata, f, indent=2, ensure_ascii=False)
        
        # 7. 儲存 indexes
        section_index_path = skill_dir / "section_index.json"
        with open(section_index_path, "w", encoding="utf-8") as f:
            json.dump([idx.model_dump() for idx in section_index], f, indent=2)
        
        evidence_index_path = skill_dir / "evidence_index.json"
        with open(evidence_index_path, "w", encoding="utf-8") as f:
            json.dump([idx.model_dump() for idx in evidence_index], f, indent=2)
        
        # 8. 建立 manifest
        manifest = PaperSkillManifest(
            paper_id=paper_id,
            skill_name=_skill_safe_name(profile.title, paper_id),
            skill_description=self._create_skill_description(profile),
            tags=profile.taxonomy_path + profile.benchmark_names[:3],
            reference_guides=reference_guides,
            routing_policies=routing_policies,
            section_index=section_index,
            evidence_index=evidence_index,
            skill_md_path=str(skill_md_path),
            metadata_json_path=str(metadata_path),
            paper_profile_path=str(skill_dir / "paper_profile.json"),
            references_dir=str(refs_dir),
            original_pdf_path=str(profile.pdf_path or (extraction_dir / "original.pdf" if extraction_dir else "")),
            created_at=datetime.utcnow().isoformat() + "Z",
            builder_version="1.0.0"
        )
        
        return manifest
    
    def build_batch(
        self,
        profiles: List[PaperProfile],
        extraction_map: Optional[Dict[str, Path]] = None
    ) -> List[PaperSkillManifest]:
        """批次建立多篇論文的 skill packs
        
        Args:
            profiles: 論文 profile 列表
            extraction_map: paper_id → extraction_dir 的映射
        """
        manifests = []
        for profile in profiles:
            extraction_dir = None
            if extraction_map and profile.paper_id in extraction_map:
                extraction_dir = extraction_map[profile.paper_id]
            
            manifest = self.build(profile, extraction_dir)
            manifests.append(manifest)
        return manifests
    
    def _create_reference_guides(
        self,
        profile: PaperProfile,
        refs_dir: Path,
        document_md_path: Optional[Path] = None
    ) -> List[ReferenceGuideInfo]:
        """建立 reference guide 檔案
        
        Args:
            profile: 論文 profile
            refs_dir: reference guides 輸出目錄
            document_md_path: 可選的 document.md 路徑（Docling 輸出）
        """
        # 讀取 document.md 內容（如果有）
        document_content = ""
        if document_md_path and document_md_path.exists():
            with open(document_md_path, "r", encoding="utf-8") as f:
                document_content = f.read()
        
        guides = []
        
        # 1. Problem and Motivation Guide
        if profile.rough_research_problem:
            content = self._generate_problem_guide(profile)
            self._write_guide(refs_dir, "problem_and_motivation.md", content)
            guides.append(ReferenceGuideInfo(
                filename="problem_and_motivation.md",
                description="Research problem and motivation",
                query_types=[
                    "what problem does it solve",
                    "what prior limitation motivates the paper",
                    "why is this problem important",
                    "motivation"
                ]
            ))
        
        # 2. Method Guide
        if profile.rough_method_intuition or profile.rough_contribution:
            content = self._generate_method_guide(profile)
            self._write_guide(refs_dir, "method_guide.md", content)
            guides.append(ReferenceGuideInfo(
                filename="method_guide.md",
                description="Method intuition and design",
                query_types=[
                    "how does the method work",
                    "what is the intuition",
                    "what are the main modules",
                    "how does it differ from prior",
                    "algorithm",
                    "architecture"
                ]
            ))
        
        # 3. Experiment Guide
        if profile.benchmark_names:
            content = self._generate_experiment_guide(profile)
            self._write_guide(refs_dir, "experiment_guide.md", content)
            guides.append(ReferenceGuideInfo(
                filename="experiment_guide.md",
                description="Experimental design and results",
                query_types=[
                    "how do the authors prove their claim",
                    "what experiments were run",
                    "what ablations were done",
                    "ablation study"
                ]
            ))
        
        # 4. Benchmark and Baselines Guide
        if profile.benchmark_names or profile.baseline_names:
            content = self._generate_benchmark_guide(profile)
            self._write_guide(refs_dir, "benchmark_and_baselines.md", content)
            guides.append(ReferenceGuideInfo(
                filename="benchmark_and_baselines.md",
                description="Benchmarks, datasets, and baselines",
                query_types=[
                    "what benchmarks were used",
                    "what datasets were evaluated",
                    "which baselines were compared",
                    "did it outperform prior methods",
                    "comparison results"
                ]
            ))
        
        # 5. Figures and Tables Guide
        content = self._generate_figures_guide(profile)
        self._write_guide(refs_dir, "figures_and_tables.md", content)
        guides.append(ReferenceGuideInfo(
            filename="figures_and_tables.md",
            description="Important figures and tables",
            query_types=[
                "which table supports the main claim",
                "what does Table X show",
                "what does Figure Y illustrate",
                "visual evidence"
            ]
        ))
        
        # 6. Limitations Guide
        if profile.rough_limitation:
            content = self._generate_limitations_guide(profile)
            self._write_guide(refs_dir, "limitations.md", content)
            guides.append(ReferenceGuideInfo(
                filename="limitations.md",
                description="Limitations and future work",
                query_types=[
                    "what are the limitations",
                    "what future work is suggested",
                    "weaknesses"
                ]
            ))
        
        return guides
    
    def _write_guide(self, refs_dir: Path, filename: str, content: str):
        """寫入 guide 檔案"""
        with open(refs_dir / filename, "w", encoding="utf-8") as f:
            f.write(content)

    def _create_reference_guides_from_pack(
        self,
        reference_pack: ReferencePack,
    ) -> List[ReferenceGuideInfo]:
        """Create manifest entries for original section/table/figure references."""
        guides: list[ReferenceGuideInfo] = []
        if reference_pack.document_path:
            guides.append(
                ReferenceGuideInfo(
                    filename=reference_pack.document_path.replace("references/", ""),
                    description="Full Docling markdown for the paper",
                    query_types=["full paper", "exact wording", "fallback evidence"],
                )
            )

        for section in reference_pack.sections:
            guides.append(
                ReferenceGuideInfo(
                    filename=section.path.split("references/", 1)[-1],
                    description=f"Original paper section: {section.title}",
                    query_types=section.query_intents,
                )
            )

        for table in reference_pack.tables:
            guides.append(
                ReferenceGuideInfo(
                    filename=table["path"].replace("references/", ""),
                    description=f"Table reference: {table['id']}",
                    query_types=table.get("query_intents", []),
                )
            )

        for figure in reference_pack.figures:
            guides.append(
                ReferenceGuideInfo(
                    filename=figure["path"].replace("references/", ""),
                    description=f"Figure reference: {figure['id']}",
                    query_types=figure.get("query_intents", []),
                )
            )

        return guides
    
    def _generate_problem_guide(self, profile: PaperProfile) -> str:
        """產生 Problem Guide"""
        content = f"""# Problem and Motivation: {profile.title}

## Research Problem
{profile.rough_research_problem or "Not extracted"}

## Key Motivation
{profile.rough_contribution or "Not extracted"}

## Why This Matters
See original PDF Section 1 (Introduction) for full problem statement.

## Related Reading
- paper_profile.json: "rough_research_problem"
- Original PDF: Section 1 (Introduction)
"""
        return content
    
    def _generate_method_guide(self, profile: PaperProfile) -> str:
        """產生 Method Guide"""
        content = f"""# Method Guide: {profile.title}

## High-Level Approach
{profile.rough_method_intuition or "Not extracted"}

## Key Contribution
{profile.rough_contribution or "Not extracted"}

## Method Family
{profile.method_family or "Unknown"}

## Related Reading
- paper_profile.json: "rough_method_intuition", "method_family"
- Original PDF: Method/Approach section

## Fallback
If insufficient detail here, read original PDF Method section.
"""
        return content
    
    def _generate_experiment_guide(self, profile: PaperProfile) -> str:
        """產生 Experiment Guide"""
        content = f"""# Experimental Design: {profile.title}

## Evaluation Focus
Benchmarks: {', '.join(profile.benchmark_names) or 'Not specified'}

## Key Claims
{profile.rough_contribution or "Not extracted"}

## Datasets Used
{', '.join(profile.dataset_names) or 'Not specified'}

## Baselines Compared
{', '.join(profile.baseline_names) or 'Not specified'}

## Related Reading
- paper_profile.json: "benchmark_names", "dataset_names", "baseline_names"
- references/benchmark_and_baselines.md: Detailed comparisons
- Original PDF: Experiments section for exact numbers

## Fallback
For exact metrics and significance tests, see original PDF Tables.
"""
        return content
    
    def _generate_benchmark_guide(self, profile: PaperProfile) -> str:
        """產生 Benchmark Guide"""
        content = f"""# Benchmarks and Baselines: {profile.title}

## Benchmarks Evaluated
{chr(10).join(f'- {b}' for b in profile.benchmark_names) or 'Not specified'}

## Datasets
{chr(10).join(f'- {d}' for d in profile.dataset_names) or 'Not specified'}

## Baselines Compared
{chr(10).join(f'- {b}' for b in profile.baseline_names) or 'Not specified'}

## Main Results
See original PDF Tables for exact numbers.

## Related Reading
- paper_profile.json: All benchmark/dataset/baseline lists
- references/experiment_guide.md: Experimental claims
- Original PDF: Results tables
"""
        return content
    
    def _generate_figures_guide(self, profile: PaperProfile) -> str:
        """產生 Figures Guide"""
        content = f"""# Figures and Tables: {profile.title}

## Mentioned Figures
{chr(10).join(f'- {f}' for f in profile.missing_fields if 'figure' in f.lower()) or 'See original PDF'}

## Mentioned Tables
{chr(10).join(f'- {t}' for t in profile.missing_fields if 'table' in t.lower()) or 'See original PDF'}

## Key Visual Evidence
See original PDF for:
- System architecture diagrams
- Results tables
- Ablation study plots

## Fallback
All exact figures and tables are in the original PDF.
"""
        return content
    
    def _generate_limitations_guide(self, profile: PaperProfile) -> str:
        """產生 Limitations Guide"""
        content = f"""# Limitations: {profile.title}

## Stated Limitations
{profile.rough_limitation or "Not extracted"}

## Reading Level
This paper was read at level: {profile.reading_level}

## Missing Information
{chr(10).join(f'- {m}' for m in profile.missing_fields) or 'None recorded'}

## Related Reading
- paper_profile.json: "rough_limitation", "missing_fields"
- Original PDF: Limitations/Conclusion section
"""
        return content
    
    def _create_section_index(
        self,
        profile: PaperProfile,
        extraction_dir: Optional[Path] = None
    ) -> List[SectionIndex]:
        """建立 section index
        
        如果 extraction_dir 存在，使用 Docling 輸出產生準確的 index。
        否則，使用基本的 placeholder index。
        """
        # 檢查是否有 Docling 輸出
        if extraction_dir and extraction_dir.exists():
            document_md = extraction_dir / "document.md"
            if document_md.exists():
                # 從 extraction_meta.json 取得總頁數
                total_pages = 0
                meta_path = extraction_dir / "extraction_meta.json"
                if meta_path.exists():
                    import json
                    with open(meta_path, "r", encoding="utf-8") as f:
                        meta = json.load(f)
                        total_pages = meta.get("num_pages", 0)
                
                # 使用 SectionIndexer 從 document.md 產生準確的 index
                sections = index_sections_from_markdown(
                    markdown_path=document_md,
                    total_pages=total_pages
                )
                
                if sections:
                    return sections
        
        # Fallback：使用基本的 placeholder index
        sections = [
            SectionIndex(
                section_name="Introduction",
                pdf_page_start=1,
                markdown_anchor="# Introduction"
            ),
            SectionIndex(
                section_name="Related Work",
                pdf_page_start=None,
                markdown_anchor="# Related Work"
            ),
            SectionIndex(
                section_name="Method",
                pdf_page_start=None,
                markdown_anchor="# Method" if profile.rough_method_intuition else None
            ),
            SectionIndex(
                section_name="Experiments",
                pdf_page_start=None,
                markdown_anchor="# Experiments" if profile.benchmark_names else None
            ),
            SectionIndex(
                section_name="Conclusion",
                pdf_page_start=None,
                markdown_anchor="# Conclusion"
            ),
        ]
        return [s for s in sections if s.markdown_anchor]
    
    def _create_evidence_index(
        self,
        profile: PaperProfile,
        extraction_dir: Optional[Path] = None
    ) -> List[EvidenceIndex]:
        """建立 evidence index（圖表）
        
        如果 extraction_dir 存在，使用 Docling 輸出產生準確的 index。
        否則，使用 placeholder index。
        """
        # 檢查是否有 Docling 輸出
        if extraction_dir and extraction_dir.exists():
            evidence = index_evidence_from_docling_output(extraction_dir)
            if evidence:
                return evidence
        
        # Fallback：從 mentioned figures/tables 建立基本 index
        evidence = []
        for i, field in enumerate(profile.missing_fields):
            if 'figure' in field.lower() or 'fig' in field.lower():
                evidence.append(EvidenceIndex(
                    evidence_id=f"fig_{i}",
                    evidence_type="figure",
                    caption=field,
                    section="Unknown"
                ))
            elif 'table' in field.lower():
                evidence.append(EvidenceIndex(
                    evidence_id=f"tab_{i}",
                    evidence_type="table",
                    caption=field,
                    section="Unknown"
                ))
        
        return evidence
    
    def _create_routing_policies(
        self,
        reference_pack: Optional[ReferencePack] = None,
    ) -> List[RoutingPolicy]:
        """建立 routing policies"""
        if reference_pack and reference_pack.sections:
            def first_target(*intents: str, default: str = "references/document.md") -> str:
                for section in reference_pack.sections:
                    if any(intent in section.query_intents for intent in intents):
                        return section.path
                return default

            table_target = (
                reference_pack.tables[0]["path"]
                if reference_pack.tables
                else first_target("results", "experiments")
            )
            figure_target = (
                reference_pack.figures[0]["path"]
                if reference_pack.figures
                else first_target("method", "algorithm")
            )
            return [
                RoutingPolicy(
                    query_pattern="Quick summary or paper overview",
                    target_file=first_target("summary", "overview"),
                    fallback_to_pdf=False,
                ),
                RoutingPolicy(
                    query_pattern="Research problem, motivation, or prior limitations",
                    target_file=first_target("motivation", "research_problem"),
                    fallback_to_pdf=True,
                ),
                RoutingPolicy(
                    query_pattern="Algorithm, method, architecture, or implementation details",
                    target_file=first_target("method", "algorithm", "technical_detail"),
                    fallback_to_pdf=True,
                ),
                RoutingPolicy(
                    query_pattern="Experiments, datasets, metrics, evaluation setup",
                    target_file=first_target("experiments", "datasets", "metrics"),
                    fallback_to_pdf=True,
                ),
                RoutingPolicy(
                    query_pattern="Exact results, table values, or comparisons",
                    target_file=table_target,
                    fallback_to_pdf=True,
                ),
                RoutingPolicy(
                    query_pattern="Figures, architecture diagrams, or visual evidence",
                    target_file=figure_target,
                    fallback_to_pdf=True,
                ),
                RoutingPolicy(
                    query_pattern="Limitations, discussion, or future work",
                    target_file=first_target("limitations", "discussion", "future_work"),
                    fallback_to_pdf=True,
                ),
            ]

        return [
            RoutingPolicy(
                query_pattern="What is this paper about",
                target_file="paper_profile.json",
                fallback_to_pdf=False
            ),
            RoutingPolicy(
                query_pattern="What problem does it address",
                target_file="references/problem_and_motivation.md",
                fallback_to_pdf=True
            ),
            RoutingPolicy(
                query_pattern="How does the method work",
                target_file="references/method_guide.md",
                fallback_to_pdf=True
            ),
            RoutingPolicy(
                query_pattern="What experiments were run",
                target_file="references/experiment_guide.md",
                fallback_to_pdf=True
            ),
            RoutingPolicy(
                query_pattern="What benchmarks were used",
                target_file="references/benchmark_and_baselines.md",
                fallback_to_pdf=True
            ),
            RoutingPolicy(
                query_pattern="Which table supports",
                target_file="references/figures_and_tables.md",
                fallback_to_pdf=True
            ),
            RoutingPolicy(
                query_pattern="exact wording",
                target_file="original.pdf",
                fallback_to_pdf=False
            ),
        ]
    
    def _create_skill_md(
        self,
        profile: PaperProfile,
        guides: List[ReferenceGuideInfo],
        policies: List[RoutingPolicy]
    ) -> str:
        """產生 SKILL.md routing manual"""
        
        guides_md = "\n".join([
            f"## Read {g.filename.replace('.md', '').replace('_', ' ')}\n"
            f"Read `references/{g.filename}` when the user asks:\n"
            + "\n".join([f"- {q}" for q in g.query_types])
            for g in guides
        ])
        
        content = f"""---
name: {_skill_safe_name(profile.title, profile.paper_id)}
description: Use this skill when the user asks about "{profile.title}". This skill helps decide which section, table, figure, or PDF region to read before answering. Topics: {', '.join(profile.taxonomy_path[:3]) or 'General'}.
---

# {profile.title}

## Purpose

Use this skill to route questions about this paper to the right level of paper evidence.

## Fast Answer Scope

Use `paper_profile.json` when the user asks:
- What is this paper about?
- What is the high-level contribution?
- Where does this paper fit in the research landscape?
- Quick summary

{guides_md}

## Fallback to Original PDF

Open `original.pdf` and use `section_index.json` when:
- The reference files do not contain enough detail
- The user asks for exact wording, exact metrics, or equation-level explanation
- The answer requires reading a specific table, figure, or appendix
- The query is about a specific claim that needs primary source verification

## Paper Metadata

- **ID**: {profile.paper_id}
- **Theme**: {profile.theme or "Unknown"}
- **Method Family**: {profile.method_family or "Unknown"}
- **Reading Level**: {profile.reading_level}
- **Confidence**: {profile.confidence:.2f}
- **Missing Fields**: {', '.join(profile.missing_fields) or "None"}
"""
        return content

    def _create_progressive_skill_md(
        self,
        profile: PaperProfile,
        reference_pack: ReferencePack,
        policies: List[RoutingPolicy],
    ) -> str:
        """Create a concise, section-aware SKILL.md using original references."""
        skill_name = _skill_safe_name(profile.title, profile.paper_id)
        description = (
            f'Navigates the paper "{profile.title[:160]}". Use when answering questions '
            "about this paper's summary, motivation, method, experiments, results, "
            "tables, figures, limitations, or exact evidence."
        )
        section_map = self._format_section_map(reference_pack)
        table_map = self._format_evidence_map(reference_pack.tables, "table")
        figure_map = self._format_evidence_map(reference_pack.figures, "figure")
        routing_map = "\n".join(
            f"- **{policy.query_pattern}** -> read `{policy.target_file}`"
            for policy in policies
        )
        summary = profile.tldr or profile.rough_contribution or "Use the references below for grounded details."

        return f"""---
name: {skill_name}
description: {description}
---

# {profile.title}

## Summary
{summary}

## Start Here
Use this file as the routing guide. Read only the reference files needed for the current query. If the answer needs exact wording, numbers, algorithms, or visual evidence, read the referenced section/table/figure before answering.

## Query Routing
{routing_map}

## Section References
{section_map}

## Table References
{table_map}

## Figure References
{figure_map}

## Full Paper Fallback
- Read `references/document.md` when the routed section is insufficient or the query asks for exact wording outside the listed sections.
- Continue inspecting more specific references until the answer is grounded in paper text.

## Paper Metadata
- ID: {profile.paper_id}
- Theme: {profile.theme or "Unknown"}
- Method family: {profile.method_family or "Unknown"}
- Reading level: {profile.reading_level}
"""

    def _format_section_map(self, reference_pack: ReferencePack) -> str:
        lines: list[str] = []
        for section in reference_pack.sections[:40]:
            contains = ", ".join(section.likely_contains[:4]) or "paper text"
            intents = ", ".join(section.query_intents[:4]) or "general"
            lines.append(f"- `{section.path}` — {section.title}; likely contains: {contains}; intents: {intents}.")
        return "\n".join(lines) or "- No section files available. Use `references/document.md`."

    def _format_evidence_map(self, entries: list[dict[str, Any]], label: str) -> str:
        if not entries:
            return f"- No {label} references extracted. Use section references or `references/document.md`."
        lines = []
        for entry in entries[:20]:
            contains = ", ".join(entry.get("likely_contains", [])[:4]) or f"{label} evidence"
            lines.append(f"- `{entry['path']}` — {entry['id']}; likely contains: {contains}.")
        return "\n".join(lines)
    
    def _create_metadata(
        self,
        profile: PaperProfile,
        guides: List[ReferenceGuideInfo],
        extraction_dir: Optional[Path] = None
    ) -> Dict[str, Any]:
        """產生 metadata.json
        
        Args:
            profile: 論文 profile
            guides: reference guides 列表
            extraction_dir: 可選的 Docling extraction 目錄
        """
        # 檢查是否有使用 Docling extraction
        has_docling_extraction = False
        num_sections = 0
        num_figures = 0
        num_tables = 0
        
        if extraction_dir and extraction_dir.exists():
            # 檢查是否有 extraction_meta.json
            meta_path = extraction_dir / "extraction_meta.json"
            if meta_path.exists():
                has_docling_extraction = True
                import json
                with open(meta_path, "r", encoding="utf-8") as f:
                    meta = json.load(f)
                    num_sections = meta.get("num_sections", 0)
                    num_figures = meta.get("num_figures", 0)
                    num_tables = meta.get("num_tables", 0)
        
        return {
            "paper_id": profile.paper_id,
            "title": profile.title,
            "created_at": datetime.utcnow().isoformat() + "Z",
            "builder_version": "1.0.0",
            "reading_level": profile.reading_level,
            "has_problem_guide": any(g.filename == "problem_and_motivation.md" for g in guides),
            "has_method_guide": any(g.filename == "method_guide.md" for g in guides),
            "has_experiment_guide": any(g.filename == "experiment_guide.md" for g in guides),
            "has_benchmark_guide": any(g.filename == "benchmark_and_baselines.md" for g in guides),
            "has_limitations_guide": any(g.filename == "limitations.md" for g in guides),
            "fallback_required": len(profile.missing_fields) > 0,
            # Docling extraction info
            "has_docling_extraction": has_docling_extraction,
            "num_sections_indexed": num_sections,
            "num_figures_indexed": num_figures,
            "num_tables_indexed": num_tables,
        }
    
    def _create_skill_description(self, profile: PaperProfile) -> str:
        """產生 skill description for trigger mechanism"""
        topics = profile.taxonomy_path[:2] if profile.taxonomy_path else ["research"]
        methods = profile.baseline_names[:2] if profile.baseline_names else []
        
        desc = f"Skill for paper: {profile.title[:80]}"
        if topics:
            desc += f". Topics: {', '.join(topics)}"
        if methods:
            desc += f". Related methods: {', '.join(methods)}"
        
        return desc


def _skill_safe_name(title: str, paper_id: str | None = None) -> str:
    safe = paper_title_slug(title, paper_id).replace("_", "-")
    safe = "".join(ch if ch.isalnum() or ch == "-" else "-" for ch in safe)
    while "--" in safe:
        safe = safe.replace("--", "-")
    return f"paper-{safe.strip('-')}"[:64]
