"""Main pipeline orchestrator - runs all stages end-to-end."""
import json
import time
from pathlib import Path
from typing import Optional

from ..core.logging import get_logger
from ..core import paths
from ..core.config import Settings
from ..core.enums import DocType
from ..core.models import FindingCandidate

from ..ingestion.pdf_manifest import PDFManifest
from ..ingestion.splitter import split_into_documents, classify_page
from ..ingestion.bedrock_client import BedrockClient

from ..extraction.vendor_master import extract_vendor_master, extract_vendor_master_with_llm
from ..extraction.llm_structured_extract import extract_with_llm
from ..extraction.text_extract import extract_from_text

from ..storage.duckdb_store import DuckDBStore
from ..storage.graph_store import GraphStore

from ..normalization.ids import normalize_po_number

from ..adjudication.confidence import finalize_findings
from ..output.formatter import (
    write_submission, write_all_candidates, write_rejected,
    write_findings_csv, write_analytics,
)

log = get_logger(__name__)


def _get_all_detectors():
    """Import and instantiate all detectors."""
    from ..detectors.easy.arithmetic_error import ArithmeticErrorDetector
    from ..detectors.easy.billing_typo import BillingTypoDetector
    from ..detectors.easy.duplicate_line_item import DuplicateLineItemDetector
    from ..detectors.easy.invalid_date import InvalidDateDetector
    from ..detectors.easy.wrong_tax_rate import WrongTaxRateDetector

    from ..detectors.medium.po_invoice_mismatch import POInvoiceMismatchDetector
    from ..detectors.medium.vendor_name_typo import VendorNameTypoDetector
    from ..detectors.medium.double_payment import DoublePaymentDetector
    from ..detectors.medium.ifsc_mismatch import IFSCMismatchDetector
    from ..detectors.medium.duplicate_expense import DuplicateExpenseDetector
    from ..detectors.medium.date_cascade import DateCascadeDetector
    from ..detectors.medium.gstin_state_mismatch import GSTINStateMismatchDetector

    from ..detectors.evil.quantity_accumulation import QuantityAccumulationDetector
    from ..detectors.evil.price_escalation import PriceEscalationDetector
    from ..detectors.evil.balance_drift import BalanceDriftDetector
    from ..detectors.evil.circular_reference import CircularReferenceDetector
    from ..detectors.evil.triple_expense_claim import TripleExpenseClaimDetector
    from ..detectors.evil.employee_id_collision import EmployeeIDCollisionDetector
    from ..detectors.evil.fake_vendor import FakeVendorDetector
    from ..detectors.evil.phantom_po_reference import PhantomPOReferenceDetector

    return [
        ArithmeticErrorDetector(),
        BillingTypoDetector(),
        DuplicateLineItemDetector(),
        InvalidDateDetector(),
        WrongTaxRateDetector(),
        POInvoiceMismatchDetector(),
        VendorNameTypoDetector(),
        DoublePaymentDetector(),
        IFSCMismatchDetector(),
        DuplicateExpenseDetector(),
        DateCascadeDetector(),
        GSTINStateMismatchDetector(),
        QuantityAccumulationDetector(),
        PriceEscalationDetector(),
        BalanceDriftDetector(),
        CircularReferenceDetector(),
        TripleExpenseClaimDetector(),
        EmployeeIDCollisionDetector(),
        FakeVendorDetector(),
        PhantomPOReferenceDetector(),
    ]


class Pipeline:
    """End-to-end pipeline orchestrator."""

    def __init__(self, pdf_path: Optional[Path] = None, team_id: str = "hackculture"):
        self.pdf_path = pdf_path or paths.GAUNTLET_PDF
        self.team_id = team_id
        self.settings = Settings.get()
        self.manifest = None
        self.page_texts = {}
        self.documents = []
        self.vendors = []
        self.store = None
        self.graph = None
        self.bedrock = None
        self.all_candidates = []

    def run_all(self, from_stage: int = 1, to_stage: int = 99,
                only_category: str = None, limit_pages: int = 0,
                resume: bool = False, debug: bool = False,
                use_agents: bool = False):
        """Run the complete pipeline."""
        start_time = time.time()
        log.info(f"Starting pipeline: stages {from_stage}-{to_stage}, team={self.team_id}, agents={use_agents}")

        if from_stage <= 1 <= to_stage:
            self._stage_1_ingest(limit_pages)

        if from_stage <= 2 <= to_stage:
            self._stage_2_split()

        if from_stage <= 3 <= to_stage:
            self._stage_3_vendor_master()

        if from_stage <= 4 <= to_stage:
            self._stage_4_extract(resume)

        if from_stage <= 5 <= to_stage:
            self._stage_5_index()

        if from_stage <= 6 <= to_stage:
            if use_agents:
                self._stage_6_detect_agents(only_category)
            else:
                self._stage_6_detect(only_category)

        if from_stage <= 7 <= to_stage:
            self._stage_7_finalize()

        elapsed = time.time() - start_time
        log.info(f"Pipeline completed in {elapsed:.1f}s")

    def _stage_1_ingest(self, limit_pages: int = 0):
        """Stage 1: Parse PDF and extract page text."""
        log.info("=== STAGE 1: INGEST ===")
        self.manifest = PDFManifest(self.pdf_path)
        self.manifest.open()

        total = min(limit_pages, self.manifest.page_count) if limit_pages else self.manifest.page_count
        log.info(f"Processing {total} pages")

        self.page_texts = {}
        for page_num in range(1, total + 1):
            text = self.manifest.get_page_text(page_num)
            self.page_texts[page_num] = text

        # Save page texts
        page_text_path = paths.PARSED / "page_texts.json"
        page_text_path.write_text(json.dumps(
            {str(k): v for k, v in self.page_texts.items()}, indent=2
        ))
        self.manifest.build_manifest()
        log.info(f"Stage 1 complete: {len(self.page_texts)} pages ingested")

    def _stage_2_split(self):
        """Stage 2: Split into logical documents."""
        log.info("=== STAGE 2: SPLIT ===")
        if not self.page_texts:
            self._load_page_texts()
        self.documents = split_into_documents(self.page_texts)
        log.info(f"Stage 2 complete: {len(self.documents)} documents")

    def _stage_3_vendor_master(self):
        """Stage 3: Extract vendor master."""
        log.info("=== STAGE 3: VENDOR MASTER ===")
        if not self.page_texts:
            self._load_page_texts()

        vm_pages = self.settings.get("vendor_master_pages", [3, 4])
        self.vendors = extract_vendor_master(self.page_texts, vm_pages)

        if len(self.vendors) < 3:
            log.warning(f"Only {len(self.vendors)} vendors from text parsing, trying LLM extraction")
            try:
                self.bedrock = self.bedrock or BedrockClient()
                self.vendors = extract_vendor_master_with_llm(self.page_texts, self.bedrock, vm_pages)
            except Exception as e:
                log.error(f"LLM vendor extraction failed: {e}")

        log.info(f"Stage 3 complete: {len(self.vendors)} vendors extracted")

    def _stage_4_extract(self, resume: bool = False):
        """Stage 4: Extract structured data from all documents.
        Uses regex-based extraction first, LLM fallback for failures.
        """
        log.info("=== STAGE 4: EXTRACT ===")
        if not self.documents:
            self._load_documents()
        if not self.page_texts:
            self._load_page_texts()

        cache_path = paths.EXTRACTED / "all_extracted.json"

        if resume and cache_path.exists():
            log.info("Resuming from cached extraction")
            return

        extracted = {"invoices": [], "pos": [], "bank_statements": [],
                     "expense_reports": [], "credit_debit_notes": []}

        skip_types = {DocType.FILLER, DocType.UNKNOWN, DocType.TERMS_CONDITIONS,
                      DocType.VENDOR_MASTER, DocType.DELIVERY_NOTE}
        text_ok = 0
        llm_ok = 0
        llm_fail = 0

        for doc in self.documents:
            doc_type_str = doc.get("doc_type", "unknown")
            try:
                doc_type = DocType(doc_type_str)
            except ValueError:
                continue

            if doc_type in skip_types:
                continue

            # Combine text for this document's page range
            page_start = doc.get("page_start", 0)
            page_end = doc.get("page_end", 0)
            doc_text = "\n".join(
                self.page_texts.get(p, "") for p in range(page_start, page_end + 1)
            )
            source_pages = list(range(page_start, page_end + 1))
            doc_id = doc.get("doc_id", "")

            # --- Try regex extraction first ---
            result = None
            try:
                result = extract_from_text(doc_text, doc_type, source_pages, doc_id)
            except Exception as e:
                log.debug(f"Text extraction failed for {doc_id}: {e}")

            if result is not None:
                text_ok += 1
            else:
                # --- Fallback to LLM ---
                try:
                    if self.bedrock is None:
                        self.bedrock = BedrockClient()
                    result = extract_with_llm(
                        doc_text, doc_type, self.bedrock,
                        source_pages=source_pages, doc_id=doc_id,
                    )
                    if result:
                        llm_ok += 1
                    else:
                        llm_fail += 1
                except Exception as e:
                    log.error(f"LLM extraction failed for {doc_id}: {e}")
                    llm_fail += 1

            if result is None:
                continue

            # Store result
            try:
                record = result.model_dump(mode="json")
                if doc_type == DocType.INVOICE:
                    extracted["invoices"].append(record)
                elif doc_type == DocType.PURCHASE_ORDER:
                    extracted["pos"].append(record)
                elif doc_type == DocType.BANK_STATEMENT:
                    extracted["bank_statements"].append(record)
                elif doc_type == DocType.EXPENSE_REPORT:
                    extracted["expense_reports"].append(record)
                elif doc_type in (DocType.CREDIT_NOTE, DocType.DEBIT_NOTE):
                    extracted["credit_debit_notes"].append(record)
            except Exception as e:
                log.error(f"Model serialization failed for {doc_id}: {e}")

        cache_path.write_text(json.dumps(extracted, indent=2, default=str))
        total = sum(len(v) for v in extracted.values())
        log.info(f"Stage 4 complete: {total} entities (text={text_ok}, llm={llm_ok}, failed={llm_fail})")

    def _stage_5_index(self):
        """Stage 5: Build indexes (DuckDB + Graph)."""
        log.info("=== STAGE 5: INDEX ===")
        if not self.page_texts:
            self._load_page_texts()

        # Load extracted data
        extracted_path = paths.EXTRACTED / "all_extracted.json"
        if not extracted_path.exists():
            log.error("No extracted data found. Run stage 4 first.")
            return

        extracted = json.loads(extracted_path.read_text())

        # Init stores
        self.store = DuckDBStore()
        self.graph = GraphStore()

        # Load pages
        for page_num, text in self.page_texts.items():
            self.store.insert_page(int(page_num), text)

        # Load documents
        if not self.documents:
            self._load_documents()
        for doc in self.documents:
            self.store.insert_document(doc)

        # Load vendors
        if not self.vendors:
            self._load_vendors()
        for v in self.vendors:
            self.store.insert_vendor(v)
            self.graph.add_vendor(v.vendor_id, name=v.canonical_name)

        # Load invoices
        from ..core.models import InvoiceRecord, LineItem
        for inv_data in extracted.get("invoices", []):
            try:
                items = [LineItem(**li) for li in inv_data.get("line_items", [])]
                inv = InvoiceRecord(**{**inv_data, "line_items": items})
                self.store.insert_invoice(inv)
                self.graph.add_invoice(inv.invoice_number, source_pages=inv.source_pages)
                if inv.po_number:
                    self.graph.link(inv.invoice_number, inv.po_number, "references_po")
                if inv.vendor_id:
                    self.graph.link(inv.vendor_id, inv.invoice_number, "issued_invoice")
            except Exception as e:
                log.debug(f"Failed to index invoice: {e}")

        # Load POs
        from ..core.models import PurchaseOrderRecord
        for po_data in extracted.get("pos", []):
            try:
                items = [LineItem(**li) for li in po_data.get("line_items", [])]
                po = PurchaseOrderRecord(**{**po_data, "line_items": items})
                self.store.insert_po(po)
                self.graph.add_po(po.po_number, source_pages=po.source_pages)
                if po.vendor_id:
                    self.graph.link(po.vendor_id, po.po_number, "has_po")
            except Exception as e:
                log.debug(f"Failed to index PO: {e}")

        # Load bank statements
        from ..core.models import BankStatement, BankStatementTxn
        for bs_data in extracted.get("bank_statements", []):
            try:
                txns = [BankStatementTxn(**t) for t in bs_data.get("transactions", [])]
                bs = BankStatement(**{**bs_data, "transactions": txns})
                self.store.insert_bank_statement(bs)
            except Exception as e:
                log.debug(f"Failed to index bank statement: {e}")

        # Load expense reports
        from ..core.models import ExpenseReportRecord, ExpenseLine
        for er_data in extracted.get("expense_reports", []):
            try:
                lines = [ExpenseLine(**el) for el in er_data.get("expense_lines", [])]
                er = ExpenseReportRecord(**{**er_data, "expense_lines": lines})
                self.store.insert_expense_report(er)
                self.graph.add_expense_report(er.report_id, source_pages=er.source_pages)
            except Exception as e:
                log.debug(f"Failed to index expense report: {e}")

        # Load credit/debit notes
        from ..core.models import CreditDebitNoteRecord
        for note_data in extracted.get("credit_debit_notes", []):
            try:
                note = CreditDebitNoteRecord(**note_data)
                self.store.insert_credit_debit_note(note)
                if note.note_type == "credit":
                    self.graph.add_credit_note(note.note_number, source_pages=note.source_pages)
                else:
                    self.graph.add_debit_note(note.note_number, source_pages=note.source_pages)
                if note.referenced_doc:
                    self.graph.link(note.note_number, note.referenced_doc, "references")
                if note.target_doc:
                    self.graph.link(note.note_number, note.target_doc, "targets")
            except Exception as e:
                log.debug(f"Failed to index note: {e}")

        self.graph.save()
        log.info("Stage 5 complete: indexes built")

    def _stage_6_detect(self, only_category: str = None):
        """Stage 6: Run all detectors."""
        log.info("=== STAGE 6: DETECT ===")
        if not self.store:
            self.store = DuckDBStore()
        if not self.graph:
            self.graph = GraphStore()
            graph_path = paths.INDEXES / "doc_graph.json"
            if graph_path.exists():
                self.graph.load()
        if not self.vendors:
            self._load_vendors()

        detectors = _get_all_detectors()
        self.all_candidates = []

        for detector in detectors:
            if only_category and detector.category.value != only_category:
                continue
            try:
                candidates = detector.detect(
                    store=self.store,
                    graph=self.graph,
                    vendors=self.vendors,
                )
                self.all_candidates.extend(candidates)
                log.info(f"  {detector.name}: {len(candidates)} candidates")
            except Exception as e:
                log.error(f"Detector {detector.name} failed: {e}")

        log.info(f"Stage 6 complete: {len(self.all_candidates)} total candidates")

    def _stage_6_detect_agents(self, only_category: str = None):
        """Stage 6 (Agent mode): Run LangGraph multi-agent detection pipeline."""
        log.info("=== STAGE 6: DETECT (AGENT MODE) ===")

        # Load extracted data as raw dicts (agents expect raw JSON dicts)
        extracted_path = paths.EXTRACTED / "all_extracted.json"
        if not extracted_path.exists():
            log.error("No extracted data found. Run stage 4 first.")
            return

        extracted = json.loads(extracted_path.read_text())
        invoices = extracted.get("invoices", [])
        pos = extracted.get("pos", [])
        bank_stmts = extracted.get("bank_statements", [])
        expense_reports = extracted.get("expense_reports", [])
        credit_debit_notes = extracted.get("credit_debit_notes", [])

        # Load vendors
        vendor_path = paths.EXTRACTED / "vendor_master.json"
        vendors = []
        if vendor_path.exists():
            vendors = json.loads(vendor_path.read_text())

        log.info(f"  Data: {len(invoices)} invoices, {len(pos)} POs, "
                 f"{len(bank_stmts)} bank stmts, {len(expense_reports)} expense reports, "
                 f"{len(credit_debit_notes)} credit/debit notes, {len(vendors)} vendors")

        # Run the LangGraph agent orchestrator
        from ..agents.orchestrator import run_pipeline as agent_run_pipeline

        submission = agent_run_pipeline(
            invoices=invoices,
            pos=pos,
            bank_stmts=bank_stmts,
            expense_reports=expense_reports,
            credit_debit_notes=credit_debit_notes,
            vendors=vendors,
        )

        # Convert agent findings to FindingCandidate objects for stage 7
        agent_findings = submission.get("findings", [])
        self.all_candidates = []
        for f in agent_findings:
            if only_category and f.get("category") != only_category:
                continue
            candidate = FindingCandidate(
                finding_id=f.get("finding_id", ""),
                category=f.get("category", ""),
                pages=f.get("pages", []),
                document_refs=f.get("document_refs", []),
                description=f.get("description", ""),
                reported_value=str(f.get("reported_value", "")),
                correct_value=str(f.get("correct_value", "")),
                confidence=float(f.get("confidence", 0.85)),
                detector_name=f"agent:{f.get('category', '')}",
                status="candidate",
            )
            self.all_candidates.append(candidate)

        log.info(f"Stage 6 (agents) complete: {len(self.all_candidates)} total candidates")

    def _stage_7_finalize(self):
        """Stage 7: Adjudicate, filter, and write outputs."""
        log.info("=== STAGE 7: FINALIZE ===")

        accepted, rejected = finalize_findings(self.all_candidates)

        # Write all outputs
        write_submission(self.team_id, accepted)
        write_all_candidates(self.all_candidates)
        write_rejected(rejected)
        write_findings_csv(accepted)

        try:
            write_analytics(accepted, rejected)
        except Exception as e:
            log.warning(f"Analytics write failed: {e}")

        log.info(f"Stage 7 complete: {len(accepted)} findings in submission.json")

    # Helper loaders
    def _load_page_texts(self):
        path = paths.PARSED / "page_texts.json"
        if path.exists():
            data = json.loads(path.read_text())
            self.page_texts = {int(k): v for k, v in data.items()}
        else:
            self._stage_1_ingest()

    def _load_documents(self):
        path = paths.SPLIT_DOCS / "document_splits.json"
        if path.exists():
            self.documents = json.loads(path.read_text())
        else:
            self._stage_2_split()

    def _load_vendors(self):
        path = paths.EXTRACTED / "vendor_master.json"
        if path.exists():
            from ..core.models import VendorRecord
            data = json.loads(path.read_text())
            self.vendors = [VendorRecord(**v) for v in data]
