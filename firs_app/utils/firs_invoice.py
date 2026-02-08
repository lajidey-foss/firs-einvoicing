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

VALIDATE_IRN = "/api/v1/invoice/irn/validate"
VALIDATE_INVOICE_DATA = "/api/v1/invoice/validate"
SIGN_INVOICE_SCHEMA = "/api/v1/invoice/sign"
AUTH_PATH = "/api/v1/utilities/authenticate"
REQUEST_TIMEOUT = 15 # seconds 
RETRY_COUNT = 2 
RETRY_DELAY = 2 # seconds


def firs_work_flow_draft (doc, method):
    firs_settings = frappe.get_doc('FIRS Einvoice Settings')
    # check if needed
    if not firs_settings.enabled: # frappe.db.get_single_value('FIRS Einvoice Settings', 'enabled'):
        return
    #coy = frappe.get_doc('Company', doc.company)

    # set  IRN & UNIX TIMESTAMP 
    irn_val = f"{doc.name}-{get_service_id(firs_settings)}-{get_unix_timestamp(doc.posting_date)}"
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
    #call auth before validation call
    """
    payload =
    {
    "email": "{{TAXPAYER_EMAIL}}",
    "password": "{{TAXPAYER_PASSWORD}}"
    }
    custom_encrypted_irn_qr
    """
    # call firs validation method ---- package_external_api_put
    # on success call do other stuff notify or create success log. --- POST base_url/api/v1/invoice/validate
    # encrypt_invoce_schema
    firs_encrypt_schema = encrypt_invoce_schema(doc.custom_firs_invoice_schema, firs_settings)

    
    validater_report = validate_firs_invoice_schema(doc,firs_encrypt_schema,firs_settings)
    
    if next(iter(validater_report.values())) :

        print(f"\n ============{next(iter(validater_report.values())) }==========> \n report to : {list(validater_report.values())[3]}")
    

    #temp fix to submit and sign firs without doc submit on frappe
    #submit_sign(doc)



def get_unix_timestamp(pdate):
    uxtime = int(time.time())
    pdate = pdate.replace("-", "")
    result = f"{pdate}" #f"{pdate}.{str(uxtime)}"
    #print(f"\n\n ========unix date & timestamp ===========> {result}")
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
        "business_description":  "This entity is a sub saller of CBM",
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
            "hsn_code": itm.get("custom_hs_code") or "",
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
    tax_total = [{
        "tax_amount": doc.get("total_taxes_and_charges") or doc.get("tax_amount") or 0.0,
        "tax_subtotal": [
            {
                "taxable_amount": doc.get("taxable_amount") or 0.0,
                "tax_amount": doc.get("tax_amount") or 0.0,
                "tax_category": {
                    "id": "STANDARD_VAT",
                    "percent": doc.get("tax_rate") or 7.5
                }
            }
        ]
    }]

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
        "invoice_line": invoice_lines
    }

    return vch_payload

def build_qrcode_generator(data):
    # if data.custom_qr_code_image or not data.custom_qr_code_image == "" or not data.custom_qr_code_image is None :

    if data.custom_encrypted_irn_qr:
        # custom_encrypted_qr_data
        existing_file_url = data.custom_encrypted_qr_image
        
        qr = qrcode.QRCode(version=1, box_size=10, border=5)
        qr.add_data(data.custom_encrypted_irn_qr)
        qr.make(fit=True)

        img = qr.make_image(fill_color="black", back_color="white")

        #save image to buffer
        buffered = BytesIO()
        img.save(buffered, format="PNG")

        #Save as file 
        file_name = f"QR_{data.name}.png"
        #print(f"\n\n ===================> {file_name}")

        if existing_file_url:
            #frappe.db.delete("File", {"file_url": existing_file_url, "attached_to_name": self.name})
            print(f"here")
            frappe.db.delete("File", {"file_url": existing_file_url, "attached_to_name": data.name})
        
        _file = frappe.get_doc({
            "doctype": "File",
            "file_name": file_name,
            "attached_to_doctype": data.doctype,
            "attached_to_name": data.name,
            "content": buffered.getvalue(),
            "is_private": 0
        })
        _file.save()

        data.db_set("custom_encrypted_qr_image", _file.file_url, update_modified=False)
        print(f"\n\n ===================> {_file.file_url}")
        return _file.file_url

# validation script
def validate_firs_invoice_schema (self, invoice_payload, firs):
    # get the schema
    
    #invoice_payload = {"invoiceRequest": self.custom_firs_invoice_schema}
    """ 
        self.db_set("api_response", json.dumps(res_data, indent=4))
        frappe.msgprint("Invoice Validated Successfully", alert=True) """

    try: 
        invoice_payload =  self.custom_firs_invoice_schema
        # get api
        api_key = firs.api_key or "YOUR_API_KEY"
        secret_key = firs.client_secret or "YOUR_SECRET_KEY"

        # call validation endpoint
        validation_result = call_invoice_validation_api(invoice_payload, api_key, secret_key, firs.base_url)

        #save validation
        save_validation_result_to_doc(self.name, validation_result, fieldname=self.custom_irn_unix_timestamp)
        #remove below just for report to user
        return validation_result
    except Exception:
        # log and persist error info for troubleshooting
        frappe.log_error(frappe.get_traceback(), "validate_firs_invoice_schema error")
        #custom_valation_data
        frappe.db.set_value("Firs Syn", self.custom_irn_unix_timestamp, "api_response", json.dumps({"error": "validation_failed"}), update_modified=True)
        frappe.db.commit()

def _build_headers(api_key: str, secret_key: str) -> Dict[str, str]:
    """Return headers required by the external API.
        """
    return {
        "Content-Type": "application/json",
        "Accept": "application/json",
        "x-api-key": api_key,
        "x-api-secret": secret_key
    }

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
            print(f"\n==> atempt :{attempt}")
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

def submit_sign(self):

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
        sign_result = call_invoice_signing_api(invoice_payload, api_key, secret_key, firs_settings.base_url)

        #save validation
        save_sign_result_to_doc(self.name, sign_result, fieldname=self.custom_irn_unix_timestamp)
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
    base_url = base_url
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

def save_sign_result_to_doc(invoice_name:str, validation_result:Dict[str, Any], fieldname: str ):
    """
    Docstring for save_validation_result_to_doc
    
    :param invoice_name: Description
    :type invoice_name: str
    :param validation_result: Description
    :type validation_result: Dict[str, Any]

    Persitst the validation result JSON 
    uses db.set_value to avoid triggering document events again.
    """

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