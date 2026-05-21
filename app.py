import streamlit as st
import os
from dotenv import load_dotenv

# Import the backend LLM/Graph classes
from langchain_openai import ChatOpenAI, OpenAIEmbeddings
from src.core.agent.multi_agent import create_multi_agent_graph
from src.core.graph.neo4j_client import Neo4jClient
from src.core.agent.qa_tools import GraphQAToolsFactory

# Load environment variables
load_dotenv()

st.set_page_config(page_title="Agentic H-GraphRAG", page_icon="🕸️", layout="wide")
st.title("🕸️ Agentic Heterogeneous GraphRAG")
st.caption("Ask complex questions about AI papers, benchmarks, and methods.")

# --- Sidebar Configuration ---
with st.sidebar:
    st.header("⚙️ Configuration")
    
    # Try to load default from ENV first
    default_api_key = os.getenv("OPENAI_API_KEY", "") # Fallback to empty string for safety
    default_uri = os.getenv("NEO4J_URI", "neo4j://127.0.0.1:7687")
    default_user = os.getenv("NEO4J_USER", "neo4j")
    default_pass = os.getenv("NEO4J_PASSWORD", "420420420")
    
    api_key = st.text_input("OpenAI API Key", value=default_api_key, type="password")
    neo4j_uri = st.text_input("Neo4j URI", value=default_uri)
    neo4j_user = st.text_input("Neo4j Username", value=default_user)
    neo4j_pass = st.text_input("Neo4j Password", value=default_pass, type="password")
    
    st.markdown("---")
    architecture = st.sidebar.radio("Agent Architecture", ["Multi-Agent (LangGraph)", "Legacy Single-Agent (ReAct)"])
    
    st.markdown("---")
    st.markdown("### Powered By")
    st.markdown("- **LangGraph**: Cognitive Query Routing")
    st.markdown("- **Neo4j**: Heterogeneous Graph")
    st.markdown("- **OpenAI**: Embeddings & Reasoning")

# --- Initialize Session State ---
if "messages" not in st.session_state:
    st.session_state.messages = []

# Instantiate the Agent only if credentials exist
@st.cache_resource(show_spinner="Initializing Backend System...")
def get_agent(_api_key, _uri, _user, _pwd, _architecture):
    if not _api_key:
        return None
        
    llm = ChatOpenAI(model="gpt-4o-mini", api_key=_api_key, temperature=0.1)
    embeddings = OpenAIEmbeddings(api_key=_api_key, model="text-embedding-3-small")
    db_client = Neo4jClient(_uri, _user, _pwd)
    
    factory = GraphQAToolsFactory(db_client, embeddings)
    tools = factory.get_tools()

    # Fetch schema once on initialization
    try:
        schema = tools[0].invoke({}) # Assuming First tool is schema tool
    except Exception:
        schema = "Schema fetch failed."
        
    if _architecture == "Legacy Single-Agent (ReAct)":
        from src.core.agent.legacy_agent import create_legacy_agent
        agent = create_legacy_agent(llm=llm, tools=tools)
    else:
        agent = create_multi_agent_graph(llm=llm, tools=tools)
        
    return agent, schema

# --- Chat Interface ---
for msg in st.session_state.messages:
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])
        if "reasoning" in msg:
            with st.expander("Agent Reasoning Steps"):
                st.markdown(msg["reasoning"])

if prompt := st.chat_input("Ex: 誰用CS資料集？"):
    if not api_key:
        st.error("Please enter your OpenAI API Key in the sidebar to start.")
        st.stop()
        
    # User message
    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)

    # Bot response
    with st.chat_message("assistant"):
        agent_tuple = get_agent(api_key, neo4j_uri, neo4j_user, neo4j_pass, architecture)
        if not agent_tuple:
            st.error("Failed to initialize Agent. Please check configuration.")
            st.stop()
            
        agent, current_schema = agent_tuple
        
        reasoning_log = ""
        final_answer = ""
        
        # Interactive status container for reasoning
        with st.status(f"Agent is thinking... ({architecture})", expanded=True) as status:
            step_count = 0
            
            if architecture == "Multi-Agent (LangGraph)":
                # Initialize empty state dictionary matching AgentState
                initial_state = {
                    "query": prompt,
                    "schema": current_schema,
                    "plan": "",
                    "messages": [],
                    "final_answer": "",
                    "retry_count": 0,
                    "feedback": "",
                    "decomposed_concepts": [],
                    "context_map": "",
                    "trace_file": ""
                }
                
                # Stream the multi-agent logic
                for step in agent.stream(initial_state):
                    for node_name, node_state in step.items():
                        if node_name == "pre_anchor_scanner":
                            context = node_state.get("context_map", "")
                            if context:
                                st.markdown("### 🔍 Pre-Anchor Scanner:")
                                st.code(context, language="text")
                                reasoning_log += f"**[Scanner]**\n{context}\n\n"
                        elif node_name == "planner":
                            st.markdown("### 🧠 Planner Agent:")
                            st.info(f"**Execution Plan:**\n{node_state['plan']}")
                            reasoning_log += f"**[Planner]**\n{node_state['plan']}\n\n"
                            
                        elif node_name == "executor":
                            # We only want to log tool calls printed by the executor
                            for msg in node_state.get("messages", []):
                                if hasattr(msg, "tool_calls") and msg.tool_calls:
                                    for tc in msg.tool_calls:
                                        step_count += 1
                                        step_msg = f"**Step {step_count}: Executor called `{tc['name']}`**\n"
                                        step_msg += f"- *Args:* `{tc['args']}`\n\n"
                                        st.markdown(step_msg)
                                        reasoning_log += step_msg
                                        
                        elif node_name == "tools":
                            # Log tool results
                            for msg in node_state.get("messages", []):
                                if hasattr(msg, "type") and msg.type == "tool":
                                    content_preview = msg.content[:500] + "..." if len(msg.content) > 500 else msg.content
                                    res_msg = f"- *Result:* `{content_preview}`\n\n"
                                    st.caption(res_msg)
                                    reasoning_log += res_msg
                                    
                        elif node_name == "synthesizer":
                            st.markdown("### ✍️ Synthesizer Agent:")
                            st.success("Drafting final academic response...")
                            final_answer = node_state["final_answer"]
                            
            else:
                # Legacy single-agent logic
                for step in agent.stream({"messages": [("user", prompt)]}):
                    for node_name, node_state in step.items():
                        messages = node_state.get("messages", [])
                        for msg in messages:
                            if hasattr(msg, "tool_calls") and msg.tool_calls:
                                for tc in msg.tool_calls:
                                    step_count += 1
                                    step_msg = f"**Step {step_count}: Call `{tc['name']}`**\n- *Args:* `{tc['args']}`\n\n"
                                    st.markdown(step_msg)
                                    reasoning_log += step_msg
                            elif hasattr(msg, "type") and msg.type == "tool":
                                content_preview = msg.content[:500] + "..." if len(msg.content) > 500 else msg.content
                                res_msg = f"- *Result:* `{content_preview}`\n\n"
                                st.caption(res_msg)
                                reasoning_log += res_msg
                            elif hasattr(msg, "content") and msg.content and not getattr(msg, "tool_calls", None):
                                if msg.content.strip():
                                    final_answer = msg.content
                                
            status.update(label="Reasoning Complete", state="complete", expanded=False)
            
        # Display the final synthesized answer outside the expander
        st.markdown(final_answer)
        
        # Save to session state
        st.session_state.messages.append({
            "role": "assistant",
            "content": final_answer,
            "reasoning": reasoning_log
        })
