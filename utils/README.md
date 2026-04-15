# Pre processing Text

I will illustrate how we clean up the inputted text to receive the best performance from Ollama.

Throughout this step by step explaination, I will illistrate how an inputted clause (below) changes before being used to prompt.

    clauses = [
        "If Amy were a tall and fair actress from the mainstream film industry, she would have won the best actress award. She is not a tall and fair actress since she has not won the best actress award."
    ]


## Global Cleanup (_clean_text)
- Basic string cleanup: Trim Edges, removes final trailing ".", normalized white spaces.
- Resulting in the same text.

## Subject detection (_extract_subject)
- Scans for capitalized words, skipping stopwords like "If", "Since" etc.
- First valid token found: "Amy"

So the subject anchor for pronoun replacement is now "Amy"

## Sentence split (_rule_based_parse)
Split on . ! ? into two sentences:

    If Amy were a tall and fair actress from the mainstream film industry, she would have won the best actress award

    She is not a tall and fair actress since she has not won the best actress award

## Pronoun normalization per sentence (_replace_pronouns)
Before pattern matching:

    If Amy were ... , Amy would have won ...

    Amy is not a tall and fair actress since Amy has not won ...

This is a key preprocessing step before any  prompt is built. Ollama's output worsens when the referenced subject's name is not mentioned within the proposition relating to it. 

### Each scetence split during this pre-processing sequence becomes it's own prompt sent to Ollama

## Sentence 1 path: if ... , ...
Matches:

```if <condition>, <consequence>```

    condition_part = Amy were a tall and fair actress from the mainstream film industry

    consequence_part = Amy would have won the best actress award

Each part is sent to _extract_atoms_from_segment, where preprocessing again does:

pronoun replacement (already normalized),
_clean_text,
then prompt construction for Ollama.
So before Ollama, the segment strings are:

Condition segment sent in prompt:

    Amy were a tall and fair actress from the mainstream film industry

Consequence segment sent in prompt:

    Amy would have won the best actress award

## Sentence 2 path: since/because
Matches:

```<claim> since <cause>```

Split:
- left_part (claim): Amy is not a tall and fair actress
- right_part (cause):  Amy has not won the best actress award

Negation preprocessing
- _contains_negation(left_part) → True
- _contains_negation(right_part) → True

#### Negation stripping (_strip_negation_words)

left_core becomes roughly: 

    Amy is a tall and fair actress

right_core becomes roughly: 

    Amy has won the best actress award

These stripped positive forms are what get atomized.

So before Ollama, the segment strings are:

Left segment in prompt: 

    Amy is a tall and fair actress

Right segment in prompt: 

    Amy has won the best actress award

Negation is reapplied later in formula rendering, not in atom text.

---

# Post Processing Ollama Output

### Parse Ollama response
Expect JSON list of atom strings.
If invalid/empty, fallback.
### Normalize returned atoms
- _clean_text(...)
- _ensure_subject(...) (inject subject if missing)
- _expand_conjunctive_atoms(...) (split A and B into separate atoms when possible)

### Canonicalize negation handling
- For since/because, negation was detected earlier (_contains_negation) and stripped before prompting.
- Now negation flags are reapplied at formula render time (¬...), not inside atom text.

### Register atoms to variables

- register_atom/register_atoms map atom text to stable proposition vars (p1, p2, etc.) via PropositionRegistry.
- Reused atoms get the same variable.

### Rebuild logical structure

R- ule tuple stored earlier: (lhs_vars, lhs_neg, rhs_vars, rhs_neg).
- _expr_from_vars(...) combines multi-atom sides with ∧.
- Build implication: lhs_expr -> rhs_expr.

### Assemble final output

Join sentence-level formulas with newlines.

Return:
- "formula": reconstructed logic text
- "variable_map": var → atom meaning

## Ollama gives local atoms, and post-processing restores global meaning by variable mapping + rule templates + negation reapplication.

# Execution:
'python complete_process.py <filepath>'
