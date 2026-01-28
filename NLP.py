import re
ALPHABET='ABCDEFGHIJKLMNOPQRSTUVWXYZ'
s = "I drink beer and play hockey. \
People who drink beer do not eat lamb. \
If I played hockey, then I either do not drink beer or I don’t gamble. \
In conclusion, I don’t gamble and I don’t eat lamb, or I don’t live in Canada."

print(s)

negations = ["don't", "never", "no", "cannot", "not", "false", "fails"]
conjunctions = ["and", "but", "although", "however", "whereas", "besides", "nevertheless", "even though", "while", "as well as"]
disjunctions = ["or", "alternatively", "otherwise", "unless"]

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