# 3. Methodology

In this section, we present the proposed Agentic Heterogeneous Graph Retrieval-Augmented Generation (Agentic H-GraphRAG) framework. Recognizing the limitations of traditional vector-based RAG—which struggles with multi-hop logical inference—and conventional GraphRAG—which suffers from rigid text matching and context overloading—our framework bridges the semantic gap between unstructured academic text and structured objective entities. The architecture consists of two primary phases: Heterogeneous Graph Construction (Phase I) and Autonomous Cognitive Query Routing (Phase II).

## 3.1 Heterogeneous Graph Construction

To represent complex academic knowledge, we decouple research papers into a multi-layered heterogeneous graph $\mathcal{G} = (\mathcal{V}, \mathcal{E})$. We define two distinct categories of nodes in $\mathcal{V}$: Subjective Nodes (Hubs) and Objective Nodes (Spokes).

**Subjective Nodes (Papers):**
The core of the graph centers around the `Paper` node. We define a progressive disclosure schema consisting of three qualitative levels (L1, L2, L3) to prevent context window saturation during retrieval.
*   **L1 (Abstract Level):** basic metadata and high-level claims.
*   **L2 (Intuition Level):** the specific *pain point* the paper addresses and the structural *intuition* behind the proposed solution.
*   **L3 (Detail Level):** full methodological steps and numerical evaluation tables.
To capture semantic nuance, we generate multiple dense vector embeddings for a single `Paper` node. Specifically, we encode the pain point, methodology intuition, and principal claims into distinct vector spaces ($\mathbf{e}_{pain}$, $\mathbf{e}_{intuition}$, $\mathbf{e}_{claim}$). This multi-slot embedding strategy allows downstream agents to anchor onto papers based specifically on the underlying intent of a user's query.

**Objective Nodes (Entities):**
The spokes of the graph consist of rigidly named entities extracted via an LLM-based deep reader, including `Task`, `Dataset`, `Baseline`, and `Method_Concept`. To overcome the brittleness of exact string matching during query time, we independently compute and store vector embeddings for the names of these objective entities.

**Directed Relational Edges:**
We establish explicit schema-bound directed edges $\mathcal{E}$ bridging papers to objective entities (e.g., `EVALUATES_ON` $\rightarrow$ Dataset, `COMPARES_AGAINST` $\rightarrow$ Baseline, `TACKLES` $\rightarrow$ Task).

## 3.2 Autonomous Cognitive Query Routing

Rather than relying on static prompt templates or monolithic context retrieval, our query phase leverages a Tool-Calling Agent equipped with four atomic tools. The agent implements a step-by-step cognitive reasoning loop:

### 3.2.1 Semantic Anchoring (Dual-Pathway Entry)
Given a natural language query, the agent first decomposes the query to determine the necessity of accessing a subjective concept versus an objective entity.
*   **Abstract Concept Pathway:** If the query pertains to abstract notions (e.g., "What are the latest benchmarks?"), the agent anchors onto the `Paper` nodes by routing the query to the most semantically aligned vector index (e.g., targeting $\mathbf{e}_{claim}$).
*   **Explicit Entity Pathway:** If the query contains named entities (e.g., "Which papers use the CS dataset?"), the agent utilizes the global entity vector index, applying a cosine similarity thresholding mechanism to map the noisy user input to the exact objective node in $\mathcal{G}$.

### 3.2.2 Topological Navigation
Once an anchor node is established, the agent avoids indiscriminate vector retrieval. Instead, it utilizes topological navigation to traverse the explicit relationships $\mathcal{E}$. Because the graph edges are rigorously typed, the agent can perform bidirectional multi-hop walks (e.g., querying from a Dataset backward through `EVALUATES_ON` edges to identify referencing Papers). This ensures deterministic and hallucination-free graph traversals for objective inquiries.

### 3.2.3 Guardrailed Context Reading 
To synthesize the final answer, the agent invokes a progressive-reading tool on the target `Paper` nodes. By default, the agent restricts its context ingestion to L1 and L2 properties, deliberately avoiding the dense, multi-thousand-token L3 properties (such as exhaustive evaluation tables) unless the user query explicitly demands stringent numerical reporting. This deliberate cognitive routing prevents attention dilution and concept drift, empirical failure modes commonly observed when LLMs process excessive unstructured technical tables.
