"""Workflow Trace Logging

QA trace logging for LangGraph workflow.
Reused concept from old multi_agent.py.
"""

import os
from pathlib import Path
from datetime import datetime
from typing import Optional


class WorkflowTracer:
    """Workflow step tracer
    
    Logs each step of the research workflow for debugging and auditing.
    """
    
    def __init__(self, log_dir: str = "logs/workflow_traces"):
        self.log_dir = Path(log_dir)
        self.log_dir.mkdir(parents=True, exist_ok=True)
        self.current_trace_file: Optional[Path] = None
    
    def start_trace(self, trace_id: str, metadata: Optional[dict] = None) -> str:
        """Start a new trace file
        
        Args:
            trace_id: Unique trace identifier
            metadata: Optional metadata to include
            
        Returns:
            str: Path to trace file
        """
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        safe_id = "".join(c if c.isalnum() or c in "-_" else "_" for c in trace_id[:30])
        
        self.current_trace_file = self.log_dir / f"trace_{timestamp}_{safe_id}.md"
        
        with open(self.current_trace_file, "w", encoding="utf-8") as f:
            f.write(f"# Workflow Trace: {trace_id}\n")
            f.write(f"Date: {datetime.now().isoformat()}\n\n")
            
            if metadata:
                f.write("## Metadata\n")
                for key, value in metadata.items():
                    f.write(f"- **{key}**: {value}\n")
                f.write("\n")
        
        return str(self.current_trace_file)
    
    def log_step(self, section_title: str, content: str):
        """Log a workflow step
        
        Args:
            section_title: Title of the step
            content: Content to log
        """
        if not self.current_trace_file:
            # Auto-start trace if not started
            self.start_trace("auto_trace")
        
        timestamp = datetime.now().strftime("%H:%M:%S")
        
        with open(self.current_trace_file, "a", encoding="utf-8") as f:
            f.write(f"\n## {section_title} - {timestamp}\n")
            f.write(f"```\n{content}\n```\n")
            f.write("-" * 40 + "\n")
    
    def log_node_enter(self, node_name: str, state: dict):
        """Log entering a workflow node"""
        self.log_step(f"ENTER: {node_name}", f"State keys: {list(state.keys())}")
    
    def log_node_exit(self, node_name: str, result: dict):
        """Log exiting a workflow node"""
        self.log_step(f"EXIT: {node_name}", f"Result keys: {list(result.keys())}")
    
    def log_error(self, node_name: str, error: Exception):
        """Log an error in a node"""
        self.log_step(f"ERROR in {node_name}", f"{type(error).__name__}: {str(error)}")
    
    def get_trace_path(self) -> Optional[str]:
        """Get current trace file path"""
        return str(self.current_trace_file) if self.current_trace_file else None
