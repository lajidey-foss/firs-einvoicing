// Copyright (c) 2025, Jide Olayinka [https://github.com/lajidey-foss] and contributors
// For license information, please see license.txt

frappe.ui.form.on("Sales Invoice", {

	refresh(frm){
        //frm.disable_save();
		//console.table(frm.doc);
        //frm.doc.items[0].item_tax_rate = '{"STANDARD_VAT - OC": 7.5}'
	},
});

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