import json
import os
import re
from langchain_core.prompts import ChatPromptTemplate
from langchain_openai import ChatOpenAI
from src.core.agent.schema import DeepReadingOutput

class DeepReaderAgent:
    def __init__(self, api_key: str, model_name: str = "gpt-5-mini-2025-08-07"):
        llm = ChatOpenAI(model=model_name, api_key=api_key, temperature=0.1)
        self.structured_llm = llm.with_structured_output(DeepReadingOutput)
        
        self.prompt = ChatPromptTemplate.from_messages([
            ("system", """You are a world-class AI researcher and academic analyst. Extract structured information from an academic paper.

# Extraction Schema (STRICT — Follow Exactly)

1. **paper.title**: Full title only. Nothing else.

2. **summary**: 
   - `year`: Publication year (string). Use 'Unknown' if not found.
   - `short_claim`: One punchy sentence capturing the core contribution.

3. **keywords**: The paper's own listed keywords (exactly as written). 5-10 items.

4. **research_problem**:
   - `summary`: Short 1-2 sentence summary of the problem addressed.
   - `previous_limitation.limitation`: How does this paper's Introduction synthesize the limitations of prior work? Capture the specific bottleneck prior methods fail at — the motivation for this research.
   - `underlying_problem.detail`: Detailed explanation of the core research question being solved. 2-4 sentences.


7. **method**:
   - `high_level_description`: 1-3 sentence elevator pitch of the proposed approach.
   - `detail.method_detail`: Detailed step-by-step explanation of the full architecture. Include all sub-modules and design choices.
   - `detail.method_section_pointer`: Section path, e.g. "Section 3: Method".
   - `referred_algorithms.algorithms`: List of classic algorithms/architectures this method is directly inspired by or builds upon. E.g. ["MoE", "LoRA"]. Only include techniques central to the design.
   - `referred_algorithms.description`: Brief explanation of how these algorithms are referenced or adapted.

8. **experiment**:
   - `result`: Comprehensive summary of what experiments were run, metrics, and key quantitative findings.
   - `experiment_section_pointer`: Section path, e.g. "Section 5: Experiments".
   - `analysis.design_overview`: The overall experimental design and metrics.
   - `analysis.experiments`: An array of conducted experiments. For each, describe `name`, `purpose`, `conclusion`, and `reference_element` (e.g., "Table 3", "Figure 5", or "None"). Don't populate `comprehensive_analysis` field manually.
   - `compared_methods`: List of all baseline/competing methods compared against.
   - `datasets`: List of all datasets used for evaluation.


# Rules
- Output MUST be valid JSON matching the schema exactly.
- Keywords must be taken verbatim from the paper's Keywords section.
- All text fields must be information-dense and suitable for vector search.
- For `referred_algorithms`, focus on algorithms the METHOD itself is built upon — not general background citations.
"""),
            ("user", "Extract structured information from this paper:\n\n{paper_content}")
        ])

        
        self.chain = self.prompt | self.structured_llm

    def _mount_table_data(self, markdown_path: str, analysis) -> None:
        try:
            with open(markdown_path, "r", encoding="utf-8") as f:
                content = f.read()

            mount_dict = {}
            paragraphs = re.split(r'\n{2,}', content)
            
            image_count = 0
            base_dir = os.path.dirname(os.path.abspath(markdown_path))
            
            for i, p in enumerate(paragraphs):
                p_clean = p.strip()
                
                is_table = p_clean.startswith('|') and '-|-' in p_clean
                is_image = "<!-- image -->" in p_clean
                
                if is_table or is_image:
                    ctx = []
                    for j in range(max(0, i-2), min(len(paragraphs), i+3)):
                        if j != i: ctx.append(paragraphs[j])
                    context_str = " ".join(ctx)
                    
                    matches = re.findall(r'(?:Table|Figure)\s+[A-Za-z0-9.-]+', context_str, re.IGNORECASE)
                    
                    if is_table:
                        for m in matches:
                            normalized_ref = m.title().strip('.')
                            mount_dict[normalized_ref] = p_clean
                    elif is_image:
                        img_path = os.path.join(base_dir, f"figure_{image_count}.png")
                        print(f"[DeepReaderAgent] Found image tag at para {i}, mapping to figure_{image_count}.png. Context: {context_str[:100]}...")
                        for m in matches:
                            normalized_ref = m.title().strip('.')
                            if os.path.exists(img_path):
                                url = f"http://localhost:5001/api/image?path={img_path}"
                                mount_dict[normalized_ref] = f"![{normalized_ref}]({url})"
                                print(f"[DeepReaderAgent] Successfully mapped {normalized_ref} to {img_path}")
                        image_count += 1
            
            lines = [f"### Design Overview\n{analysis.design_overview}\n"]
            for idx, exp in enumerate(analysis.experiments, 1):
                lines.append(f"#### {idx}. {exp.name}")
                lines.append(f"- **Purpose**: {exp.purpose}")
                lines.append(f"- **Conclusion**: {exp.conclusion}")
                
                ref = exp.reference_element.strip()
                ref_norm = ref.title().strip('.')
                
                if ref_norm and ref_norm.lower() not in ["none", "null", "n/a", ""]:
                    lines.append(f"- **Evidence ({ref})**:")
                    found = False
                    # Exact and fuzzy match
                    for k, val in mount_dict.items():
                        if k == ref_norm or ref_norm in k or k in ref_norm:
                            lines.append("\n" + val + "\n")
                            found = True
                            break
                    if not found:
                        lines.append(f"\n*No table or figure extracted from local markdown for '{ref}'.*\n")
                else:
                    lines.append("")
                    
            analysis.comprehensive_analysis = "\n".join(lines)
            print(f"[DeepReaderAgent] Successfully mounted {len(mount_dict)} items (tables/figures) from local markdown.")
        except Exception as e:
            print(f"[DeepReaderAgent] Table mounting failed: {e}")

    def run(self, markdown_path: str, output_json_path: str = None) -> DeepReadingOutput:
        with open(markdown_path, "r", encoding="utf-8") as f:
            content = f.read()

        print(f"[DeepReaderAgent] Analyzing paper ({len(content)} chars)...")
        result: DeepReadingOutput = self.chain.invoke({"paper_content": content})
        
        # Call the local mounting function to combine insights and CSV/Markdown tables
        self._mount_table_data(markdown_path, result.experiment.analysis)
        
        if output_json_path:
            os.makedirs(os.path.dirname(os.path.abspath(output_json_path)), exist_ok=True)
            with open(output_json_path, "w", encoding="utf-8") as f:
                json.dump(result.model_dump(), f, indent=2, ensure_ascii=False)
            print(f"[DeepReaderAgent] Extraction saved to: {output_json_path}")
            
        return result
