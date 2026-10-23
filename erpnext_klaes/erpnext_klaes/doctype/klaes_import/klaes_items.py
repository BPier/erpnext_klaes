"""
Items of the Klaes JSON (step 3).

Each Klaes item becomes a VARIANT of its template (field "template" in the JSON):
- Item Code = full_item_number, Item Name = short_description, Description = long_description
- 5 attributes, read from the Klaes item (see get_attribute_values below)
- the variant copies the rest from its template (item group, unit...), as usual in ERPNext

If the item already exists, its attributes and description are updated from the new JSON.

Created automatically when missing:
- the 5 Item Attributes (Stock > Item Attribute)
- the template item: "Has Variants" ticked, with the 5 attributes,
  item group = item_group_name of the JSON if it exists in ERPNext, otherwise "All Item Groups"
- new values of the list attributes (each new full item number, each new color)
"""

import frappe
from erpnext.controllers.item_variant import create_variant
from frappe.utils import flt

# The 5 variant attributes (names of the Item Attributes in ERPNext)
FULL_ITEM_NUMBER = "Klaes Full Item Number"
HEIGHT = "Klaes Height"
WIDTH = "Klaes Width"
COLOR = "Klaes Color"
COLONIAL = "Klaes Colonial"
ATTRIBUTES = [FULL_ITEM_NUMBER, HEIGHT, WIDTH, COLOR, COLONIAL]

# Number attributes: no list of values, any number in this range (in mm, 2 decimals)
NUMBER_ATTRIBUTES = {HEIGHT, WIDTH}
NUMBER_RANGE = {"from_range": 0, "to_range": 100000, "increment": 0.01}

# List attributes with a fixed list (the others get new values added automatically)
FIXED_VALUES = {COLONIAL: ["Yes", "No"]}


def get_attribute_values(klaes_item):
	"""Return {attribute: value} of a Klaes item. Empty values are left out."""
	values = {
		FULL_ITEM_NUMBER: klaes_item["full_item_number"],
		HEIGHT: str(flt(klaes_item["height"])) if klaes_item.get("height") is not None else None,
		WIDTH: str(flt(klaes_item["width"])) if klaes_item.get("width") is not None else None,
		COLOR: klaes_item.get("color"),
		# true -> Yes, false or null -> No
		COLONIAL: "Yes" if klaes_item.get("OPTION_YN_colonial") else "No",
	}
	return {attribute: value for attribute, value in values.items() if value not in (None, "")}


def create_or_update_items(document):
	"""Create (or update) the variant of every item of the Klaes JSON."""
	for klaes_item in document.get("item", []):
		create_or_update_item(klaes_item)


def create_or_update_item(klaes_item):
	"""Create the variant of one Klaes item, or update it if it already exists."""
	item_code = klaes_item["full_item_number"]
	template = get_or_create_template(klaes_item)

	values = get_attribute_values(klaes_item)
	for attribute, value in values.items():
		add_attribute_value(attribute, value)

	if frappe.db.exists("Item", item_code):
		update_variant(item_code, template, values, klaes_item)
	else:
		create_new_variant(item_code, template, values, klaes_item)


def create_new_variant(item_code, template, values, klaes_item):
	# ERPNext's standard function: copies the template's fields into a new variant
	variant = create_variant(template, values)
	variant.item_code = item_code
	variant.item_name = klaes_item.get("short_description") or item_code
	variant.description = make_description(klaes_item)
	variant.insert()


def update_variant(item_code, template, values, klaes_item):
	item = frappe.get_doc("Item", item_code)
	if item.variant_of != template:
		frappe.throw(f"Item '{item_code}' already exists but is not a variant of template '{template}'.")

	item.set("attributes", [{"attribute": a, "attribute_value": v} for a, v in values.items()])
	item.description = make_description(klaes_item)
	item.save()


def make_description(klaes_item):
	"""Klaes separates the lines of long_description with "||": show one line each."""
	lines = [line.strip() for line in (klaes_item.get("long_description") or "").split("||")]
	return "<br>".join(line for line in lines if line) or klaes_item.get("short_description") or ""


# ---- templates -----------------------------------------------------------------


def get_or_create_template(klaes_item):
	"""Return the template of a Klaes item, after creating it (or checking it) if needed."""
	template = (klaes_item.get("template") or "").strip()
	if not template:
		frappe.throw(f"Item '{klaes_item['full_item_number']}' has no template in the Klaes JSON.")

	if frappe.db.exists("Item", template):
		check_template(template)
	else:
		create_template(template, klaes_item)

	return template


def check_template(template):
	item = frappe.get_doc("Item", template)
	if not item.has_variants:
		frappe.throw(f"Item '{template}' exists but is not a template: tick 'Has Variants' on it.")

	missing = [a for a in ATTRIBUTES if a not in {row.attribute for row in item.attributes}]
	if missing:
		frappe.throw(f"Template '{template}' is missing these attributes: {', '.join(missing)}.")


def create_template(template, klaes_item):
	for attribute in ATTRIBUTES:
		get_or_create_attribute(attribute)

	item_group = klaes_item.get("item_group_name")
	if not item_group or not frappe.db.exists("Item Group", item_group):
		item_group = "All Item Groups"

	item = frappe.new_doc("Item")
	item.item_code = template
	item.item_name = template
	item.item_group = item_group
	item.stock_uom = "Nos"
	item.has_variants = 1
	for attribute in ATTRIBUTES:
		row = {"attribute": attribute}
		if attribute in NUMBER_ATTRIBUTES:
			row.update(numeric_values=1, **NUMBER_RANGE)
		item.append("attributes", row)
	item.insert()

	if item.name != template:
		frappe.throw(
			f"Template '{template}' was created as '{item.name}'. "
			"In Stock Settings, set 'Item Naming By' to 'Item Code'."
		)


# ---- attributes ----------------------------------------------------------------


def get_or_create_attribute(attribute):
	"""Create an Item Attribute if it does not exist yet."""
	if frappe.db.exists("Item Attribute", attribute):
		return

	item_attribute = frappe.new_doc("Item Attribute")
	item_attribute.attribute_name = attribute
	if attribute in NUMBER_ATTRIBUTES:
		item_attribute.numeric_values = 1
		item_attribute.update(NUMBER_RANGE)
	for value in FIXED_VALUES.get(attribute, []):
		item_attribute.append("item_attribute_values", {"attribute_value": value, "abbr": value})
	item_attribute.insert()


def add_attribute_value(attribute, value):
	"""Add a value to a list attribute (e.g. a new full item number or a new color) if it is not there yet."""
	get_or_create_attribute(attribute)
	if attribute in NUMBER_ATTRIBUTES:
		return  # number attributes have no list of values

	if frappe.db.exists("Item Attribute Value", {"parent": attribute, "attribute_value": value}):
		return

	if attribute in FIXED_VALUES:
		allowed = " or ".join(FIXED_VALUES[attribute])
		frappe.throw(f"'{value}' is not a valid value for {attribute} (expected {allowed}).")

	item_attribute = frappe.get_doc("Item Attribute", attribute)
	item_attribute.append("item_attribute_values", {"attribute_value": value, "abbr": value})
	item_attribute.save()
