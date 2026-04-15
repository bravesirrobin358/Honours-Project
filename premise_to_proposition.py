import ollama
import json
import re
from utils.clean_propositions import PropositionRegistry

class LLMProcessingPremise:
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
            - Decompose disjunctions into separate atoms where possible.
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
        formula = var_names[0]
        for i in var_names[1:]:
            formula = "(" + formula + " ∧ " + i + ")"
        return formula

    def _register_atoms(self, atom_texts):
        # We need to map variables, but also keep track of ALL synonymous text for the LLM
        ordered_mapping = {}
        for atom in atom_texts:
            var_name = self.registery.get_variable(atom)
            if var_name not in ordered_mapping:
                ordered_mapping[var_name] = [atom]
            elif atom not in ordered_mapping[var_name]:
                ordered_mapping[var_name].append(atom)
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
                    formula = lhs_expr[0]
                    if len(lhs_terms) > 1:
                        for i in lhs_terms[1:]:
                            formula = "(" + formula + " ∧ " + i + ")"
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

    def _post_processing(self,formula):
        # This function adds the relevant parentheses to sequential binary operators lacking them.
        premises, conclusion = formula.split("/")
        premise_list = premises.strip().split("\n")
        
        premise_done = []
        def fix(premise):
            premise = premise.strip()
            full_prem = ""
            symbols = premise.split(" ")
            op_list = ['∧','->','∨','<->']
            props = []
            operators = []

            # Add each space-separated symbol to either the operator list or the propositions list
            for s in symbols:
                if s in op_list:
                    operators.append(s)
                else:
                    props.append(s)

            # Here we traverse backwards through our list of propositions. If a proposition has more closing parentheses than opening parentheses 
            # and the proposition earlier in the list by a certain gap has more opening than closing, then we extract this portion of the premise
            # recursively call the fix function with the goal of combining all propositions in this subpremise into 1, with correct parentheses to boot.
            # Once we are done checking proposition pairs of a certain distance apart, we increase the distance check and try again, repeating this
            # process until the gap encompases the entire premise.
            gap = 1
            while True:
                if len(operators) > 1:
                    p = len(props)-1
                    while p-gap >= 0:
                        if props[p].endswith(')') and (props[p].count('(') < props[p].count(')')) and props[p-gap].startswith('(') and (props[p-gap].count('(') > props[p-gap].count(')')):
                            sub_premise_props = props[p-gap:p+1]
                            if len(sub_premise_props) != len(props):
                                sub_premise_ops = operators[p-gap:p]
                                sub_premise =  " ".join([f'{sub_premise_props[i]} {sub_premise_ops[i]}' for i in range(len(sub_premise_ops))]) + " " + sub_premise_props[-1]
                                props[p-gap] = fix(sub_premise)
                                is_at_end = (p == len(props)-1)
                                props = props[:p-gap+1] + ([] if is_at_end else props[p+1:])
                                operators = operators[:p-gap] + ([] if is_at_end else operators[p:])
                                p = p-gap+1
                        p -= 1
                        
                else:
                    break
                gap += 1
                if gap == len(props):
                    break
                    
            # Once a premise is out of the recursion loop, we join them in a 'proposition operator proposition' pattern, adding parentheses if they
            # did not previously exist.
            if operators:
                full_prem = f'{props[-2]} {operators[-1]} {props[-1]}'
                if not (full_prem.startswith('(') and full_prem.endswith(')')):
                    full_prem = '('+full_prem+')'
                props.pop()
                props.pop()
                operators.pop()
            else:
                full_prem = props[0]
            while operators:
                full_prem = f'{props[-1]} {operators[-1]} {full_prem}'
                if not (full_prem.startswith('(') and full_prem.endswith(')')):
                    full_prem = '('+full_prem+')'
                props.pop()
                operators.pop()
            return full_prem
        for premise in premise_list:
            
            premise_done.append(fix(premise))
        
        return f'{", ".join(premise_done)} / {fix(conclusion)}'







    def _post_process_formula(self, formula):
        prompt = f"""
        Fix the following propositional logic formula to strictly comply with these rules:
        1. Every single binary operation (AND, OR, IMPLIES, IFF) MUST be strictly enclosed in its own set of parentheses.
        2. There must NEVER be three or more terms joined without nested parentheses.
           Example ERROR: A ∧ B ∧ C -> Must be: (A ∧ B) ∧ C
           Example ERROR: ~A ∧ ~B ∧ ~C -> Must be: (~A ∧ ~B) ∧ ~C
        4. NEVER output consecutive top-level binary operators within parenthesis like (A ∧ B ∧ C). Break them into pairs recursively.

        Only return the fixed formula string. Do not add any other text or commentary.
        Remember to keep the split between premises and conclusion with the forward slash ' / '.

        Formula: "{formula}"
        """
        return self._llm_call(prompt, json_mode=False).strip()

    def _llm_fallback_parse(self, clause_text):
        all_atoms = []
        '''
        extract_prompt = f"""
                    Extract atomic logical propositions from the following text.
                    Rules:
                    - Decompose conjunctions (such as the use of 'and') into separate atoms where possible.
                    - Decompose disjunctions (such as the use of 'or') into separate atoms where possible.
                    - Decompose implications ('if...then','implies') into separate atoms where possible.
                    - Keep each atom minimal and declarative.
                    - Keep atoms as positive canonical statements when possible (negation is handled separately).
                    - Resolve obvious pronouns to named entities in context.
                    - Do NOT merge synonymous atoms. Extract all distinct verbalized propositions exactly as written.
                    Return ONLY a JSON object with a key "atoms" containing a list of strings.
                    Text: "{clause_text}"
                    """'''
        extract_prompt = f"""
                Extract atomic propositions from this text in the form of propositional logic.
                Rules:
                - Decompose conjunctions (such as the use of 'and') into separate atoms where possible.
                - Decompose disjunctions into separate atoms where possible.
                - Keep each atom minimal and declarative.
                - Keep atoms as positive canonical statements when possible (negation is handled separately).
                - Resolve obvious pronouns to named entities in context.
                - Do NOT merge synonymous atoms. Extract all distinct verbalized propositions exactly as written.
                Return ONLY a JSON object with a key "atoms" containing a list of strings.
                Text: "{clause_text}"
                """

        raw_response = self._llm_call(extract_prompt)
        try:
            parsed_json = json.loads(raw_response)
            raw_atoms = parsed_json.get("atoms", [])
        except json.JSONDecodeError:
            print(f"Failed to parse LLM response as JSON: {raw_response}")
            raw_atoms = []
        all_atoms.extend(raw_atoms)
            

        if not isinstance(all_atoms, list):
            all_atoms = []
        raw_atoms2 = [self._clean_text(atom) for atom in all_atoms if isinstance(atom, str) and atom.strip()]

        mapping = self._register_atoms(raw_atoms2)
        mapping_str = ",\n".join([f"{var}: {' OR '.join(texts)}" for var, texts in mapping.items()])

        final_mapping = {var: texts[0] for var, texts in mapping.items()}

        # take the atoms and send it to SentenceTransformer('all-MiniLM-L6-v2') to cluster them based on semantic similarity. If they are above a certain threshold, we will treat them as the same variable in the formula.
        clustered = self.registery.cluster_atoms(raw_atoms2, threshold=0.85)

        ## Now we need to update the mapping to reflect the clustering. If multiple atoms are clustered together, they should all map to the same variable.
        cluster_to_var = {}
        for atom in clustered:
            var_name = self.registery.get_variable(atom)
            cluster_to_var[atom] = var_name
        final_mapping = {}
        for atom in raw_atoms2:
            var_name = cluster_to_var.get(atom, self.registery.get_variable(atom))
            final_mapping[var_name] = atom

        print(f'--- LLM Extracted Atoms ---\n{json.dumps(final_mapping, indent=2)}\n')
        '''        formula_prompt = f"""
            Using the provided variable labels, substitute the variables' text with the variables' labels and translate the text into a propositional logic form.
            Use ONLY these variable labels:
            "{mapping_str}"

            Use ONLY these operators: '¬', '∧', '∨', '->', '<->'. No first order logic predicates, existential like '∃' or universal quantifiers should be used. 
            For 'since' and 'because', use cause -> claim.

            The conclusion, still having a label, should be separated from the rest of the propositions with a forward slash ' / '.

            Return ONLY the formula string.
            Text: "{clause_text}"
            """'''
        formula_prompt = f"""
            Translate the following clause into propositional logic. Do not combine the propositions of multiple sentences, leave them seperate.
            Use ONLY these variable labels:
            "{mapping_str}"

            Use ONLY these operators: '¬', '∧', '∨', '->', '<->'. No first order logic predicates, existential like '∃' or universal quantifiers should be used. 
            For 'since' and 'because', use cause -> claim.

            The conclusion of the overall text should be separated from the rest of the propositions with a forward slash ' / ' on the right side of it.

            Return ONLY the formula string.
            Text: "{clause_text}"
            """
        formula = self._llm_call(formula_prompt, json_mode=False).strip()
        formula2 = self._post_processing(formula)
        # ((P1 ∧ P6) ∧ P2) ∧ (P1 → ~P3) ∧ P2 → (~P1 ∨ ~P4) / P5 ∨ (~P4 ∧ ~P3)
        # P1 = I drink beer, P2 = I play hockey, P3=I eat lamb, P4=I gamble, P5=I wrote novels P6 = I play music
        return {
            "formula": formula2,
            "variable_map": final_mapping
        }

    def process_clause(self, clause_text, use_llm=False):
        if not use_llm:
            parsed = self._rule_based_parse(clause_text)
            if parsed is not None:
                return parsed
        else:
            return self._llm_fallback_parse(clause_text)


def run(clause_text=None):
    parser = LLMProcessingPremise()

    # Testing similarity normalization
    #'I drink beer and play hockey. If I drink beer, I do not eat lamb. If I play hockey, then I either do not drink beer or I don’t gamble. In conclusion, either I draw or I both don’t gamble and I don’t eat lamb.'

    clauses = [
 'I drink beer and wewewwI play music and play hockey. If I drink beer, then I do not eat lamb. If I play hockey, then I do not drink beer and I do not gamble. In conclusion, either I draw or I do not both gamble and eat lamb.'  ]
    '''
    clauses = [
        """I. Overview
[1] Dennis John Paul Tondreau [Applicant], a member of the Canadian Armed Forces [CAF], seeks a judicial review of a December 15, 2022 decision to release him from the CAF, and a March 7, 2023 decision of the Commander of the 33 Canadian Brigade Group [Brigade Commander] of the CAF to release the Applicant under category 5(a) pursuant to article 15.01 of the Queen's Regulations and Orders [QR&O].
 Chapter 15 governs the release of CAF members from service. CAF officers who enrolled before July 2004, such as the Applicant, are subject to compulsory retirement at age 55 (art 15.17).
 Both of these decisions, discussed in more detail below are referenced in the Notice of Application.

[2] The application for judicial review is dismissed. 
The application is time-barred, an additional decision is improperly being challenged, and the application is moot.

II. Background
[3] The Applicant was a member of the CAF who belonged to the Cameron Highlanders of Ottawa (CH of O). 
The chain of command from most to least superior is as follows: the Commander of the Canadian Army [Commander Canadian Army], Commander 4th Canadian Division [Division Commander], the Brigade Commander, and CH of O Commanding Officer.

[4] The Commander Canadian Army, as a delegate for the Chief of Defence Staff, may approve the retention of an officer in the CAF beyond the compulsory retirement age pursuant to QR&O 15.17(5)(b). 
There is also a streamlined process available for members to request their compulsory retirement age to be 60, if the member requests the change before reaching age 54.

[5] The Applicant reached the compulsory retirement age on August 30, 2022. 
In December 2022, the CH of O Commanding Officer noticed that the Applicant had reached his compulsory retirement age. 
A cessation of service form was prepared around this time, which the Applicant and the CH of O Commanding Officer signed on December 15, 2022 [Release Decision]. 
It was at this time that the Applicant was released from the CAF.

III. Decision
[6] On December 19, 2022, the Applicant submitted an extension request [Extension Request]. 
The Division Commander did not send the Extension Request to the Commander Canadian Army due to the view that it lacked any prospect of being approved since it was late. 
Instead, the Brigade Commander sent a letter to the CH of O Commanding Officer on March 7, 2023 denying the Extension Request and directing the completion of the release administration by March 31, 2023 [Denial Decision]. 
The Applicant received the letter on March 20, 2023.

[7] The Applicant filed this application on May 11, 2023. 
Since commencing this matter, the Brigade Commander sent the Extension Request to the Division Commander for onward transmission to the Commander Canadian Army for a decision. 
The Canadian Army Headquarters received the Extension Request on July 13, 2023 and it is awaiting a decision from the Commander Canadian Army.

IV. Preliminary Issue
A. Is this application time-barred?
[8] The Respondent submits that this application should be dismissed as the Applicant brought it later than 30 days from the date of the decision being challenged, contrary to subsection 18.1(2) of the Federal Courts Act, RSC 1985, c F-7. 
The sum of the Applicant’s submissions challenge both the Release Decision and the Denial Decision. 
However, the Applicant brought the application forward on May 11, 2023, which was more than 30 days after both the Release Decision and the Denial Decision.

[9] The Applicant did not make written submissions on the late filing. 
At the hearing, the Applicant submitted that he disagreed that his Release Date was December 15, 2022 and he also submitted that he received notice of the Denial Decision in an April 17, 2023 letter. 
The Applicant submitted that the letter attempts to backdate his release.

[10] The Respondent disputed that the April 17, 2023 letter is an attempt to backdate the Applicant’s release and submitted that there is no indication in the Notice of Application that the April 17, 2023 letter is under review and that this letter deals with grievances.
 Accordingly, it is a separate and distinct issue from the matter at issue.

[11] The application concerning the Denial Decision is time-barred. 
The Applicant filed the application more than 30 days after the Denial Decision and failed to bring a motion seeking approval for an extension of time (Meeches v Assiniboine, 2017 FCA 123 at para 33; Canada v Berhad, 2005 FCA 267 at para 60).

B. Is the Release Decision reviewable?
(1) Applicant’s Position
[12] The Applicant submits that the authority to approve releases of commissioner officers in the CAF and set their release date lies with the Governor General under article 15.01(3) of the QR&O. 
The Release Decision was an improper release since the CH of O Commanding Officer did not have the Governor General’s approval to set the release date as December 15, 2022.

(2) Respondent’s Position
[13] The Court should not entertain this argument because the Applicant did not raise the grounds related to the Governor General’s approval in the Notice of Application as required under Rule 301(e) of the Federal Courts Rules, SOR/98-106 [Rules].
 The Federal Court of Appeal has stated that a “complete” statement of grounds means all the legal basis and material facts that, if taken as true, will support granting the relief sought while a “concise” statement of grounds must include the material facts necessary to show that the Court can and should grant the relief sought (Canada (National Revenue) v JP Morgan Asset Management (Canada) Inc, at paras 39-40). 
This Court has further held that pursuant to Rule 308, it will not consider grounds to be argued that are not invoked in a notice of application, subject to limited exceptions (Boubala v Khwaja, 2023 FC 658 at paras 27-28). 
The limited exceptions do not apply to this matter as the Applicant prejudiced the Respondent by not identifying this submission in the Notice of Application.

[14] Alternatively, the CH of O Commanding Officer had authority to recommend the Applicant’s release to the Governor General. 
In the event that the Applicant is correct that he is not released until the Governor General approves the release, then the challenge regarding the Release Decision is premature, as the military grievance system has been recognized as an adequate alternative remedy.

(3) Conclusion
[15] I agree with the Respondent that the Notice of Application does not set out a complete and concise statement of grounds to challenge the Release Decision, particularly with respect to the required approval by the Governor General. 
From a simple reading, the focus in the Notice of Application appears to be on the Denial Decision, however, the Applicant’s written and oral submissions relate to both the Release Decision and the Denial Decision. 
The Applicant submits that the only authority that could approve his release was the Governor General. 
I agree with the Respondent that this was not raised in the Notice of Application and that the Respondent is prejudiced.

[16] The Court does have discretion, where relevant matters have arisen after the filing of the notice of application; the new issues have some merit, are related to those set out in the notice of application and are supported by the evidentiary record; the respondent would not be prejudiced; and no undue delay would result (Tl’azt’en Nation v Sam, 2013 FC 226 at paras 6-7, citing Al Mansuri v Canada (Public Safety and Emergency Preparedness), 2007 FC 22 at paras 12-13). 
Apart from the submission related to the Governor General’s approval, I also note that the Release Decision itself was made months prior to the Denial Decision, as the Denial Decision itself is the result of a request to extend the date decided upon in the Release Decision. 
Accordingly, the Release Decision is not properly before the Court.

[17] Furthermore, the Applicant has not made submissions on the Release Decision and the Denial Decision being a continuing course of conduct that would be an exception to Rule 302 that an applicant can only challenge one decision (Rules; David Suzuki Foundation v Canada (Health), 2018 FC 380 at para 173).

[18] In response to the Respondent’s alternative submissions, I note that neither party has provided sufficient evidence of the alternative remedy through the grievance process to determine its adequacy. 
Neither party has provided evidence on when the grievance process is available. 
There is no evidence on whether the Governor General has signed the Release Decision. 
The Respondent included a copy of the Release Decision as an exhibit to the affidavit of Stephane Tremblay, which the Commander CH of O and the Applicant have signed but not the Governor General. 
The Respondent submits that it would be available if the Governor General has not yet signed the release as the approving authority. 
However, the Applicant has submitted evidence that a grievance filed on March 30, 2023 was not actioned as he was no longer a member of CAF. 
In light of the insufficient submissions, the Court will not address this matter.

C. Is this application moot?
[19] There is a two-stage analysis when mootness is raised: (1) whether the proceeding is indeed moot, meaning whether a live controversy remains that affects or may affect the rights of the parties; and (2) whether the Court should nonetheless exercise its discretion to hear and decide it (Borowski; Democracy Watch v Canada (Attorney General), 2018 FCA 195 at para 10 [Democracy Watch]). 
The second stage of analysis involves considering the requirement of an adversarial context; the concern for judicial economy; and the need for the court to respect its proper law-making function and its role as the adjudicative branch of our political framework (Borowski at 358-363; Yahaan v Canada, 2018 FCA 41 at para 32).

[20] The Respondent submits that the Extension Request has since been sent to the Commander Canadian Army for a decision. 
The challenge of the Denial Decision is moot for lack of a live controversy, which will or may affect the rights of the parties to the litigation (Borowski v Canada (Attorney General), 1989 CanLII 123 (SCC) at 353 [Borowski]; Doucet-Boudreau v Nova Scotia (Minister of Education), 2003 SCC 62 at para 17). 
The Respondent acknowledges that the Denial Decision was made by an individual who did not have the delegated authority to make it. 
The Extension Request has since been sent to the Commander Canadian Army for a decision, which is the proper authority. 
There is also no adversarial context and it would not be a useful expenditure of scarce judicial resources to canvas this issue further.

[21] On the first stage of the analysis, I agree with the Respondent that there is not a live issue before this Court. 
The appropriate remedy if the Denial Decision is unreasonable or procedurally unfair would be to quash and remit the matter to the appropriate authority, however, the matter is already with the Commander Canadian Army for review. 
The discussion on remedies is set out below as to why the other relief sought by the Applicant is not appropriate.

[22] As to the second stage, I find that the Court should not exercise its discretion to hear a moot application. 
First, there is no longer an adversarial context. 
An adversarial context persists where the “litigants have continued to argue their respective sides vigorously” or where “both sides, represented by counsel, take opposing positions” (Boland v Canada (Attorney General), 2024 FC 11 at para 25). 
The Respondent concedes that the Denial Decision was made without the appropriate authority, which is why the matter is now with the Commander Canadian Army.

[23] Second, it would be a waste of scarce judicial resources. 
The decision would have no practical effect on the Applicant’s rights. 
This is not a situation that can evade review from Court since it is not of a recurring nature but brief duration and it is not of public importance of which a resolution is in the public interest (Borowski at 360-361). 
The Court must be sensitive of not pronouncing judgments in the absence of a dispute affecting the rights of the parties as it may be viewed as intruding into the role of the legislative branch (Borowski at 362). 
The Court’s primary role is to resolve real disputes (Democracy Watch at para 14). In light of the Borowski factors, it is my view that this matter is not an appropriate case for the Court to exercise its discretion to decide a moot case on its merits.

[24] It is not necessary to proceed further and review the merits of the decision.

V. Conclusions
[25] For the reasons above, this application for judicial review is dismissed. 
The application was filed later than 30 days after the date of the Denial Decision, another decision sought to be challenged is improperly before the Court, and this matter is also moot. 
It is not appropriate for the Court to exercise its discretion to hear and decide the application on its merits.
"""
    ]'''

    for i, text in enumerate(clauses):
        print(f"\n--- Analyzing Clause {i+1} ---")
        result = parser.process_clause(text if clause_text is None else clause_text, use_llm=True)
        print(f"Formula: {result['formula']}")
        print(f"Current Registry: {json.dumps(result['variable_map'], indent=2)}")
    return (result['formula'],result['variable_map'])

if __name__ == '__main__':
    run()