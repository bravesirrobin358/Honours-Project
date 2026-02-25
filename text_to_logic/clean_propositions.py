from sentence_transformers import SentenceTransformer, util

class PropositionRegistry:
    def __init__(self, threshold=0.85):
        # This model is small, fast, and runs entirely on your CPU/RAM
        self.model = SentenceTransformer('all-MiniLM-L6-v2')
        self.registry = {}  # Format: { "P1": "The tenant pays rent" }
        self.threshold = threshold

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
        max_score, idx = cosine_scores.max(), cosine_scores.argmax()

        if max_score > self.threshold:
            return var_names[idx]  # Return existing variable
        else:
            var_name = f"P{len(self.registry) + 1}"
            self.registry[var_name] = text
            return var_name