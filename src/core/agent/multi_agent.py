from typing import Dict, TypedDict, List, Annotated, Sequence
import json
from langchain_core.messages import BaseMessage, HumanMessage, AIMessage, SystemMessage, ToolMessage
from langgraph.graph import StateGraph, START, END
from langgraph.graph.message import add_messages
from langchain_openai import ChatOpenAI
from langgraph.prebuilt import ToolNode, tools_condition

import datetime
import os

# --- 1. Define State ---
class AgentState(TypedDict):
    query: str
    schema: str
    plan: str
    messages: Annotated[list, add_messages]
    final_answer: str
    retry_count: int
    feedback: str
    decomposed_concepts: List[str]
    context_map: str   # Pre-flight scan result
    trace_file: str    # Path to the log file for this query

def _log_trace(file_path: str, section_title: str, content: str):
    """Simple helper to append steps to the trace file."""
    if not file_path:
        return
    with open(file_path, "a", encoding="utf-8") as f:
        f.write(f"\n## {section_title} - {datetime.datetime.now().strftime('%H:%M:%S')}\n")
        f.write(f"```\n{content}\n```\n")
        f.write("-" * 40 + "\n")

def create_multi_agent_graph(llm: ChatOpenAI, tools: list):
    
    executor_llm = llm.bind_tools(tools)
    
    # Get the broadcast_scan_tool directly for use in the scanner node (no LLM needed)
    broadcast_scan_tool = next((t for t in tools if t.name == "broadcast_scan_tool"), None)
    
    # --- 2. Define Nodes ---

    def pre_anchor_scanner_node(state: AgentState):
        """Pre-flight: Scans the entire graph for matches to the query, builds a Context Map."""
        
        # Initialize trace file if not exists
        trace_dir = "logs/qa_traces"
        os.makedirs(trace_dir, exist_ok=True)
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        safe_query = "".join([c if c.isalnum() else "_" for c in state["query"][:20]])
        trace_file = os.path.join(trace_dir, f"trace_{timestamp}_{safe_query}.md")
        
        with open(trace_file, "w", encoding="utf-8") as f:
            f.write(f"# QA TRACE: {state['query']}\n")
            f.write(f"Date: {datetime.datetime.now().isoformat()}\n\n")

        if not broadcast_scan_tool:
            result = "Scanner unavailable."
        else:
            result = broadcast_scan_tool.invoke({"query": state["query"]})
        
        _log_trace(trace_file, "PRE-ANCHOR SCANNER (QCM)", result)
        return {"context_map": result, "trace_file": trace_file}

    def planner_node(state: AgentState):
        """The Brain: Uses the Context Map to write a grounded execution plan."""
        
        retry_info = ""
        if state.get("feedback"):
            retry_info = f"\n\nPREVIOUS ATTEMPT FAILED: {state['feedback']}\nBecause the previous approach failed, broaden your keywords and suggest an alternative navigation path. Do NOT just repeat the same keywords."

        context_map_section = ""
        if state.get("context_map"):
            context_map_section = f"""
QUERY CONTEXT MAP (Pre-scanned from graph — use this as your ground truth):
{state['context_map']}
CRITICAL: Use ONLY node names and types listed above. Do NOT anchor on nodes not shown in the context map.
"""

        prompt = f"""You are a Master Graph Routing Planner.
Answer the user's query by writing a concise execution plan for a Neo4j Knowledge Graph.

USER QUERY: {state['query']}{retry_info}

GRAPH SCHEMA:
{state['schema']}
{context_map_section}

ONTOLOGY RULES (Mixed Hierarchy):
1. **Paper** only has a `title`. ALL content is in child nodes.
2. **L2 nodes** (1 hop from Paper):
   - Summary (year, short_claim)
   - Keyword (name)
   - ResearchProblem (summary)
   - Method (high_level_description)
   - Experiment (result)
3. **L3 nodes** (2 hops via L2 parents):
   - ResearchProblem → PreviousLimitation (limitation)
   - ResearchProblem → UnderlyingResearchProblem (detail)
   - Method → MethodDetail (detailed architecture)
   - Method → ReferredAlgorithm (inspired-by algorithms)
   - Experiment → ExperimentAnalysis (experimental design, SOTA, ablation)
   - Experiment → ComparedMethod (baseline names)
   - Experiment → Dataset (dataset names)

4. **read_properties_tool** levels:
   - L1: year, short_claim
   - L2: research problem, prior limitations, underlying detail
   - L3: method brief/detail, referred algorithms, experiment results/analysis, datasets, baselines
5. MAX 5 steps. ONE read per Paper.

Format:
Step 0: [Ground truth from context map]
Step 1: Anchor [node] as [type]
Step 2: Navigate [Source] -[EDGE]-> [Target]
Step 3: Read properties of [Paper Title] at level [L1/L2/L3]
"""
        _log_trace(state.get("trace_file"), "PLANNER INPUT (PROMPT)", prompt)
        response = llm.invoke([HumanMessage(content=prompt)])
        _log_trace(state.get("trace_file"), "PLANNER OUTPUT (PLAN)", response.content)
        
        new_count = state.get("retry_count", 0)
        if state.get("feedback"):
             new_count += 1
             
        return {"plan": response.content, "retry_count": new_count, "feedback": ""}
        
    def executor_node(state: AgentState):
        """The Hands: Takes the plan and executes tools. Performs relevance checks."""
        
        system_msg = SystemMessage(content=f"""You are a Tool Executor Agent.
Your job is to execute the planned steps. 
CRITICAL: If a tool returns a result with a LOW similarity score, an 'error' message about thresholds, or an EMPTY list, DO NOT CONTINUE. 
Instead, output a clear failure message starting with 'FAILURE FEEDBACK:' and explaining what happened.
NEVER lower the score_threshold on your own.
Plan to follow:
{state['plan']}
""")
        _log_trace(state.get("trace_file"), "EXECUTOR (STARTING EXECUTION)", f"Plan:\n{state['plan']}\n\nRunning tools...")
        msg_list = [system_msg] + state['messages']
        response = executor_llm.invoke(msg_list)
        
        # Log tool outputs (all messages except system_msg)
        tool_outputs = "\n".join([str(m.content) for m in state['messages'] if isinstance(m, ToolMessage)])
        _log_trace(state.get("trace_file"), "TOOL EXECUTION RESULTS", tool_outputs if tool_outputs else "No tool calls in this iteration yet.")
        _log_trace(state.get("trace_file"), "EXECUTOR OUTPUT (SUMMARY)", response.content)
        
        feedback = ""
        if "FAILURE FEEDBACK:" in response.content:
            feedback = response.content.split("FAILURE FEEDBACK:")[1].strip()

        return {"messages": [response], "feedback": feedback}
        
    def synthesizer_node(state: AgentState):
        """The Spokesperson: Writes the final answer based on gathered context."""
        
        context_str = "\n".join([m.content for m in state['messages'] if isinstance(m, (AIMessage, ToolMessage))])
        
        prompt = f"""You are the Final Synthesizer Agent.
Answer the user's original query based ONLY on the context gathered.

USER QUERY: {state['query']}

GATHERED CONTEXT:
{context_str}

If the context indicates that no relevant information was found even after retries, explain what was searched for and why it yielded no results instead of hallucinating. Answer in the same language as the query.
"""
        _log_trace(state.get("trace_file"), "SYNTHESIZER INPUT (CONTEXT)", prompt)
        response = llm.invoke([HumanMessage(content=prompt)])
        _log_trace(state.get("trace_file"), "SYNTHESIZER OUTPUT (FINAL)", response.content)
        
        return {"final_answer": response.content}

    # --- 3. Custom Router ---
    def route_after_executor(state: AgentState):
        last_msg = state["messages"][-1]
        
        if isinstance(last_msg, AIMessage) and last_msg.tool_calls:
            return "tools"
            
        if state.get("feedback") and state.get("retry_count", 0) < 3:
            return "replan"
            
        return "synthesize"

    # --- 4. Define Graph Builder ---
    workflow = StateGraph(AgentState)
    
    workflow.add_node("pre_anchor_scanner", pre_anchor_scanner_node)
    workflow.add_node("planner", planner_node)
    workflow.add_node("executor", executor_node)
    workflow.add_node("tools", ToolNode(tools))
    workflow.add_node("synthesizer", synthesizer_node)
    
    # Scanner runs first, then feeds Planner
    workflow.add_edge(START, "pre_anchor_scanner")
    workflow.add_edge("pre_anchor_scanner", "planner")
    workflow.add_edge("planner", "executor")
    
    workflow.add_conditional_edges(
        "executor",
        route_after_executor, 
        {
            "tools": "tools", 
            "replan": "planner",   # Re-plan skips scanner (context_map already built)
            "synthesize": "synthesizer"
        }
    )
    
    workflow.add_edge("tools", "executor")
    workflow.add_edge("synthesizer", END)
    
    return workflow.compile()

