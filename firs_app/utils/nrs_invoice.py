

import frappe
import requests
from frappe import _
from frappe.utils import now_datetime, add_to_date, nowdate

VALIDATE_IRN = "/api/v1/invoice/irn/validate"
VALIDATE_INVOICE_DATA = "/api/v1/invoice/validate"
SIGN_INVOICE_SCHEMA = "/api/v1/invoice/sign"
AUTH_PATH = "/api/v1/utilities/authenticate"
UPDATE_EINVOICE = "/api/v1/invoice/update"
DOWNLOAD_INVOICE = "/api/v1/invoice/download"
CONFIRM_INVOICE = "/api/v1/invoice/confirm"
SEARCH_INVOICE = "/api/v1/invoice"
LOOKUP_INVOICE = "/api/v1/invoice/transmit/lookup"
TRANSMIT_INVOICE = "/api/v1/invoice/transmit"
REQUEST_TIMEOUT = 15 # seconds 
RETRY_COUNT = 2 
RETRY_DELAY = 2 # seconds

_SETTINGS_DOCTYPE = "Nigeria Compliance Settings"
_MAX_RETRIES = 3
_TIMEOUT_SHORT = 30
_TIMEOUT_LONG = 60

# ── Settings helpers ──────────────────────────────────────────────────────────

def _get_settings():
    return frappe.get_cached_doc(_SETTINGS_DOCTYPE)

def _base_url(settings) -> str:
    
    return (settings.einvoice_sandbox_url or "https://eivc-k6z6d.ondigitalocean.app").rstrip("/")

# def _build_headers(api_key: str, secret_key: str) -> Dict[str, str]:
def _headers(settings) -> dict:
    """
    Auth is permanent API key + secret headers — no token fetch, no Bearer token.
    Every request carries x-api-key and x-api-secret.
    """
    return {
        "x-api-key": settings.get_password("einvoice_api_key"),
        "x-api-secret": settings.get_password("einvoice_api_secret"),
        "Content-Type": "application/json",
    }

# ── IRN generation ─────────────────────────────────────────────────────────────
# def get_irn_unix_timestamp(pdate):

def generate_irn(invoice_name: str, settings=None) -> str:
    """
    FIRS IRN template: {InvoiceNumber}-{ServiceID}-{YYYYMMDD}

    Note:
      InvoiceNumber — alphanumeric only (stripped all hyphens and slashes)

    Example: INV251200001-15KJ72IS-20251227
    """
    if settings is None:
        settings = _get_settings()

    service_id = (settings.einvoice_service_id or "").strip()
    if not service_id:
        frappe.throw(_("NRS Service ID is not configured in Nigeria Compliance Settings. "
                       "Set the 8-character Service ID from your NRS dashboard."))

    # Strip all non-alphanumeric characters — NRS rejects hyphens, slashes, spaces
    import re
    invoice_number = re.sub(r"[^A-Za-z0-9]", "", invoice_name)
    # Use the invoice's posting date — not today — so backdated invoices have matching IRNs
    posting_date = frappe.db.get_value("Sales Invoice", invoice_name, "posting_date")
    date_str = str(posting_date).replace("-", "") if posting_date else now_datetime().strftime("%Y%m%d")
    return f"{invoice_number}-{service_id}-{date_str}"

# ── Payload builder ────────────────────────────────────────────────────────────

def build_invoice_payload(sales_invoice: str, irn: str) -> dict[str, Any]:
    """
    Build UBL BIS Billing 3.0 JSON payload for POST => /validate
    and POST=> /sign
    """
    doc = frappe.get_doc("Sales Invoice", sales_invoice)
    settings = _get_settings()

    # _payment_code

    # ── Business IDs ────────────────────────────────────────────────────────
    business_id = (
        frappe.db.get_value("Company", doc.company, "custom_business_id")
        or settings.get("business_id")
        or ""
    )
    seller_tin = (
        frappe.db.get_value("Company", doc.company, "custom_tin")
        or settings.tin
        or ""
    )
    buyer_tin = frappe.db.get_value("Customer", doc.customer, "custom_tin") or ""
    if not buyer_tin:
        rc_number = frappe.db.get_value("Customer", doc.customer, "custom_rc_number") or ""
        if rc_number:
            buyer_tin = f"RN-{rc_number}"

    # ── Invoice type ─────────────────────────────────────────────────────────
    is_return = bool(doc.get("is_return"))
    is_debit_note = bool(doc.get("is_debit_note"))
    invoice_type_code = "381" #get_invoice_type_code("Sales Invoice", is_return, is_debit_note)

    # ── Invoice kind (B2C / B2B / B2G) ───────────────────────────────────────
    # Explicit flag on Customer takes precedence; fall back to TIN presence.
    customer_kind = frappe.db.get_value("Customer", doc.customer, "custom_invoice_kind") or ""
    if customer_kind in ("B2B", "B2C", "B2G"):
        invoice_kind = customer_kind
    elif buyer_tin:
        invoice_kind = "B2B"
    else:
        invoice_kind = "B2C"

    # ── Billing reference (credit notes / debit notes) ────────────────────────
    # Link back to the original invoice's IRN so NRS can reverse its VAT entry.
    billing_reference = None
    if is_return or is_debit_note:
        original_invoice = doc.get("return_against") or doc.get("amended_from") or ""
        if original_invoice:
            original_irn, original_date = frappe.db.get_value(
                "Sales Invoice", original_invoice, ["custom_irn", "posting_date"]
            ) or ("", "")
            if original_irn:
                billing_reference = [{"irn": original_irn, "issue_date": str(original_date)}]

    # ── Addresses ─────────────────────────────────────────────────────────────
    company_fields = frappe.db.get_value(
        "Company", doc.company,
        ["custom_address", "custom_city", "custom_postal_code", "custom_state", "custom_lga",
         "email", "phone_no", "company_description"],
        as_dict=True,
    ) or {}
    seller_address = _build_postal_address(
        company_fields.get("custom_address") or "",
        company_fields.get("custom_city") or "",
        company_fields.get("custom_postal_code") or "",
        "NG",
        state=company_fields.get("custom_state") or "",
        lga=company_fields.get("custom_lga") or "",
    )
    customer_fields = frappe.db.get_value(
        "Customer", doc.customer,
        ["custom_state", "custom_lga"],
        as_dict=True,
    ) or {}
    # Resolve the linked Address document to get the actual street text
    customer_address_name = doc.get("customer_address") or ""
    addr_street, addr_city, addr_postal = "", "", ""
    if customer_address_name:
        addr = frappe.db.get_value(
            "Address", customer_address_name,
            ["address_line1", "city", "pincode"],
            as_dict=True,
        ) or {}
        addr_street = addr.get("address_line1") or ""
        addr_city = addr.get("city") or ""
        addr_postal = addr.get("pincode") or ""
    buyer_address = _build_postal_address(
        addr_street,
        addr_city,
        addr_postal,
        "NG",
        state=customer_fields.get("custom_state") or "",
        lga=customer_fields.get("custom_lga") or "",
    )

    # ── Tax — read actual ERPNext tax lines, fall back to settings default ────
    vat_rate = float(settings.einvoice_default_vat_rate or 7.5)
    tax_subtotals, total_vat = _build_tax_subtotals(doc, vat_rate)

    # ── Payment means ─────────────────────────────────────────────────────────
    #payment_mode = doc.get("custom_payment_means") or doc.get("mode_of_payment") or ""
    payment_means_code = "97" #get_payment_means_code(payment_mode)
    due_date = str(doc.due_date) if doc.get("due_date") else str(doc.posting_date)

    # ── Line items ────────────────────────────────────────────────────────────
    invoice_lines = []
    total_line_extension = 0.0

    # Batch-fetch all item NRS fields to avoid N+1 queries
    item_codes = [row.item_code for row in doc.items]
    item_fields_map: dict[str, dict] = {}
    if item_codes:
        for item_row in frappe.get_all(
            "Item", filters={"name": ("in", item_codes)},
            fields=["name", "custom_hs_code", "custom_service_code"],
        ):
            item_fields_map[item_row.name] = item_row

    for row in doc.items:
        net = float(row.net_amount)
        total_line_extension += net

        item_f = item_fields_map.get(row.item_code, {})
        hs_code = (item_f.get("custom_hs_code") or "").strip()
        service_code = (item_f.get("custom_service_code") or "").strip()
        quantity_code = "EA"

        line = {
            "invoiced_quantity": float(row.qty),
            "line_extension_amount": net,
            "item": {
                "name": row.item_name or row.item_code,
                "description": row.description or row.item_name or "",
                "sellers_item_identification": row.item_code,
            },
            "price": {
                "price_amount": float(row.rate),
                "base_quantity": 1,
                "price_unit": quantity_code,
            },
        }
        # NRS line classification (per NRS Support): GOODS use hsn_code +
        # product_category; SERVICES use isic_code + service_category. The two
        # pairs are mutually exclusive on a line. The "category" is the code's
        # description. before_submit_ng guarantees one code is present.
        if hs_code:
            line["hsn_code"] = hs_code
            line["product_category"] = (
                frappe.db.get_value("Nigeria HS Code", hs_code, "description")
                or row.item_group or "General"
            )
        elif service_code:
            line["isic_code"] = service_code
            line["service_category"] = (
                frappe.db.get_value("Nigeria Service Code", service_code, "description")
                or row.item_group or "General"
            )
        else:
            # Unclassified — before_submit_ng should have blocked this; emit an
            # empty hsn_code so NRS returns a clear, actionable rejection.
            line["hsn_code"] = ""
            line["product_category"] = row.item_group or "General"

        invoice_lines.append(line)

    tax_exclusive = round(float(doc.net_total), 2)
    tax_inclusive = round(float(doc.grand_total), 2)
    payable_amount = round(float(doc.outstanding_amount or doc.grand_total), 2)

    # ── Allowance / charge (invoice-level discount) ───────────────────────────
    allowance_charges = []
    if float(doc.get("additional_discount_amount") or 0) > 0:
        allowance_charges.append({
            "charge_indicator": False,
            "amount": round(float(doc.additional_discount_amount), 2),
        })

    payload: dict[str, Any] = {
        # ── Invoice header ──────────────────────────────────────────────────
        "business_id": business_id,
        "irn": irn,
        "issue_date": str(doc.posting_date),
        "due_date": due_date,
        "issue_time": now_datetime().strftime("%H:%M:%S"),
        "invoice_type_code": invoice_type_code,
        "invoice_kind": invoice_kind,
        "integrator_service_id": settings.einvoice_integrator_service_id or "00000",
        "payment_status": "PENDING",
        "document_currency_code": doc.currency or "NGN",
        "tax_currency_code": "NGN",

        # ── Buyer reference / order reference ─────────────────────────────
        **({"buyer_reference": doc.po_no} if doc.get("po_no") else {}),
        **({"order_reference": doc.po_no} if doc.get("po_no") else {}),

        # ── Note (invoice remarks) ────────────────────────────────────────
        **({"note": doc.terms[:500]} if doc.get("terms") else {}),

        # ── Billing reference (credit notes / debit notes) ────────────────
        **({"billing_reference": billing_reference} if billing_reference else {}),

        # ── Supplier ────────────────────────────────────────────────────────
        "accounting_supplier_party": {
            "party_name": doc.company,
            "tin": seller_tin,
            "email": company_fields.get("email") or "",
            "telephone": company_fields.get("phone_no") or "",
            "business_description": company_fields.get("company_description") or "",
            "postal_address": seller_address,
        },

        # ── Customer ─────────────────────────────────────────────────────────
        "accounting_customer_party": {
            "party_name": doc.customer_name,
            "tin": buyer_tin,
            "email": frappe.db.get_value("Customer", doc.customer, "email_id") or "",
            "telephone": frappe.db.get_value("Customer", doc.customer, "mobile_no") or "",
            "postal_address": buyer_address,
        },

        # ── Payment ──────────────────────────────────────────────────────────
        "payment_means": [
            {
                "payment_means_code": payment_means_code,
                "payment_due_date": due_date,
            }
        ],
        "payment_terms_note": doc.payment_terms_template or "",

        # ── Allowances (invoice-level discounts) ──────────────────────────
        **({"allowance_charge": allowance_charges} if allowance_charges else {}),

        # ── Tax ──────────────────────────────────────────────────────────────
        "tax_total": [
            {
                "tax_amount": total_vat,
                "tax_subtotal": tax_subtotals,
            }
        ],

        # ── Totals ────────────────────────────────────────────────────────────
        "legal_monetary_total": {
            "line_extension_amount": round(total_line_extension, 2),
            "tax_exclusive_amount": tax_exclusive,
            "tax_inclusive_amount": tax_inclusive,
            "payable_amount": payable_amount,
        },

        # ── Lines ─────────────────────────────────────────────────────────────
        "invoice_line": invoice_lines,
    }
    return payload

def _build_tax_subtotals(doc, default_vat_rate: float) -> tuple[list[dict], float]:
    """
    Get TaxTotal subtotals
    """
    from nigeria_compliance.nigeria_compliance.constants.tax_categories import get_tax_category_code

    merged: dict[str, dict] = {}  # category_code → subtotal dict

    for tax_row in (doc.taxes or []):
        amount = float(tax_row.tax_amount or 0)
        if amount == 0:
            continue
        rate = float(tax_row.rate or 0)
        category = "STANDARD_VAT" #get_tax_category_code(rate)
        if category in merged:
            merged[category]["tax_amount"] = round(merged[category]["tax_amount"] + amount, 2)
        else:
            merged[category] = {
                "taxable_amount": round(float(doc.net_total), 2),
                "tax_amount": round(amount, 2),
                "tax_category": {"id": category, "percent": rate},
            }

    if not merged:
        # No ERPNext tax rows — fall back to configured default
        category ="STANDARD_VAT" #get_tax_category_code(default_vat_rate)
        total_vat = round(float(doc.net_total) * (default_vat_rate / 100), 2)
        return [
            {
                "taxable_amount": round(float(doc.net_total), 2),
                "tax_amount": total_vat,
                "tax_category": {"id": category, "percent": default_vat_rate},
            }
        ], total_vat

    subtotals = list(merged.values())
    total_vat = round(sum(s["tax_amount"] for s in subtotals), 2)
    return subtotals, total_vat

def _build_postal_address(
    street: str, city: str, postal_zone: str, country: str,
    state: str = "", lga: str = "",
) -> dict:
    addr = {
        "street_name": street or "",
        "city_name": city or "",
        "postal_zone": postal_zone or "",
        "country": country or "NG",
    }
    if state:
        addr["state"] = state
    if lga:
        addr["lga"] = lga
    return addr


# ── IRN pre-validation ────────────────────────────────────────────────────────

def validate_irn(irn: str, invoice_reference: str, business_id: str) -> dict[str, Any]:
    """
    POST=> /validate
    Validates that the generated IRN is unique and correctly formatted before submission.
    """
    settings = _get_settings()
    resp = requests.post(
        f"{_base_url(settings)}{VALIDATE_IRN}",
        json={
            "invoice_reference": invoice_reference,
            "business_id": business_id,
            "irn": irn,
        },
        headers=_headers(settings),
        timeout=_TIMEOUT_SHORT,
    )
    if not resp.ok:
        raise EInvoiceError(f"IRN validation failed [{resp.status_code}]: {resp.text}")
    return resp.json() if resp.content else {}

# ── Submission ────────────────────────────────────────────────────────────────

def submit_invoice_enqueued(sales_invoice: str) -> dict:
    """
    """
    settings = _get_settings()
    if not settings.einvoice_enabled:
        return {}

    frappe.enqueue(
        "nigeria_compliance.nigeria_compliance.nrs.einvoice.submit_invoice",
        queue="default",
        timeout=180,
        enqueue_after_commit=True,
        sales_invoice=sales_invoice,
    )
    return {"queued": True}

def submit_invoice(sales_invoice: str) -> dict[str, Any]:
    """
    Submission Process:
      1. Generate IRN
      2. Check invoice schema for error POST=> /validate
      3. Submit valid payload POST=> /sign 
    """
    settings = _get_settings()
    # nrs_enabled or enabled
    if not settings.einvoice_enabled:
        return {}

    einvoice_doc = _get_or_create_einvoice(sales_invoice)
    if einvoice_doc.status == "Cleared":
        return {}

    max_retries = einvoice_doc.max_retries or _MAX_RETRIES
    if (einvoice_doc.retry_count or 0) >= max_retries:
        # Stop auto-retrying and flag red for manual review instead of spinning
        # forever as Auto-Retry.
        _update_einvoice(
            einvoice_doc, {}, {}, "Failed",
            f"Automatic retries exhausted ({max_retries}). Needs manual review — "
            "use the Nigeria → Submit to NRS button to retry.",
            irn=einvoice_doc.irn,
        )
        frappe.log_error(
            f"Max retries reached for Sales Invoice {sales_invoice}",
            "NRS e-Invoice",
        )
        return {}

    # Respect B2B-only setting
    actual_buyer_tin = frappe.db.get_value(
        "Customer",
        frappe.db.get_value("Sales Invoice", sales_invoice, "customer"),
        "custom_tin",
    ) or ""
    if settings.einvoice_b2b_only and not actual_buyer_tin:
        return {}

    business_id = (
        frappe.db.get_value(
            "Company",
            frappe.db.get_value("Sales Invoice", sales_invoice, "company"),
            "ng_nrs_business_id",
        )
        or settings.get("einvoice_business_id")
        or ""
    )

    try:
        # Use existing IRN if already generated (retry scenario)
        irn = einvoice_doc.irn or generate_irn(sales_invoice, settings)

        payload = build_invoice_payload(sales_invoice, irn)

        # Step 1: Validate
        validate_resp = requests.post(
            f"{_base_url(settings)}{VALIDATE_INVOICE_DATA}",
            json=payload,
            headers=_headers(settings),
            timeout=_TIMEOUT_LONG,
        )

        if validate_resp.status_code in (400, 422):
            # NRS returns transient "try again later" errors as 400 too — those must
            # auto-retry, not be marked permanently Failed.
            if _is_transient_nrs_error(validate_resp.text):
                _update_einvoice(einvoice_doc, payload, {}, "Auto-Retry",
                                 f"NRS temporarily unavailable (validate), will retry: {validate_resp.text}",
                                 irn=irn)
                _flag_retry_pending()
                return {}
            _update_einvoice(einvoice_doc, payload, {}, "Failed",
                             f"Validation error: {validate_resp.text}", irn=irn)
            raise EInvoiceValidationError(
                f"NRS validation error [{validate_resp.status_code}]: {validate_resp.text}"
            )

        if not validate_resp.ok:
            _update_einvoice(einvoice_doc, payload, {}, "Auto-Retry",
                             f"Validate step error: {validate_resp.text}", irn=irn)
            _flag_retry_pending()
            return {}

        # Step 2: Sign
        sign_resp = requests.post(
            f"{_base_url(settings)}/{SIGN_INVOICE_SCHEMA}",
            json=payload,
            headers=_headers(settings),
            timeout=_TIMEOUT_LONG,
        )

        if sign_resp.status_code in (400, 422):
            # NRS often returns "unable to complete this operation at this time,
            # kindly try again later" as a 400 during sign — that's transient and
            # must auto-retry, not be marked permanently Failed.
            if _is_transient_nrs_error(sign_resp.text):
                _update_einvoice(einvoice_doc, payload, {}, "Auto-Retry",
                                 f"NRS temporarily unavailable (sign), will retry: {sign_resp.text}",
                                 irn=irn)
                _flag_retry_pending()
                return {}
            _update_einvoice(einvoice_doc, payload, {}, "Failed",
                             f"Sign error: {sign_resp.text}", irn=irn)
            raise EInvoiceValidationError(
                f"NRS sign error [{sign_resp.status_code}]: {sign_resp.text}"
            )

        if not sign_resp.ok:
            _update_einvoice(einvoice_doc, payload, {}, "Auto-Retry",
                             f"Sign step error: {sign_resp.text}", irn=irn)
            _flag_retry_pending()
            return {}

        result = sign_resp.json() if sign_resp.content else {}
        csid = result.get("csid") or result.get("CSID") or ""

        # Use NRS-returned QR if present; fall back to client-side RSA-encrypted QR
        qr_data = result.get("qrCode") or result.get("QRCode") or result.get("qr_code") or ""
        if not qr_data:
            from nigeria_compliance.nigeria_compliance.nrs.signing import generate_invoice_qr_data
            qr_data = generate_invoice_qr_data(irn, settings)

        _update_einvoice(einvoice_doc, payload, result, "Submitted", "", irn=irn, csid=csid, qr_data=qr_data)

        frappe.db.set_value("Sales Invoice", sales_invoice, {
            "ng_nrs_irn": irn,
            "ng_nrs_csid": csid,
            "ng_nrs_status": "Submitted",
        })
        return result

    except (EInvoiceValidationError, EInvoiceError):
        raise
    except Exception as e:
        _update_einvoice(einvoice_doc, {}, {}, "Auto-Retry", str(e))
        _flag_retry_pending()
        frappe.log_error(frappe.get_traceback(), "NRS e-Invoice Submission")

def _get_or_create_einvoice(sales_invoice: str):
    name = frappe.db.get_value("Nigeria E-Invoice", {"sales_invoice": sales_invoice}, "name")
    if name:
        return frappe.get_doc("Nigeria E-Invoice", name)

    inv = frappe.get_doc("Sales Invoice", sales_invoice)
    customer_kind = frappe.db.get_value("Customer", inv.customer, "ng_invoice_kind") or ""
    buyer_tin = frappe.db.get_value("Customer", inv.customer, "ng_tin") or ""
    if customer_kind in ("B2B", "B2C", "B2G"):
        invoice_kind = customer_kind
    elif buyer_tin:
        invoice_kind = "B2B"
    else:
        invoice_kind = "B2C"

    doc = frappe.new_doc("FIRS EInvoice")
    doc.sales_invoice = sales_invoice
    doc.status = "Pending"
    doc.invoice_type = invoice_kind
    doc.invoice_number = sales_invoice
    doc.invoice_date = inv.posting_date
    doc.seller_tin = frappe.db.get_value("Company", inv.company, "custom_tin") or ""
    doc.buyer_tin = frappe.db.get_value("Customer", inv.customer, "custom_tin") or ""
    doc.total_excluding_vat = inv.net_total
    doc.grand_total = inv.grand_total
    doc.max_retries = _MAX_RETRIES
    doc.insert(ignore_permissions=True)
    frappe.db.commit()
    return doc

def _update_einvoice(doc, payload: dict, response: dict, status: str, error: str,
                     irn: str = "", csid: str = "", qr_data: str = ""):
    doc.status = status
    if irn:
        doc.irn = irn
    if csid:
        doc.csid = csid
    doc.payload = json.dumps(payload, indent=2, default=str)
    doc.response = json.dumps(response, indent=2, default=str)
    doc.error_message = error

    if status in ("Failed", "Auto-Retry"):
        doc.retry_count = (doc.retry_count or 0) + 1
        doc.last_retry_at = now_datetime()

    if status == "Submitted":
        doc.submitted_at = now_datetime()
        # Read computed VAT from the payload we sent — NRS sign response does not echo this back
        try:
            doc.vat_amount = (
                payload.get("tax_total", [{}])[0].get("tax_amount")
                or response.get("totalVAT")
                or response.get("total_vat")
                or 0
            )
        except (IndexError, TypeError):
            doc.vat_amount = 0
    if status == "Cleared":
        doc.cleared_at = now_datetime()

    if qr_data:
        _attach_qr_code(doc, qr_data)

    doc.save(ignore_permissions=True)
    frappe.db.commit()
#
def _is_transient_nrs_error(text: str) -> bool:
    """True if an NRS 400/422 response is a transient 'try again later' condition
    rather than a real payload/validation rejection."""
    t = (text or "").lower()
    return any(marker in t for marker in _TRANSIENT_NRS_MARKERS)

def _flag_retry_pending():
    # Do not commit here — caller is responsible for transaction boundaries
    frappe.db.set_value(_SETTINGS_DOCTYPE, _SETTINGS_DOCTYPE, "is_retry_einvoice_pending", 1)

#
# NRS returns transient/server-busy conditions as HTTP 400 with one of these
# phrases. They must be treated as retryable (Auto-Retry), NOT permanent failures.
_TRANSIENT_NRS_MARKERS = (
    "try again later",
    "unable to complete this operation at this time",
    "we are unable to process your request",
    "temporarily unavailable",
    "please try again",
)