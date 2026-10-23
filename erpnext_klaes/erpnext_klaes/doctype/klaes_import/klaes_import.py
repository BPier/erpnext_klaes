"""
Klaes Import: one record = one file sent by Klaes.

How it works:
1. klaes_sender.exe creates a Klaes Import record (standard Frappe REST API).
2. After the record is saved, process_import() runs in the background.
3. process_import() creates the documents in ERPNext and sets the status:
   - Done:  everything was created (see the "Quotation" or "Sales Order" field)
   - Error: something failed (see the "Error Message" field),
            fix the cause, then click "Process again".

Which document is created depends on "doc_type" in the Klaes JSON:
   - "Quotation" -> draft Quotation   (doc_number must start with "Q", e.g. Q241023-001A)
   - "Order"     -> draft Sales Order (doc_number must start with "O", e.g. O260909-0201)

The items of the JSON are created first, as variants of their template (see klaes_items.py).

The customer is always the generic "klaes import" customer (C99-9999, see install.py):
the sales team sets the real customer on the draft document in ERPNext.
"""

import json

import frappe
from frappe.model.document import Document
from frappe.utils import today

from erpnext_klaes.erpnext_klaes.doctype.klaes_import.klaes_items import create_or_update_items
from erpnext_klaes.install import create_generic_customer

# Klaes "doc_type" -> first letter that its "doc_number" must start with
DOC_NUMBER_PREFIX = {
	"Quotation": "Q",
	"Order": "O",
}


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
		document = read_klaes_document(klaes_import)
		doc_type, doc_number = check_doc_type_and_number(document)

		# Step 3: create (or update) the items, as variants of their template
		create_or_update_items(document)

		customer = get_customer()
		if doc_type == "Quotation":
			result = {"quotation": create_draft_quotation(customer, document)}
		else:
			result = {"sales_order": create_draft_sales_order(customer, document)}

		klaes_import.db_set(
			{
				"status": "Done",
				"doc_type": doc_type,
				"doc_number": doc_number,
				"customer": customer,
				"error_message": "",
				**result,
			}
		)

	except Exception as error:
		frappe.db.rollback(save_point="klaes_import")
		klaes_import.db_set({"status": "Error", "error_message": str(error)})
		# Full technical details go to the standard Error Log
		frappe.log_error(title=f"Klaes Import {import_name} failed")


def get_customer():
	"""Return the generic Klaes customer (created if it does not exist)."""
	customer = create_generic_customer()
	if not customer:
		frappe.throw("Complete the ERPNext setup wizard first: the Klaes customer cannot be created.")
	return customer


def read_klaes_document(klaes_import):
	"""Check the Klaes Import and return the "Document" part of its JSON."""
	if not klaes_import.json_data:
		frappe.throw("No JSON data on this Klaes Import.")

	return json.loads(klaes_import.json_data)["Document"]


def check_doc_type_and_number(document):
	"""
	Return (doc_type, doc_number) from the Klaes JSON, after checking that they agree:
	a "Quotation" number starts with "Q", an "Order" number starts with "O".
	"""
	doc_type = (document.get("doc_type") or "").strip()
	doc_number = (document.get("doc_number") or "").strip()

	if doc_type not in DOC_NUMBER_PREFIX:
		expected = " or ".join(DOC_NUMBER_PREFIX)
		frappe.throw(f"Unknown Klaes document type '{doc_type}' (expected {expected}).")

	prefix = DOC_NUMBER_PREFIX[doc_type]
	if not doc_number.startswith(prefix):
		frappe.throw(
			f"Klaes document type '{doc_type}' does not match document number '{doc_number}' "
			f"(a {doc_type} number must start with '{prefix}')."
		)

	return doc_type, doc_number


def create_draft_quotation(customer, document):
	"""Create a Quotation with the items of the Klaes JSON, saved as DRAFT. Returns its name."""
	quotation = frappe.new_doc("Quotation")
	quotation.quotation_to = "Customer"
	quotation.party_name = customer
	quotation.transaction_date = today()
	quotation.klaes_doc_number = document["doc_number"].strip()
	add_items(quotation, document)

	# insert() only saves the draft. Do NOT call submit() here.
	quotation.insert()
	return quotation.name


def create_draft_sales_order(customer, document):
	"""Create a Sales Order with the items of the Klaes JSON, saved as DRAFT. Returns its name."""
	order = frappe.new_doc("Sales Order")
	order.customer = customer
	order.transaction_date = today()
	order.delivery_date = today()
	order.klaes_doc_number = document["doc_number"].strip()
	add_items(order, document)

	# insert() only saves the draft. Do NOT call submit() here.
	order.insert()
	return order.name


def add_items(erpnext_document, document):
	"""
	Add one line per item of the Klaes JSON to a Quotation or Sales Order.

	The Item Code is "SAP_Item_Number" in the JSON.
	The items are created before, by create_or_update_items().
	"""
	for klaes_item in document.get("item", []):
		item_code = klaes_item["SAP_Item_Number"]
		if not frappe.db.exists("Item", item_code):
			frappe.throw(f"Item '{item_code}' does not exist in ERPNext.")

		# ERPNext fills in the rest (name, unit, price, warehouse...) when saving
		erpnext_document.append("items", {"item_code": item_code, "qty": klaes_item["quantity"]})

	if not erpnext_document.items:
		frappe.throw("The Klaes JSON has no items.")
