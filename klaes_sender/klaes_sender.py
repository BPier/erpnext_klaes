"""
klaes_sender - sends a Klaes JSON file to ERPNext.

Usage (Klaes runs this after generating the JSON file):
    klaes_sender.exe "C:\\path\\to\\file.JSON"

Without a file path, it sends sample_order.json (next to the program),
useful to test the connection. Edit it so it uses an item that exists in ERPNext.

The program creates a "Klaes Import" record in ERPNext with the standard
Frappe REST API. ERPNext then processes it (creates the draft Sales Order).
The result is visible in ERPNext: Klaes Import list > Status.

All settings are in config.ini, in the same folder as this program.
Everything that happens is written to klaes_sender.log, in the same folder.

Exit code: 0 = sent to ERPNext, 1 = error (Klaes can check this).
"""

import configparser
import json
import logging
import os
import sys
import urllib.error
import urllib.parse
import urllib.request

# Folder where the .exe (or the .py) is located
if getattr(sys, "frozen", False):
	APP_FOLDER = os.path.dirname(sys.executable)
else:
	APP_FOLDER = os.path.dirname(os.path.abspath(__file__))

CONFIG_FILE = os.path.join(APP_FOLDER, "config.ini")
LOG_FILE = os.path.join(APP_FOLDER, "klaes_sender.log")
SAMPLE_FILE = os.path.join(APP_FOLDER, "sample_order.json")

logging.basicConfig(
	filename=LOG_FILE,
	level=logging.INFO,
	format="%(asctime)s  %(levelname)s  %(message)s",
)
logger = logging.getLogger("klaes_sender")


class KlaesSenderError(Exception):
	"""An error in klaes_sender: the message is written to klaes_sender.log."""

def read_config():
	"""Read config.ini and return the [erpnext] section."""
	if not os.path.exists(CONFIG_FILE):
		raise KlaesSenderError(
			f"Config file not found: {CONFIG_FILE}. "
			"Copy config.example.ini to config.ini and fill in your settings."
		)
	config = configparser.ConfigParser()
	config.read(CONFIG_FILE, encoding="utf-8")
	return config["erpnext"]


def read_klaes_file(file_path):
	"""Return (doc_number, file content) of a Klaes JSON file."""
	with open(file_path, "rb") as f:
		raw = f.read()

	# Klaes files may be UTF-8 (with or without BOM) or Windows encoding
	try:
		content = raw.decode("utf-8-sig")
	except UnicodeDecodeError:
		content = raw.decode("cp1252")

	# Take the document number from the file, or the file name if not readable
	try:
		doc_number = json.loads(content)["Document"]["doc_number"]
	except Exception:
		doc_number = os.path.basename(file_path)

	return doc_number, content


def create_record(settings, doctype, data):
	"""
	Create a record in ERPNext with the standard REST API:
	    POST /api/resource/<doctype>
	Returns the name of the new record.
	"""
	url = settings["url"].rstrip("/") + "/api/resource/" + urllib.parse.quote(doctype)
	body = json.dumps(data).encode("utf-8")
	request = urllib.request.Request(url, data=body, method="POST")
	request.add_header("Content-Type", "application/json")
	request.add_header("Authorization", f"token {settings['api_key']}:{settings['api_secret']}")

	try:
		with urllib.request.urlopen(request, timeout=60) as response:
			answer = json.loads(response.read().decode("utf-8"))
	except urllib.error.HTTPError as error:
		# ERPNext answered with an error: put its message in the log
		details = error.read().decode("utf-8", errors="replace")
		raise KlaesSenderError(f"ERPNext refused the request (HTTP {error.code}): {details}")

	return answer["data"]["name"]


def main():
	logger.info("---- klaes_sender started ----")
	try:
		settings = read_config()

		if len(sys.argv) > 1:
			file_path = sys.argv[1]
		else:
			# No file given: send the test file next to the program
			file_path = SAMPLE_FILE
		logger.info(f"File: {file_path}")
		doc_number, content = read_klaes_file(file_path)

		record_name = create_record(
			settings,
			"Klaes Import",
			{
				"doc_number": doc_number,
				# STEP 1 only: customer comes from config.ini
				"customer": settings["test_customer"],
				"json_data": content,
			},
		)

		logger.info(f"Klaes Import created: {record_name} ({doc_number})")
		print(f"Klaes Import created: {record_name} ({doc_number})")
		return 0

	except Exception as error:
		logger.error(str(error))
		print(f"ERROR: {error}")
		return 1


if __name__ == "__main__":
	sys.exit(main())