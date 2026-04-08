from utils.extract_statement import extract_section, extract_statements, read_contact
import premise_to_proposition
import string
from logics.utils.solvers.natural_deduction import classical_natural_deduction_solver
from logics.utils.parsers import classical_parser
from logics.instances.propositional.many_valued_semantics import ST_mvl_semantics as ST

text = read_contact(".\T-2620-25_20260216_OR-OM_E-A_O_TOR_20260216093845_HR1.pdf")
section_text = extract_section(text)
statements = extract_statements(section_text)
print("Extracted Statements:")
for s in statements:
    print(s)

formula,variable_map = premise_to_proposition.run(' '.join(statements))
rewritten_initial_conditions = formula.replace("\n"," / ").replace(" / ",", ",formula.count("\n")-1).replace("->","→").translate(str.maketrans("⋀⋁¬","∧∨~"))
alphabet = list(string.ascii_uppercase)
ls = sorted(variable_map.keys())
for i in ls:
    rewritten_initial_conditions = rewritten_initial_conditions.replace(i,alphabet[int(i[1:])-1])

print("formula: ", rewritten_initial_conditions)



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

from logics.instances.propositional.languages import classical_language
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

