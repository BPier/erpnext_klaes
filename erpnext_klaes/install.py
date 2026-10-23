"""
Things done when the app is installed and after each `bench migrate`.

Hooked in hooks.py:
    after_install = "erpnext_klaes.install.after_install"
    after_migrate = "erpnext_klaes.install.after_migrate"
"""

import frappe

# The generic customer used for every Klaes import (Quotation / Sales Order).
# The sales team sets the real customer on the draft document in ERPNext.
GENERIC_CUSTOMER = "C99-9999"  # ID of the customer
GENERIC_CUSTOMER_NAME = "klaes import"  # Customer Name


def after_install():
	create_generic_customer()


def after_migrate():
	create_generic_customer()


def create_generic_customer():
	"""Create the generic Klaes customer if it does not exist yet. Returns its ID."""
	if frappe.db.exists("Customer", GENERIC_CUSTOMER):
		return GENERIC_CUSTOMER

	# Before the ERPNext setup wizard, defaults (customer group, territory) are missing:
	# the customer is then created later, by the first Klaes import.
	if not frappe.is_setup_complete():
		return None

	customer = frappe.new_doc("Customer")
	customer.customer_name = GENERIC_CUSTOMER_NAME
	customer.customer_type = "Company"
	# Fixed ID instead of the next number of the customer naming series
	customer.insert(ignore_permissions=True, set_name=GENERIC_CUSTOMER)
	return customer.name
