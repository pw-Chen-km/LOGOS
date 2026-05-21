import sys
import io
import os

# Force UTF-8 output so Chinese/CJK queries don't crash stdout
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', line_buffering=True)
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', line_buffering=True)

from langchain_openai import ChatOpenAI, OpenAIEmbeddings
from langchain.agents import create_agent

from src.core.graph.neo4j_client import Neo4jClient
from src.core.agent.qa_tools import GraphQAToolsFactory
from src.core.agent.multi_agent import create_multi_agent_graph

def run_qa_agent(api_key: str, neo4j_uri: str, neo4j_user: str, neo4j_pass: str, user_query: str):
    llm = ChatOpenAI(model="gpt-4o-mini", api_key=api_key, temperature=0.1)
    embeddings = OpenAIEmbeddings(api_key=api_key, model="text-embedding-3-small")
    db_client = Neo4jClient(neo4j_uri, neo4j_user, neo4j_pass)
    
    try:
        factory = GraphQAToolsFactory(db_client, embeddings)
        tools = factory.get_tools()
        
        # Initial schema fetch
        schema_tool = [t for t in tools if t.name == "get_graph_schema_tool"][0]
        schema = schema_tool.invoke({})
        
        agent = create_multi_agent_graph(llm=llm, tools=tools)
        
        print(f"\n[User Query]: {user_query}")
        print("=" * 60)
        
        initial_state = {
            "query": user_query,
            "schema": schema,
            "plan": "",
            "messages": [],
            "final_answer": "",
            "retry_count": 0,
            "feedback": "",
            "decomposed_concepts": [],
            "context_map": "",
            "trace_file": ""
        }
        
        final_answer = ""
        step_count = 0
        
        for step in agent.stream(initial_state):
            for node_name, node_state in step.items():
                if node_name == "pre_anchor_scanner":
                    print(f"\n--- [Pre-Anchor Scanner] Context Map ---")
                    print(node_state.get("context_map", ""))
                elif node_name == "planner":
                    print(f"\n--- [Planner] Plan ---")
                    print(node_state["plan"])
                elif node_name == "executor":
                    for msg in node_state.get("messages", []):
                        if hasattr(msg, "tool_calls") and msg.tool_calls:
                            for tc in msg.tool_calls:
                                step_count += 1
                                print(f"\nStep {step_count}: Executor called {tc['name']}")
                                print(f"  Args: {tc['args']}")
                        elif msg.content:
                            print(f"\n[Executor Message]: {msg.content}")
                elif node_name == "tools":
                    for msg in node_state.get("messages", []):
                        if hasattr(msg, "type") and msg.type == "tool":
                            print(f"  Tool Result: {msg.content[:200]}...")
                elif node_name == "synthesizer":
                    final_answer = node_state["final_answer"]
        
        print("\n" + "=" * 60)
        print("[Final Answer]:")
        print(final_answer)
        
    finally:
        db_client.close()

if __name__ == "__main__":
    API_KEY = os.getenv("OPENAI_API_KEY") # Get from environment variable
    URI = "neo4j://127.0.0.1:7687"
    USR = "neo4j"
    PWD = "420420420"
    
    # Using the user's specific query for verification
    TEST_QUERY = "Wireless Federated Multi-Task LLM Fine-Tuning 這篇論文要解決的研究問題是什麼？他的方法 intuition 是什麼？"
    
    run_qa_agent(API_KEY, URI, USR, PWD, TEST_QUERY)
