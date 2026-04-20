from utils.extract_statement import extract_section, extract_statements, read_contact
import premise_to_proposition
import string
from logics.utils.solvers.natural_deduction import classical_natural_deduction_solver
from logics.utils.parsers import classical_parser
from logics.instances.propositional.many_valued_semantics import ST_mvl_semantics as ST
import json
from logics.instances.propositional.languages import classical_language
import logics
import sys

file = "shorter.pdf" if not sys.argv[1:] else sys.argv[1]
if file.endswith(".txt"):
    with open(file) as f:
        section_text = f.read()
else:
    text = read_contact(file)
    section_text = extract_section(text)
statements = extract_statements(section_text)
print("Extracted Statements:")
for s in statements:
    print(s)

LLMProcessingPremise = premise_to_proposition.LLMProcessingPremise(model_name="llama3.1")
result = LLMProcessingPremise.process_clause(' '.join(statements), use_llm=True)
formula, variable_map = result["formula"], result["variable_map"]
# Post-process formula string to ensure formatting
import re
formula = formula.replace("->", "→").translate(str.maketrans("⋀⋁¬", "∧∨~"))
# removing bad parens around negations e.g. (~P2) -> ~P2
formula = re.sub(r'\(\s*(~P\d+)\s*\)', r'\1', formula)
# Make sure conclusions and things have outer parentheses if they don't
if "/" in formula:
    premises_str, conclusion_str = formula.split("/", 1)
    premises = [p.strip() for p in re.split(r',|\n', premises_str) if p.strip()]
    
    rewritten_initial_conditions = ", ".join(premises) + " / " + conclusion_str.strip()
else:
    rewritten_initial_conditions = formula
rewritten_initial_conditions = re.sub(r'\s+', ' ', rewritten_initial_conditions)

print("formula: ", rewritten_initial_conditions)
print("mapping: ")
print(json.dumps(variable_map, indent=2))




logics.instances.predicate.languages.metavariables = list(variable_map.keys())
logics.instances.propositional.languages.metavariables = list(variable_map.keys())
parsed = classical_parser.parse(rewritten_initial_conditions)
is_valid = ST.is_valid(parsed)
if not is_valid:
    print(rewritten_initial_conditions, " is not a valid inference")
    exit(1)
derivation = classical_natural_deduction_solver.solve(parsed)

# original solution
derivation.print_derivation(classical_parser)

# Find unused premise lines of the original solution
args_used = set([x for sublist in [i.on_steps for i in list(derivation)] for x in sublist])
prem_size = len(derivation)-1
unused_args = set(range(prem_size)) - args_used
unused_formulas = [derivation[i].content for i in unused_args]

print("Propositional map:\n",variable_map)


print("\nSimplified version:")

# Find and all instances of the unused formulas and remove them. Also remove any premises that consist entirely of unused formulas.
for i in unused_formulas:
    for prem in range(len(parsed.premises)):
        red = parsed.premises[prem].schematic_reduction(classical_language,parsed.premises[prem],i)
        parsed = parsed.substitute(parsed.premises[prem],red)

    parsed.premises = [p for p in parsed.premises if i != p]

#Solve again using the simplified premises
derivation = classical_natural_deduction_solver.solve(parsed)

derivation.print_derivation(classical_parser)

