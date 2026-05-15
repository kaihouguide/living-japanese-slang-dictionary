import os
import json
import re
import requests
from bs4 import BeautifulSoup

# Configuration
URL = "https://wesleycrobertson.wordpress.com/2022/06/19/living-japanese-slang-dictionary/"
OUTPUT_FILE = "japanese_slang_dict.json"

def fetch_dictionary_html(url):
    """Fetches the HTML content from the target URL."""
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
    }
    response = requests.get(url, headers=headers)
    response.raise_for_status()
    return response.text

def parse_slang_entries(html_content):
    """Parses the HTML and extracts dictionary entries into a list of dicts."""
    soup = BeautifulSoup(html_content, 'html.parser')
    entries = []
    
    # WordPress block paragraphs containing the actual entries
    paragraphs = soup.find_all('p', class_='wp-block-paragraph')
    
    for p in paragraphs:
        # Pre-process the HTML of the paragraph to replace <br> with newlines.
        # This makes it easier to parse structured lines (Type:, Meaning:, etc.)
        p_html = str(p)
        p_html_with_newlines = re.sub(r'<br\s*/?>', '\n', p_html, flags=re.IGNORECASE)
        
        # Re-parse to get clean text without HTML tags
        clean_text = BeautifulSoup(p_html_with_newlines, 'html.parser').get_text()
        
        # Replace non-breaking spaces and split into lines
        lines = [line.strip() for line in clean_text.replace('\xa0', ' ').split('\n') if line.strip()]
        
        # If the block doesn't contain "Type:" or "Meaning:", it's likely a header or FAQ text, skip it
        if not any(re.search(r'^(Type|Meaning)\s*\d*:', line, re.IGNORECASE) for line in lines):
            continue
            
        entry_data = {
            "term": "",
            "readings": "",
            "link": "",
            "type": [],
            "meaning": [],
            "example": [],
            "note": []
        }
        
        # 1. Extract Term and Link
        a_tag = p.find('a')
        if a_tag and a_tag.get('href', '').startswith('http'):
            entry_data['term'] = a_tag.get_text(strip=True)
            entry_data['link'] = a_tag.get('href', '')
        else:
            # Fallback if there is no hyperlink on the term
            term_match = re.match(r'^([^\(（]+)', lines[0])
            if term_match:
                entry_data['term'] = term_match.group(1).strip()
                
        # 2. Extract Readings (Usually trapped in parentheses on the first line)
        reading_match = re.search(r'[\(（](.*?)[\)）]', lines[0])
        if reading_match:
            entry_data['readings'] = [r.strip() for r in re.split(r'[・,、]', reading_match.group(1))]
            
        # 3. Parse Definitions Line-by-Line
        current_key = None
        for line in lines[1:]:
            # Match standard prefixes (Type:, Meaning 1:, Example:, Note:, See also:)
            if re.match(r'^Type\s*\d*:', line, re.IGNORECASE):
                entry_data['type'].append(re.sub(r'^Type\s*\d*:\s*', '', line, flags=re.IGNORECASE))
                current_key = 'type'
            elif re.match(r'^Meaning\s*\d*:', line, re.IGNORECASE):
                entry_data['meaning'].append(re.sub(r'^Meaning\s*\d*:\s*', '', line, flags=re.IGNORECASE))
                current_key = 'meaning'
            elif re.match(r'^Example\s*\d*:', line, re.IGNORECASE):
                entry_data['example'].append(re.sub(r'^Example\s*\d*:\s*', '', line, flags=re.IGNORECASE))
                current_key = 'example'
            elif re.match(r'^(Note|See also)\s*\d*:', line, re.IGNORECASE):
                entry_data['note'].append(re.sub(r'^(Note|See also)\s*\d*:\s*', '', line, flags=re.IGNORECASE))
                current_key = 'note'
            else:
                # If it doesn't match a prefix, it's a multi-line continuation of the previous key
                if current_key:
                    entry_data[current_key][-1] += " " + line
                    
        entries.append(entry_data)
        
    return entries

def sync_data(new_entries, output_file):
    """Compares new scraped data with local JSON and updates it."""
    old_entries = []
    
    # Load old data if it exists
    if os.path.exists(output_file):
        with open(output_file, 'r', encoding='utf-8') as f:
            try:
                old_entries = json.load(f)
            except json.JSONDecodeError:
                pass
                
    old_terms = {item['term'] for item in old_entries}
    new_terms = {item['term'] for item in new_entries}
    
    added_terms = new_terms - old_terms
    removed_terms = old_terms - new_terms
    
    print(f"Total entries found online: {len(new_entries)}")
    
    if added_terms:
        print(f"✅ Added {len(added_terms)} new entries: {', '.join(added_terms)}")
    if removed_terms:
        print(f"❌ Removed {len(removed_terms)} old entries: {', '.join(removed_terms)}")
    if not added_terms and not removed_terms:
        print("🔄 Up to date. No changes detected.")
        
    # Always overwrite the file to ensure 1:1 mirroring (handles detail modifications too)
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(new_entries, f, ensure_ascii=False, indent=4)
    print(f"📂 Saved latest data to {output_file}")

if __name__ == "__main__":
    print(f"Fetching data from {URL}...")
    try:
        html = fetch_dictionary_html(URL)
        parsed_entries = parse_slang_entries(html)
        sync_data(parsed_entries, OUTPUT_FILE)
    except Exception as e:
        print(f"An error occurred: {e}")