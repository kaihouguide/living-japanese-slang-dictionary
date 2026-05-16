import json
import re
import zipfile
import os
from datetime import datetime

def parse_example(ex_string):
    """
    Extracts the English translation from the end of the Japanese example.
    Looks for text wrapped in () or （） at the very end of the string.
    """
    ex_string = str(ex_string).strip()
    match = re.search(r'\s*[\(（](.*?)[\)）]\s*$', ex_string)
    if match:
        jp_text = ex_string[:match.start()].strip()
        eng_text = match.group(1).strip()
        return jp_text, eng_text
    return ex_string, ""

def split_and_clean(text):
    """
    Splits text by delimiters (or, both, often, ・, /, ,) 
    and cleans out brackets, quotes, and tildes to ensure clean Yomitan lookups.
    """
    if not text:
        return []
    
    text = str(text)
    
    # Split by common slang delimiters
    parts = re.split(r'\s+(?:or|both|often)\s+|\s*・\s*|\s*,\s*|\s*\/\s*|\s*｜\s*', text)
    
    cleaned = []
    for p in parts:
        # Remove variable brackets like [NOUN], [A]
        p = re.sub(r'\[.*?\]', '', p)
        p = re.sub(r'【.*?】', '', p)
        # Remove quotes and tildes
        p = re.sub(r'[「」\'"〜~〰]', '', p)
        # Clean whitespace
        p = p.strip()
        if p:
            cleaned.append(p)
            
    # Return list of unique parts while preserving order
    return list(dict.fromkeys(cleaned))

def parse_term_and_readings(term_raw, readings_raw):
    """
    Extracts embedded readings, then splits and cleans all variations.
    """
    # 1. Check if reading is hidden at the end of the term in parentheses
    match = re.search(r'\s*[\(（]([^\)）]+)[\)）]$', term_raw)
    
    term_to_split = term_raw
    if match:
        extracted_reading = match.group(1).strip()
        term_to_split = term_raw[:match.start()].strip()
        
        # If no readings were provided in the JSON, use the extracted one
        if not readings_raw or (isinstance(readings_raw, list) and not any(readings_raw)):
            readings_raw = extracted_reading

    # 2. Split and clean the terms
    terms = split_and_clean(term_to_split)
    
    # 3. Format and split the readings
    if isinstance(readings_raw, list):
        # Filter out empty entries and join with 'or' to pipe into our standard parser
        valid_readings = [str(r) for r in readings_raw if r]
        readings_str = " or ".join(valid_readings)
    else:
        readings_str = str(readings_raw) if readings_raw else ""
        
    readings = split_and_clean(readings_str)
    
    # Yomitan requires at least an empty string for the reading
    if not readings:
        readings = [""]
        
    return terms, readings

def create_dictionary(input_file, output_zip):
    repo = os.environ.get("GITHUB_REPOSITORY", "YOUR_USERNAME/YOUR_REPO")
    index_url = f"https://github.com/{repo}/releases/latest/download/index.json"
    download_url = f"https://github.com/{repo}/releases/latest/download/dictionary.zip"

    with open(input_file, 'r', encoding='utf-8') as f:
        data = json.load(f)

    term_bank = []
    seq = 1

    for item in data:
        original_term = item.get("term", "")
        if not original_term:
            continue

        readings_raw = item.get("readings", [])
        
        # Parse, clean, and generate all term/reading variations
        terms, readings = parse_term_and_readings(original_term, readings_raw)
        
        if not terms:
            continue

        content_nodes = []

        # 0. Header Node (Displays the Absolute Original Term)
        content_nodes.append({
            "tag": "div",
            "style": {
                "fontSize": "1.2em",
                "fontWeight": "bold",
                "marginBottom": "10px",
                "color": "#e0e0e0" # Optional: Makes the header stand out nicely on dark modes
            },
            "content": original_term
        })

        # 1. Part of Speech / Type (Compact Colored Badge)
        item_type = item.get("type", [])
        if item_type:
            type_str = ", ".join(item_type) if isinstance(item_type, list) else str(item_type)
            content_nodes.append({
                "tag": "div",
                "style": {"marginBottom": "12px"},
                "content": [{
                    "tag": "span",
                    "style": {
                        "color": "#ffffff",
                        "backgroundColor": "#5c6bc0", 
                        "padding": "3px 8px",
                        "fontWeight": "bold",
                        "fontSize": "13px"
                    },
                    "content": type_str
                }]
            })

        # 2. Meanings (Bullet List)
        meanings = item.get("meaning", [])
        if meanings:
            if isinstance(meanings, list):
                ul = {
                    "tag": "ul",
                    "style": {"marginBottom": "14px", "marginLeft": "20px"},
                    "content": [{"tag": "li", "content": m} for m in meanings]
                }
                content_nodes.append(ul)
            else:
                content_nodes.append({
                    "tag": "div",
                    "style": {"marginBottom": "14px"},
                    "content": str(meanings)
                })

        # 3. Examples (Parsed Japanese + English)
        examples = item.get("example", [])
        if examples:
            if not isinstance(examples, list):
                examples = [examples]
            for ex in examples:
                jp_text, eng_text = parse_example(ex)
                
                # Ex Badge + Japanese Text
                ex_content = [
                    {
                        "tag": "span",
                        "style": {
                            "color": "#ffffff",
                            "backgroundColor": "#4caf50", 
                            "padding": "2px 6px",
                            "fontSize": "12px",
                            "fontWeight": "bold",
                            "marginRight": "8px"
                        },
                        "content": "Ex"
                    },
                    {
                        "tag": "span",
                        "style": {"fontSize": "14px"},
                        "content": jp_text
                    }
                ]
                
                # English Translation (New line, Indented)
                if eng_text:
                    ex_content.append({
                        "tag": "div",
                        "style": {
                            "marginTop": "6px",
                            "marginLeft": "32px", 
                            "fontSize": "13px",
                            "fontStyle": "italic" 
                        },
                        "content": eng_text
                    })

                content_nodes.append({
                    "tag": "div",
                    "style": {
                        "marginTop": "8px",
                        "marginBottom": "12px",
                        "marginLeft": "8px"
                    },
                    "content": ex_content
                })

        # 4. Notes (Info Box)
        notes = item.get("note", [])
        if notes:
            if not isinstance(notes, list):
                notes = [notes]
            for note in notes:
                content_nodes.append({
                    "tag": "div",
                    "style": {
                        "marginTop": "8px",
                        "paddingLeft": "12px",
                        "fontSize": "13px"
                    },
                    "content": f"📝 Note: {note}"
                })

        # 5. External Link
        link = item.get("link", "")
        if link:
            content_nodes.append({
                "tag": "div",
                "style": {"marginTop": "14px", "textAlign": "right", "fontSize": "12px"},
                "content": [{"tag": "a", "href": link, "content": "🔗 Read more / Source"}]
            })

        glossary = [{
            "type": "structured-content",
            "content": {
                "tag": "div",
                "content": content_nodes
            }
        }]

        # Create row entries for ALL combinations of Terms and Readings
        for t in terms:
            for r in readings:
                row = [t, r, "", "", 0, glossary, seq, ""]
                term_bank.append(row)

        seq += 1

    with open("term_bank_1.json", "w", encoding="utf-8") as f:
        json.dump(term_bank, f, ensure_ascii=False, separators=(',', ':'))

    # Update Index Metadata (Title, Author)
    revision_date = datetime.now().strftime("%Y-%m-%d")
    index_data = {
        "title": "Scripting Japan (Slang)",
        "format": 3,
        "revision": f"slang_{revision_date}",
        "sequenced": True,
        "author": "Wes Robertson Converted by Selxo",
        "url": "https://wesleycrobertson.wordpress.com/",
        "description": "Daily-updated collection of modern Japanese slang compiled by Wes Robertson.",
        "attribution": "Wes Robertson",
        "isUpdatable": True,
        "indexUrl": index_url,
        "downloadUrl": download_url
    }

    with open("index.json", "w", encoding="utf-8") as f:
        json.dump(index_data, f, ensure_ascii=False, indent=2)

    with zipfile.ZipFile(output_zip, 'w', zipfile.ZIP_DEFLATED) as zf:
        zf.write("index.json")
        zf.write("term_bank_1.json")

    print(f"✅ Generated Yomitan dictionary: {output_zip}")

if __name__ == "__main__":
    create_dictionary("japanese_slang_dict.json", "Scripting_Japan_Slang.zip")
