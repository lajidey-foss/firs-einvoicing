import frappe
import json
import base64
from frappe import _

def get_api_url(endpoint):
    # Fetch base URL from a custom 'Settings' DocType
    base_url = frappe.db.get_single_value('My App Settings', 'base_url')
    return f"{base_url.strip('/')}/{endpoint.lstrip('/')}"

@frappe.whitelist()
def fetch_and_import_currencies():
    # 1. External GET call from the server
    api_url = "api.your-source.com"
    try:
        response = frappe.make_get_request(api_url)
        # response is automatically parsed if it's JSON
    except Exception as e:
        frappe.throw(f"Failed to fetch data: {str(e)}")

    import_count = 0
    
    # 2. Iterate and Insert/Update records
    for item in response:
        code = item.get("code")
        
        # Check if record exists to avoid duplicates
        if not frappe.db.exists("Currency Detail", code):
            doc = frappe.get_doc({
                "doctype": "Currency Detail",
                "code": code,
                "symbol": item.get("symbol"),
                "currency_name": item.get("name"),
                "symbol_native": item.get("symbol_native"),
                "decimal_digits": item.get("decimal_digits"),
                "rounding": item.get("rounding"),
                "name_plural": item.get("name_plural")
            })
            doc.insert()
            import_count += 1
            
    # Commit changes to DB
    frappe.db.commit()
    
    return {"status": "success", "imported": import_count}


#### 
@frappe.whitelist()
def update_invoice_type(invoice_data):
    print("n/n/======================================>")
    if isinstance(invoice_data, str):
        invoice_data = json.loads(invoice_data)

    print("/n/n here",invoice_data)
    for item in invoice_data:
        code = item.get("code")
        value = item.get("value")

        if frappe.db.exists("Invoice Type", {"type_code": code}):
            frappe.db.set_value("Invoice Type", {"type_code": code}, "value", value)
        else:
            doc = frappe.get_doc({
                "doctype": "Invoice Type",
                "type_code": code,
                "value": value
            })
            doc.insert(ignore_permissions=True)

    frappe.db.commit()
    return "OK"

@frappe.whitelist()
def update_currencies(currency_data):

    """ try:
        if isinstance(currency_data, str):
            try:
                currency_data = json.loads(currency_data)
            except Exception:
                frappe.throw(_("Invalid currencies payload"))
        if not isinstance(currency_data, list):
            frappe.throw(_("Expected a list of currency objects"))
        
        created = 0
        updated = 0
        errors = []

        for cd in currency_data:
            try:
                code = (cd.get("code") or "").strip()
                if not code:
                    raise ValueError("Missing currency code")
                
                values = {
                    "currency_name": cd.get("name"),
                    "symbol": cd.get("symbol"),
                    "symbol_native": cd.get("symbol_native"),
                    "decimal_digits": cd.get("decimal_digits"),
                    "rounding": cd.get("rounding"),
                    "plural_name": cd.get("name_plural")
                }
                # check this code if already exists
                existing = frappe.db.exists("Firs Currency", {"currency_code": code}, ["name"], as_dict=True)

                if existing:
                    doc = frappe.get_doc("Firs Currency", existing.name)

                    for k, v in values.items():
                        if v is not None:
                            if k in doc.meta.get_fieldnames():
                                doc.set(k, v)
                    doc.save(ignore_permission=True)
                    updated += 1
                else:
                    new_doc = frappe.get_doc({
                        "doctype": "Firs Currency",
                        "currency_code": code,
                    })

                    for k in ("currency_name", "symbol", "symbol_native", "decimal_digits", "rounding", "plural_name"):
                        if values.get(k) is not None and k in new_doc.meta.get_fieldnames():
                            new_doc.set(k, values.get(k))
                    new_doc.insert(ignore_permissions=True)
                    created +=1
            except Exception as e:
                errors.append({"item": cd, "error": str(e)})
                frappe.log_error(frappe.get_traceback(), "update_currencies item error")
        
        result = {"status": "success", "created": created, "updated": updated, "errors": errors}
        return result
    
    except frappe.ValidationError:
        raise
    except Exception as exc:
        frappe.log_error(frappe.get_traceback(), "update_currencies error")
        return {"status": "error", "message": str(exc)} """



    if isinstance(currency_data, str):
        currency_data = json.loads(currency_data)

    for item in currency_data:
        code = item.get("code")

        if not code:
            continue

        values = {
            "currency_name": item.get("name"),
            "symbol": item.get("symbol"),
            "symbol_native": item.get("symbol_native"),
            "decimal_digits": item.get("decimal_digits"),
            "rounding": item.get("rounding"),
            "plural_name": item.get("name_plural")
        }

        # Check if record exists
        existing = frappe.db.exists(
            "Firs Currency",
            {"currency_code": code}
        )

        if existing:
            frappe.db.set_value(
                "Firs Currency",
                {"currency_code": code},
                values
            )
        else:
            doc = frappe.get_doc({
                "doctype": "Firs Currency",
                "currency_code": code,
                **values
            })
            doc.insert(ignore_permissions=True)

    frappe.db.commit()
    result = {"status": "success"}
    return result

@frappe.whitelist()
def update_countries(countries_data):
    if isinstance(countries_data, str):
        countries_data = json.loads(countries_data)

    for item in countries_data:
        country_code = item.get("country_code")
        #alpha_2 = item.get("alpha_2")
        if not country_code:
            continue

        values = {
            "country_name": item.get("name"),
            "alpha_3": item.get("alpha_3"),
            "alpha_2": item.get("alpha_2"),
            "iso_3166_2": item.get("iso_3166_2"),
            "region": item.get("region"),
            "sub_region": item.get("sub_region"),
            "intermediate_region": item.get("intermediate_region"),
            "region_code": item.get("region_code"),
            "sub_region_code": item.get("sub_region_code"),
            "intermediate_region_code": item.get("intermediate_region_code"),
        }

        existing = frappe.db.exists(
            "Firs Countries",
            {"country_code": country_code}
        )

        if existing:
            frappe.db.set_value(
                "Firs Countries",
                {"country_code": country_code},
                values
            )
        else:
            doc = frappe.get_doc({
                "doctype": "Firs Countries",
                "country_code": country_code,
                **values
            })
            doc.insert(ignore_permissions=True)

    frappe.db.commit()
    return {"status": "success"}

@frappe.whitelist()
def update_payment_means(invoice_data):
    print("n/n/================================>")
    if isinstance(invoice_data, str):
        invoice_data = json.loads(invoice_data)

    for item in invoice_data:
        code = item.get("code")
        value = item.get("value")

        if frappe.db.exists("Payment Means", {"payment_code": code}):
            frappe.db.set_value("Payment Means", {"payment_code": code}, "value", value)
        else:
            doc = frappe.get_doc({
                "doctype": "Payment Means",
                "payment_code": code,
                "value": value
            })
            doc.insert(ignore_permissions=True)

    frappe.db.commit()
    return "OK"

@frappe.whitelist()
def update_products_codes(invoice_data):
    if isinstance(invoice_data, str):
        invoice_data = json.loads(invoice_data)

    for item in invoice_data:
        code = item.get("hscode")
        value = item.get("description")

        if frappe.db.exists("Products Codes", {"hscode": code}):
            frappe.db.set_value("Products Codes", {"hscode": code}, "description", value)
            #frappe.db.set_value("Products Codes", {"hscode": code}, "description", value)
        else:
            doc = frappe.get_doc({
                "doctype": "Products Codes",
                "hscode": code,
                "description": value
            })
            doc.insert(ignore_permissions=True)

    frappe.db.commit()
    return "OK"

@frappe.whitelist()
def update_all_states(invoice_data):
    if isinstance(invoice_data, str):
        invoice_data = json.loads(invoice_data)

    for item in invoice_data:
        code = item.get("code")
        value = item.get("name")

        if frappe.db.exists("Firs States", {"state_code": code}):
            frappe.db.set_value("Firs States", {"state_code": code}, "state_name", value)
        else:
            doc = frappe.get_doc({
                "doctype": "Firs States",
                "state_code": code,
                "state_name": value
            })
            doc.insert(ignore_permissions=True)

    frappe.db.commit()
    return "OK"

@frappe.whitelist()
def update_tax_categories(invoice_data):
    if isinstance(invoice_data, str):
        invoice_data = json.loads(invoice_data)

    for item in invoice_data:
        code = item.get("code")
        value = item.get("value")

        if frappe.db.exists("Tax Categories", {"tax_category_code": code}):
            frappe.db.set_value("Tax Categories", {"tax_category_code": code}, "value", value)
        else:
            doc = frappe.get_doc({
                "doctype": "Tax Categories",
                "tax_category_code": code,
                "value": value
            })
            doc.insert(ignore_permissions=True)

    frappe.db.commit()
    return "OK"

@frappe.whitelist()
def update_services_codes(invoice_data):
    if isinstance(invoice_data, str):
        invoice_data = json.loads(invoice_data)

    for item in invoice_data:
        code = item.get("code")
        value = item.get("description")

        if frappe.db.exists("Service Codes", {"service_id": code}):
            frappe.db.set_value("Service Codes", {"service_id": code}, "description", value)
        else:
            doc = frappe.get_doc({
                "doctype": "Service Codes",
                "service_id": code,
                "description": value
            })
            doc.insert(ignore_permissions=True)

    frappe.db.commit()
    return "OK"

@frappe.whitelist()
def update_local_governments(invoice_data):
    if isinstance(invoice_data, str):
        invoice_data = json.loads(invoice_data)

    # might encounter error on lg_state = item.get("state_code") line introduction
    for item in invoice_data:
        code = item.get("code")
        value = item.get("name")
        lg_state = item.get("state_code")

        if frappe.db.exists("Local Governments", {"lg_code": code}):
            frappe.db.set_value("Local Governments", {"lg_code": code}, "lg_name", value)
        else:
            doc = frappe.get_doc({
                "doctype": "Local Governments",
                "lg_code": code,
                "lg_name": value,
                "state_code": lg_state

            })
            doc.insert(ignore_permissions=True)

    frappe.db.commit()
    return "OK"

@frappe.whitelist(allow_guest= False)
def get_keys_cert_upload():
    file_url = frappe.form_dict.get("file_url")
    docname = frappe.form_dict.get("docname")

    if not file_url or not docname:
        frappe.throw("Missing file URL or Document Name")

    # Find the File document
    file_name = frappe.db.get_value("File", {"file_url": file_url}, "name")

    if file_name:
        # Get content and parse JSON
        file_doc = frappe.get_doc("File", file_name)
        content = file_doc.get_content()
    
        try:
            data = json.loads(content)
            encoded_key = data.get("public_key")

            if encoded_key is None:
                frappe.throw(_("Uploaded JSON missing 'key' information "))

            #frappe.db.set_value("Schema Setting", None, "sm_public_key", public_key_val, update_modified=True)
            
            if encoded_key:
                normalize_encoded_key = "".join(encoded_key.split())
                frappe.db.set_value("FIRS Einvoice Settings", None, "public_key", normalize_encoded_key, update_modified=True)
                
                # Decode the Base64 key to PEM format
                try: 
                    #decoded_bytes = base64.b64decode(b64_str) 
                    decoded_key = base64.b64decode(normalize_encoded_key).decode("utf-8")
                except Exception as e: 
                    frappe.throw(f"Failed to decode key: {e}")
                
                if "-----BEGIN PUBLIC KEY-----" not in decoded_key or "-----END PUBLIC KEY-----" not in decoded_key:
                    stripped = decoded_key.strip()
                    if stripped.startswith("LS0t") or stripped.startswith("MIIB") or stripped.startswith("MIGf"):
                        warning = "Decoded content does not contain PEM markers. Saved anyway."
                    else:
                        warning = None
                else:
                    warning = None
                

                frappe.db.set_value("FIRS Einvoice Settings", None, "public_key_decoded", decoded_key, update_modified=True)

                if warning:
                    frappe.response["warning"] = warning

                frappe.response["message"] = True
            else:
                frappe.throw("Field 'key' not found in JSON payload")
            if data.get("certificate") is not None: 
                frappe.db.set_value("FIRS Einvoice Settings", None, "certificate", data.get("certificate"), update_modified=True) 
            
            frappe.db.commit()
                
        except Exception as e:
            frappe.throw(f"Failed to process file: {str(e)}")
    else:
        frappe.throw("Uploaded file record not found in database.")
