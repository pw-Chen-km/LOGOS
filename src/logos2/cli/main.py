"""LOGOS 2.0 CLI Main Entry Point

Usage:
    python -m logos2.cli.main research "Your research question"
    python -m logos2.cli.main qa "What is MRAG?"
    python -m logos2.cli.main status
"""

import os
import sys
import argparse
from pathlib import Path

# Add parent directory to path for development
sys.path.insert(0, str(Path(__file__).parent.parent.parent))


def load_env_file() -> None:
    """Load LOGOS/.env and nearest .env before reading runtime settings."""
    try:
        from dotenv import load_dotenv
    except ImportError:
        return

    logos_root = Path(__file__).resolve().parents[3]
    load_dotenv(logos_root / ".env", override=False)
    load_dotenv(override=False)


def run_research(args):
    """Run the research pipeline"""
    from ..workflow.graph import LogosResearchWorkflow

    workflow = LogosResearchWorkflow(
        paper_skills_dir=args.paper_skills_dir or "paper_skills",
        artifacts_dir=args.artifacts_dir or "artifacts",
        paper_library_dir=args.paper_library_dir or "paper_library",
        neo4j_uri=os.getenv("NEO4J_URI", args.neo4j_uri),
        neo4j_user=os.getenv("NEO4J_USER", args.neo4j_user),
        neo4j_password=os.getenv("NEO4J_PASSWORD", args.neo4j_password),
        config_path=args.config,
    )
    
    print(f"Running research pipeline for: {args.query}")
    print("-" * 50)
    
    try:
        state = workflow.run_research_pipeline(
            user_input=args.query,
            request_id=args.request_id
        )
        
        print(f"\nPipeline completed!")
        print(f"Phase: {state.current_phase}")
        print(f"Paper candidates: {len(state.paper_candidates)}")
        print(f"Web findings: {len(state.web_findings)}")
        if state.taxonomy_source:
            print(f"Taxonomy source: {state.taxonomy_source}")
        if state.evo_thread_id:
            print(f"EvoScientist thread: {state.evo_thread_id}")
        if state.survey_report_paths:
            print("Survey reports:")
            for language, path in state.survey_report_paths.items():
                print(f"  - {language}: {path}")
        print(f"Profiles created: {len(state.paper_profiles)}")
        print(f"Skills created: {len(state.paper_skill_paths)}")
        print(f"Trace file: {state.trace_file}")
        if state.discovery_trace:
            print(
                "Discovery mode: "
                f"{state.discovery_trace.get('mode', 'unknown')} "
                f"(target {state.discovery_trace.get('target_n', '?')})"
            )
        
        if state.errors:
            print(f"\nErrors encountered: {len(state.errors)}")
            for err in state.errors:
                print(f"  - [{err['phase']}] {err['error']}")
        
        return state
        
    except Exception as e:
        print(f"Pipeline failed: {e}")
        raise
    finally:
        workflow.close()


def run_qa(args, previous_state=None):
    """Run QA on existing knowledge base"""
    from ..workflow.graph import LogosResearchWorkflow
    from ..workflow.state import LogosResearchState

    workflow = LogosResearchWorkflow(
        paper_skills_dir=args.paper_skills_dir or "paper_skills",
        artifacts_dir=args.artifacts_dir or "artifacts",
        paper_library_dir=args.paper_library_dir or "paper_library",
        neo4j_uri=os.getenv("NEO4J_URI", args.neo4j_uri),
        neo4j_user=os.getenv("NEO4J_USER", args.neo4j_user),
        neo4j_password=os.getenv("NEO4J_PASSWORD", args.neo4j_password),
        config_path=args.config,
    )
    
    print(f"Q: {args.query}")
    print("-" * 50)
    
    try:
        if previous_state:
            answer = workflow.run_qa(args.query, previous_state)
        else:
            # Create a minimal state for QA-only mode
            state = LogosResearchState(
                workflow_complete=True,
                current_phase="qa"
            )
            answer = workflow.run_qa(args.query, state)
        
        print(f"\nA: {answer}")
        
    except Exception as e:
        print(f"QA failed: {e}")
        raise
    finally:
        workflow.close()


def show_status(args):
    """Show knowledge base status"""
    from ..config import LogosConfig
    from ..storage import SkillRegistry, create_graph_repository, graph_repository_counts
    
    print("LOGOS 2.0 Knowledge Base Status")
    print("=" * 50)
    
    # Check paper skills
    registry = SkillRegistry(args.paper_skills_dir or "paper_skills")
    skills = registry.list_all_skills()
    print(f"\nPaper Skills: {len(skills)}")
    for skill in skills[:5]:  # Show first 5
        print(f"  - {skill['paper_id']}")
    if len(skills) > 5:
        print(f"  ... and {len(skills) - 5} more")
    
    config = LogosConfig.load(args.config)
    repo = create_graph_repository(
        config,
        neo4j_uri=os.getenv("NEO4J_URI", args.neo4j_uri),
        neo4j_user=os.getenv("NEO4J_USER", args.neo4j_user),
        neo4j_password=os.getenv("NEO4J_PASSWORD", args.neo4j_password),
    )

    print(f"\nGraph backend: {config.graph.backend}")
    if config.graph.backend.lower() == "sqlite":
        print(f"Graph DB: {config.graph.sqlite_path}")

    try:
        repo.connect()
        paper_count, relation_count = graph_repository_counts(repo)
        if paper_count is not None:
            print(f"Graph Papers Indexed: {paper_count}")
            print(f"Graph Relations: {relation_count}")
        else:
            print("Graph counts: backend does not expose count helpers")
        print("Graph: Connected")
    except Exception as e:
        print(f"Graph: Not available ({e})")
    finally:
        repo.close()


def setup_paper_navigator(args):
    """Install EvoSkills paper-navigator from a normal terminal."""
    from ..setup import install_paper_navigator

    destination = "global"
    if args.local:
        destination = "local"
    if args.destination:
        destination = args.destination

    result = install_paper_navigator(
        destination=destination,
        force=args.force,
        repo_url=args.repo_url,
    )
    print(result.message)
    if not result.success:
        sys.exit(1)


def check_paper_navigator(args):
    """Show paper-navigator detection status."""
    from ..adapters.evoscientist.paper_navigator_adapter import DirectPaperNavigatorAdapter
    from ..config import LogosConfig

    config = LogosConfig.load(args.config)
    adapter = DirectPaperNavigatorAdapter(config=config)
    report = adapter.validate_installation()

    if report.available:
        print("paper-navigator: available")
        print(f"skill_dir: {report.skill_dir}")
        print(f"scripts_dir: {report.scripts_dir}")
        return

    print("paper-navigator: missing")
    print("\nChecked paths:")
    for path in report.checked_paths:
        print(f"  - {path}")
    print(f"\n{report.setup_hint}")
    sys.exit(1)


def main():
    """Main entry point"""
    load_env_file()

    parser = argparse.ArgumentParser(
        description="LOGOS 2.0 - Paper-Skill-Centered Research Management",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
    # Run research pipeline
    python -m logos2.cli.main research "GraphRAG latest methods"
    
    # Run QA
    python -m logos2.cli.main qa "What is MRAG?"
    
    # Show status
    python -m logos2.cli.main status
        """
    )
    
    # Global options
    parser.add_argument(
        "--paper-skills-dir",
        help="Directory for paper skill packs (default: paper_skills)"
    )
    parser.add_argument(
        "--artifacts-dir",
        help="Directory for artifacts (default: artifacts)"
    )
    parser.add_argument(
        "--paper-library-dir",
        help="Directory for paper library (default: paper_library)"
    )
    parser.add_argument(
        "--neo4j-uri",
        default="neo4j://localhost:7687",
        help="Neo4j URI (default: neo4j://localhost:7687)"
    )
    parser.add_argument(
        "--neo4j-user",
        default="neo4j",
        help="Neo4j user (default: neo4j)"
    )
    parser.add_argument(
        "--neo4j-password",
        default="",
        help="Neo4j password (or use NEO4J_PASSWORD env var)"
    )
    parser.add_argument(
        "--config",
        help="Path to LOGOS config YAML (default: configs/logos2.yaml)"
    )
    
    subparsers = parser.add_subparsers(dest="command", help="Available commands")
    
    # Research command
    research_parser = subparsers.add_parser(
        "research",
        help="Run the research pipeline"
    )
    research_parser.add_argument(
        "query",
        help="Research question or topic"
    )
    research_parser.add_argument(
        "--request-id",
        help="Optional request ID"
    )
    research_parser.set_defaults(func=run_research)
    
    # QA command
    qa_parser = subparsers.add_parser(
        "qa",
        help="Ask questions about the knowledge base"
    )
    qa_parser.add_argument(
        "query",
        help="Question to ask"
    )
    qa_parser.set_defaults(func=run_qa)
    
    # Status command
    status_parser = subparsers.add_parser(
        "status",
        help="Show knowledge base status"
    )
    status_parser.set_defaults(func=show_status)

    # Setup paper-navigator command
    setup_pn_parser = subparsers.add_parser(
        "setup-paper-navigator",
        help="Install EvoSkills paper-navigator without entering EvoScientist CLI"
    )
    setup_pn_parser.add_argument(
        "--global",
        dest="global_install",
        action="store_true",
        help="Install to ~/.evoscientist/skills (default)"
    )
    setup_pn_parser.add_argument(
        "--local",
        action="store_true",
        help="Install to LOGOS/skills"
    )
    setup_pn_parser.add_argument(
        "--destination",
        help="Custom skills root or direct destination parent"
    )
    setup_pn_parser.add_argument(
        "--force",
        action="store_true",
        help="Replace an existing paper-navigator directory"
    )
    setup_pn_parser.add_argument(
        "--repo-url",
        default="https://github.com/EvoScientist/EvoSkills.git",
        help="EvoSkills git URL"
    )
    setup_pn_parser.set_defaults(func=setup_paper_navigator)

    # Check paper-navigator command
    check_pn_parser = subparsers.add_parser(
        "check-paper-navigator",
        help="Validate direct paper-navigator filesystem detection"
    )
    check_pn_parser.set_defaults(func=check_paper_navigator)
    
    args = parser.parse_args()
    
    if not args.command:
        parser.print_help()
        sys.exit(1)
    
    args.func(args)


if __name__ == "__main__":
    main()
