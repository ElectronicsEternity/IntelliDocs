"""Read-only audit of saved page hints and local usage records. No API calls."""
import json
import re
from pathlib import Path
import fitz
from restore_mapping_lab import sql

ROOT = Path(__file__).resolve().parents[2] / 'backups/2026-09-17'

def main():
    report = json.loads((ROOT / 'akta-page-profile-experiment-v2/page-comparison.json').read_text())
    pdf = fitz.open(ROOT / 'pdfs/Akta Kerja 1955 (Akta 265).pdf')
    records = sql('mapping_working', "SELECT coalesce(json_agg(t),'[]') FROM (SELECT id,activity,model,attempt,input_tokens,cached_input_tokens,output_tokens,reasoning_tokens,estimated_cost_usd,document_id,created_at FROM ai_usage ORDER BY created_at) t;")
    print('LEDGER', records)
    for row in report['generated_results']:
        if not row['text_node'] or row['anchor_on_predicted_page']:
            continue
        page = row['predicted_page']
        text = re.sub(r'\s+', ' ', pdf[page-1].get_text())
        identifier = row['identifier']
        print('\nANCHOR', identifier, row['title'], 'PAGE', page)
        pattern = re.escape(identifier).replace(r'\.', r'\s*\.')
        matches = list(re.finditer(pattern, text, re.I))
        if matches:
            for match in matches:
                print(text[max(0,match.start()-130):match.end()+350])
        else:
            print(text[:1800])
    for number in [51, 52, 90, 94, 99]:
        print('\nFULL PAGE', number, re.sub(r'\s+', ' ', pdf[number-1].get_text()))

if __name__ == '__main__':
    main()
