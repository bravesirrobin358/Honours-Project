# extract statements from pdfs
from pypdf import PdfReader
import ollama

def read_contact(filename):
    reader = PdfReader(filename)
    text = ""
    for page in reader.pages:
        text += page.extract_text() + "\n"
    return text

# we want to get the text within the section "III. Analysis"
def extract_section(text):
    # find the start and end positions of the section
    start_pos = text.find("III. Analysis")
    if start_pos == -1:
        return []
    end_pos = text.find("IV", start_pos)
    if end_pos == -1:
        end_pos = len(text)
    # get the text within the section
    section_text = text[start_pos:end_pos]
    return section_text

def extract_statements(section_text):
    # split the chunk of text into the sections (that are signified by each number)
    # aka split by [#] till next [#]
    # return a list of those statements
    statements = []
    current_statement = ""
    for line in section_text.split("\n"):
        if line.strip().startswith("["):
            if current_statement:
                statements.append(current_statement.strip())
            current_statement = line.strip()
        else:
            current_statement += " " + line.strip()
    return statements

text = read_contact("..\\T-2620-25_20260216_OR-OM_E-A_O_TOR_20260216093845_HR1.pdf")
section_text = extract_section(text)
statements = extract_statements(section_text)
print("Extracted Statements:")
for s in statements:
    print(s)

# send the statements to Ollama to extract propostions from them
def extract_propositions_with_ollama(statements, model="llama3.1"):
    extracted_propositions = []

    # for s in statements
    prompt = f"""
        Summarize the following legal text into a logical argument with premises and a final conclusion.
        Format each as a clear, standalone English sentence that expresses a condition, permission, obligation, or consequence.
        - Resolve any pronouns to their actual subjects.
        - Use clear "If [condition], then [consequence]" structures.
        - Important: The very last sentence MUST be the main conclusion of the text.
        - Provide exactly the premises followed by the conclusion, each on a new line. Do not include extra commentary or bullet points.

        Legal text:
        {''.join(statements)}
        """

    try:
        response = ollama.generate(
            model=model,
            prompt=prompt,
            options={"temperature": 0}
        )
        response_text = response['response'].strip()
        extracted_propositions.append(response_text)
        print(f"--- Propositions for statement ---\n{response_text}\n")
    except Exception as e:
        print(f"Error connecting to Ollama: {e}")
        extracted_propositions.append(None)

    return extracted_propositions

propositions_list = extract_propositions_with_ollama(statements, model="llama3.1")

if propositions_list and propositions_list[0]:
    from parse_contract import ParseContract
    import json

    parser = ParseContract(model_name="llama3.1")

    print("\n--- Parsing Propositions into Logic ---")
    result = parser.process_clause(propositions_list[0])

    if result:
        print(f"Formula: \n{result['formula']}")
        print(f"Variables: \n{json.dumps(result['variable_map'], indent=2)}")
    else:
        print("Could not parse the propositions into a logical formula.")


