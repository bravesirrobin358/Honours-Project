import ollama
import json
from sentence_transformers import SentenceTransformer
from clean_propositions import PropositionRegistry


class ParseContract:
    def __init__(self, model_name="llama3.1"):
        self.model = model_name
        self.registery = PropositionRegistry()


    def _llm_call(self, prompt, json_mode=True):
        format_type = 'json' if json_mode else ''
        response = ollama.generate(model=self.model, prompt=prompt, format=format_type)
        return response['response']

    def process_clause(self, clause_text):
        extract_prompt = f"""
                Extract the atomic propositions (simple true/false statements) from this text.
                Return ONLY a JSON list of strings. 
                Text: "{clause_text}"
                """
        raw_atoms = json.loads(self._llm_call(extract_prompt))

        mapping = {}

        for atom in raw_atoms:
            var_name = self.registery.get_variable(atom)
            mapping[var_name] = atom

        mapping_str = ", ".join([f"{var}: {text}" for var, text in mapping.items()])

        formula_prompt = f"""
            Translate the following clause into a propositional logic formula.
            Use ONLY these specific variable labels:
            Labels: {mapping_str}
            
            Logical Operators to use: NOT, AND, OR, -> (for IF..THEN), <-> (for IFF).
            Text: "{clause_text}"
            Return ONLY the formula string.
            """
        formula = self._llm_call(formula_prompt, json_mode=False).strip()

        return {
            "formula": formula,
            "variable_map": mapping
        }
    
# --- EXECUTION ---
if __name__ == "__main__":
    parser = ParseContract()

    # Testing similarity normalization
    clauses = [
        "If Amy were a tall and fair actress from the mainstream film industry, she would have won the best actress award.",
        "She is not a tall and fair actress since she has not won the best actress award."
    ]

    for i, text in enumerate(clauses):
        print(f"\n--- Analyzing Clause {i+1} ---")
        result = parser.process_clause(text)
        print(f"Formula: {result['formula']}")
        print(f"Current Registry: {json.dumps(result['variable_map'], indent=2)}")