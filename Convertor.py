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

def parse_term_and_readings(term_raw, readings_raw):
    term_raw = str(term_raw).strip()
    
    # 1. Extract parenthetical reading at the end of term_raw
    match = re.search(r'\s*[\(（]([^\)）]+)[\)）]$', term_raw)
    extracted_reading = None
    if match:
        possible_reading = match.group(1).strip()
        # Check if the extracted string contains Kanji; if it does, it's likely a part 
        # of the term (like スイーツ（笑）), NOT a reading.
        if not re.search(r'[一-龥]', possible_reading):
            extracted_reading = possible_reading
            term_raw = term_raw[:match.start()].strip()
            
    # If no readings were provided in the JSON, use the extracted one
    if not readings_raw or (isinstance(readings_raw, list) and not any(readings_raw)):
        if extracted_reading:
            readings_raw = [extracted_reading]
        else:
            readings_raw = []
            
    # Normalize string reading to a list
    if isinstance(readings_raw, str):
        readings_raw = [readings_raw]
        
    filtered_readings = []
    for r in readings_raw:
        r_str = str(r).strip()
        if not r_str:
            continue
        # Filter out false readings misidentified as readings in the JSON due to parenthesis
        # e.g., ignoring "が" from "腐臭(が)する" or "^Д^" from "m9(^Д^)ﾌﾟｷﾞｬｰ"
        if f"({r_str})" in term_raw or f"（{r_str}）" in term_raw:
            continue
        filtered_readings.append(r_str)
        
    cleaned_readings = []
    for r in filtered_readings:
        # Remove English modifiers like "often", "both", "usually"
        c = re.sub(r'^(often|both|usually)\s+', '', r, flags=re.IGNORECASE).strip()
        # Split merged readings by common delimiters
        sub_r = re.split(r'\s+(?:or|both|often)\s+|\s*・\s*|\s*,\s*|\s*\/\s*|\s*｜\s*', c)
        for sr in sub_r:
            sr = sr.strip()
            if sr:
                cleaned_readings.append(sr)
                
    if not cleaned_readings:
        cleaned_readings = [""]
        
    # Check for cases where phrases are delimited by standard Japanese comma `、`
    # E.g., `横を見るな、推しを見ろ` -> length 2. If reading list is length 2, join them!
    term_comma_parts = [p.strip() for p in term_raw.split('、') if p.strip()]
    if '、' in term_raw and len(term_comma_parts) == len(cleaned_readings) and len(cleaned_readings) > 1:
        cleaned_readings = ['、'.join(cleaned_readings)]
        
    # Split term by brackets \[.*?\] or 【.*?】 
    # (By splitting rather than deleting, this creates two distinct terms "もうやめて" and "のライフはゼロよ！" 
    # making them both natively scannable in Yomitan instead of mangled).
    bracket_parts = [p.strip() for p in re.split(r'\[.*?\]|【.*?】', term_raw) if p.strip()]
    
    final_terms = []
    for bp in bracket_parts:
        # Split terms by actual synonym delimiters 
        # (Excluding commas as those are handled appropriately or belong to English quotes inside terms)
        synonyms = re.split(r'\s+(?:or|both|often)\s+|\s*・\s*|\s*\/\s*|\s*｜\s*', bp)
        for syn in synonyms:
            syn = re.sub(r'[「」\'"〜~〰]', '', syn).strip()
            if syn:
                final_terms.append(syn)
                
    # Remove duplicates but preserve logical order
    final_terms = list(dict.fromkeys(final_terms))
    cleaned_readings = list(dict.fromkeys(cleaned_readings))
    
    pairs = []
    # If the amount of distinct synonym terms equals the exact amount of distinct readings, match them 1-to-1.
    if len(final_terms) == len(cleaned_readings) and len(final_terms) > 1:
        for t, r in zip(final_terms, cleaned_readings):
            pairs.append((t, r))
    else:
        # Otherwise, fall back to linking permutations (Cartesian product)
        for t in final_terms:
            for r in cleaned_readings:
                pairs.append((t, r))
                
    return pairs

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
        
        # Parse, clean, and generate all correctly paired term/reading variations
        pairs = parse_term_and_readings(original_term, readings_raw)
        
        if not pairs:
            continue

        content_nodes = []

        # 0. Header Node (Displays the Absolute Original Term)
        content_nodes.append({
            "tag": "div",
            "style": {
                "fontSize": "1.2em",
                "fontWeight": "bold",
                "marginBottom": "10px",
                "color": "#e0e0e0" 
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

        # Append using the strictly paired outputs
        for t, r in pairs:
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
