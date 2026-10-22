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

import json

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
	STEP 1: create a Sales Order with the items of the Klaes JSON,
	saved as DRAFT only (never submitted).

	The items must ALREADY EXIST in ERPNext: the Item Code is "SAP_Item_Number"
	in the JSON. (Creating new items is a later step.)

	Returns the name of the new Sales Order.
	"""
	if not klaes_import.customer:
		frappe.throw("No customer on this Klaes Import.")

	if not klaes_import.json_data:
		frappe.throw("No JSON data on this Klaes Import.")

	document = json.loads(klaes_import.json_data)["Document"]

	order = frappe.new_doc("Sales Order")
	order.customer = klaes_import.customer
	order.transaction_date = today()
	order.delivery_date = today()

	for klaes_item in document.get("item", []):
		item_code = klaes_item["SAP_Item_Number"]
		if not frappe.db.exists("Item", item_code):
			frappe.throw(f"Item '{item_code}' does not exist in ERPNext.")

		# ERPNext fills in the rest (name, unit, price, warehouse...) when saving
		order.append("items", {"item_code": item_code, "qty": klaes_item["quantity"]})

	if not order.items:
		frappe.throw("The Klaes JSON has no items.")

	# insert() only saves the draft. Do NOT call order.submit() here.
	order.insert()

	return order.name