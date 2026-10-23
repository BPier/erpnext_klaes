# Copyright (c) 2026, Pierrick BLAISE and Contributors
# See license.txt

"""
Tests for Klaes Import:
- step 2: Klaes "Quotation" -> draft Quotation, Klaes "Order" -> draft Sales Order,
          with the Klaes document number on the created document.
- step 3: the items are created as variants of their template (template and attributes
          created when missing, existing items updated).
- the customer is always the generic Klaes customer (C99-9999 "klaes import").
- real Klaes files: the JSON files in the test_data/ folder are imported as Klaes sends them.
  To test a new file: put it in test_data/ and copy one of the "real Klaes files" tests.

Run them with:
    bench --site <site> run-tests --doctype "Klaes Import" --skip-before-tests

Everything created by these tests is rolled back at the end (IntegrationTestCase).
"""

import json
import os

import frappe
from frappe.tests import IntegrationTestCase

from erpnext_klaes.erpnext_klaes.doctype.klaes_import.klaes_import import process_import
from erpnext_klaes.erpnext_klaes.doctype.klaes_import.klaes_items import (
	ATTRIBUTES,
	COLONIAL,
	COLOR,
	FULL_ITEM_NUMBER,
	HEIGHT,
	WIDTH,
)
from erpnext_klaes.install import GENERIC_CUSTOMER, GENERIC_CUSTOMER_NAME, create_generic_customer

# Do not load the standard ERPNext test records for these links:
# the tests create the only records they need.
EXTRA_TEST_RECORD_DEPENDENCIES = []
IGNORE_TEST_RECORD_DEPENDENCIES = ["Customer", "Quotation", "Sales Order"]

ORDER_NUMBER = "O-TEST-UNIT-001"
QUOTATION_NUMBER = "Q-TEST-UNIT-001"
TEST_TEMPLATE = "_Test Klaes Template"
TEST_ITEM_GROUP = "_Test Klaes Item Group"

# Real Klaes JSON files used by the tests
TEST_DATA_FOLDER = os.path.join(os.path.dirname(__file__), "test_data")


def read_test_file(file_name):
	"""Return the text of a JSON file of the test_data/ folder, read like klaes_sender does."""
	with open(os.path.join(TEST_DATA_FOLDER, file_name), "rb") as f:
		return f.read().decode("utf-8-sig")


def make_klaes_item(full_item_number, quantity=1, **changes):
	"""One item of a Klaes JSON, with the fields the import uses. `changes` overrides any field."""
	klaes_item = {
		"full_item_number": full_item_number,
		"item_number": "1",
		"template": TEST_TEMPLATE,
		"item_group_name": "FG - Test",
		"short_description": "Test window",
		"long_description": "Test window||H:1200.5 mm x W:900 mm||_Test White||",
		"height": 1200.5,
		"width": 900,
		"color": "_Test White",
		"OPTION_YN_colonial": True,
		"quantity": quantity,
	}
	klaes_item.update(changes)
	return klaes_item


def get_or_create(doctype, name_field, values):
	"""
	Return the ID of the record whose `name_field` is values[name_field], creating it if needed.

	The ID is not always the name we give: on sites using a naming series,
	a record gets an ID like "C26-00002" instead of its name.
	"""
	existing = frappe.db.get_value(doctype, {name_field: values[name_field]})
	if existing:
		return existing
	return frappe.get_doc({"doctype": doctype, **values}).insert().name


def get_attributes(item_code):
	"""Return {attribute: value} of an item."""
	return {row.attribute: row.attribute_value for row in frappe.get_doc("Item", item_code).attributes}


class IntegrationTestKlaesImport(IntegrationTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()

		# The Klaes Doc Number field comes from the app's fixtures, imported by migrate
		for doctype in ("Quotation", "Sales Order"):
			if not frappe.get_meta(doctype).has_field("klaes_doc_number"):
				raise RuntimeError(f"Field klaes_doc_number missing on {doctype}: run bench migrate first.")

		get_or_create(
			"Item Group",
			"item_group_name",
			{"item_group_name": TEST_ITEM_GROUP, "parent_item_group": "All Item Groups"},
		)

	# ---- helpers -------------------------------------------------------------

	def make_klaes_json(self, klaes_items, doc_type="Order", doc_number=ORDER_NUMBER):
		"""Build a Klaes JSON (same layout as the real export) with the given items."""
		return json.dumps(
			{
				"Document": {
					"doc_type": doc_type,
					"doc_number": doc_number,
					"item": klaes_items,
				}
			}
		)

	def make_klaes_import(self, json_data):
		"""Create a Klaes Import record, like klaes_sender does."""
		return frappe.get_doc(
			{
				"doctype": "Klaes Import",
				"doc_number": "TEST",
				"json_data": json_data,
			}
		).insert()

	def process(self, klaes_import):
		"""Run the processing (what the background job does) and reload the record."""
		process_import(klaes_import.name)
		klaes_import.reload()
		return klaes_import

	def import_items(self, klaes_items, **json_options):
		"""Import a Klaes JSON with these items and return the reloaded Klaes Import."""
		return self.process(self.make_klaes_import(self.make_klaes_json(klaes_items, **json_options)))

	# ---- step 2: Quotation or Sales Order ----------------------------------------

	def test_order_creates_draft_sales_order(self):
		klaes_import = self.import_items([make_klaes_item("_Test-KL-ORDER-1", 2)])

		self.assertEqual(klaes_import.status, "Done", klaes_import.error_message)
		self.assertEqual(klaes_import.doc_type, "Order")
		self.assertEqual(klaes_import.doc_number, ORDER_NUMBER)
		self.assertTrue(klaes_import.sales_order)
		self.assertFalse(klaes_import.quotation)

		order = frappe.get_doc("Sales Order", klaes_import.sales_order)
		self.assertEqual(order.docstatus, 0)  # Draft, never submitted
		self.assertEqual(order.customer, GENERIC_CUSTOMER)
		self.assertEqual(order.klaes_doc_number, ORDER_NUMBER)
		self.assertEqual(len(order.items), 1)
		self.assertEqual(order.items[0].item_code, "_Test-KL-ORDER-1")
		self.assertEqual(order.items[0].qty, 2)

	def test_quotation_creates_draft_quotation(self):
		klaes_import = self.import_items(
			[make_klaes_item("_Test-KL-QUOT-1", 3)], doc_type="Quotation", doc_number=QUOTATION_NUMBER
		)

		self.assertEqual(klaes_import.status, "Done", klaes_import.error_message)
		self.assertEqual(klaes_import.doc_type, "Quotation")
		self.assertEqual(klaes_import.doc_number, QUOTATION_NUMBER)
		self.assertTrue(klaes_import.quotation)
		self.assertFalse(klaes_import.sales_order)

		quotation = frappe.get_doc("Quotation", klaes_import.quotation)
		self.assertEqual(quotation.docstatus, 0)  # Draft, never submitted
		self.assertEqual(quotation.quotation_to, "Customer")
		self.assertEqual(quotation.party_name, GENERIC_CUSTOMER)
		self.assertEqual(quotation.klaes_doc_number, QUOTATION_NUMBER)
		self.assertEqual(len(quotation.items), 1)
		self.assertEqual(quotation.items[0].item_code, "_Test-KL-QUOT-1")
		self.assertEqual(quotation.items[0].qty, 3)

	def test_doc_type_with_spaces_is_accepted(self):
		klaes_import = self.import_items([make_klaes_item("_Test-KL-SPACES-1")], doc_type=" Order ")

		self.assertEqual(klaes_import.status, "Done", klaes_import.error_message)
		self.assertEqual(klaes_import.doc_type, "Order")

	def test_unknown_doc_type_sets_error(self):
		klaes_import = self.import_items([make_klaes_item("_Test-KL-TYPE-1")], doc_type="Invoice")

		self.assertEqual(klaes_import.status, "Error")
		self.assertIn("Unknown Klaes document type", klaes_import.error_message)

	def test_quotation_with_order_number_sets_error(self):
		klaes_import = self.import_items(
			[make_klaes_item("_Test-KL-MISMATCH-1")], doc_type="Quotation", doc_number=ORDER_NUMBER
		)

		self.assertEqual(klaes_import.status, "Error")
		self.assertIn("does not match", klaes_import.error_message)
		self.assertFalse(klaes_import.quotation)

	def test_order_with_quotation_number_sets_error(self):
		klaes_import = self.import_items(
			[make_klaes_item("_Test-KL-MISMATCH-2")], doc_type="Order", doc_number=QUOTATION_NUMBER
		)

		self.assertEqual(klaes_import.status, "Error")
		self.assertIn("does not match", klaes_import.error_message)
		self.assertFalse(klaes_import.sales_order)

	# ---- step 3: items as variants of their template --------------------------------

	def test_creates_template_and_attributes(self):
		template = "_Test Klaes Template NEW"
		klaes_import = self.import_items([make_klaes_item("_Test-KL-TPL-1", template=template)])
		self.assertEqual(klaes_import.status, "Done", klaes_import.error_message)

		for attribute in ATTRIBUTES:
			self.assertTrue(frappe.db.exists("Item Attribute", attribute))

		template_item = frappe.get_doc("Item", template)
		self.assertEqual(template_item.has_variants, 1)
		self.assertEqual([row.attribute for row in template_item.attributes], ATTRIBUTES)
		numeric = {row.attribute for row in template_item.attributes if row.numeric_values}
		self.assertEqual(numeric, {HEIGHT, WIDTH})
		# "FG - Test" does not exist in ERPNext, so the template goes to the root group
		self.assertEqual(template_item.item_group, "All Item Groups")

	def test_template_uses_item_group_of_the_json(self):
		template = "_Test Klaes Template GROUP"
		klaes_import = self.import_items(
			[make_klaes_item("_Test-KL-GROUP-1", template=template, item_group_name=TEST_ITEM_GROUP)]
		)
		self.assertEqual(klaes_import.status, "Done", klaes_import.error_message)

		self.assertEqual(frappe.db.get_value("Item", template, "item_group"), TEST_ITEM_GROUP)
		# the variant copies its template's group
		self.assertEqual(frappe.db.get_value("Item", "_Test-KL-GROUP-1", "item_group"), TEST_ITEM_GROUP)

	def test_creates_variant_with_attributes(self):
		klaes_import = self.import_items([make_klaes_item("_Test-KL-VAR-1")])
		self.assertEqual(klaes_import.status, "Done", klaes_import.error_message)

		item = frappe.get_doc("Item", "_Test-KL-VAR-1")
		self.assertEqual(item.variant_of, TEST_TEMPLATE)
		self.assertEqual(item.item_name, "Test window")
		self.assertEqual(item.description, "Test window<br>H:1200.5 mm x W:900 mm<br>_Test White")
		self.assertEqual(
			get_attributes("_Test-KL-VAR-1"),
			{
				FULL_ITEM_NUMBER: "_Test-KL-VAR-1",
				HEIGHT: "1200.5",
				WIDTH: "900.0",
				COLOR: "_Test White",
				COLONIAL: "Yes",
			},
		)

	def test_colonial_null_or_false_is_no(self):
		klaes_import = self.import_items(
			[
				make_klaes_item("_Test-KL-COLONIAL-1", OPTION_YN_colonial=None),
				make_klaes_item("_Test-KL-COLONIAL-2", OPTION_YN_colonial=False),
			]
		)
		self.assertEqual(klaes_import.status, "Done", klaes_import.error_message)

		self.assertEqual(get_attributes("_Test-KL-COLONIAL-1")[COLONIAL], "No")
		self.assertEqual(get_attributes("_Test-KL-COLONIAL-2")[COLONIAL], "No")

	def test_new_color_is_added_to_the_list(self):
		klaes_import = self.import_items([make_klaes_item("_Test-KL-COLOR-1", color="_Test Purple")])
		self.assertEqual(klaes_import.status, "Done", klaes_import.error_message)

		self.assertTrue(
			frappe.db.exists("Item Attribute Value", {"parent": COLOR, "attribute_value": "_Test Purple"})
		)
		self.assertEqual(get_attributes("_Test-KL-COLOR-1")[COLOR], "_Test Purple")

	def test_existing_variant_is_updated(self):
		first = self.import_items([make_klaes_item("_Test-KL-UPDATE-1", height=1000)])
		self.assertEqual(first.status, "Done", first.error_message)

		# Klaes sends the same item again, with another height and color
		second = self.import_items(
			[make_klaes_item("_Test-KL-UPDATE-1", height=1500, color="_Test Black")],
			doc_number="O-TEST-UNIT-002",
		)
		self.assertEqual(second.status, "Done", second.error_message)

		attributes = get_attributes("_Test-KL-UPDATE-1")
		self.assertEqual(attributes[HEIGHT], "1500.0")
		self.assertEqual(attributes[COLOR], "_Test Black")
		self.assertEqual(frappe.db.count("Item", {"item_code": "_Test-KL-UPDATE-1"}), 1)

	def test_existing_item_not_a_variant_sets_error(self):
		frappe.get_doc(
			{
				"doctype": "Item",
				"item_code": "_Test-KL-PLAIN-1",
				"item_group": "All Item Groups",
				"stock_uom": "Nos",
			}
		).insert()

		klaes_import = self.import_items([make_klaes_item("_Test-KL-PLAIN-1")])

		self.assertEqual(klaes_import.status, "Error")
		self.assertIn("is not a variant of template", klaes_import.error_message)

	def test_template_that_is_not_a_template_sets_error(self):
		frappe.get_doc(
			{
				"doctype": "Item",
				"item_code": "_Test Klaes Not A Template",
				"item_group": "All Item Groups",
				"stock_uom": "Nos",
			}
		).insert()

		klaes_import = self.import_items(
			[make_klaes_item("_Test-KL-NOTPL-1", template="_Test Klaes Not A Template")]
		)

		self.assertEqual(klaes_import.status, "Error")
		self.assertIn("is not a template", klaes_import.error_message)

	def test_missing_template_sets_error(self):
		klaes_import = self.import_items([make_klaes_item("_Test-KL-NOTEMPLATE-1", template="")])

		self.assertEqual(klaes_import.status, "Error")
		self.assertIn("has no template", klaes_import.error_message)

	def test_error_creates_nothing(self):
		# The 1st item is fine, the 2nd one fails: the 1st item must not be left behind
		klaes_import = self.import_items(
			[
				make_klaes_item("_Test-KL-ROLLBACK-1"),
				make_klaes_item("_Test-KL-ROLLBACK-2", template=""),
			]
		)

		self.assertEqual(klaes_import.status, "Error")
		self.assertFalse(frappe.db.exists("Item", "_Test-KL-ROLLBACK-1"))
		self.assertFalse(frappe.db.exists("Item Attribute Value", {"attribute_value": "_Test-KL-ROLLBACK-1"}))

	# ---- real Klaes files (test_data/ folder) --------------------------------------

	def check_lines(self, erpnext_document, klaes_items):
		"""Check one line per Klaes item, in the same order, with the same item and quantity."""
		self.assertEqual(len(erpnext_document.items), len(klaes_items))
		for line, klaes_item in zip(erpnext_document.items, klaes_items, strict=True):
			self.assertEqual(line.item_code, klaes_item["full_item_number"])
			self.assertEqual(line.qty, klaes_item["quantity"])

	def check_variants(self, klaes_items):
		"""Check that every Klaes item is a variant of its template."""
		for klaes_item in klaes_items:
			item_code = klaes_item["full_item_number"]
			self.assertEqual(frappe.db.get_value("Item", item_code, "variant_of"), klaes_item["template"])
			self.assertEqual(get_attributes(item_code)[FULL_ITEM_NUMBER], item_code)

	def test_real_klaes_quotation_file(self):
		klaes_json = read_test_file("Q241023-001A_ItemsList.JSON")
		klaes_items = json.loads(klaes_json)["Document"]["item"]

		klaes_import = self.process(self.make_klaes_import(klaes_json))

		self.assertEqual(klaes_import.status, "Done", klaes_import.error_message)
		self.assertEqual(klaes_import.doc_type, "Quotation")
		self.assertEqual(klaes_import.doc_number, "Q241023-001A")

		quotation = frappe.get_doc("Quotation", klaes_import.quotation)
		self.assertEqual(quotation.docstatus, 0)  # Draft
		self.assertEqual(quotation.klaes_doc_number, "Q241023-001A")
		self.check_lines(quotation, klaes_items)  # 49 items in this file
		self.check_variants(klaes_items)  # all variants of ALU-NSHWIN-001

		# The 1st item of the file: H 1828.8 x W 1219.2, White Powder Coat, colonial
		self.assertEqual(
			get_attributes("ALU-NSHWIN-001_Q241023-001A-2"),
			{
				FULL_ITEM_NUMBER: "ALU-NSHWIN-001_Q241023-001A-2",
				HEIGHT: "1828.8",
				WIDTH: "1219.2",
				COLOR: "White Powder Coat",
				COLONIAL: "Yes",
			},
		)

	def test_real_klaes_order_file(self):
		klaes_json = read_test_file("O241023-001B_ItemsList.JSON")
		klaes_items = json.loads(klaes_json)["Document"]["item"]

		klaes_import = self.process(self.make_klaes_import(klaes_json))

		self.assertEqual(klaes_import.status, "Done", klaes_import.error_message)
		self.assertEqual(klaes_import.doc_type, "Order")
		self.assertEqual(klaes_import.doc_number, "O241023-001B")

		order = frappe.get_doc("Sales Order", klaes_import.sales_order)
		self.assertEqual(order.docstatus, 0)  # Draft
		self.assertEqual(order.klaes_doc_number, "O241023-001B")
		self.check_lines(order, klaes_items)  # 2 items, quantities 2 and 3
		self.check_variants(klaes_items)

	# ---- other errors ------------------------------------------------------------

	def test_no_items_sets_error(self):
		klaes_import = self.import_items([])

		self.assertEqual(klaes_import.status, "Error")
		self.assertIn("no items", klaes_import.error_message)

	def test_empty_json_sets_error(self):
		klaes_import = self.process(self.make_klaes_import(""))

		self.assertEqual(klaes_import.status, "Error")
		self.assertIn("No JSON data", klaes_import.error_message)

	# ---- generic customer -------------------------------------------------------

	def test_generic_customer(self):
		self.assertEqual(create_generic_customer(), GENERIC_CUSTOMER)
		self.assertEqual(
			frappe.db.get_value("Customer", GENERIC_CUSTOMER, "customer_name"), GENERIC_CUSTOMER_NAME
		)
		# Calling it again does not create a second customer
		self.assertEqual(create_generic_customer(), GENERIC_CUSTOMER)
		self.assertEqual(frappe.db.count("Customer", {"customer_name": GENERIC_CUSTOMER_NAME}), 1)

	def test_import_uses_the_generic_customer(self):
		klaes_import = self.import_items([make_klaes_item("_Test-KL-CUSTOMER-1")])

		self.assertEqual(klaes_import.status, "Done", klaes_import.error_message)
		self.assertEqual(klaes_import.customer, GENERIC_CUSTOMER)
		self.assertEqual(
			frappe.db.get_value("Sales Order", klaes_import.sales_order, "customer"), GENERIC_CUSTOMER
		)

	# ---- Process again ---------------------------------------------------------

	def test_process_again_after_fixing_the_json(self):
		klaes_import = self.import_items([make_klaes_item("_Test-KL-AGAIN-1", template="")])
		self.assertEqual(klaes_import.status, "Error")

		# Someone fixes the JSON, then clicks "Process again"
		klaes_import.db_set("json_data", self.make_klaes_json([make_klaes_item("_Test-KL-AGAIN-1")]))
		klaes_import.reload()
		klaes_import.process_again()
		klaes_import.reload()

		self.assertEqual(klaes_import.status, "Done", klaes_import.error_message)
		self.assertTrue(klaes_import.sales_order)

	def test_process_again_refuses_when_done(self):
		klaes_import = self.import_items([make_klaes_item("_Test-KL-DONE-1")])
		self.assertEqual(klaes_import.status, "Done", klaes_import.error_message)

		# A second click must not create a second document
		with self.assertRaises(frappe.ValidationError):
			klaes_import.process_again()
