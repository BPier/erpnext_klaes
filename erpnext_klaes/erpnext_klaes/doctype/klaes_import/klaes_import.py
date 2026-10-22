"""
Klaes Import: one record = one file sent by Klaes.

How it works:
1. klaes_sender.exe creates a Klaes Import record (standard Frappe REST API).
2. After the record is saved, process_import() runs in the background.
3. process_import() creates the documents in ERPNext and sets the status:
   - Done:  everything was created (see the "Sales Order" field)
   - Error: something failed (see the "Error Message" field),
            fix the cause, then click "Process again".
"""

import frappe
from frappe.model.document import Document
from frappe.utils import today


class KlaesImport(Document):
	def after_insert(self):
		# Run in the background, only once the record is safely saved
		frappe.enqueue(process_import, import_name=self.name, enqueue_after_commit=True)

	@frappe.whitelist()
	def process_again(self):
		"""Called by the "Process again" button on the form."""
		if self.status == "Done":
			frappe.throw("This import is already done.")
		process_import(self.name)


def process_import(import_name):
	"""Create the ERPNext documents for one Klaes Import and record the result."""
	klaes_import = frappe.get_doc("Klaes Import", import_name)

	# If anything fails, undo everything created during this processing
	frappe.db.savepoint("klaes_import")
	try:
		sales_order = create_draft_sales_order(klaes_import)
		klaes_import.db_set({"status": "Done", "sales_order": sales_order, "error_message": ""})

	except Exception as error:
		frappe.db.rollback(save_point="klaes_import")
		klaes_import.db_set({"status": "Error", "error_message": str(error)})
		# Full technical details go to the standard Error Log
		frappe.log_error(title=f"Klaes Import {import_name} failed")


def create_draft_sales_order(klaes_import):
	"""
	STEP 1: create an empty Sales Order, saved as DRAFT only (never submitted).
	Returns the name of the new Sales Order.
	"""
	if not klaes_import.customer:
		frappe.throw("No customer on this Klaes Import.")

	order = frappe.new_doc("Sales Order")
	order.customer = klaes_import.customer
	order.transaction_date = today()
	order.delivery_date = today()

	# The order has no items yet, so we must tell ERPNext to accept
	# an order with the mandatory "Items" table empty.
	order.flags.ignore_mandatory = True

	# insert() only saves the draft. Do NOT call order.submit() here.
	order.insert()

	return order.name
