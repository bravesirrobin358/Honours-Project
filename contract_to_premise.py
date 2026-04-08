# extract statements from pdfs
from pypdf import PdfReader
import ollama
from premise_to_proposition import LLMProcessingPremise
import json

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

# send the statements to Ollama to extract propostions from them
def extract_propositions_with_ollama(statements, model="llama3.1"):
    extracted_propositions = []

    # for s in statements
    prompt = f"""
        Summarize the following legal text into a sequence of simple, short, and continuous propositional sentences separated by periods. Add a claim at the end that captures the main conclusion of the text.
        - The sentences should be as simple as possible, like "Applicant is eligible or applicant is rejected. Applicant is not eligible. Applicant is rejected."
        - Resolve any pronouns to their actual subjects.
        - Do not use lists, bullet points, or newlines. Just output a single paragraph of simple sentences separated by periods.
        - Important: The very last sentence MUST be the main conclusion of the text.
        - Do not include extra commentary, just the logically buildable text.

        Legal text:
        {' '.join(statements)}
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
