"""LangGraph Workflow Definition

Research workflow: 
START → intent_intake → paper_discovery → survey_taxonomy_generation 
      → profile_normalization → paper_skill_building → lightweight_graph_indexing 
      → qa_ready → END

Optional path:
candidate_edge_selected → cross_paper_edge_verification → update_graph_edge_status
"""

from typing import Optional, Callable, Any
from dataclasses import asdict
from pathlib import Path

# Note: In MVP, we use a simplified workflow without LangGraph dependency
# Future versions can migrate to actual LangGraph

from ..config import LogosConfig
from ..schemas import ResearchRequest
from ..adapters import PaperNavigatorAdapter
from ..extraction import DoclingExtractor
from ..nodes import (
    SurveyTaxonomyGenerator,
    ProfileNormalizer,
    PaperSkillBuilder,
    IterativeDiscovery,
    EvoSurveyAgentDiscovery,
    LightweightGraphIndexer,
    QAAgent,
    EdgeVerifier,
)
from ..storage import SkillRegistry, create_graph_repository
from .state import LogosResearchState
from .trace import WorkflowTracer


class LogosResearchWorkflow:
    """LOGOS 2.0 Research Workflow
    
    MVP implementation using a simple step-based execution.
    Future versions can integrate with LangGraph for more complex routing.
    """
    
    def __init__(
        self,
        paper_skills_dir: str = "paper_skills",
        artifacts_dir: str = "artifacts",
        paper_library_dir: str = "paper_library",
        neo4j_uri: Optional[str] = None,
        neo4j_user: Optional[str] = None,
        neo4j_password: Optional[str] = None,
        config: Optional[LogosConfig] = None,
        config_path: Optional[str] = None,
    ):
        """Initialize workflow with all components
        
        Args:
            paper_skills_dir: Directory for paper skill packs
            artifacts_dir: Directory for taxonomy artifacts
            paper_library_dir: Directory for PDF library
            neo4j_uri: Neo4j URI
            neo4j_user: Neo4j user
            neo4j_password: Neo4j password
        """
        self.config = config or LogosConfig.load(config_path)
        self.paper_skills_dir = paper_skills_dir or str(self.config.runtime.paper_skills_dir)
        self.artifacts_dir = artifacts_dir or str(self.config.runtime.artifacts_dir)
        self.paper_library_dir = paper_library_dir or str(self.config.runtime.paper_library_dir)
        
        # Initialize components
        self.tracer = WorkflowTracer()
        self.navigator = PaperNavigatorAdapter(
            artifact_dir=self.artifacts_dir,
            paper_library_dir=self.paper_library_dir,
            config=self.config,
        )
        self.discovery = IterativeDiscovery(self.navigator, config=self.config)
        self.survey_agent_discovery = EvoSurveyAgentDiscovery(config=self.config)
        self.taxonomy_generator = SurveyTaxonomyGenerator(output_dir=self.artifacts_dir)
        self.normalizer = ProfileNormalizer(output_dir=self.paper_skills_dir)
        self.skill_builder = PaperSkillBuilder(paper_skills_dir=self.paper_skills_dir)
        self.docling_extractor = DoclingExtractor(output_base_dir=self.paper_library_dir)
        
        # Storage
        self.repository = create_graph_repository(
            self.config,
            neo4j_uri=neo4j_uri,
            neo4j_user=neo4j_user,
            neo4j_password=neo4j_password,
        )
        self.skill_registry = SkillRegistry(paper_skills_dir=self.paper_skills_dir)
        
        # Nodes with storage
        self.indexer = LightweightGraphIndexer(repository=self.repository)
        self.qa_agent = QAAgent(repository=self.repository, skill_registry=self.skill_registry)
        self.edge_verifier = EdgeVerifier(repository=self.repository, skill_registry=self.skill_registry)
    
    def run_research_pipeline(
        self,
        user_input: str,
        request_id: Optional[str] = None,
    ) -> LogosResearchState:
        """Run the complete research pipeline
        
        Args:
            user_input: Natural language research idea
            request_id: Optional request ID
            
        Returns:
            LogosResearchState: Final workflow state
        """
        # Initialize state
        state = LogosResearchState(
            user_request=user_input,
            current_phase="init",
            request_id=request_id,
        )
        
        # Start trace
        trace_path = self.tracer.start_trace(
            request_id or f"research_{id(state)}",
            {"user_input": user_input}
        )
        state.trace_file = trace_path
        
        try:
            # Phase 1: Intent Intake (MVP - simplified)
            state = self._intent_intake(state)
            
            # Phase 2: Paper Discovery
            state = self._paper_discovery(state)
            
            # Phase 3: Survey Taxonomy Generation
            state = self._taxonomy_generation(state)
            
            # Phase 4: Profile Normalization
            state = self._profile_normalization(state)
            
            # Phase 5: Paper Skill Building
            state = self._skill_building(state)
            
            # Phase 6: Lightweight Graph Indexing
            state = self._graph_indexing(state)
            
            # Pipeline complete
            state.current_phase = "complete"
            state.workflow_complete = True
            
        except Exception as e:
            state.add_error(state.current_phase, str(e))
            self.tracer.log_error(state.current_phase, e)
            raise
        
        return state
    
    def run_qa(self, query: str, state: LogosResearchState) -> str:
        """Run QA on the built knowledge base
        
        Args:
            query: User question
            state: Current workflow state (must have completed pipeline)
            
        Returns:
            str: Answer
        """
        if not state.workflow_complete:
            raise ValueError("Research pipeline must be completed before QA")
        
        state.current_query = query
        state.current_phase = "qa"
        
        self.tracer.log_step("QA_START", f"Query: {query}")
        
        try:
            result = self.qa_agent.answer(query)
            
            state.qa_answer = result.answer
            state.qa_status = "completed"
            
            # Add to trace
            trace_entry = {
                "query": query,
                "answer": result.answer,
                "sources": result.source_paper_ids,
                "files_read": result.files_read,
                "confidence": result.confidence,
            }
            state.qa_trace.append(trace_entry)
            
            self.tracer.log_step("QA_COMPLETE", f"Answer confidence: {result.confidence}")
            
            # Optional: Edge verification if needed
            if result.needs_verification and result.source_paper_ids:
                state = self._optional_edge_verification(state, result.source_paper_ids)
            
            return result.answer
            
        except Exception as e:
            state.qa_error = str(e)
            state.qa_status = "failed"
            self.tracer.log_error("qa", e)
            raise
    
    def _intent_intake(self, state: LogosResearchState) -> LogosResearchState:
        """Phase 1: Intent Intake
        
        MVP: Simplified - create ResearchRequest from user input
        Future: Use LLM to clarify intent and create structured request
        """
        state.current_phase = "intent_intake"
        self.tracer.log_node_enter("intent_intake", asdict(state))
        
        # Extract basic info from user input
        import re
        
        # Try to extract paper count target
        paper_count = 50
        match = re.search(r'(\d+)\s*(papers?|articles?)', state.user_request, re.IGNORECASE)
        if match:
            paper_count = int(match.group(1))
        
        # Try to extract year range
        time_range = None
        year_match = re.search(r'(\d{4})\s*-\s*(\d{4})', state.user_request)
        if year_match:
            from_year = int(year_match.group(1))
            to_year = int(year_match.group(2))
            time_range = {"from_year": from_year, "to_year": to_year}
        
        # Create research request
        import uuid
        request_id = state.request_id or f"req_{uuid.uuid4().hex[:8]}"
        
        state.research_request = {
            "request_id": request_id,
            "raw_user_input": state.user_request,
            "research_goal": state.user_request,
            "paper_count_target": paper_count,
            "time_range": time_range,
            "survey_profile": "survey",
        }
        state.request_id = request_id
        
        self.tracer.log_node_exit("intent_intake", {
            "request_id": request_id,
            "paper_count": paper_count
        })
        
        return state
    
    def _paper_discovery(self, state: LogosResearchState) -> LogosResearchState:
        """Phase 2: Paper Discovery
        
        MVP: Load from artifacts
        Future: Integrate with external paper-navigator skill
        """
        state.current_phase = "paper_discovery"
        self.tracer.log_node_enter("paper_discovery", asdict(state))
        
        try:
            run_dir = self.config.runtime.runs_dir / (state.request_id or "unknown")
            self.navigator.run_dir = run_dir

            request = ResearchRequest(**state.research_request)
            install_report = self.navigator.validate_installation()
            readings = []
            discovery = None

            if self._use_survey_agent():
                try:
                    self.survey_agent_discovery.run_dir = run_dir
                    discovery = self.survey_agent_discovery.run(request)
                except Exception as discovery_error:
                    self.tracer.log_error("paper_discovery_survey_agent", discovery_error)
                    if not self.config.survey_agent.fallback_to_direct:
                        raise

            if discovery is None and install_report.available:
                try:
                    discovery = self.discovery.run(request)
                except Exception as discovery_error:
                    self.tracer.log_error("paper_discovery_live", discovery_error)
            elif discovery is None:
                self.tracer.log_step("PAPER_NAVIGATOR_MISSING", install_report.setup_hint)

            if discovery is not None:
                try:
                    state.paper_candidates = [
                        candidate.model_dump()
                        for candidate in discovery.paper_candidates
                    ]
                    state.paper_metadata = {
                        paper_id: metadata.model_dump()
                        for paper_id, metadata in discovery.metadata_map.items()
                    }
                    state.web_findings = discovery.web_findings
                    state.discovery_trace = discovery.trace
                    state.survey_report_paths = discovery.survey_report_paths
                    state.evo_thread_id = discovery.evo_thread_id
                    if discovery.survey_taxonomy is not None:
                        state.survey_taxonomy = discovery.survey_taxonomy.model_dump()
                        state.taxonomy_id = discovery.survey_taxonomy.taxonomy_id
                        state.taxonomy_source = "evoscientist_survey_agent"
                    readings = discovery.readings
                    self.navigator.save_artifacts(
                        run_dir=run_dir,
                        candidates=discovery.paper_candidates,
                        metadata_map=discovery.metadata_map,
                        readings=readings,
                        pdf_manifest=discovery.pdf_manifest,
                    )
                    self._save_discovery_extras(
                        run_dir,
                        discovery.trace,
                        discovery.web_findings,
                        discovery.survey_report_paths,
                    )
                except Exception as discovery_error:
                    self.tracer.log_error("paper_discovery_artifact_save", discovery_error)

            # Artifact replay remains useful for tests and offline runs.
            try:
                artifact_readings = self.navigator.load_artifacts(self.artifacts_dir)
            except FileNotFoundError:
                artifact_readings = []
            if artifact_readings and not readings:
                readings = artifact_readings

            state.paper_navigator_readings = [r.model_dump() for r in readings]
            state.discovery_status = "completed"
            
            self.tracer.log_node_exit("paper_discovery", {
                "papers_found": len(readings),
                "web_findings": len(state.web_findings),
                "taxonomy_source": state.taxonomy_source or "logos_generator",
            })
            
        except Exception as e:
            state.discovery_error = str(e)
            state.discovery_status = "failed"
            self.tracer.log_error("paper_discovery", e)
            # Continue with empty readings for MVP testing
            state.paper_navigator_readings = []
        
        return state

    def _use_survey_agent(self) -> bool:
        return (
            self.config.paper_navigator.mode == "survey_agent"
            and self.config.survey_agent.enabled
            and self.config.evoscientist.enabled
        )

    def _save_discovery_extras(
        self,
        run_dir: Any,
        discovery_trace: dict[str, Any],
        web_findings: list[dict[str, Any]],
        survey_report_paths: dict[str, str] | None = None,
    ) -> None:
        import json

        base = run_dir / "paper_navigator"
        base.mkdir(parents=True, exist_ok=True)
        (base / "discovery_trace.json").write_text(
            json.dumps(discovery_trace, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        (base / "web_findings.json").write_text(
            json.dumps(web_findings, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        (base / "survey_report_paths.json").write_text(
            json.dumps(survey_report_paths or {}, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
    
    def _taxonomy_generation(self, state: LogosResearchState) -> LogosResearchState:
        """Phase 3: Survey Taxonomy Generation"""
        state.current_phase = "taxonomy_generation"
        self.tracer.log_node_enter("taxonomy_generation", asdict(state))
        
        if not state.paper_navigator_readings:
            state.taxonomy_error = "No paper readings available"
            state.taxonomy_status = "failed"
            return state
        
        try:
            from ..schemas import PaperNavigatorReading, SurveyTaxonomy

            if state.survey_taxonomy:
                taxonomy = SurveyTaxonomy(**state.survey_taxonomy)
                self.taxonomy_generator._save_taxonomy(taxonomy)
                state.taxonomy_id = taxonomy.taxonomy_id
                state.taxonomy_status = "completed"
                state.taxonomy_source = state.taxonomy_source or "evoscientist_survey_agent"
                self.tracer.log_node_exit("taxonomy_generation", {
                    "taxonomy_id": taxonomy.taxonomy_id,
                    "themes": len(taxonomy.themes),
                    "relations": len(taxonomy.candidate_relations),
                    "source": state.taxonomy_source,
                })
                return state
            
            # Convert dicts back to objects
            readings = [PaperNavigatorReading(**r) for r in state.paper_navigator_readings]
            
            # Generate taxonomy
            taxonomy = self.taxonomy_generator.generate(
                readings=readings,
                request_id=state.request_id or "unknown"
            )
            
            state.survey_taxonomy = taxonomy.model_dump()
            state.taxonomy_id = taxonomy.taxonomy_id
            state.taxonomy_status = "completed"
            state.taxonomy_source = "logos_generator"
            
            self.tracer.log_node_exit("taxonomy_generation", {
                "taxonomy_id": taxonomy.taxonomy_id,
                "themes": len(taxonomy.themes),
                "relations": len(taxonomy.candidate_relations),
                "source": state.taxonomy_source,
            })
            
        except Exception as e:
            state.taxonomy_error = str(e)
            state.taxonomy_status = "failed"
            self.tracer.log_error("taxonomy_generation", e)
        
        return state
    
    def _profile_normalization(self, state: LogosResearchState) -> LogosResearchState:
        """Phase 4: Profile Normalization"""
        state.current_phase = "profile_normalization"
        self.tracer.log_node_enter("profile_normalization", asdict(state))
        
        if not state.paper_navigator_readings or not state.survey_taxonomy:
            state.profile_error = "Missing readings or taxonomy"
            state.profile_status = "failed"
            return state
        
        try:
            from ..schemas import PaperNavigatorReading, SurveyTaxonomy
            
            readings = [PaperNavigatorReading(**r) for r in state.paper_navigator_readings]
            taxonomy = SurveyTaxonomy(**state.survey_taxonomy)
            
            # Normalize all profiles
            profiles = self.normalizer.normalize_batch(
                readings,
                taxonomy,
                metadata_map=state.paper_metadata,
            )
            
            state.paper_profiles = [p.model_dump() for p in profiles]
            state.profile_status = "completed"
            
            self.tracer.log_node_exit("profile_normalization", {
                "profiles_created": len(profiles)
            })
            
        except Exception as e:
            state.profile_error = str(e)
            state.profile_status = "failed"
            self.tracer.log_error("profile_normalization", e)
        
        return state

    def _candidate_to_metadata_reading(self, candidate: dict) -> Any:
        """Create a minimal reading so taxonomy/profile can proceed after discovery."""
        from ..schemas import PaperNavigatorReading

        title = candidate.get("title") or candidate.get("paper_id") or "Unknown paper"
        tldr = candidate.get("tldr") or candidate.get("abstract") or title
        missing_fields = [
            "main_contribution",
            "problem_statement",
            "method_intuition",
            "rough_limitation",
        ]
        return PaperNavigatorReading(
            paper_id=candidate.get("paper_id") or title,
            reading_level="metadata_only",
            title=title,
            tldr=tldr,
            confidence=0.3,
            missing_fields=missing_fields,
        )
    
    def _skill_building(self, state: LogosResearchState) -> LogosResearchState:
        """Phase 5: Paper Skill Building"""
        state.current_phase = "skill_building"
        self.tracer.log_node_enter("skill_building", asdict(state))
        
        if not state.paper_profiles:
            state.skill_build_error = "No profiles available"
            state.skill_build_status = "failed"
            return state
        
        try:
            from ..schemas import PaperProfile
            
            profiles = [PaperProfile(**p) for p in state.paper_profiles]
            extraction_map = self._prepare_extraction_map(profiles, state)
            
            # Build skill packs for all profiles
            manifests = self.skill_builder.build_batch(profiles, extraction_map=extraction_map)
            
            state.paper_skill_paths = [m.skill_md_path for m in manifests]
            state.skill_build_status = "completed"
            
            # Register with skill registry
            for manifest in manifests:
                self.skill_registry.register(manifest)
            
            self.tracer.log_node_exit("skill_building", {
                "skills_created": len(manifests),
                "extractions": len(extraction_map),
            })
            
        except Exception as e:
            state.skill_build_error = str(e)
            state.skill_build_status = "failed"
            self.tracer.log_error("skill_building", e)
        
        return state

    def _prepare_extraction_map(
        self,
        profiles: list[Any],
        state: LogosResearchState,
    ) -> dict[str, Path]:
        """Run Docling extraction for profiles with available PDF sources."""
        extraction_map: dict[str, Path] = {}
        if not self.config.docling.enabled:
            return extraction_map

        for profile in profiles:
            metadata = state.paper_metadata.get(profile.paper_id, {})
            pdf_source = self._resolve_pdf_source(profile, metadata)
            if not pdf_source:
                self.tracer.log_step(
                    "PDF_EXTRACTION_SKIPPED",
                    f"{profile.paper_id}: no PDF source",
                )
                continue

            result = self.docling_extractor.extract(
                pdf_source,
                profile.paper_id,
                force_reextract=self.config.docling.force_reextract,
            )
            if result.success and result.output_dir:
                extraction_map[profile.paper_id] = result.output_dir
                self.tracer.log_step(
                    "PDF_EXTRACTION_COMPLETE",
                    f"{profile.paper_id}: {result.output_dir}",
                )
            else:
                self.tracer.log_step(
                    "PDF_EXTRACTION_FAILED",
                    f"{profile.paper_id}: {result.error}",
                )
        return extraction_map

    def _resolve_pdf_source(self, profile: Any, metadata: dict[str, Any]) -> str | None:
        """Resolve local path or URL suitable for Docling conversion."""
        candidates = [
            metadata.get("pdf_path"),
            profile.pdf_path,
            metadata.get("pdf_url"),
        ]

        raw_data = metadata.get("raw_data") if isinstance(metadata, dict) else None
        if isinstance(raw_data, dict):
            open_pdf = raw_data.get("openAccessPdf")
            if isinstance(open_pdf, dict):
                candidates.append(open_pdf.get("url"))

        for candidate in candidates:
            if not candidate:
                continue
            value = str(candidate)
            if value.startswith(("http://", "https://")):
                return value
            path = Path(value)
            if path.exists():
                return str(path)

        arxiv_id = metadata.get("arxiv_id")
        if not arxiv_id and str(profile.paper_id).lower().startswith("arxiv:"):
            arxiv_id = profile.paper_id
        if arxiv_id:
            arxiv = str(arxiv_id)
            if arxiv.lower().startswith("arxiv:"):
                arxiv = arxiv.split(":", 1)[1]
            if arxiv:
                return f"https://arxiv.org/pdf/{arxiv}"

        return None
    
    def _graph_indexing(self, state: LogosResearchState) -> LogosResearchState:
        """Phase 6: Lightweight Graph Indexing"""
        state.current_phase = "graph_indexing"
        self.tracer.log_node_enter("graph_indexing", asdict(state))
        
        if not state.paper_profiles or not state.survey_taxonomy:
            state.indexing_error = "Missing profiles or taxonomy"
            state.indexing_status = "failed"
            return state
        
        try:
            from ..schemas import PaperProfile, SurveyTaxonomy, CandidateRelation
            
            taxonomy = SurveyTaxonomy(**state.survey_taxonomy)
            profiles = [PaperProfile(**p) for p in state.paper_profiles]
            
            # Index everything
            result = self.indexer.run(taxonomy, profiles)
            
            state.neo4j_index_status = result
            state.indexing_status = "completed" if result["success"] else "failed"
            if result.get("error"):
                state.indexing_error = result["error"]
            
            self.tracer.log_node_exit("graph_indexing", result)
            
        except Exception as e:
            state.indexing_error = str(e)
            state.indexing_status = "failed"
            self.tracer.log_error("graph_indexing", e)
        
        return state
    
    def _optional_edge_verification(
        self,
        state: LogosResearchState,
        paper_ids: list
    ) -> LogosResearchState:
        """Optional Phase: Edge Verification for QA context
        
        Only runs when QA determines verification is needed.
        """
        state.current_phase = "edge_verification"
        self.tracer.log_node_enter("edge_verification", asdict(state))
        
        try:
            # Find relations between mentioned papers
            from ..schemas import CandidateRelation, VerifiedEdge
            
            candidate_relations = [
                CandidateRelation(**r) for r in state.survey_taxonomy.get("candidate_relations", [])
            ]
            
            # Filter for relations between mentioned papers
            relevant_relations = [
                r for r in candidate_relations
                if r.source_paper_id in paper_ids and r.target_paper_id in paper_ids
            ]
            
            # Verify each
            verified = []
            rejected = []
            
            for relation in relevant_relations[:3]:  # Limit to 3 per QA
                result = self.edge_verifier.verify(relation)
                
                if result.success and result.verified_edge:
                    verified.append(result.verified_edge.model_dump())
                elif not result.success:
                    if result.verified_edge:
                        rejected.append(result.verified_edge.model_dump())
            
            state.verified_edges = verified
            state.rejected_edges = rejected
            state.verification_status = "completed"
            
            self.tracer.log_node_exit("edge_verification", {
                "verified": len(verified),
                "rejected": len(rejected)
            })
            
        except Exception as e:
            state.verification_error = str(e)
            state.verification_status = "failed"
            self.tracer.log_error("edge_verification", e)
        
        return state
    
    def close(self):
        """Close all connections"""
        self.indexer.close()
        self.qa_agent.close()
        self.edge_verifier.close()
        self.repository.close()
