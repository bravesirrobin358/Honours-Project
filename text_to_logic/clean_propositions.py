from sentence_transformers import SentenceTransformer, util
import re

class PropositionRegistry:
    def __init__(self, threshold=0.85):
        self.model = SentenceTransformer('all-MiniLM-L6-v2')
        self.registry = {}  # Format: { "P1": "The tenant pays rent" }
        self.threshold = threshold

    @staticmethod
    def _is_negated(text):
        lowered = f" {text.lower()} "
        return " not " in lowered or "n't" in lowered or lowered.strip().startswith("¬")

    @staticmethod
    def _canonical_text(text):
        cleaned = text.strip().lower()
        cleaned = re.sub(r"\b(not|never)\b", "", cleaned)
        cleaned = re.sub(r"n't", "", cleaned)
        cleaned = re.sub(r"\s+", " ", cleaned)
        return cleaned.strip()

    def get_variable(self, text):
        if not self.registry:
            var_name = f"P{len(self.registry) + 1}"
            self.registry[var_name] = text
            return var_name

        # Compare new text against everything in the registry
        sentences = list(self.registry.values())
        var_names = list(self.registry.keys())
        
        new_emb = self.model.encode(text, convert_to_tensor=True)
        old_embs = self.model.encode(sentences, convert_to_tensor=True)
        
        # Find the highest similarity score
        cosine_scores = util.cos_sim(new_emb, old_embs)[0]
        adjusted_scores = cosine_scores.clone()

        new_neg = self._is_negated(text)
        new_canonical = self._canonical_text(text)

        for i, existing_text in enumerate(sentences):
            existing_neg = self._is_negated(existing_text)
            existing_canonical = self._canonical_text(existing_text)
            if new_neg != existing_neg and new_canonical == existing_canonical:
                adjusted_scores[i] = -1.0

        max_score, idx = adjusted_scores.max(), adjusted_scores.argmax()

        if max_score > self.threshold:
            return var_names[idx]  # Return existing variable
        else:
            var_name = f"P{len(self.registry) + 1}"
            self.registry[var_name] = text
            return var_name