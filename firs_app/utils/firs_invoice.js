// Copyright (c) 2025, Jide Olayinka [https://github.com/lajidey-foss] and contributors
// For license information, please see license.txt

frappe.ui.form.on("Sales Invoice", {

	refresh(frm){
        if (frm.doc.docstatus !== 1 || !frm.doc.custom_irn_unix_timestamp) {
            return;
        }

        const firs_actions = frm.add_custom_button(__("Validate IRN"), () => {
            callFirsAction(frm, "validate_irn", {}, "Validate IRN");
        }, __("FIRS Actions"));
        //firs_actions.parent().addClass("btn-group");

        frm.add_custom_button(__("Download Invoice"), () => {
            frappe.call({
                method: "firs_app.utils.firs_invoice.download_invoice",
                args: { invoice_name: frm.doc.name },
                freeze: true,
                freeze_message: __("Downloading invoice...")
            }).then((response) => {
                const result = response.message;
                if (!result || !result.success) {
                    showFirsActionError(result, __("Download Invoice"));
                    return;
                }

                const blob = new Blob([result.body || ""], {
                    type: result.content_type || "application/xml"
                });
                const link = document.createElement("a");
                link.href = URL.createObjectURL(blob);
                link.download = result.filename || `${frm.doc.name}.xml`;
                document.body.appendChild(link);
                link.click();
                link.remove();
                URL.revokeObjectURL(link.href);
            }).catch((error) => showFirsActionError(error, __("Download Invoice")));
        }, __("FIRS Actions"));
        /*

        frm.add_custom_button(__("Confirm Invoice"), () => {
            callFirsAction(frm, "confirm_invoice", {}, "Confirm Invoice");
        }, __("FIRS Actions"));

        frm.add_custom_button(__("Search Invoice"), () => showFirsSearchDialog(frm), __("FIRS Actions"));
        */

        frm.add_custom_button(__("Lookup With IRN"), () => {
            callFirsAction(frm, "lookup_invoice", {}, "Lookup With IRN");
        }, __("FIRS Actions"));

        frm.add_custom_button(__("Transmit"), () => {
            callFirsAction(frm, "transmit_invoice", {}, "Transmit");
        }, __("FIRS Actions"));
	},
});

function callFirsAction(frm, method, args, title) {
    frappe.call({
        method: `firs_app.utils.firs_invoice.${method}`,
        args: { invoice_name: frm.doc.name, ...args },
        freeze: true,
        freeze_message: __(`${title}...`)
    }).then((response) => {
        const result = response.message;
        if (!result || !result.success) {
            showFirsActionError(result, title);
            return;
        }
        showFirsResponseDialog(title, result);
    }).catch((error) => showFirsActionError(error, title));
}

function showFirsActionError(result, title) {
    const error = result && (result.error || result.exception || result.message) || __("The FIRS request failed.");
    frappe.msgprint({
        title: __(title),
        indicator: "red",
        message: escapeFirsHtml(typeof error === "string" ? error : JSON.stringify(error, null, 2))
    });
}

function showFirsResponseDialog(title, result) {
    const body = typeof result.body === "string" ? result.body : JSON.stringify(result.body, null, 2);
    const content = `<pre style="white-space: pre-wrap; max-height: 60vh; overflow: auto;">${escapeFirsHtml(body || "")}</pre>`;
    frappe.msgprint({
        title: `${__(title)} (${result.status_code})`,
        message: content,
        wide: true
    });
}

function escapeFirsHtml(value) {
    return String(value)
        .replaceAll("&", "&amp;")
        .replaceAll("<", "&lt;")
        .replaceAll(">", "&gt;")
        .replaceAll('"', "&quot;")
        .replaceAll("'", "&#039;");
}

function showFirsSearchDialog(frm) {
    const dialog = new frappe.ui.Dialog({
        title: __("Search Invoice"),
        fields: [
            { fieldname: "business_id", label: __("Business ID"), fieldtype: "Data", default: "" },
            { fieldname: "page", label: __("Page"), fieldtype: "Int", default: 1 },
            { fieldname: "size", label: __("Size"), fieldtype: "Int", default: 20 },
            { fieldname: "sort_by", label: __("Sort By"), fieldtype: "Data", default: "created_at" },
            { fieldname: "sort_direction_desc", label: __("Sort Descending"), fieldtype: "Check", default: 1 },
            { fieldname: "payment_status", label: __("Payment Status"), fieldtype: "Select", options: "\nPENDING\nPAID\nREJECTED" },
            { fieldname: "invoice_type_code", label: __("Invoice Type Code"), fieldtype: "Data", default: "396" },
            { fieldname: "issue_date", label: __("Issue Date"), fieldtype: "Date", default: frm.doc.posting_date },
            { fieldname: "due_date", label: __("Due Date"), fieldtype: "Date", default: frm.doc.due_date || frm.doc.posting_date },
            { fieldname: "tax_currency_code", label: __("Tax Currency"), fieldtype: "Data", default: frm.doc.currency || "NGN" },
            { fieldname: "document_currency_code", label: __("Document Currency"), fieldtype: "Data", default: frm.doc.currency || "NGN" }
        ],
        primary_action_label: __("Search"),
        primary_action(values) {
            callFirsAction(frm, "search_invoice", { filters: values }, "Search Invoice");
            dialog.hide();
        }
    });

    frappe.db.get_single_value("FIRS Einvoice Settings", "business_id").then((business_id) => {
        dialog.set_value("business_id", business_id || "");
    });
    dialog.show();
}

frappe.ui.form.on("Sales Invoice Item", {
    
    item_code: function(frm, cdt, cdn) {
        updateFirsCustomfields(frm, cdt, cdn);
        //frm.refresh_field(accepted_qty);
    },
    qty: function (frm, cdt, cdn) {
        updateFirsCustomfields(frm, cdt, cdn);
    },
    rate: function (frm, cdt, cdn) {
        updateFirsCustomfields(frm, cdt, cdn);
    }
});

var updateFirsCustomfields = function(frm, cdt, cdn) {
    let row = locals[cdt][cdn];

    if (!row.item_code || !row.qty || !row.rate) return;
    //console.table(row);
    
    let taxData = JSON.parse(row.item_tax_rate);
    let firsVat = Object.values(taxData)[0] || 0.0;
    
    // let val1 = (row.qty || 0) * (row.rate || 0);
    let vatIncRate = (row.rate || 0) + ((row.rate || 0) * flt(firsVat) / 100);
    let vatIncAmount = (row.qty || 0) * vatIncRate;

    // Use frappe.model.set_value to ensure the UI updates and the form is marked 'Dirty'
    frappe.model.set_value(cdt, cdn, 'custom_firs_vat', firsVat);
    frappe.model.set_value(cdt, cdn, 'custom_vat_inclusive_rate', vatIncRate);
    frappe.model.set_value(cdt, cdn, 'custom_vat_inclusive_amount', vatIncAmount);
    
    // Refresh the table field to show changes
    frm.refresh_field('items');
};