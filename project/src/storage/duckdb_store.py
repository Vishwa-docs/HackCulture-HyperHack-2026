"""DuckDB-based analytical storage for cross-document queries."""
import json
from pathlib import Path
from typing import Any, Optional

import duckdb

from ..core.logging import get_logger
from ..core import paths

log = get_logger(__name__)

DB_PATH = paths.INDEXES / "needle_finder.duckdb"


class DuckDBStore:
    """Analytical data store using DuckDB for cross-document queries."""

    def __init__(self, db_path: Optional[Path] = None):
        self.db_path = str(db_path or DB_PATH)
        self.conn = duckdb.connect(self.db_path)
        self._init_schema()

    def _init_schema(self):
        """Create all tables."""
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS pages (
                page_num INTEGER PRIMARY KEY,
                page_text TEXT,
                doc_id TEXT,
                doc_type TEXT,
                word_count INTEGER,
                char_count INTEGER
            )
        """)
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS documents (
                doc_id TEXT PRIMARY KEY,
                doc_type TEXT,
                page_start INTEGER,
                page_end INTEGER,
                doc_refs TEXT,
                confidence DOUBLE,
                raw_text TEXT
            )
        """)
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS vendors (
                vendor_id TEXT PRIMARY KEY,
                raw_name TEXT,
                canonical_name TEXT,
                gstin TEXT,
                ifsc TEXT,
                state TEXT,
                pan TEXT,
                bank_account TEXT
            )
        """)
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS invoices (
                invoice_number TEXT,
                vendor_name_raw TEXT,
                vendor_id TEXT,
                invoice_date TEXT,
                due_date TEXT,
                po_number TEXT,
                subtotal DOUBLE,
                tax_amount DOUBLE,
                tax_rate DOUBLE,
                grand_total DOUBLE,
                gstin_vendor TEXT,
                gstin_buyer TEXT,
                bank_ifsc TEXT,
                bank_account TEXT,
                source_pages TEXT,
                doc_id TEXT,
                line_items_json TEXT,
                raw_text TEXT
            )
        """)
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS purchase_orders (
                po_number TEXT,
                vendor_name_raw TEXT,
                vendor_id TEXT,
                po_date TEXT,
                delivery_date TEXT,
                gstin_vendor TEXT,
                subtotal DOUBLE,
                tax_amount DOUBLE,
                grand_total DOUBLE,
                source_pages TEXT,
                doc_id TEXT,
                line_items_json TEXT,
                raw_text TEXT
            )
        """)
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS bank_statements (
                statement_id TEXT,
                statement_month TEXT,
                account_number TEXT,
                opening_balance DOUBLE,
                closing_balance DOUBLE,
                source_pages TEXT,
                doc_id TEXT,
                transactions_json TEXT
            )
        """)
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS expense_reports (
                report_id TEXT,
                employee_name TEXT,
                employee_id TEXT,
                department TEXT,
                hotel_name TEXT,
                stay_start TEXT,
                stay_end TEXT,
                total_amount DOUBLE,
                source_pages TEXT,
                doc_id TEXT,
                expense_lines_json TEXT
            )
        """)
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS credit_debit_notes (
                note_number TEXT,
                note_type TEXT,
                vendor_name_raw TEXT,
                gstin_vendor TEXT,
                referenced_doc TEXT,
                target_doc TEXT,
                reason TEXT,
                amount DOUBLE,
                linked_documents TEXT,
                source_pages TEXT,
                doc_id TEXT,
                raw_text TEXT
            )
        """)
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS findings (
                finding_id TEXT,
                category TEXT,
                pages TEXT,
                document_refs TEXT,
                description TEXT,
                reported_value TEXT,
                correct_value TEXT,
                confidence DOUBLE,
                detector_name TEXT,
                status TEXT
            )
        """)

    def insert_page(self, page_num: int, text: str, doc_id: str = "", doc_type: str = ""):
        self.conn.execute(
            "INSERT OR REPLACE INTO pages VALUES (?, ?, ?, ?, ?, ?)",
            [page_num, text, doc_id, doc_type, len(text.split()), len(text)]
        )

    def insert_document(self, doc: dict):
        self.conn.execute(
            "INSERT OR REPLACE INTO documents VALUES (?, ?, ?, ?, ?, ?, ?)",
            [doc["doc_id"], doc.get("doc_type", ""), doc.get("page_start", 0),
             doc.get("page_end", 0), json.dumps(doc.get("doc_refs", [])),
             doc.get("confidence", 0.0), doc.get("raw_text", "")]
        )

    def insert_vendor(self, v):
        self.conn.execute(
            "INSERT OR REPLACE INTO vendors VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            [v.vendor_id, v.raw_name, v.canonical_name, v.gstin, v.ifsc, v.state, v.pan, v.bank_account]
        )

    def insert_invoice(self, inv):
        self.conn.execute(
            "INSERT INTO invoices VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            [inv.invoice_number, inv.vendor_name_raw, inv.vendor_id, inv.invoice_date,
             inv.due_date, inv.po_number,
             float(inv.subtotal) if inv.subtotal else None,
             float(inv.tax_amount) if inv.tax_amount else None,
             float(inv.tax_rate) if inv.tax_rate else None,
             float(inv.grand_total) if inv.grand_total else None,
             inv.gstin_vendor, inv.gstin_buyer, inv.bank_ifsc, inv.bank_account,
             json.dumps(inv.source_pages), inv.doc_id,
             json.dumps([li.model_dump(mode="json") for li in inv.line_items]),
             inv.raw_text]
        )

    def insert_po(self, po):
        self.conn.execute(
            "INSERT INTO purchase_orders VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            [po.po_number, po.vendor_name_raw, po.vendor_id, po.po_date,
             po.delivery_date, getattr(po, 'gstin_vendor', ''),
             float(po.subtotal) if po.subtotal else None,
             float(po.tax_amount) if po.tax_amount else None,
             float(po.grand_total) if po.grand_total else None,
             json.dumps(po.source_pages), po.doc_id,
             json.dumps([li.model_dump(mode="json") for li in po.line_items]),
             po.raw_text]
        )

    def insert_bank_statement(self, bs):
        self.conn.execute(
            "INSERT INTO bank_statements VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            [bs.statement_id, bs.statement_month, bs.account_number_masked,
             float(bs.opening_balance) if bs.opening_balance else None,
             float(bs.closing_balance) if bs.closing_balance else None,
             json.dumps(bs.source_pages), bs.doc_id,
             json.dumps([t.model_dump(mode="json") for t in bs.transactions])]
        )

    def insert_expense_report(self, er):
        self.conn.execute(
            "INSERT INTO expense_reports VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            [er.report_id, er.employee_name, er.employee_id, er.department,
             er.hotel_name, er.stay_start, er.stay_end,
             float(er.total_amount) if er.total_amount else None,
             json.dumps(er.source_pages), er.doc_id,
             json.dumps([el.model_dump(mode="json") for el in er.expense_lines])]
        )

    def insert_credit_debit_note(self, note):
        self.conn.execute(
            "INSERT INTO credit_debit_notes VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            [note.note_number, note.note_type,
             getattr(note, 'vendor_name_raw', ''), getattr(note, 'gstin_vendor', ''),
             note.referenced_doc, note.target_doc,
             note.reason, float(note.amount) if note.amount else None,
             json.dumps(getattr(note, 'linked_documents', [])),
             json.dumps(note.source_pages), note.doc_id,
             getattr(note, 'raw_text', '')]
        )

    def query(self, sql: str, params=None) -> list[dict]:
        """Execute query and return list of dicts."""
        if params:
            result = self.conn.execute(sql, params)
        else:
            result = self.conn.execute(sql)
        cols = [desc[0] for desc in result.description]
        rows = result.fetchall()
        return [dict(zip(cols, row)) for row in rows]

    def close(self):
        self.conn.close()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()
