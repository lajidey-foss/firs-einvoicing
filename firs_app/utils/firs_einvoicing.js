// Copyright (c) 2025, Jide Olayinka [https://github.com/lajidey-foss] and contributors
// For license information, please see license.txt


frappe.ui.form.on('Currency Detail', {
    refresh: function(frm) {
        // Add a button to trigger the API fetch and data insertion
        frm.add_custom_button(__('Fetch and Import Currencies'), function() {
            
            // 1. The GET call to your API endpoint
            fetch('api.your-source.com') // Replace with your actual URL
                .then(response => {
                    if (!response.ok) {
                        throw new Error('Network response was not ok');
                    }
                    return response.json();
                })
                .then(data => {
                    // 2. Iterate through the "GET response" data
                    data.forEach(item => {
                        frappe.db.insert({
                            doctype: 'Currency Detail',
                            symbol: item.symbol,
                            currency_name: item.name,
                            symbol_native: item.symbol_native,
                            decimal_digits: item.decimal_digits,
                            rounding: item.rounding,
                            code: item.code,
                            name_plural: item.name_plural
                        }).then(doc => {
                            console.log(`Success: Imported ${doc.code}`);
                        }).catch(err => {
                            console.error(`Error importing ${item.code}:`, err);
                        });
                    });

                    frappe.msgprint(__('Import process started. Check the browser console for details.'));
                })
                .catch(error => {
                    frappe.msgprint(__('Failed to fetch data: ') + error.message);
                });
        });
    },
    process_file: function (frm) {
		var filedata = $('#upload_mac')[0].files[0];
		if (filedata != undefined && filedata.name != null) {
			//console.log(`you: ${filedata.name} `);			
			frappe.call({
				method: "moldex3d_integration.moldex3d_integration.doctype.mac_file.mac_file.process_moldex_mac",
				args: {
					data: frm.doc.doctype
				},
				callback: function (r) {
					//console.log('first call : ',r.message,'doctype : ',frm.doc.doctype);
					if (r.message != null ) {
						frappe.show_alert({
							message: __("Mac file Processed ... : ",r.message),
							indicator: 'blue'
						});
						
					}
					if(r.message && filedata){
						//console.log(`to south: ${r.message}  `)						
						let imagefile = new FormData();					
						imagefile.append('doctype',frm.doc.doctype);
						imagefile.append('docname', r.message);											
						imagefile.append('folder', "Home/"+frm.doc.doctype);						
						imagefile.append('file', filedata);

						fetch('/api/method/upload_file', {
							headers: {
								'X-Frappe-CSRF-Token': frappe.csrf_token
							},
							method: 'POST',
							body: imagefile
						})
						.then(res => 
							res.json())
						.then(data => {			
							if (data.message){
								frappe.call({				
									method: 'moldex3d_integration.moldex3d_integration.doctype.mac_file.mac_file.update_moldex_mac',
									
									args: {
										doctype:frm.doc.doctype,
										docname: r.message,
										data_file: data.message.file_url
									}
								}).then(rs => {
									var options = [];
									//console.log('final call :',rs.message);
									frm.reload_doc();
									frappe.set_route("Form",frm.doc.doctype,'');
								
								});
								
							}
						})
						//frappe.set_route("Form",frm.doc.doctype,r.message);
					}
				}
				
			});			
		}
		else {
			frappe.msgprint('Please select a moldex mac file');
		}
	},
});
