import frappe
import time
import base64 
import json
import os 

from cryptography.hazmat.primitives import hashes, serialization 
from cryptography.hazmat.primitives.asymmetric import padding 
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.fernet import Fernet
import qrcode
from io import BytesIO
import requests
from typing import Dict, Any, Optional
from urllib.parse import quote
from frappe.utils import cstr, flt
from collections import defaultdict


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


def firs_work_flow_draft (doc, method):
    firs_settings = frappe.get_doc('FIRS Einvoice Settings')
    # check if needed
    if not firs_settings.enabled: # frappe.db.get_single_value('FIRS Einvoice Settings', 'enabled'):
        return

    # set  IRN & UNIX TIMESTAMP 
    irn_val = f"{revamp_vch_name(doc.name)}-{get_service_id(firs_settings)}-{get_unix_timestamp(doc.posting_date)}"
    doc.db_set("custom_irn_unix_timestamp", irn_val)

    # Generate FIR Encrypted QR Data
    firs_encrypt_qr_data = encrypt_qrcode(irn_val, firs_settings)
    doc.db_set("custom_encrypted_irn_qr", json.dumps(firs_encrypt_qr_data))

    # set FIRs Invoice Schema
    invoice_schema_paylod = build_invoice_schema(doc, firs_settings)
    invoice_schema_paylod["irn"] = irn_val
    doc.db_set("custom_firs_invoice_schema", json.dumps(invoice_schema_paylod, indent=4))

    # Generate  QR Code
    generate_qr_code_path = build_qrcode_generator(doc)
    # call firs validation method ---- package_external_api_put
    # on success call do other stuff notify or create success log. --- POST base_url/api/v1/invoice/validate
    # encrypt_invoce_schema
    firs_encrypt_schema = encrypt_invoce_schema(doc.custom_firs_invoice_schema, firs_settings)

    
    # this has to go into a new different logic downwards
    # check if validation should happened
    if not firs_settings.invoice_update_frequency == 'Per Transaction':
        print(f"===========================================\n  *********Ended Cycle********\n ")
        return
    # wrong way of writing a code logic
    
    print(f"===========================================> \n **********Process*******\n ")
    """ validater_report = validate_firs_invoice_schema(doc,firs_settings, invoice_schema_paylod)
    
    if next(iter(validater_report.values())) :

        print(f"\n ============{next(iter(validater_report.values())) }==========> \n report to : {list(validater_report.values())[3]}")
 """
    #temp fix: --> move to on_submit or after_submit to sign with firs server
    #submit_sign(doc,firs_settings, invoice_schema_paylod)
    
def create_firs_einvoice(doc, method):
     """ Background create new firs_einvoice doc form doc """
     frappe.enqueue(
          "firs_app.utils.firs_invoice.sync_sales_invoice_to_einvoice",
          queue="long",
          doc=doc,
          action="create"
     )


def update_firs_einvoice(doc, method):
     """Updates in background queue when relevant lifecycle changes occur."""
     frappe.enqueue(
          "firs_app.utils.firs_invoice.sync_sales_invoice_to_einvoice",
          queue="long",
          doc=doc,
          action="update"
     )


def sync_sales_invoice_to_einvoice(doc, action="create"):
     """Creates a FIRS invoice record and updates it only for relevant triggers."""
     if not doc or not getattr(doc, "name", None):
          return

     firs_settings = frappe.get_doc('FIRS Einvoice Settings')
     if not firs_settings.enabled:
          return

     if action == "create":
          if frappe.db.exists("firs_einvoice", {"sales_invoice_code": doc.name}):
               return

          irn_val = f"{revamp_vch_name(doc.name)}-{get_service_id(firs_settings)}-{get_unix_timestamp(doc.posting_date)}"
          firs_encrypt_qr_data = encrypt_qrcode(irn_val, firs_settings)

          invoice_schema_paylod = build_invoice_schema(doc, firs_settings)
          invoice_schema_paylod["irn"] = irn_val

          firs_doc = frappe.get_doc({
               "doctype": "FIRS EInvoice",
               "sales_invoice": doc.name,
               "sales_invoice_code": doc.name,
               "irn": irn_val,
               "irn_unix_timestamp": irn_val,
               "encrypted_irn_qr": json.dumps(firs_encrypt_qr_data),
               "firs_invoice_schema": json.dumps(invoice_schema_paylod, indent=4),
               "sales_invoice_status": doc.status,
               "payment_status": doc.status,
               "sync_status": "Pending Validation",
               "last_sync_at": frappe.utils.now(),
               "is_cancelled": 0
          })
          firs_doc.insert(ignore_permissions=True)
          frappe.db.commit()

          build_qrcode_generator(firs_doc)
          return

     if action != "update":
          return

     current_status = (doc.status or "").strip().lower()
     previous_status = ""
     if hasattr(doc, "get_doc_before_save"):
          prev_doc = doc.get_doc_before_save()
          previous_status = (getattr(prev_doc, "status", "") or "").strip().lower()

     firs_name = frappe.db.get_value("firs_einvoice", {"sales_invoice_code": doc.name}, "name")
     if not firs_name:
          return

     firs_doc = frappe.get_doc("firs_einvoice", firs_name)
     firs_doc.sales_invoice = doc.name
     firs_doc.sales_invoice_status = doc.status
     firs_doc.payment_status = doc.status

     # Trigger only when invoice is cancelled or moves to Paid from any other state.
     is_cancelled = doc.docstatus == 2
     is_paid_transition = current_status == "paid" and previous_status != "paid"

     if not (is_cancelled or is_paid_transition):
          return

     firs_doc.sync_status = "Pending Update"
     firs_doc.is_cancelled = 1 if is_cancelled else 0
     firs_doc.response_log = json.dumps({
          "trigger": "sales_invoice_cancelled" if is_cancelled else "status_changed_to_paid",
          "previous_status": previous_status,
          "current_status": current_status,
          "saved_at": frappe.utils.now()
     }, indent=4)

     firs_doc.save(ignore_permissions=True)
     frappe.db.commit()



def get_unix_timestamp(pdate):
    uxtime = int(time.time())
    pdate = pdate.replace("-", "")
    result = f"{pdate}"  # f"{pdate}.{str(uxtime)}" #
    #print(f"\n\n ========unix date & timestamp ===========> {result}")
    return result

def revamp_vch_name(si):
     si = si.replace("-", "")
     result = f"{si}"
     return result

def get_service_id(settings):
    firs_service_id = settings.service_id
    return firs_service_id

def encrypt_qrcode(irn,settings):
    # load the public key
    cert = settings.certificate
    pem_public_key = settings.public_key_decoded
    #public_key = serialization.load_pem_public_key(pem_public_key.encode("utf-8"))

    payload = {
        "irn": irn,
        "certificate": cert
    }
    # Serialize to json and encrypt
    payload_bytes = json.dumps(payload, separators=(",", ":")).encode("utf-8")
    public_key = serialization.load_pem_public_key(pem_public_key.encode("utf-8"))
    encrypted = public_key.encrypt(
        payload_bytes,
        padding.PKCS1v15()
    )
    # Next convert encrypted data to Base64
    encrypted_base64 = base64.b64encode(encrypted).decode("utf-8")
    #print(f"\n\n plain: ====================> {encrypted}")

    return encrypted_base64

def process_einvoice_job():
     """Main loop executing via Frappe scheduler."""
     pending_validation = frappe.get_all(
          "FIRS EInvoice",
          filters={"sync_status": "Pending Validation"},
          pluck="name"
     )
     for firs_name in pending_validation:
          execute_validation_and_sign(frappe.get_doc("FIRS EInvoice", firs_name))

     pending_updates = frappe.get_all(
          "FIRS EInvoice",
          filters={"sync_status": "Pending Update"},
          pluck="name"
     )
     for firs_name in pending_updates:
          execute_einvoice_patch_update(frappe.get_doc("FIRS EInvoice", firs_name))

def encrypt_invoce_schema(data, settings):
    
    # load invoice data
    invoice_payload_bytes = json.dumps(data, separators=(",", ":")).encode("utf-8")
    public_key = serialization.load_pem_public_key(settings.public_key_decoded.encode("utf-8"))
    """ encrypted = public_key.encrypt(
        invoice_payload_bytes,
        padding.PKCS1v15()
    ) """
    # hybrid AES-GCM + RSA 
    aes_key = os.urandom(32)
    nonce = os.urandom(12)
    aesgcm = AESGCM(aes_key)
    ciphertext = aesgcm.encrypt(nonce, invoice_payload_bytes, None)
    encrypted_key = public_key.encrypt(aes_key, padding.PKCS1v15())
    #out = { "method":"hybrid_aes_gcm", "encrypted_key": base64.b64encode(encrypted_key).decode(), "nonce": base64.b64encode(nonce).decode(), "ciphertext": base64.b64encode(ciphertext).decode() }
    out = {
        "method":"hybrid_aes_gcm",
        "encrypted_key": base64.b64encode(encrypted_key).decode(),
        "nonce": base64.b64encode(nonce).decode(),
        "ciphertext": base64.b64encode(ciphertext).decode()
    }
    
    #invoice_encrypted_base64 = base64.b64encode(encrypted).decode("utf-8")
    return out

def build_invoice_schema(doc, settings):
    """
    Map Sales Invoice doc fields to the vch_payload structure.
    Adjust field names below to match your custom fields.
    """
    # Supplier mapping (company-level or custom fields)
    # supplier address
    # frappe.db.exists("Firs Currency", {"currency_code": code}, ["name"], as_dict=True)
    #supplier_address = frappe.get_doc(doctype='Address', filters={"is_your_company_address":1, "address_type": "Office"})
    
    supplier_address = frappe.db.get_value("Address", filters={"is_your_company_address":1}, 
                                           fieldname=["address_line1", "city", "pincode", "custom_country_name"], 
                                           as_dict=True
                                           )

    supplier = {
        "party_name": settings.business_information  or "",
        "tin": settings.tax_id or "",
        "email": settings.email or "",
        "telephone": settings.phone_details or "",
        "business_description": settings.business_description or "",
        "postal_address": {
            "street_name": supplier_address.address_line1 or "",
            "city_name": supplier_address.city or "",
            "postal_zone": supplier_address.pincode or "",
            "country": supplier_address.custom_country_name or ""
        }
    }

    # Customer mapping
    # customer
    val_customer = frappe.get_doc('Customer', doc.get("customer"))
    customer_address = frappe.db.get_value("Address", filters={"name":val_customer.customer_primary_address},
                                           fieldname=["address_line1", "city", "pincode", "custom_country_name"],
                                           as_dict=True)
    #print(f"\n =============> \n address : {customer_address} \n")
    customer = {
        "party_name": doc.get("customer_name") or doc.get("customer") or "",
        "tin": val_customer.tax_id or "",
        "email": val_customer.custom_email or "",
        "telephone": val_customer.custom_phone or "",
        "business_description": val_customer.custom_business_description or "This entity is a sub saller of CBM",
        "postal_address": {
            "street_name": customer_address.address_line1 or "",
            "city_name": customer_address.city or "",
            "postal_zone": customer_address.pincode or "",
            "country": customer_address.custom_country_name or ""
        }
    }

    # invoice_line from items table
    invoice_lines = []
    for item in doc.get("items") or []:
        # load the specific item
        # myitem = item.get("item_name") 
        # print(f"get item : {myitem}")
        itm = frappe.get_doc('Item', item.get("item_code"))
        invoice_lines.append({
            "hsn_code": itm.get("custom_hs_code") if itm.custom_firs_item_type == f"Product" else itm.get("custom_firs_service_code"),
            "product_category": itm.get("custom_hs_product_description") or  "",
            "discount_rate": item.get("discount_percentage") or 0.0,
            "discount_amount": item.get("discount_amount") or 0.0,
            "fee_rate": item.get("fee_rate") or 0.0,
            "fee_amount": item.get("fee_amount") or 0.0,
            "invoiced_quantity": item.get("qty") or 0,
            "line_extension_amount": item.get("amount") or 0.0,
            "item": {
                "name": item.get("item_name") or "",
                "description": item.get("description") or "",
                "sellers_item_identification": item.get("item_code") or ""
            },
            "price": {
                "price_amount": item.get("rate") or 0.0,
                "base_quantity": item.get("qty") or 1,
                "price_unit": f"{doc.get('currency') or 'NGN'} per 1"
            }
        })

    # tax_total and legal_monetary_total mapping
    # frm.doc.taxes[0].item_wise_tax_detail
    # printtaxsection = get_tax_details(doc.get("taxes"), doc.get("taxes")) #get_invoice_summary(doc.get("items"), doc.get("taxes"))
    tax_itemised = get_itemised_tax_breakup(doc)
    tax_groups = {} #defaultdict(lambda: {'taxable_amount': 0.0, 'tax_amount': 0.0})
    #tax_total = []
    for entry  in tax_itemised:
        taxable = entry.get('taxable_amount', 0.0)
        for k, v in entry.items():
            if k not in ('item', 'taxable_amount'):
                if k not in tax_groups:
                    tax_groups[k] = {'taxable_amount': 0.0, 'tax_amount': 0.0, 'percent': v.get('tax_rate')}
                tax_groups[k]['taxable_amount'] += taxable
                tax_groups[k]['tax_amount'] += v.get('tax_amount', 0.0)
    
    #for k, v in entry.items():
    # Convert to list of tax_total entries 
    tax_total = []
    for tax_key, vals in tax_groups.items():
        tax_total.append({
            'tax_amount': round(vals['tax_amount'], 2),
            'tax_subtotal': [{
                'taxable_amount': round(vals['taxable_amount'], 2),
                'tax_amount': round(vals['tax_amount'], 2),
                'tax_category': {
                    'id': remove_last_part(tax_key),
                    'percent':  round(vals['percent'], 1)
                }
            }]
        })
    



    """ tax_total.append({
                    "tax_amount": doc.get("total_taxes_and_charges") or doc.get("tax_amount") or 0.0,
                    "tax_subtotal": [{
                        "taxable_amount": taxised.get("taxable_amount") or 0.0,
                        "tax_amount": v.get("tax_amount") or 0.0,
                        "tax_category": {
                            "id": "STANDARD_VAT",
                            "percent": v.get("tax_rate") or 7.5
                        }
                    }]
                }) """

    legal_monetary_total = {
        "line_extension_amount": doc.get("rounded_total") or doc.get("net_total") or 0.0,
        "tax_exclusive_amount": doc.get("net_total") or 0.0,
        "tax_inclusive_amount": doc.get("grand_total") or 0.0,
        "payable_amount": doc.get("outstanding_amount") or doc.get("grand_total") or 0.0
    }

    # Build final payload
    vch_payload = {
        "business_id": settings.business_id or "",
        "irn": doc.get("irn") or "",
        "issue_date": (doc.get("posting_date")) if doc.get("posting_date") else doc.get("issue_date") or "",
        "due_date": (doc.get("posting_date")) if doc.get("posting_date") else doc.get("issue_date") or "",
        "invoice_type_code": doc.get("invoice_type_code") or "381",
        "document_currency_code": doc.get("currency") or "NGN",
        "tax_currency_code": doc.get("currency") or "NGN",
        "accounting_supplier_party": supplier,
        "accounting_customer_party": customer,
        "tax_total": tax_total,
        "legal_monetary_total": legal_monetary_total,
        "invoice_line": build_invoice_payload(doc)
        
    }
    # "invoice_line": invoice_lines
    if doc.get("status") == "Paid":
         vch_payload["payment_status"] = "PAID"

    return vch_payload

def  remove_last_part(value):
    return value.rsplit("-", 1)[0].strip()

def get_tax_details(itemx, taxex):

    summary_data = frappe._dict()
    # print(f"\n==> frappe declaration :{summary_data}")
    for tax in taxex: 
        # include only VAT charges.
        if tax.charge_type == "Actual":
            continue

        ## Charges to appear as items in the e-invoice.
        if tax.charge_type in ["On Previous Row Total", "On Previous Row Amount"]:
            print(f"\n==> if charges ")
            reference_row = next((row for row in taxex if row.idx == int(tax.row_id or 0)), None)
        

        # check item tax rates if tax rate is zero
        if tax.rate == 0:
            print(f"\n==> item tax rate is zero")
            for item in itemx:
                item_tax_rate = item.item_tax_rate
                if isinstance(item.item_tax_rate, str):
                    item_tax_rate = json.loads(item.item_tax_rate)
                if item_tax_rate and tax.account_head in item_tax_rate:
                    key = cstr (item_tax_rate[tax.account_head])
                    if key not in summary_data:
                        summary_data.setdefault(
                            key,
							{
								"tax_amount": 0.0,
								"taxable_amount": 0.0,
								"tax_exemption_reason": "",
								"tax_exemption_law": "",
							},
                        )
                    #
                    summary_data[key]["tax_amount"] += item.tax_amount
                    summary_data[key]["taxable_amount"] += item.net_amount
                    if key == "0.0":
                        #
                        summary_data[key]["tax_exemption_reason"] = tax.tax_exemption_reason
                        summary_data[key]["tax_exemption_law"] = tax.tax_exemption_law
            if summary_data.get("0.0") and tax.charge_type in [
                "On Previous Row Total",
                "On Previous Row Amount",
            ]:
                summary_data[key]["taxable_amount"] = tax.total
            if summary_data == {}:
                summary_data.setdefault(
                    "0.0",
					{
						"tax_amount": 0.0,
						"taxable_amount": tax.total,
						"tax_exemption_reason": tax.tax_exemption_reason,
						"tax_exemption_law": tax.tax_exemption_law,
					},
                )
        else:
            # get
            item_wise_tax_detail = json.loads(tax.item_wise_tax_detail)
            for rate_item in [
                tax_item for tax_item in item_wise_tax_detail.items() if tax_item[1][0] == tax.rate
            ]:
                key = cstr(tax.rate)
                if not summary_data.get(key):
                    summary_data.setdefault(key, {"tax_amount": 0.0, "taxable_amount": 0.0})
                    summary_data[key]["tax_amount"] += rate_item[1][1]
                    summary_data[key]["taxable_amount"] += sum(
                        [item.net_amount for item in itemx if item.item_code == rate_item[0]]
                    )
            for item in itemx:
                key = cstr(tax.rate)
                if item.get("charges"):
                    if not summary_data.get(key):
                        summary_data.setdefault(key, {"taxable_amount": 0.0})
                    summary_data[key]["taxable_amount"] += item.taxable_amount
    return summary_data


def build_qrcode_generator(data):
    # if data.custom_qr_code_image or not data.custom_qr_code_image == "" or not data.custom_qr_code_image is None :

    if data.encrypted_irn_qr:
        # custom_encrypted_irn_qr
        # custom_encrypted_qr_data
        existing_file_url = data.encrypted_qr_image
        
        qr = qrcode.QRCode(version=1, box_size=10, border=5)
        qr.add_data(data.encrypted_irn_qr)
        qr.make(fit=True)

        img = qr.make_image(fill_color="black", back_color="white")

        #save image to buffer
        buffered = BytesIO()
        img.save(buffered, format="PNG")

        #Save as file 
        file_name = f"QR_{data.name}.png"
        #print(f"\n\n ===================> {file_name}")

        """ if existing_file_url:
            frappe.db.delete("File", {"file_url": existing_file_url, "attached_to_name": data.name}) """
        
        _file = frappe.get_doc({
            "doctype": "File",
            "file_name": file_name,
            "attached_to_doctype": data.doctype,
            "attached_to_name": data.name,
            "content": buffered.getvalue(),
            "is_private": 0
        })
        _file.save()

        data.db_set("encrypted_qr_image", _file.file_url, update_modified=False)
        #print(f"\n\n ===================> {_file.file_url}")
        return _file.file_url

# validation script
def validate_firs_invoice_schema (firs, payload):
    # get the schema
    #invoice_payload =  self.custom_firs_invoice_schema
    #doc.db_set("custom_firs_invoice_schema", json.dumps(invoice_schema_paylod, indent=4))
    invoice_payload = json.dumps({"invoiceRequest": payload}, indent=4)
    #payload_json = json.dumps(invoice_payload, ensure_ascii=False)

    try: 
        
        # get api
        api_key = firs.api_key or "YOUR_API_KEY"
        secret_key = firs.client_secret or "YOUR_SECRET_KEY"

        # call validation endpoint
        validation_result = call_invoice_validation_api(payload, api_key, secret_key, firs.base_url)

        #save validation
        # a rewiring of this block of code
        #save_validation_result_to_doc(self.name, validation_result, fieldname=self.custom_irn_unix_timestamp)
        #remove below just for report to user
        return validation_result
    except Exception:
        # log and persist error info for troubleshooting
        frappe.log_error(frappe.get_traceback(), "validate_firs_invoice_schema error")
        #custom_valation_data
        #frappe.db.set_value("Firs Syn", self.custom_irn_unix_timestamp, "api_response", json.dumps({"error": "validation_failed"}), update_modified=True)
        #frappe.db.commit()

def _build_headers(api_key: str, secret_key: str) -> Dict[str, str]:
    """Return headers required by the external API.
        """
    return {
        "Content-Type": "application/json",
        "Accept": "application/json",
        "x-api-key": api_key,
        "x-api-secret": secret_key
    }


def _firs_action_context(invoice_name: str):
    """Return the submitted invoice, settings, and IRN for a desk action."""
    invoice = frappe.get_doc("Sales Invoice", invoice_name)
    invoice.check_permission("read")
    if invoice.docstatus != 1:
        frappe.throw("FIRS actions are available only for submitted Sales Invoices.")

    irn = (invoice.custom_irn_unix_timestamp or "").strip()
    if not irn:
        frappe.throw("This Sales Invoice does not have a FIRS IRN.")

    settings = frappe.get_doc("FIRS Einvoice Settings")
    if not settings.enabled:
        frappe.throw("FIRS e-invoicing is disabled.")
    if not settings.base_url:
        frappe.throw("FIRS Base URL is not configured.")

    return invoice, settings, irn


def _firs_action_request(settings, method: str, path: str, params=None, payload=None, accept=None):
    """Call a FIRS action endpoint and normalize JSON or text responses."""
    headers = _build_headers(settings.api_key or "", settings.client_secret or "")
    if accept:
        headers["Accept"] = accept

    try:
        response = requests.request(
            method=method,
            url=settings.base_url.rstrip("/") + path,
            params=params,
            json=payload,
            headers=headers,
            timeout=REQUEST_TIMEOUT
        )
    except requests.RequestException as exc:
        return {
            "success": False,
            "status_code": None,
            "content_type": "",
            "body": None,
            "error": str(exc)
        }
    content_type = response.headers.get("Content-Type", "").split(";", 1)[0].strip()
    try:
        body = response.json() if "json" in content_type else response.text
    except ValueError:
        body = response.text

    return {
        "success": response.ok,
        "status_code": response.status_code,
        "content_type": content_type,
        "body": body,
        "error": None if response.ok else body
    }


@frappe.whitelist()
def validate_irn(invoice_name: str):
    invoice, settings, irn = _firs_action_context(invoice_name)
    return _firs_action_request(
        settings,
        "POST",
        VALIDATE_IRN,
        payload={
            "invoice_reference": invoice.name,
            "business_id": settings.business_id,
            "irn": irn
        }
    )


@frappe.whitelist()
def download_invoice(invoice_name: str):
    _, settings, irn = _firs_action_context(invoice_name)
    result = _firs_action_request(
        settings,
        "GET",
        f"{DOWNLOAD_INVOICE}/{quote(irn, safe='')}",
        accept="application/xml"
    )
    result["filename"] = f"{invoice_name}-{irn}.xml"
    return result


@frappe.whitelist()
def confirm_invoice(invoice_name: str):
    _, settings, irn = _firs_action_context(invoice_name)
    return _firs_action_request(
        settings,
        "GET",
        f"{CONFIRM_INVOICE}/{quote(irn, safe='')}"
    )


@frappe.whitelist()
def search_invoice(invoice_name: str, filters=None):
    _, settings, irn = _firs_action_context(invoice_name)
    if isinstance(filters, str):
        filters = json.loads(filters or "{}")
    filters = filters or {}
    business_id = filters.get("business_id") or settings.business_id
    if not business_id:
        frappe.throw("Business ID is not configured.")

    params = {
        "size": filters.get("size") or 20,
        "page": filters.get("page") or 1,
        "sort_by": filters.get("sort_by") or "created_at",
        "sort_direction_desc": filters.get("sort_direction_desc", True),
        "irn": irn
    }
    optional_filters = (
        "payment_status",
        "invoice_type_code",
        "issue_date",
        "due_date",
        "tax_currency_code",
        "document_currency_code"
    )
    for fieldname in optional_filters:
        if filters.get(fieldname):
            params[fieldname] = filters[fieldname]

    return _firs_action_request(settings, "GET", f"{SEARCH_INVOICE}/{quote(business_id, safe='')}", params=params)


@frappe.whitelist()
def lookup_invoice(invoice_name: str):
    _, settings, irn = _firs_action_context(invoice_name)
    return _firs_action_request(
        settings,
        "GET",
        f"{LOOKUP_INVOICE}/{quote(irn, safe='')}"
    )


@frappe.whitelist()
def transmit_invoice(invoice_name: str):
    _, settings, irn = _firs_action_context(invoice_name)
    return _firs_action_request(
        settings,
        "POST",
        f"{TRANSMIT_INVOICE}/{quote(irn, safe='')}"
    )

def call_invoice_validation_api(payload: Dict[str, Any],
                                api_key: str,
                                secret_key: str,
                                base_url: Optional[str] = None,
                                timeout: int = REQUEST_TIMEOUT,
                                retries: int = RETRY_COUNT) -> Dict[str, Any]:
    """
    Call external POST /api/v1/invoice/validate with JSON payload and headers.
    Returns a dict with keys: success (bool), status_code (int|None), response (dict|string), error (str|None)
    """
    base_url = base_url
    url = base_url.rstrip("/") +  VALIDATE_INVOICE_DATA
    headers = _build_headers(api_key, secret_key)
    #print(f"\n header : \n{headers}")
    #print(f"\n payload : \n {payload}")

    last_exception = None
    for attempt in range(1, retries + 2):  # retries attempts + initial
        try:
            #print(f"\n==> atempt :{attempt}")
            resp = requests.post(url, json=payload, headers=headers, timeout=timeout)
            # Try to parse JSON response, fallback to text
            try:
                resp_json = resp.json()
            except ValueError:
                resp_json = resp.text

            result = {
                "success": resp.ok,
                "status_code": resp.status_code,
                "response": resp_json,
                "error": None
            }
            # ! print(f"\n==> response :{resp_json}")
            return result

        except requests.RequestException as exc:
            last_exception = exc
            # small backoff before retrying
            if attempt <= retries:
                time.sleep(RETRY_DELAY)
            else:
                break

    # If we reach here, all attempts failed
    frappe.log_error(frappe.get_traceback(), "call_invoice_validation_api error")
    return {
        "success": False,
        "status_code": None,
        "response": None,
        "error": str(last_exception) if last_exception else "unknown error"
    }

def save_validation_result_to_doc(invoice_name:str, validation_result:Dict[str, Any], fieldname: str ):
    """

    Persitst the validation result JSON 
    uses db.set_value to avoid triggering document events again.
    """

    try:
        payload_to_save ={
            "validation_result": validation_result,
            "saved_at": frappe.utils.now()
        }
        
        vch_syn = frappe.get_doc({
            "doctype": "Firs Syn",
            "syn_id": fieldname,
            "sales_invoice": invoice_name,
            "syn_status": "Validated",
            "returned_code": "201",
            "api_response": json.dumps(payload_to_save, indent=4)
        })
        vch_syn.insert(ignore_permissions=True)

        frappe.db.commit()
    except Exception:
        frappe.log_error(frappe.get_traceback(), "save_validation_result_to_doc error")

def submit_sign(self,firs_settings, schema_paylod):

    firs_settings = frappe.get_doc('FIRS Einvoice Settings')
    # endpoint call POST base_url/api/v1/invoice/sign
    # get the schema
    invoice_payload = self.custom_firs_invoice_schema
    """ 
        self.db_set("api_response", json.dumps(res_data, indent=4))
        frappe.msgprint("Invoice Validated Successfully", alert=True) """

    try: 
        #invoice_payload = self.custom_invoice_schema
        # get api
        api_key = firs_settings.api_key or "YOUR_API_KEY"
        secret_key = firs_settings.client_secret or "YOUR_SECRET_KEY"

        # call validation endpoint
        sign_result = call_invoice_signing_api(schema_paylod, api_key, secret_key, firs_settings.base_url)

        #save validation
        # remove this logic / as fir_sync doctype is going to be abandon
        #save_sign_result_to_doc(self.name, sign_result, fieldname=self.custom_irn_unix_timestamp)
        return sign_result
    except Exception:
        # log and persist error info for troubleshooting
        frappe.log_error(frappe.get_traceback(), "validate_firs_invoice_schema error")
        #custom_valation_data
        #frappe.db.set_value("Firs Syn", self.custom_irn_unix_timestamp, "api_response", json.dumps({"error": "validation_failed"}), update_modified=True)
        #frappe.db.commit()

def call_invoice_signing_api(payload: Dict[str, Any],
                                api_key: str,
                                secret_key: str,
                                base_url: Optional[str] = None,
                                timeout: int = REQUEST_TIMEOUT,
                                retries: int = RETRY_COUNT) -> Dict[str, Any]:
    """
    Call external POST /api/v1/invoice/validate with JSON payload and headers.
    Returns a dict with keys: success (bool), status_code (int|None), response (dict|string), error (str|None)
    """
    if not base_url:
        return {
            "success": False,
            "status_code": None,
            "response": None,
            "error": "Base URL is missing"
        }
    #base_url = base_url
    url = base_url.rstrip("/") + SIGN_INVOICE_SCHEMA
    headers = _build_headers(api_key, secret_key)

    last_exception = None
    for attempt in range(1, retries + 2):  # retries attempts + initial
        try:
            resp = requests.post(url, json=payload, headers=headers, timeout=timeout)
            # Try to parse JSON response, fallback to text
            try:
                resp_json = resp.json()
            except ValueError:
                resp_json = resp.text

            result = {
                "success": resp.ok,
                "status_code": resp.status_code,
                "response": resp_json,
                "error": None
            }
            # ! print(f"\n==> submit response :{resp_json}")
            return result

        except requests.RequestException as exc:
            last_exception = exc
            # small backoff before retrying
            if attempt <= retries:
                time.sleep(RETRY_DELAY)
            else:
                break

    # If we reach here, all attempts failed
    frappe.log_error(frappe.get_traceback(), "call_invoice_validation_api error")
    return {
        "success": False,
        "status_code": None,
        "response": None,
        "error": str(last_exception) if last_exception else "unknown error"
    }


def call_invoice_update_api(irn: str,
                           payment_status: str,
                           api_key: str,
                           secret_key: str,
                           base_url: Optional[str] = None,
                           reference: Optional[str] = None,
                           timeout: int = REQUEST_TIMEOUT,
                           retries: int = RETRY_COUNT) -> Dict[str, Any]:
    """Call PATCH /api/v1/invoice/update/{irn} for payment state changes."""
    if not irn:
        return {
            "success": False,
            "status_code": None,
            "response": None,
            "error": "IRN is missing"
        }

    if not base_url:
        return {
            "success": False,
            "status_code": None,
            "response": None,
            "error": "Base URL is missing"
        }

    url = base_url.rstrip("/") + f"{UPDATE_EINVOICE}/{irn}"
    headers = _build_headers(api_key, secret_key)
    payload = {"payment_status": payment_status.upper()}
    if reference:
        payload["reference"] = reference

    last_exception = None
    for attempt in range(1, retries + 2):
        try:
            resp = requests.patch(url, json=payload, headers=headers, timeout=timeout)
            try:
                resp_json = resp.json()
            except ValueError:
                resp_json = resp.text

            return {
                "success": resp.ok,
                "status_code": resp.status_code,
                "response": resp_json,
                "error": None if resp.ok else (resp_json if isinstance(resp_json, str) else json.dumps(resp_json, default=str))
            }
        except requests.RequestException as exc:
            last_exception = exc
            if attempt <= retries:
                time.sleep(RETRY_DELAY)
            else:
                break

    frappe.log_error(frappe.get_traceback(), "call_invoice_update_api error")
    return {
        "success": False,
        "status_code": None,
        "response": None,
        "error": str(last_exception) if last_exception else "unknown error"
    }

def save_sign_result_to_doc(invoice_name:str, validation_result:Dict[str, Any], fieldname: str ):

    try:
        payload_to_save ={
            "validation_result": validation_result,
            "saved_at": frappe.utils.now()
        }
        frappe.db.set_value("Firs Syn", fieldname, "syn_status", "Signed", update_modified=True)
        frappe.db.set_value("Firs Syn", fieldname, "syned", 1, update_modified=True)
        #vch_syn.insert(ignore_permissions=True)

        frappe.db.commit()
    except Exception:
        frappe.log_error(frappe.get_traceback(), "save_sign_result_to_doc error")

# tax break up section
def get_itemised_tax_breakup_html(doc):
	if not doc.taxes:
		return
	# get headers  
	tax_accounts = [] #itemised_tax_data = get_itemised_tax_breakup_data(doc) # get_rounded_tax_amount(itemised_tax_data, doc.precision("tax_amount", "taxes"))
     
	for tax in doc.taxes:
		if getattr(tax, "category", None) and tax.category == "Valuation":
			continue
		if tax.description not in tax_accounts:
			tax_accounts.append(tax.description) 
	itemised_tax_data = get_itemised_tax_breakup_data(doc)
	get_rounded_tax_amount(itemised_tax_data, doc.precision("tax_amount", "taxes"))

def get_itemised_tax_breakup(doc):
    print(f"\n==> frappe declaration :")
    if not doc.taxes:
        return
    # get headers  
	
    tax_accounts = [] #itemised_tax_data = get_itemised_tax_breakup_data(doc) # get_rounded_tax_amount(itemised_tax_data, doc.precision("tax_amount", "taxes"))
     
	
    for tax in doc.taxes:
		
        if getattr(tax, "category", None) and tax.category == "Valuation":
			
            continue
		
        """ if tax.description not in tax_accounts:
			
            tax_accounts.append(tax.description)  """
        if tax.account_head not in tax_accounts:
             tax_accounts.append(tax.account_head)
    
	
    itemised_tax_data = get_itemised_tax_breakup_data(doc)
	
    get_rounded_tax_amount(itemised_tax_data, doc.precision("tax_amount", "taxes"))
    print(f"\n\n ======= got get_itemised_tax_breakup ")
    print(f"\n checker : {itemised_tax_data} \n")
    return itemised_tax_data

def get_itemised_tax_breakup_data(doc):
	itemised_tax = get_itemised_tax(doc.taxes)

	itemised_taxable_amount = get_itemised_taxable_amount(doc.items)

	itemised_tax_data = []
	for item_code, taxes in itemised_tax.items():
		itemised_tax_data.append(
			frappe._dict(
				{"item": item_code, "taxable_amount": itemised_taxable_amount.get(item_code, 0), **taxes}
			)
		)

	return itemised_tax_data


def get_itemised_tax(taxes, with_tax_account=False):
	itemised_tax = {}
	for tax in taxes:
		if getattr(tax, "category", None) and tax.category == "Valuation":
			continue

		item_tax_map = json.loads(tax.item_wise_tax_detail) if tax.item_wise_tax_detail else {}
		if item_tax_map:
			for item_code, tax_data in item_tax_map.items():
				itemised_tax.setdefault(item_code, frappe._dict())

				tax_rate = 0.0
				tax_amount = 0.0

				if isinstance(tax_data, list):
					tax_rate = flt(tax_data[0])
					tax_amount = flt(tax_data[1])
				else:
					tax_rate = flt(tax_data)

				itemised_tax[item_code][tax.description] = frappe._dict(
					dict(tax_rate=tax_rate, tax_amount=tax_amount)
				)

				if with_tax_account:
					itemised_tax[item_code][tax.description].tax_account = tax.account_head

	return itemised_tax


def get_itemised_taxable_amount(items):
	itemised_taxable_amount = frappe._dict()
	for item in items:
		item_code = item.item_code or item.item_name
		itemised_taxable_amount.setdefault(item_code, 0)
		itemised_taxable_amount[item_code] += item.net_amount

	return itemised_taxable_amount

def get_rounded_tax_amount(itemised_tax, precision):
	# Rounding based on tax_amount precision
	for taxes in itemised_tax:
		for row in taxes.values():
			if isinstance(row, dict) and isinstance(row["tax_amount"], float):
				row["tax_amount"] = flt(row["tax_amount"], precision)
                   

def execute_validation_and_sign(data):
     """Validate and sign a pending FIRS invoice."""
     if not data or data.sync_status != "Pending Validation":
          return

     firs_settings = frappe.get_doc('FIRS Einvoice Settings')
     if not firs_settings.enabled:
          return

     try:
          payload = json.loads(data.firs_invoice_schema or "{}")
          if not payload:
               data.db_set({
                    "firs_status": "Failed Validation",
                    "sync_status": "Failed",
                    "last_error": "Missing invoice schema",
                    "response_log": json.dumps({"error": "Missing invoice schema", "saved_at": frappe.utils.now()}, indent=4)
               }, update_modified=False)
               frappe.db.commit()
               return

          val_response = validate_firs_invoice_schema(firs_settings, payload)
          data.last_validation_response = json.dumps(val_response, indent=4) if val_response else None
          if not val_response or val_response.get("status_code") not in [200, 201]:
               data.db_set({
                    "firs_status": "Failed Validation",
                    "sync_status": "Failed",
                    "last_error": val_response.get("error") if val_response else "Validation failed",
                    "last_validation_response": json.dumps(val_response, indent=4) if val_response else json.dumps({"error": "Validation failed"}, indent=4),
                    "response_log": json.dumps({
                         "validation_result": val_response.get("error") or val_response.get("message") or val_response,
                         "saved_at": frappe.utils.now()
                    }, indent=4)
               }, update_modified=False)
               frappe.db.commit()
               return

          sign_response = submit_sign(firs_settings, payload)
          data.last_signing_response = json.dumps(sign_response, indent=4) if sign_response else None
          if sign_response and sign_response.get("success"):
               response_data = sign_response.get("response", {})
               sales_invoice_name = data.sales_invoice or data.sales_invoice_code
               if sales_invoice_name and data.irn:
                    frappe.db.set_value(
                         "Sales Invoice",
                         sales_invoice_name,
                         "custom_irn_unix_timestamp",
                         data.irn,
                         update_modified=False
                    )
               data.db_set({
                    "firs_status": "Synced",
                    "sync_status": "Signed",
                    "last_signing_response": json.dumps(sign_response, indent=4),
                    "last_sync_at": frappe.utils.now(),
                    "last_error": "",
                    "response_log": json.dumps(response_data, indent=4)
               }, update_modified=False)
               frappe.db.commit()
               return

          data.db_set({
               "firs_status": "Failed Validation",
               "sync_status": "Failed",
               "last_error": (sign_response.get("error") if sign_response else "Signing failed") or "Signing failed",
               "last_signing_response": json.dumps(sign_response, indent=4) if sign_response else json.dumps({"error": "Signing failed"}, indent=4),
               "response_log": json.dumps({
                    "validation_result": "Validation passed, but signing failed.",
                    "signing_error": sign_response.get("error") or sign_response,
                    "saved_at": frappe.utils.now()
               }, indent=4)
          }, update_modified=False)
          frappe.db.commit()

     except Exception:
          frappe.log_error(frappe.get_traceback(), "FIRS EInoice Sign Error")
          data.db_set({
               "firs_status": "Failed Validation",
               "sync_status": "Failed",
               "last_error": frappe.get_traceback(),
               "response_log": json.dumps({
                    "validation_result": "System Exception",
                    "error": frappe.get_traceback(),
                    "saved_at": frappe.utils.now()
               }, indent=4)
          }, update_modified=False)
          frappe.db.commit()


def execute_einvoice_patch_update(firs_doc):
     """Patch a previously signed invoice when payment status changes to PAID or REJECTED."""
     if not firs_doc:
          return

     if firs_doc.firs_status not in ["Pending Update", "Cancelled"] and firs_doc.sync_status != "Pending Update":
          return

     sales_invoice_code = firs_doc.sales_invoice_code or firs_doc.sales_invoice
     if not sales_invoice_code:
          return

     sales_invoice = frappe.get_doc("Sales Invoice", sales_invoice_code)
     if not sales_invoice:
          firs_doc.db_set({
               "firs_status": "Failed Validation",
               "sync_status": "Failed",
               "last_error": "Sales Invoice not found",
               "response_log": json.dumps({"error": "Sales Invoice not found", "saved_at": frappe.utils.now()}, indent=4)
          }, update_modified=False)
          frappe.db.commit()
          return

     firs_settings = frappe.get_doc('FIRS Einvoice Settings')
     if not firs_settings.enabled:
          return

     irn = (firs_doc.irn or firs_doc.irn_unix_timestamp or "").strip()
     if not irn:
          firs_doc.db_set({
               "firs_status": "Failed Validation",
               "sync_status": "Failed",
               "last_error": "IRN is missing for patch update",
               "response_log": json.dumps({"error": "IRN is missing for patch update", "saved_at": frappe.utils.now()}, indent=4)
          }, update_modified=False)
          frappe.db.commit()
          return

     try:
          if sales_invoice.docstatus == 2:
               payment_status = "REJECTED"
               reference = f"sales_invoice_cancelled:{sales_invoice.name}"
          elif (sales_invoice.status or "").strip().lower() == "paid":
               payment_status = "PAID"
               reference = f"sales_invoice_paid:{sales_invoice.name}"
          else:
               return

          update_response = call_invoice_update_api(
               irn=irn,
               payment_status=payment_status,
               api_key=firs_settings.api_key or "YOUR_API_KEY",
               secret_key=firs_settings.client_secret or "YOUR_SECRET_KEY",
               base_url=firs_settings.base_url,
               reference=reference,
               timeout=REQUEST_TIMEOUT,
               retries=RETRY_COUNT
          )

          if update_response.get("success"):
               firs_doc.db_set({
                    "firs_status": "Signed",
                    "sync_status": "Synced",
                    "payment_status": payment_status,
                    "is_cancelled": 1 if sales_invoice.docstatus == 2 else 0,
                    "last_patch_response": json.dumps(update_response, indent=4),
                    "last_sync_at": frappe.utils.now(),
                    "last_error": "",
                    "response_log": json.dumps({"patch_response": update_response, "saved_at": frappe.utils.now()}, indent=4)
               }, update_modified=False)
               frappe.db.commit()
               return

          firs_doc.db_set({
               "firs_status": "Failed Validation",
               "sync_status": "Failed",
               "payment_status": payment_status,
               "last_patch_response": json.dumps(update_response, indent=4),
               "last_error": update_response.get("error") or "Patch update failed",
               "response_log": json.dumps({
                    "patch_error": update_response,
                    "saved_at": frappe.utils.now()
               }, indent=4)
          }, update_modified=False)
          frappe.db.commit()

     except Exception:
          frappe.log_error(frappe.get_traceback(), "FIRS invoice patch update error")
          firs_doc.db_set({
               "firs_status": "Failed Validation",
               "sync_status": "Failed",
               "last_error": frappe.get_traceback(),
               "response_log": json.dumps({
                    "error": "Patch update exception",
                    "traceback": frappe.get_traceback(),
                    "saved_at": frappe.utils.now()
               }, indent=4)
          }, update_modified=False)
          frappe.db.commit()

def add_if_value (data, key, value):
    """Add key only when value is not empty."""
    if value is not None and value != "":
        data[key] = value

def build_invoice_line (row):
    """Convert one Sales Invoice Item into invoice_line format."""

    line = {
        "invoiced_quantity": flt(row.qty),
        "line_extension_amount": flt(row.amount),

        "item": {
            "name": row.item_name,
            "description": row.description or "",
        },

        "price": {
            "price_amount": flt(row.rate),
            "base_quantity": flt(
                getattr(row, "base_quantity", 1)
            ) or 1,
            "price_unit":  "EA",
        },
        
    }
    # "price_unit": getattr(row, "uom", None) or "XBG",

    # ---------------------------------------------------------
    # Goods vs Service
    # ---------------------------------------------------------

    # Determine if item is a service or product based on Item doctype
    itm = frappe.get_doc('Item', row.item_code)
    is_service = itm.custom_firs_item_type == "Service"

    if is_service:

        add_if_value(
            line,
            "isic_code",
            getattr(row, itm.get("custom_firs_service_code"), None)
        )

        """ add_if_value(
            line,
            "service_category",
            getattr(row, itm.get("custom_firs_service_description"), None)
        ) """

    else:

        hsn_code = (
            getattr(row, itm.get("custom_hs_code"), None)
            or getattr(row, "hsn_code", None)
        )

        add_if_value(
            line,
            "hsn_code",
            hsn_code
        )

        """ add_if_value(
            line,
            "product_category",
            getattr(row, itm.get("custom_hs_product_description"), None)
        ) """

    # ---------------------------------------------------------
    # Seller identification
    # ---------------------------------------------------------

    add_if_value(
        line["item"],
        "sellers_item_identification",
        row.item_code
    )

    # ---------------------------------------------------------
    # Discount
    # ---------------------------------------------------------

    add_if_value(
        line,
        "discount_rate",
        flt(getattr(row, "discount_percentage", 0))
    )

    add_if_value(
        line,
        "discount_amount",
        flt(getattr(row, "discount_amount", 0))
    )

    # ---------------------------------------------------------
    # Fees
    # ---------------------------------------------------------

    add_if_value(
        line,
        "fee_rate",
        flt(getattr(row, "rate", 0)) 
    )
    # flt(getattr(row, "fee_rate", 0))

    add_if_value(
        line,
        "fee_amount",
        flt(getattr(row, "amount", 0))
    )

    # ---------------------------------------------------------
    # Tax
    # ---------------------------------------------------------

    add_if_value(
        line,
        "tax_rate",
        flt(getattr(row, "tax_rate", 0))
    )

    add_if_value(
        line,
        "tax_amount",
        flt(getattr(row, "tax_amount", 0))
    )

    return line
def build_invoice_lines (doc):

    return [
        build_invoice_line(row)
        for row in doc.items
    ]
def build_invoice_payload (doc):

    return  build_invoice_lines(doc)