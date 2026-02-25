import ollama
import json
import re
from clean_propositions import PropositionRegistry


class ParseContract:
    def __init__(self, model_name="llama3.1"):
        self.model = model_name
        self.registery = PropositionRegistry()


    def _llm_call(self, prompt, json_mode=True):
        format_type = 'json' if json_mode else ''
        response = ollama.generate(
            model=self.model,
            prompt=prompt,
            format=format_type,
            options={"temperature": 0}
        )
        return response['response']

    @staticmethod
    def _clean_text(text):
        cleaned = text.strip().rstrip(".")
        cleaned = re.sub(r"\s+", " ", cleaned)
        return cleaned

    @staticmethod
    def _extract_subject(text):
        stopwords = {"If", "Then", "Since", "Because", "When", "Where", "While", "Unless"}
        for token in re.findall(r"\b([A-Z][a-z]+)\b", text):
            if token not in stopwords:
                return token
        return "The party"

    @staticmethod
    def _replace_pronouns(text, subject):
        return re.sub(r"\b(she|her|he|him|they|them)\b", subject, text, flags=re.IGNORECASE)

    @staticmethod
    def _subject_anchor(sentence, detected_subject):
        lowered = sentence.lower()
        if re.search(r"\b(an|a|the)\s+[a-z]+\b", lowered) or detected_subject.lower().endswith("s"):
            return "Agent"
        return detected_subject

    @staticmethod
    def _extract_role(noun_phrase):
        words = re.findall(r"[A-Za-z]+", noun_phrase.lower())
        if not words:
            return "party"
        while words and words[0] in {"a", "an", "the"}:
            words.pop(0)
        if not words:
            return "party"
        role = words[-1]
        if role.endswith("s") and len(role) > 3:
            role = role[:-1]
        return role

    @staticmethod
    def _without_premise_to_predicate(text):
        premise = text.strip()
        premise = re.sub(r"^having\s+", "", premise, flags=re.IGNORECASE)
        appreciation_match = re.search(r"appreciation\s+for\s+(.+)$", premise, flags=re.IGNORECASE)
        if appreciation_match:
            return f"appreciates {appreciation_match.group(1).strip()}"
        return premise

    @staticmethod
    def _action_key(text):
        lowered = text.lower()
        verb_match = re.search(r"\bcan\s+(\w+)\b", lowered)
        if not verb_match:
            return None
        verb = verb_match.group(1)
        object_hint = ""
        if "modern building" in lowered or "modern buildings" in lowered:
            object_hint = "modern-building"
        return (verb, object_hint)

    def _heuristic_extract_atoms(self, segment, subject):
        normalized = self._clean_text(self._replace_pronouns(segment, subject))
        copula_match = re.search(
            rf"^{re.escape(subject)}\s+(is|are|was|were|be|been)\s+(.+)$",
            normalized,
            flags=re.IGNORECASE
        )
        if not copula_match:
            return [normalized]

        predicate = self._clean_text(copula_match.group(2))
        if " and " not in predicate:
            return [f"{subject} is {predicate}"]

        pieces = [self._clean_text(p) for p in predicate.split(" and ") if self._clean_text(p)]
        pieces = [re.sub(r"^(a|an|the)\s+", "", piece, flags=re.IGNORECASE) for piece in pieces]
        if not pieces:
            return [f"{subject} is {predicate}"]

        if len(pieces) == 2 and len(pieces[0].split()) == 1 and len(pieces[1].split()) >= 2:
            tail_words = pieces[1].split()
            if len(tail_words) >= 2:
                pieces = [pieces[0], tail_words[0], " ".join(tail_words[1:])]

        return [f"{subject} is {piece}" for piece in pieces]

    @staticmethod
    def _ensure_subject(atom, subject):
        cleaned = atom.strip()
        cleaned = re.sub(r"^(if|then|since|because)\s+", "", cleaned, flags=re.IGNORECASE)
        if not cleaned:
            return cleaned
        if re.match(rf"^{re.escape(subject)}\b", cleaned, flags=re.IGNORECASE):
            return cleaned
        if re.match(r"^(is|are|was|were|has|have|had|would|should|could|will|can)\b", cleaned, flags=re.IGNORECASE):
            return f"{subject} {cleaned}"
        if cleaned and cleaned[0].islower():
            return f"{subject} {cleaned}"
        return cleaned

    def _expand_conjunctive_atoms(self, atoms, subject):
        expanded = []
        for atom in atoms:
            copula_match = re.search(
                rf"^{re.escape(subject)}\s+(is|are|was|were|be|been)\s+(.+)$",
                atom,
                flags=re.IGNORECASE
            )
            if not copula_match:
                expanded.append(atom)
                continue

            predicate = self._clean_text(copula_match.group(2))
            if " and " not in predicate:
                expanded.append(atom)
                continue

            pieces = [self._clean_text(p) for p in predicate.split(" and ") if self._clean_text(p)]
            pieces = [re.sub(r"^(a|an|the)\s+", "", piece, flags=re.IGNORECASE) for piece in pieces]
            if not pieces:
                expanded.append(atom)
                continue

            if len(pieces) == 2 and len(pieces[0].split()) == 1 and len(pieces[1].split()) >= 2:
                tail_words = pieces[1].split()
                if len(tail_words) >= 2:
                    pieces = [pieces[0], tail_words[0], " ".join(tail_words[1:])]

            expanded.extend([f"{subject} is {piece}" for piece in pieces])

        return expanded

    def _extract_atoms_from_segment(self, text, subject):
        segment = self._clean_text(self._replace_pronouns(text, subject))
        if not segment:
            return []

        prompt = f"""
            Extract atomic propositions from this short clause segment.
            Constraints:
            - Return ONLY a JSON list of strings.
            - Decompose conjunctions into separate atoms where possible.
            - Keep each atom minimal and declarative.
            - Use subject '{subject}' when a pronoun is implied.
            - Prefer positive canonical atoms (negation is handled separately).
            Segment: "{segment}"
        """

        try:
            raw = json.loads(self._llm_call(prompt))
            if isinstance(raw, list):
                atoms = [self._ensure_subject(self._clean_text(item), subject) for item in raw if isinstance(item, str) and item.strip()]
                if atoms:
                    return self._expand_conjunctive_atoms(atoms, subject)
        except Exception:
            pass

        return self._heuristic_extract_atoms(segment, subject)

    @staticmethod
    def _contains_negation(text):
        lowered = f" {text.lower()} "
        return " not " in lowered or "n't" in lowered

    @staticmethod
    def _strip_negation_words(text):
        stripped = re.sub(r"\b(not|never)\b", "", text, flags=re.IGNORECASE)
        stripped = re.sub(r"\b(has|have|had|is|are|was|were|would|should|could|did)\s+n't\b", "", stripped, flags=re.IGNORECASE)
        stripped = re.sub(r"\b(no|without)\b", "", stripped, flags=re.IGNORECASE)
        stripped = re.sub(r"\s+", " ", stripped)
        return stripped.strip()

    @staticmethod
    def _expr_from_vars(var_names):
        if len(var_names) == 1:
            return var_names[0]
        return "(" + " ∧ ".join(var_names) + ")"

    def _register_atoms(self, atom_texts):
        ordered_mapping = {}
        for atom in atom_texts:
            var_name = self.registery.get_variable(atom)
            if var_name not in ordered_mapping:
                ordered_mapping[var_name] = atom
        return ordered_mapping

    def _rule_based_parse(self, clause_text):
        text = self._clean_text(clause_text)
        subject = self._extract_subject(text)

        sentences = [self._clean_text(part) for part in re.split(r"[.!?]+", text) if part.strip()]
        formulas = []
        mapping = {}
        action_cache = {}

        def register_atom(atom):
            var_name = self.registery.get_variable(atom)
            if var_name not in mapping:
                mapping[var_name] = self.registery.registry[var_name]
            return var_name

        def register_atoms(atom_list):
            vars_for_atoms = []
            for atom in atom_list:
                vars_for_atoms.append(register_atom(atom))
            return vars_for_atoms

        for sentence in sentences:
            normalized_sentence = self._replace_pronouns(sentence, subject)
            lowered = normalized_sentence.lower()

            that_able_match = re.match(
                r"^(.+?)\s+that\s+(.+?)\s+(is|are)\s+able\s+to\s+(.+)$",
                normalized_sentence,
                flags=re.IGNORECASE
            )
            if that_able_match:
                subject_np = that_able_match.group(1).strip()
                condition_text = that_able_match.group(2).strip()
                action_text = that_able_match.group(4).strip()

                anchor = self._subject_anchor(normalized_sentence, subject)
                role = self._extract_role(subject_np)

                role_var = register_atom(f"{anchor} is {role}")
                condition_atoms = self._extract_atoms_from_segment(f"{anchor} {condition_text}", anchor)
                condition_vars = register_atoms(condition_atoms)

                action_atom = self._extract_atoms_from_segment(f"{anchor} can {action_text}", anchor)
                action_vars = register_atoms(action_atom)
                if action_vars:
                    key = self._action_key(action_atom[0])
                    if key:
                        action_cache[key] = action_vars[0]

                antecedent = [role_var] + condition_vars
                lhs_expr = self._expr_from_vars(antecedent)
                rhs_expr = self._expr_from_vars(action_vars)
                formulas.append(f"{lhs_expr} -> {rhs_expr}")
                continue

            without_match = re.match(r"^without\s+(.+?),\s*(.+)$", normalized_sentence, flags=re.IGNORECASE)
            if without_match:
                premise_text = without_match.group(1).strip()
                consequence_text = without_match.group(2).strip()

                anchor = self._subject_anchor(normalized_sentence, subject)
                actor_match = re.match(r"^(an|a|the)\s+([a-zA-Z]+)", consequence_text)
                role_source = actor_match.group(0) if actor_match else consequence_text
                role = self._extract_role(role_source)
                role_var = register_atom(f"{anchor} is {role}")

                premise_predicate = self._without_premise_to_predicate(premise_text)
                premise_atoms = self._extract_atoms_from_segment(f"{anchor} {premise_predicate}", anchor)
                premise_vars = register_atoms(premise_atoms)

                consequence_core = self._strip_negation_words(consequence_text)
                consequence_core = re.sub(r"^(an|a|the)\s+\w+\s+", "", consequence_core, flags=re.IGNORECASE)
                consequence_atoms = self._extract_atoms_from_segment(f"{anchor} {consequence_core}", anchor)
                consequence_vars = register_atoms(consequence_atoms)

                if consequence_atoms:
                    action_key = self._action_key(consequence_atoms[0])
                    if action_key and action_key in action_cache:
                        consequence_vars = [action_cache[action_key]]

                if premise_vars and consequence_vars:
                    lhs_terms = [role_var] + [f"¬{v}" for v in premise_vars]
                    lhs_expr = "(" + " ∧ ".join(lhs_terms) + ")" if len(lhs_terms) > 1 else lhs_terms[0]
                    rhs_expr = self._expr_from_vars(consequence_vars)
                    formulas.append(f"{lhs_expr} -> ¬{rhs_expr}")
                continue

            if lowered.startswith("if ") and "," in normalized_sentence:
                condition_part, consequence_part = normalized_sentence.split(",", 1)
                condition_part = condition_part[3:].strip()
                consequence_part = consequence_part.strip()

                condition_atoms = self._extract_atoms_from_segment(condition_part, subject)
                consequence_atoms = self._extract_atoms_from_segment(consequence_part, subject)
                condition_vars = register_atoms(condition_atoms)
                consequence_vars = register_atoms(consequence_atoms)
                formulas.append((condition_vars, False, consequence_vars, False))
                continue

            if " since " in lowered or " because " in lowered:
                left_part, right_part = re.split(r"\bsince\b|\bbecause\b", normalized_sentence, maxsplit=1, flags=re.IGNORECASE)

                left_negated = self._contains_negation(left_part)
                right_negated = self._contains_negation(right_part)

                left_core = self._strip_negation_words(left_part)
                right_core = self._strip_negation_words(right_part)

                left_atoms = self._extract_atoms_from_segment(left_core, subject)
                right_atoms = self._extract_atoms_from_segment(right_core, subject)
                left_vars = register_atoms(left_atoms)
                right_vars = register_atoms(right_atoms)
                formulas.append((right_vars, right_negated, left_vars, left_negated))
                continue

        if not formulas or not mapping:
            return None

        rendered_formulas = []
        for item in formulas:
            if isinstance(item, str):
                rendered_formulas.append(item)
                continue

            lhs_vars, lhs_neg, rhs_vars, rhs_neg = item
            lhs_vars = [var for var in lhs_vars if var in mapping]
            rhs_vars = [var for var in rhs_vars if var in mapping]

            if not lhs_vars or not rhs_vars:
                continue

            lhs_expr = self._expr_from_vars(lhs_vars)
            rhs_expr = self._expr_from_vars(rhs_vars)

            if lhs_neg:
                lhs_expr = f"¬{lhs_expr}" if len(lhs_vars) == 1 else f"¬{lhs_expr}"
            if rhs_neg:
                rhs_expr = f"¬{rhs_expr}" if len(rhs_vars) == 1 else f"¬{rhs_expr}"

            rendered_formulas.append(f"{lhs_expr} -> {rhs_expr}")

        if not rendered_formulas:
            return None

        return {
            "formula": "\n".join(rendered_formulas),
            "variable_map": mapping
        }

    def _llm_fallback_parse(self, clause_text):
        extract_prompt = f"""
                Extract atomic propositions from this text.
                Rules:
                - Split conjunctions into separate atoms where semantically valid.
                - Keep atoms as positive canonical statements when possible.
                - Resolve obvious pronouns to named entities in context.
                Return ONLY a JSON list of strings.
                Text: "{clause_text}"
                """
        raw_atoms = json.loads(self._llm_call(extract_prompt))

        if not isinstance(raw_atoms, list):
            raw_atoms = []
        raw_atoms = [self._clean_text(atom) for atom in raw_atoms if isinstance(atom, str) and atom.strip()]

        mapping = self._register_atoms(raw_atoms)
        mapping_str = ", ".join([f"{var}: {text}" for var, text in mapping.items()])

        formula_prompt = f"""
            Translate the following clause into propositional logic.
            Use ONLY these variable labels: {mapping_str}
            Use operators: ¬, ∧, ∨, ->, <->.
            For 'since' and 'because', use cause -> claim.
            Return ONLY the formula string.
            Text: "{clause_text}"
            """
        formula = self._llm_call(formula_prompt, json_mode=False).strip()

        return {
            "formula": formula,
            "variable_map": mapping
        }

    def process_clause(self, clause_text):
        parsed = self._rule_based_parse(clause_text)
        if parsed is not None:
            return parsed
        return self._llm_fallback_parse(clause_text)
    

if __name__ == "__main__":
    parser = ParseContract()

    # Testing similarity normalization
    clauses = [
        "If Amy were a tall and fair actress from the mainstream film industry, she would have won the best actress award. She is not a tall and fair actress since she has not won the best actress award."
    ]

    # clauses = [
    #     "Architects that appreciate historic architecture are able to design very innovative modern buildings. Without having an appreciation for historic architecture, an architect can never design a famous modern building."
    # ]

    for i, text in enumerate(clauses):
        print(f"\n--- Analyzing Clause {i+1} ---")
        result = parser.process_clause(text)
        print(f"Formula: {result['formula']}")
        print(f"Current Registry: {json.dumps(result['variable_map'], indent=2)}")