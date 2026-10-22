# Copyright (c) 2026, Pierrick BLAISE and Contributors
# See license.txt

"""
Tests for Klaes Import (step 1: draft Sales Order with existing items).

Run them with:
    bench --site <site> run-tests --doctype "Klaes Import" --skip-before-tests

Everything created by these tests is rolled back at the end (IntegrationTestCase).
"""

import json

import frappe
from frappe.tests import IntegrationTestCase

from erpnext_klaes.erpnext_klaes.doctype.klaes_import.klaes_import import process_import

# Do not load the standard ERPNext test records for these links:
# the tests create the only Customer and Item they need (see setUpClass).
EXTRA_TEST_RECORD_DEPENDENCIES = []
IGNORE_TEST_RECORD_DEPENDENCIES = ["Customer", "Sales Order"]

UNKNOWN_ITEM = "_Test Item That Does Not Exist"


def get_or_create(doctype, name_field, values):
	"""
	Return the ID of the record whose `name_field` is values[name_field], creating it if needed.

	The ID is not always the name we give: on sites using a naming series,
	a customer called "_Test Klaes Customer" gets an ID like "C26-00002".
	"""
	existing = frappe.db.get_value(doctype, {name_field: values[name_field]})
	if existing:
		return existing
	return frappe.get_doc({"doctype": doctype, **values}).insert().name


class IntegrationTestKlaesImport(IntegrationTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()

		cls.customer = get_or_create(
			"Customer",
			"customer_name",
			{
				"customer_name": "_Test Klaes Customer",
				"territory": "All Territories",
			},
		)

		# Not a stock item, so the order does not need a warehouse
		cls.item = get_or_create(
			"Item",
			"item_name",
			{
				"item_code": "_Test Klaes Item",
				"item_name": "_Test Klaes Item",
				"item_group": "All Item Groups",
				"stock_uom": "Nos",
				"is_stock_item": 0,
			},
		)

	# ---- helpers -------------------------------------------------------------

	def make_klaes_json(self, items):
		"""Build a Klaes JSON (same layout as the real export) with the given (item_code, quantity)."""
		return json.dumps(
			{
				"Document": {
					"doc_type": "Quotation",
					"doc_number": "TEST-UNIT-001",
					"customer_number": self.customer,
					"item": [
						{"SAP_Item_Number": item_code, "item_number": str(i + 1), "quantity": qty}
						for i, (item_code, qty) in enumerate(items)
					],
				}
			}
		)

	def make_klaes_import(self, json_data, with_customer=True):
		"""Create a Klaes Import record, like klaes_sender does."""
		return frappe.get_doc(
			{
				"doctype": "Klaes Import",
				"doc_number": "TEST-UNIT-001",
				"customer": self.customer if with_customer else None,
				"json_data": json_data,
			}
		).insert()

	def process(self, klaes_import):
		"""Run the processing (what the background job does) and reload the record."""
		process_import(klaes_import.name)
		klaes_import.reload()
		return klaes_import

	# ---- tests ---------------------------------------------------------------

	def test_creates_draft_sales_order_with_items(self):
		klaes_import = self.process(self.make_klaes_import(self.make_klaes_json([(self.item, 2)])))

		self.assertEqual(klaes_import.status, "Done", klaes_import.error_message)
		self.assertTrue(klaes_import.sales_order)

		order = frappe.get_doc("Sales Order", klaes_import.sales_order)
		self.assertEqual(order.docstatus, 0)  # Draft, never submitted
		self.assertEqual(order.customer, self.customer)
		self.assertEqual(len(order.items), 1)
		self.assertEqual(order.items[0].item_code, self.item)
		self.assertEqual(order.items[0].qty, 2)

	def test_unknown_item_sets_error(self):
		klaes_import = self.process(self.make_klaes_import(self.make_klaes_json([(UNKNOWN_ITEM, 1)])))

		self.assertEqual(klaes_import.status, "Error")
		self.assertIn("does not exist", klaes_import.error_message)
		self.assertFalse(klaes_import.sales_order)

	def test_no_items_sets_error(self):
		klaes_import = self.process(self.make_klaes_import(self.make_klaes_json([])))

		self.assertEqual(klaes_import.status, "Error")
		self.assertIn("no items", klaes_import.error_message)

	def test_empty_json_sets_error(self):
		klaes_import = self.process(self.make_klaes_import(""))

		self.assertEqual(klaes_import.status, "Error")
		self.assertIn("No JSON data", klaes_import.error_message)

	def test_no_customer_sets_error(self):
		klaes_import = self.process(
			self.make_klaes_import(self.make_klaes_json([(self.item, 1)]), with_customer=False)
		)

		self.assertEqual(klaes_import.status, "Error")
		self.assertIn("No customer", klaes_import.error_message)

	def test_process_again_after_fixing_the_json(self):
		klaes_import = self.process(self.make_klaes_import(self.make_klaes_json([(UNKNOWN_ITEM, 1)])))
		self.assertEqual(klaes_import.status, "Error")

		# Someone fixes the JSON, then clicks "Process again"
		klaes_import.db_set("json_data", self.make_klaes_json([(self.item, 1)]))
		klaes_import.reload()
		klaes_import.process_again()
		klaes_import.reload()

		self.assertEqual(klaes_import.status, "Done", klaes_import.error_message)
		self.assertTrue(klaes_import.sales_order)

	def test_process_again_refuses_when_done(self):
		klaes_import = self.process(self.make_klaes_import(self.make_klaes_json([(self.item, 1)])))
		self.assertEqual(klaes_import.status, "Done", klaes_import.error_message)

		# A second click must not create a second Sales Order
		with self.assertRaises(frappe.ValidationError):
			klaes_import.process_again()
