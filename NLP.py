'''import re
ALPHABET='ABCDEFGHIJKLMNOPQRSTUVWXYZ'
s = "I drink beer and play hockey. \
People who drink beer do not eat lamb. \
If I played hockey, then I either do not drink beer or I don’t gamble. \
In conclusion, I don’t gamble and I don’t eat lamb, or I don’t live in Canada."

print(s)

negations = ["don't", "never", "no", "cannot", "not", "false", "fails"]
conjunctions = ["and", "but", "although", "however", "whereas", "besides", "nevertheless", "even though", "while", "as well as"]
disjunctions = ["or", "alternatively", "otherwise", "unless"]
'''
# so basically we want to interate through the sentence twice
# we split the sentence by symbols first
# and then we treat each split like it's own Letter (p, q) then we go over each split to find common words
# assigning those the same letters
# then we handle negations
# and put that all together

# example "you can have a dog or a cat, but not both. Since mom is allergic to cats, you cannot have a cat."
# you would go through it   [you can have a dog] [or] [a cat] [but not both] [since mom is allergic to cats you] [cannot] [have a cat]
# then on second pass you would assign letters to common words
# you can have a A [or] a B, [but not both]. Since mom is allergic to B, you [cannot] have a B
# then we remove the extra words and handle negations
# resulting in something like:  A or B, not both. not B
# which then results in:  A⊕B. ¬B

import re

def Rule(output, *patterns):
    "A rule that produces `output` if the entire input matches any one of the `patterns`." 
    return (output, [name_group(pat) + '$' for pat in patterns])

def name_group(pat):
    "Replace '{Q}' with '(?P<Q>.+?)', which means 'match 1 or more characters, and call it Q'"
    return re.sub('{(.)}', r'(?P<\1>.+?)', pat)
            
def word(w):
    "Return a regex that matches w as a complete word (not letters inside a word)."
    return r'\b' + w + r'\b' # '\b' matches at word boundary

# rules = [
#     Rule('{P} ⇒ {Q}',         'if {P} then {Q}', 'if {P}, {Q}'),
#     Rule('{P} ⋁ {Q}',          'either {P} or else {Q}', 'either {P} or {Q}'),
#     Rule('{P} ⋀ {Q}',          'both {P} and {Q}'),
#     Rule('～{P} ⋀ ～{Q}',       'neither {P} nor {Q}'),
#     Rule('～{A}{P} ⋀ ～{A}{Q}', '{A} neither {P} nor {Q}'), # The Kaiser neither ...
#     Rule('～{Q} ⇒ {P}',        '{P} unless {Q}'),
#     Rule('{P} ⇒ {Q}',          '{Q} provided that {P}', '{Q} whenever {P}', 
#                                '{P} implies {Q}', '{P} therefore {Q}', 
#                                '{Q}, if {P}', '{Q} if {P}', '{P} only if {Q}'),
#     Rule('{P} ⋀ {Q}',          '{P} and {Q}', '{P} but {Q}'),
#     Rule('{P} ⋁ {Q}',          '{P} or else {Q}', '{P} or {Q}'),
#     ]

# Our explansion of the rules:
rules = [
    Rule('～{P} ⋀ ～{Q}',       'neither {P} nor {Q}'),
    Rule('～{A}{P} ⋀ ～{A}{Q}', '{A} neither {P} nor {Q}'), # The Kaiser neither ...
    Rule('～{Q} ⇒ {P}',        '{P} unless {Q}'),
    Rule('{P} ⇒ {Q}',          '{Q} provided that {P}', 
                                '{Q} whenever {P}', 
                               '{P} implies {Q}', 
                               '{P} therefore {Q}', 
                               '{Q}, if {P}', 
                               '{Q} if {P}', 
                               '{Q} only if {P}',
                               'if {P} then {Q}', 
                               'if {P}, {Q}',
                               'given that {P}, it follows that {Q}',
                               'given that {P}, {Q}',
                               'provided that {P}, {Q}',
                               'whenever {P}, {Q}',
                               'when {P}, {Q}',
                               '{P} who {Q}',
                               'as long as {P}, {Q}',
                               'so long as {P}, {Q}',
                               'in the event that {P}, {Q}',
                                'on the condition that {P}, {Q}',
                                'assuming that {P}, {Q}',
                                '{P} is a sufficient condition for {Q}',
                                '{Q} is a necessary condition for {P}'
                               ),
    Rule('{P} ⋀ {Q}',          'both {P} and {Q}',
                                '{P} and {Q}', 
                                '{P} but {Q}', 
                                '{P} although {Q}',
                                '{P} however {Q}',
                                '{P} whereas {Q}',
                                '{P} besides {Q}',
                                '{P} nevertheless {Q}',
                                '{P} even though {Q}',
                                '{P} while {Q}',
                                '{P} as well as {Q}'),
    Rule('{P} ⋁ {Q}',          'either {P} or else {Q}', 
                                'either {P} or {Q}',
                                '{P} or else {Q}', 
                                '{P} or {Q}',
                                '{P} alternatively {Q}',
                                "{P} otherwise {Q}",
                                "{P} unless {Q}"),
    ]

negations = [
    (word("not"), ""),
    (word("cannot"), "can"),
    (word("can't"), "can"),
    (word("won't"), "will"),
    (word("ain't"), "is"),
    (word("false"), "true"),
    (word("fails"), "succeeds"),
    #(word("never"), "always"),
    ("n't", ""), # matches as part of a word: didn't, couldn't, etc.
    ]


def match_rules(sentence, rules, defs):
    """Match sentence against all the rules, accepting the first match; or else make it an atom.
    Return two values: the Logic translation and a dict of {P: 'english'} definitions."""
    sentence = clean(sentence)
    for rule in rules:
        result = match_rule(sentence, rule, defs)
        if result: 
            return result
    return match_literal(sentence, negations, defs)
        
def match_rule(sentence, rule, defs):
    "Match rule, returning the logic translation and the dict of definitions if the match succeeds."
    output, patterns = rule
    for pat in patterns:
        # print(f"DEBUG: Compiling pattern: {pat}")
        match = re.match(pat, sentence, flags=re.I)
        if match:
            groups = match.groupdict()
            for P in sorted(groups): # Recursively apply rules to each of the matching groups
                 groups[P] = match_rules(groups[P], rules, defs)[0]
            return '(' + output.format(**groups) + ')', defs
        
def match_literal(sentence, negations, defs):
    "No rule matched; sentence is an atom. Add new proposition to defs. Handle negation."
    polarity = ''
    for (neg, pos) in negations:
        (sentence, n) = re.subn(neg, pos, sentence, flags=re.I)
        polarity += n * '～'
    sentence = clean(sentence)
    P = proposition_name(sentence, defs)
    defs[P] = sentence
    return polarity + P, defs
    
def proposition_name(sentence, defs, names='PQRSTUVWXYZBCDEFGHJKLMN'):
    "Return the old name for this sentence, if used before, or a new, unused name."
    inverted = {defs[P]: P for P in defs}
    if sentence in inverted:
        return inverted[sentence]                      # Find previously-used name
    else:
        return next(P for P in names if P not in defs) # Use a new unused name
    
def clean(text): 
    "Remove redundant whitespace; handle curly apostrophe and trailing comma/period."
    return ' '.join(text.split()).replace("’", "'").rstrip('.').rstrip(',')

sentences = '''
Polkadots and Moonbeams.
If you liked it then you shoulda put a ring on it.
If you build it, he will come.
It don't mean a thing, if it ain't got that swing.
If loving you is wrong, I don't want to be right.
Should I stay or should I go.
I shouldn't go and I shouldn't not go.
If I fell in love with you,
  would you promise to be true
  and help me understand.
I could while away the hours
  conferrin' with the flowers,
  consulting with the rain
  and my head I'd be a scratchin'
  while my thoughts are busy hatchin'
  if I only had a brain.
There's a federal tax, and a state tax, and a city tax, and a street tax, and a sewer tax.
A ham sandwich is better than nothing 
  and nothing is better than eternal happiness
  therefore a ham sandwich is better than eternal happiness.
If I were a carpenter
  and you were a lady,
  would you marry me anyway?
  and would you have my baby.
Either Danny didn't come to the party or Virgil didn't come to the party.
Either Wotan will triumph and Valhalla will be saved or else he won't and Alberic will have 
  the final word.
Sieglinde will survive, and either her son will gain the Ring and Wotan’s plan 
  will be fulfilled or else Valhalla will be destroyed.
Wotan will intervene and cause Siegmund's death unless either Fricka relents 
  or Brunnhilde has her way.
Figaro and Susanna will wed provided that either Antonio or Figaro pays and Bartolo is satisfied 
  or else Marcellina’s contract is voided and the Countess does not act rashly.
If the Kaiser neither prevents Bismarck from resigning nor supports the Liberals, 
  then the military will be in control and either Moltke's plan will be executed 
  or else the people will revolt and the Reich will not survive'''.split('.')

import textwrap, string
s = "I do drink beer and I play hockey. \
      I watch movies. \
If I do drink beer, then I don't eat lamb. \
If I play hockey, then either I don't drink beer or I don’t gamble. \
I don’t gamble and I don’t eat lamb".split('.')
def logic(sentences, width=80): 
    alphabet = list(string.ascii_uppercase)
    next_p = 0
    prop_list = {}
    prem_conc_list = []
    "Match the rules against each sentence in text, and print each result."
    for s in map(clean, sentences):
        letter_map = {}
        logic, defs = match_rules(s, rules, {})
        for P in sorted(defs):
            # Proposition doesn't exist
            if not prop_list.get(defs[P]):
                out_letter = alphabet[next_p]
                prop_list[defs[P]] = out_letter
                next_p = (next_p+1)%25
            logic = '(P)' if logic == "P" else logic
            out_letter = prop_list[defs[P]]
            print('{}: {}'.format(out_letter, defs[P]))
            letter_map[P] = out_letter
        prem_conc_list.append((line:=logic.translate(str.maketrans("".join(letter_map.keys()),"".join(letter_map.values())))))
        print(textwrap.fill('English: ' + s +'.', width), '\nLogic:', line,'\n\n')
    return prem_conc_list


from logics.utils.solvers.natural_deduction import classical_natural_deduction_solver
from logics.utils.parsers import classical_parser
#       I watch movies. \
s = "I do drink beer and I play hockey. \
I watch movies. \
If I do drink beer, then I don't eat lamb. \
If I play hockey, then either I don't drink beer or I don’t gamble. \
I don’t gamble and I don’t eat lamb".split('.')
s = "I do drink beer and I play hockey and I like books and I want meds. \
I watch movies. \
If I do drink beer, then I don't eat lamb. \
If I play hockey, then either I don't drink beer or I don’t gamble. \
I don’t gamble and I don’t eat lamb".split('.')

s = "I do drink beer and I play hockey. \
I do drink beer or I eat lamb".split('.')

initial_conditions = logic(s)
rewritten_initial_conditions = " / ".join([i[1:-1] for i in initial_conditions]).replace(" /",",",len(initial_conditions)-2).translate(str.maketrans("⋀⋁⇒～","∧∨→~"))
print('\nformal logic proof:', rewritten_initial_conditions,'\n')
# A ∧ B, C, A → ~D, B → (~A ∨ ~E) / ~E ∧ ~D
parsed = classical_parser.parse(rewritten_initial_conditions)
derivation = classical_natural_deduction_solver.solve(parsed)
# 'P ∧ Q, P → ~R, Q → (~P ∨ ~S) / ~S ∧ ~R'
derivation.print_derivation(classical_parser)

args_used = set([x for sublist in [i.on_steps for i in list(derivation)] for x in sublist])
prem_size = len(derivation)-1
unused_args = set(range(prem_size)) - args_used
unused_formulas = [derivation[i].content for i in unused_args]
from logics.classes.propositional.formula import Formula
from logics.instances.propositional.languages import classical_language
print("\nSimplified version:")
for i in unused_formulas:
    for prem in range(len(parsed.premises)):
        red = parsed.premises[prem].schematic_reduction(classical_language,parsed.premises[prem],i)
        parsed = parsed.substitute(parsed.premises[prem],red)

    parsed.premises = [p for p in parsed.premises if i != p]

#keep B
print()
derivation = classical_natural_deduction_solver.solve(parsed)
# 'P ∧ Q, P → ~R, Q → (~P ∨ ~S) / ~S ∧ ~R'
derivation.print_derivation(classical_parser)