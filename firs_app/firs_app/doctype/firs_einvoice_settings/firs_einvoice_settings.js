// Copyright (c) 2025, Jide Olayinka and contributors
// For license information, please see license.txt

const MY_APP_CONFIG = {
    get_url(baseurl, endpoint) {
        if (!baseurl || !baseurl.trim()) {
            throw new Error("Base URL is not configured");
        }

        return `${baseurl.replace(/\/+$/, "")}/${endpoint.replace(/^\/+/, "")}`;
    }
};

async function fetchResource(baseurl, endpoint) {
    const url = MY_APP_CONFIG.get_url(baseurl, endpoint);
    const response = await fetch(url, {
        method: "GET",
        headers: {
            "Content-Type": "application/json"
        }
    });

    if (!response.ok) {
        throw new Error(`External API returned HTTP ${response.status}`);
    }

    const result = await response.json();
    if (!result || !Array.isArray(result.data)) {
        throw new Error("External API returned an invalid data format");
    }

    return result.data;
}

frappe.ui.form.on("FIRS Einvoice Settings", {
	refresh(frm) {
        // Add a custom button to the form
        //
	},

    get_invoice_type: function (frm) {
        const url = MY_APP_CONFIG.get_url(frm.doc.base_url, "api/v1/invoice/resources/invoice-types");

        fetch(url, {
            method: "GET",
            headers: {
                "Content-Type": "application/json"
            }
        })
        .then(response => response.json())
        .then(data => {
            frappe.call({
                method: "firs_app.utils.firs_einvoicing.update_invoice_type",
                args: {
                    invoice_data: data.data
                },
                callback: function (r) {
                    if (!r.exc) {
                        frappe.msgprint("Invoice Niche updated successfully");
                    }
                }
            });
        })
        .catch(error => {
            console.error(error);
            frappe.msgprint("Failed to fetch external data");
        });
    },
    get_currencies: function (frm) {
        // const url = values.base_url.replace(/\/+$/, '') + values.endpoint;
        let endpoint = "api/v1/invoice/resources/currencies";
        const url = MY_APP_CONFIG.get_url(frm.doc.base_url,endpoint);

        frm.page.set_indicator(__('Syncing currencies...'), 'orange');

        // Call external API
        fetch(url, {
            method: "GET",
            headers: {
                "Content-Type": "application/json"
            }
        })
        .then(response => response.json())
        .then(data => {
            // data = array of currency objects
            console.log("data returned :", data.data);

            frappe.call({
                method: "firs_app.utils.firs_einvoicing.update_currencies",
                args: {
                    currency_data: data.data
                },
                freeze: true, 
                freeze_message: __("Saving currencies to site..."),
                callback: function (r) {
                    frm.page.clear_indicator(); 
                    if (r.message && r.message.status === "success") {
                        frappe.msgprint(__('Currencies synced: ', [r.message.created || 0, r.message.updated || 0]));
                    }
                    else { frappe.msgprint(__('Sync failed: {0}', [r.message && r.message.message || JSON.stringify(r.message)])); }
                    /* if (!r.exc) {
                        frappe.msgprint("Currency master updated successfully");
                    } */
                }
            });
        })
        .catch(err => {
            console.error(err);
            frm.page.clear_indicator();
            frappe.msgprint(__('Failed to fetch currencies: {0}', [err.message]));
            //frappe.msgprint("Failed to fetch currency data");
        });

    },
    get_countries: function (frm) {
        const url = MY_APP_CONFIG.get_url(frm.doc.base_url,'api/v1/invoice/resources/countries');
        

        // Call external API
        fetch(url, {
            method: "GET",
            headers: {
                "Content-Type": "application/json"
            }
        })
        .then(response => response.json())
        .then(data => {
            // data = array of country objects
            console.log("data returned :", data.data);

            frappe.call({
                method: "firs_app.utils.firs_einvoicing.update_countries",
                args: {
                    countries_data: data.data
                },
                callback: function (r) {
                    if (!r.exc) {
                        frappe.msgprint("Countries master updated successfully");
                    }
                }
            });
        })
        .catch(error => {
            console.error(error);
            frappe.msgprint("Failed to fetch country data");
        });

    },
    get_payment_means: function (frm) {
        // pending returned null -- handle null
        const url = MY_APP_CONFIG.get_url(frm.doc.base_url,'api/v1/invoice/resources/payment_means');
        console.log("uri :",url);
                // Call external API
                fetch(url, {
                    method: "GET",
                    headers: {
                        "Content-Type": "application/json"
                    }
                })
                .then(response => response.json())
                .then(data => {
                    // data should be an array of { code, value }
                    console.log("data 1 :", data);

                    frappe.call({
                        method: "firs_app.utils.firs_einvoicing.update_payment_means",
                        args: {
                            invoice_data: data.data
                        },
                        callback: function (r) {
                            if (!r.exc) {
                                frappe.msgprint("Invoice Niche updated successfully");
                            }
                        }
                    });
                })
                .catch(error => {
                    console.error(error);
                    frappe.msgprint("Failed to fetch external data");
                });
    },
    //
    get_products_codes: function (frm) {
        fetchResource(frm.doc.base_url, "api/v1/invoice/resources/hs-codes")
            .then(products => {
                const invalidProduct = products.find(product =>
                    !product || !String(product.hscode || "").trim()
                );

                if (invalidProduct) {
                    throw new Error("External API returned a product without an hscode");
                }

                return frappe.call({
                    method: "firs_app.utils.firs_einvoicing.update_products_codes",
                    args: {
                        invoice_data: products
                    },
                    freeze: true,
                    freeze_message: __("Saving product codes...")
                });
            })
            .then(result => {
                if (result.exc) {
                    throw new Error(result.exc);
                }

                frappe.msgprint(__("Product codes updated successfully"));
            })
            .catch(error => {
                console.error("Product code synchronization failed:", error);
                frappe.msgprint(__("Product code synchronization failed: {0}", [error.message]));
            });
    },
    //
    get_all_states: function (frm) {
        
        const url = MY_APP_CONFIG.get_url(frm.doc.base_url,'api/v1/invoice/resources/states');
                // Call external API
                fetch(url, {
                    method: "GET",
                    headers: {
                        "Content-Type": "application/json"
                    }
                })
                .then(response => response.json())
                .then(data => {
                    // data should be an array of { code, value }
                    console.log("data returned :", data.data);

                    frappe.call({
                        method: "firs_app.utils.firs_einvoicing.update_all_states",
                        args: {
                            invoice_data: data.data
                        },
                        callback: function (r) {
                            if (!r.exc) {
                                frappe.msgprint("Invoice Niche updated successfully");
                            }
                        }
                    });
                })
                .catch(error => {
                    console.error(error);
                    frappe.msgprint("Failed to fetch external data");
                });
    },
    //
    get_categories: function (frm) {
        
        const url = MY_APP_CONFIG.get_url(frm.doc.base_url,'api/v1/invoice/resources/tax-categories');
        
                // Call external API
                fetch(url, {
                    method: "GET",
                    headers: {
                        "Content-Type": "application/json"
                    }
                })
                .then(response => response.json())
                .then(data => {
                    // data should be an array of { code, value }
                    console.log("data returned :", data.data);

                    frappe.call({
                        method: "firs_app.utils.firs_einvoicing.update_tax_categories",
                        args: {
                            invoice_data: data.data
                        },
                        callback: function (r) {
                            if (!r.exc) {
                                frappe.msgprint("Invoice Niche updated successfully");
                            }
                        }
                    });
                })
                .catch(error => {
                    console.error(error);
                    frappe.msgprint("Failed to fetch external data");
                });
    },
    //
    get_services_codes: function (frm) {
        
        const url = MY_APP_CONFIG.get_url(frm.doc.base_url,'api/v1/invoice/resources/services-codes');
                // Call external API
                fetch(url, {
                    method: "GET",
                    headers: {
                        "Content-Type": "application/json"
                    }
                })
                .then(response => response.json())
                .then(data => {
                    // data should be an array of { code, value }
                    console.log("data returned :", data.data);

                    frappe.call({
                        method: "firs_app.utils.firs_einvoicing.update_services_codes",
                        args: {
                            invoice_data: data.data
                        },
                        callback: function (r) {
                            if (!r.exc) {
                                frappe.msgprint("Invoice Niche updated successfully");
                            }
                        }
                    });
                })
                .catch(error => {
                    console.error(error);
                    frappe.msgprint("Failed to fetch external data");
                });
    },
    //
    get_all_local_governments: function (frm) {
        
        const url = MY_APP_CONFIG.get_url(frm.doc.base_url,'api/v1/invoice/resources/lgas');
                // Call external API
                fetch(url, {
                    method: "GET",
                    headers: {
                        "Content-Type": "application/json"
                    }
                })
                .then(response => response.json())
                .then(data => {
                    // data should be an array of { code, value }
                    console.log("data returned :", data.data);

                    frappe.call({
                        method: "firs_app.utils.firs_einvoicing.update_local_governments",
                        args: {
                            invoice_data: data.data
                        },
                        callback: function (r) {
                            if (!r.exc) {
                                frappe.msgprint("Invoice Niche updated successfully");
                            }
                        }
                    });
                })
                .catch(error => {
                    console.error(error);
                    frappe.msgprint("Failed to fetch external data");
                });
    },
    //
    process_key: function (frm){
        new frappe.ui.FileUploader({
                doctype: frm.doctype,
                docname: frm.name,
                allow_multiple: false,
                restrictions: {
					allowed_file_types: [".txt"],
				},
                on_success: (file_doc) => {
                    // Trigger the server processing after successful upload
                    frm.call({
                        method: "firs_app.utils.firs_einvoicing.get_keys_cert_upload", // This must match the Server Script "API Method"
                        args: {
                            "file_url": file_doc.file_url,
                            "docname": file_doc.name
                        },
                        callback: function(r) {
                            if (r.message) {
                                frm.reload_doc(); // Refresh form to show the new key
                                frappe.show_alert({message: __('Key extracted and saved'), indicator: 'green'});
                            }
                        }
                    });
                }
            });
    }

});
