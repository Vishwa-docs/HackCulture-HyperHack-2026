"""Run pipeline stages 1-5 (text extraction, no LLM for stage 4 unless needed)."""
import sys, os
sys.path.insert(0, os.path.dirname(__file__) + "/..")
os.chdir(os.path.dirname(__file__) + "/..")

from dotenv import load_dotenv
load_dotenv()

from src.pipelines.run_all import Pipeline

p = Pipeline(team_id="hackculture")
p.run_all(from_stage=1, to_stage=5)

# Show extraction stats
import json
extracted = json.load(open("data/extracted/all_extracted.json"))
for k, v in extracted.items():
    if v:
        print(f"  {k}: {len(v)}")
        if v:
            sample = v[0]
            key_field = {
                "invoices": "invoice_number",
                "pos": "po_number",
                "bank_statements": "statement_id",
                "expense_reports": "report_id",
                "credit_debit_notes": "note_number",
            }.get(k, "")
            if key_field:
                print(f"    sample: {sample.get(key_field, '?')}")
