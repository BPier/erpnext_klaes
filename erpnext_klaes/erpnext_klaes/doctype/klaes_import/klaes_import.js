frappe.ui.form.on("Klaes Import", {
	refresh(frm) {
		// Button to retry an import that failed
		if (!frm.is_new() && frm.doc.status !== "Done") {
			frm.add_custom_button(__("Process again"), () => {
				frm.call("process_again").then(() => frm.reload_doc());
			});
		}
	},
});
