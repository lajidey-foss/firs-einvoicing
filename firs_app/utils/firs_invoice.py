import frappe
import time
import base64 
import json 

from cryptography.hazmat.primitives import hashes, serialization 
from cryptography.hazmat.primitives.asymmetric import padding 
from cryptography.fernet import Fernet

# Configure these values for your environment
PUBLIC_KEY_PATH = "/home/frappe/frappe-bench/sites/site1/public/files/public_key.pem"
EXTERNAL_API_URL = "https://example.com/endpoint"   # replace with real endpoint
EXTERNAL_API_HEADERS = {"Content-Type": "application/json"}  # add Authorization if required


def firs_work_flow_draft (doc, method):
    firs_settings = frappe.get_doc('FIRS Einvoice Settings')
    # check if needed
    if not firs_settings.enabled: # frappe.db.get_single_value('FIRS Einvoice Settings', 'enabled'):
        return
    coy = frappe.get_doc('Company', doc.company)

    # set  IRN & UNIX TIMESTAMP 
    irn_val = doc.name +"-" + get_service_id(firs_settings) +"-" + get_unix_timestamp()

    print(f"\n\n IRN {irn_val}")

    # Generate FIR Encrypted QR Data
    #firs_encrypt_qr_data = get_encrypt_qr_code(irn_val)
    firs_encrypt_qr_data = encrypt_qrcode(irn_val, firs_settings)

    # set FIRs Invoice Schema
    invoice_schema_paylod = build_invoice_schema(doc, firs_settings)
    invoice_schema_paylod["irn"] = irn_val
    #doc.custom_invoice_schema = invoice_schema_paylod
    print(f"\n\n invoice schema  : {invoice_schema_paylod}")

    # add new data to doc
    doc.db_set({"custom_irn_unix_timestamp": irn_val,
                "custom_encrypted_qr_data": json.dumps(firs_encrypt_qr_data),
                "custom_invoice_schema": json.dumps(invoice_schema_paylod)
             })
    
    #doc.save(ignore_permissions=True)

    # call firs validation method
    # on success call do other stuff notify or create success log.

def get_unix_timestamp():
    uxtime = int(time.time())
    print(f"\n\n ===================> {uxtime}")
    return str(uxtime)

def get_service_id(settings):
    firs_service_id = settings.service_id
    return firs_service_id

def get_encrypt_qr_code(irn):
    #
    cert = frappe.db.get_single_value('FIRS Einvoice Settings', 'certificate')
    pem_public_key = frappe.db.get_single_value('FIRS Einvoice Settings', 'public_key_decoded') 
    # "irn": irn
    payload = { 
        "irn": "INV001-345SFG-20241011.1731618237", 
        "certificate": cert 
    }
    # Serialize payload to compact JSON bytes 
    payload_bytes = json.dumps(payload, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    
    # Generate Fernet key and encrypt payload
    fernet_key = Fernet.generate_key() # bytes (base64 urlsafe)
    f = Fernet(fernet_key)
    token = f.encrypt(payload_bytes) # bytes (Fernet token)

    # Load RSA public key and encrypt the Fernet key using OAEP-SHA256
    public_key = serialization.load_pem_public_key(pem_public_key.encode("utf-8"))
    encrypted_fernet_key = public_key.encrypt(
        fernet_key, padding.OAEP( mgf=padding.MGF1(algorithm=hashes.SHA256()), algorithm=hashes.SHA256(), label=None )
    )

    # Base64-encode outputs for storage/transport
    encrypted_key_b64 = base64.b64encode(encrypted_fernet_key).decode("utf-8")
    token_b64 = base64.b64encode(token).decode("utf-8")

    # Prepare JSON to save in the Sales Invoice field

    save_obj = { "encrypted_key": encrypted_key_b64, "token": token_b64 }
    # doc.db_set("custom_encrypt_qr_data", json.dumps(save_obj), update_modified=True)
    print(f"\n\n ====================> {save_obj}")
    return save_obj

def encrypt_qrcode(irn,settings):
    # load the public key
    cert = settings.certificate
    pem_public_key = settings.public_key_decoded
    public_key = serialization.load_pem_public_key(pem_public_key.encode("utf-8"))

    # define the payload
    # "INV001-345SFG-20241011.1731618237"
    payload = {
        "irn": irn,
        "certificate": cert
    }
    # Serialize to json and encrypt
    payload_json = json.dumps(payload)
    encrypted = public_key.encrypt(
        payload_json.encode('utf-8'),
        padding.OAEP(
            mgf=padding.MGF1(algorithm=hashes.SHA256()),
            algorithm=hashes.SHA256(),
            label=None
        )
    )
    # Next convert encrypted data to Base64
    encrypted_b64 = base64.b64encode(encrypted).decode('utf-8')
    #print(f"\n\n plain: ====================> {encrypted}")

    return encrypted_b64

""" vch Invoice Schema """
def set_invoice_schema():
    """
    Docstring for set_invoice_schema
    """

def build_invoice_schema(doc, settings):
    """
    Map Sales Invoice doc fields to the vch_payload structure.
    Adjust field names below to match your custom fields.
    """
    # Supplier mapping (company-level or custom fields)
    # supplier address
    supplier_address = frappe.get_doc(doctype='Address', filters={"is_your_company_address":1, "address_type": "Office"})
    supplier = {
        "party_name": settings.business_information  or "",
        "tin": settings.tax_id or "",
        "email": settings.email or "",
        "telephone": settings.phone_number or "",
        "business_description": settings.business_description or "",
        "postal_address": {
            "street_name": supplier_address.address_line1 or "",
            "city_name": supplier_address.city or "",
            "postal_zone": supplier_address.pincode or "",
            "country": supplier_address.custom_country_code or ""
        }
    }

    # Customer mapping
    # customer
    val_customer = frappe.get_doc('Customer', doc.get("customer"))
    customer_address = frappe.get_doc(doctype='Address', filters={"title":val_customer.customer_primary_address})
    customer = {
        "party_name": doc.get("customer_name") or doc.get("customer") or "",
        "tin": val_customer.tax_id or "",
        "email": val_customer.custom_email or "",
        "telephone": val_customer.custom_email or "",
        "business_description":  "",
        "postal_address": {
            "street_name": customer_address.address_line1 or "",
            "city_name": customer_address.city or "",
            "postal_zone": customer_address.pincode or "",
            "country": customer_address.custom_country_code or ""
        }
    }

    # invoice_line from items table
    invoice_lines = []
    for item in doc.get("items") or []:
        # load the specific item 
        itm = frappe.get_doc('Item', item.get("item_name"))
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
                    "id": "LOCAL_SALES_TAX",
                    "percent": doc.get("tax_rate") or 0.0
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
        "invoice_type_code": doc.get("invoice_type_code") or "396",
        "document_currency_code": doc.get("currency") or "NGN",
        "accounting_supplier_party": supplier,
        "accounting_customer_party": customer,
        "tax_total": tax_total,
        "legal_monetary_total": legal_monetary_total,
        "invoice_line": invoice_lines
    }

    return vch_payload

