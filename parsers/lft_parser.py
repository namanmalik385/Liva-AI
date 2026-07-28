from services.text_extractor import extract_text
import re


def extract_numeric(pattern, text):
    match = re.search(pattern, text, re.IGNORECASE)

    if match:
        return float(match.group(1))

    return None


def parse_lft(text):

    result = {}

    result["total_bilirubin"] = extract_numeric(
        r"SERUM\s+BILIRUBIN\s*\(TOTAL\)\s+([\d.]+)",
        text
    )

    result["ast"] = extract_numeric(
        r"SGOT\s*\(AST\)\s+([\d.]+)",
        text
    )

    result["alt"] = extract_numeric(
        r"SGPT\s*\(ALT\)\s+([\d.]+)",
        text
    )

    result["ggt"] = extract_numeric(
        (
            r"(?:GAMMA[\s-]*GLUTAMYL\s+TRANSFERASE"
            r"(?:\s*\(GGT\))?|GGT)\s*[:\-]?\s*([\d.]+)"
        ),
        text
    )

    result["albumin"] = extract_numeric(
        r"SERUM\s+ALBUMIN\s+([\d.]+)",
        text
    )

    ast_uln_match = re.search(
        r"SGOT\s*\(AST\).*?(\d+)\s*-\s*(\d+)",
        text,
        re.IGNORECASE | re.DOTALL
    )

    if ast_uln_match:
        result["ast_uln"] = float(ast_uln_match.group(2))

    return result
