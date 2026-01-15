import frappe
import json
import base64

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

        if frappe.db.exists("Invoice Type", {"code": code}):
            frappe.db.set_value("Invoice Type", {"code": code}, "value", value)
        else:
            doc = frappe.get_doc({
                "doctype": "Invoice Type",
                "key": code,
                "value": value
            })
            doc.insert(ignore_permissions=True)

    frappe.db.commit()
    return "OK"

@frappe.whitelist()
def update_currencies(currency_data):
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
            "Firs Currencies",
            {"code": code}
        )

        if existing:
            frappe.db.set_value(
                "Firs Currencies",
                {"code": code},
                values
            )
        else:
            doc = frappe.get_doc({
                "doctype": "Firs Currencies",
                "code": code,
                **values
            })
            doc.insert(ignore_permissions=True)

    frappe.db.commit()
    return {"status": "success"}

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

        if frappe.db.exists("Payment Means", {"key": code}):
            frappe.db.set_value("Payment Means", {"key": code}, "value", value)
        else:
            doc = frappe.get_doc({
                "doctype": "Payment Means",
                "key": code,
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

        if frappe.db.exists("Tax Categories", {"key": code}):
            frappe.db.set_value("Tax Categories", {"key": code}, "value", value)
        else:
            doc = frappe.get_doc({
                "doctype": "Tax Categories",
                "key": code,
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

        if frappe.db.exists("Service Codes", {"code": code}):
            frappe.db.set_value("Service Codes", {"code": code}, "description", value)
        else:
            doc = frappe.get_doc({
                "doctype": "Service Codes",
                "code": code,
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

            # print(f"n/n/ raw public key : {encoded_key} n/")
            
            if encoded_key:
                # Decode the Base64 key to PEM format
                decoded_key = base64.b64decode(encoded_key).decode("utf-8")
                
                #frappe.db.set_value("Your DocType Name", docname, "public_key_field", decoded_key)
                frappe.db.set_value("FIRS Einvoice Settings","FIRS Einvoice Settings", {
                    "public_key": encoded_key,"public_key_decoded": decoded_key,"certificate": data.get("certificate")
                })

                #frappe.db.commit()
                
                #result = { "public_key": decoded_key }
                #print(result)

                # Return success message to client
                frappe.response["message"] = True
            else:
                frappe.throw("Field 'public_key' not found in JSON payload")
                
        except Exception as e:
            frappe.throw(f"Failed to process file: {str(e)}")
    else:
        frappe.throw("Uploaded file record not found in database.")
