### Erpnext Klaes

Link ERPNext with Klaes (windows and doors software). Made for **ERPNext / Frappe v16**.

This repository contains two parts:

| Folder | Runs on | What it is |
|---|---|---|
| `erpnext_klaes/` | ERPNext server | The Frappe app, with one DocType: **Klaes Import**. |
| `klaes_sender/` | Windows Server 2019 (Klaes machine) or any machine that run python3 | A small program, `klaes_sender.exe`, that Klaes runs after exporting a JSON file. |

```
erpnext_klaes/                       ← this repository (branch version-16)
├── pyproject.toml                   ← app info + supported Frappe/ERPNext versions
├── README.md
├── license.txt
├── .gitignore
├── erpnext_klaes/                   ← the Frappe app (installed on the server)
│   ├── hooks.py
│   ├── modules.txt
│   ├── fixtures/custom_field.json   ← "Klaes Doc Number" field on Quotation and Sales Order
│   └── erpnext_klaes/doctype/klaes_import/
│       ├── klaes_import.json        ← fields of the Klaes Import DocType
│       ├── klaes_import.py          ← ALL the processing logic
│       └── klaes_import.js          ← "Process again" button
└── klaes_sender/                    ← the Windows program (not installed on the server)
    ├── klaes_sender.py
    ├── config.example.ini
    ├── sample_order.json            ← test file (one item that exists in ERPNext)
    └── build_exe.bat
```

`bench get-app` downloads the whole repository, but only the inner `erpnext_klaes/` folder is
installed as the app. The `klaes_sender/` folder is only stored here, so both parts stay together
in Git.

### How it works

```
Klaes ──JSON file──> klaes_sender.exe ──HTTPS (standard REST API)──> ERPNext
                         │                                              │
                     config.ini                             new "Klaes Import" record
                     klaes_sender.log                                   │
                                                          background job (process_import)
                                                                        │
                                    draft Quotation or Sales Order with items + Status Done/Error
```

1. The exe creates a **Klaes Import** record with Frappe's built-in REST API
   (`POST /api/resource/Klaes Import`). No custom endpoint is needed.
2. Once the record is saved, ERPNext processes it in the background.
3. The result is visible in ERPNext, in the **Klaes Import** list:
   - **Done**: the Quotation or Sales Order field links to the created document.
   - **Error**: the Error Message field explains why. Fix the cause, then click **Process again**.
     Technical details are also in ERPNext's standard **Error Log**.
4. The JSON received from Klaes is kept on each record, so it can always be checked or reprocessed.

The Windows side uses only **standard Python** (no extra libraries).

---

### Installation

You can install this app using the [bench](https://github.com/frappe/bench) CLI:

```bash
cd $PATH_TO_YOUR_BENCH
bench get-app $URL_OF_THIS_REPO --branch version-16
bench --site erpnext-dev.saintlu.lc install-app erpnext_klaes
bench --site erpnext-dev.saintlu.lc migrate
bench restart
```

If the app is already installed, update it instead:

```bash
cd $PATH_TO_YOUR_BENCH
bench update --apps erpnext_klaes   # or: cd apps/erpnext_klaes && git pull
bench --site erpnext-dev.saintlu.lc migrate
bench restart
```

(If ERPNext is hosted on Frappe Cloud: add the app from the repository in the dashboard, then install it on the site.)

After installing, search for **Klaes Import** in the ERPNext search bar: the list should open (empty).

---

### Steps 1 and 2 — create a draft Quotation or Sales Order with its items  ← current step

`doc_type` and `doc_number` in the JSON decide which document is created. They must agree:

| `doc_type` in the JSON | `doc_number` must start with | ERPNext creates |
|---|---|---|
| `Quotation` | `Q` (e.g. `Q241023-001A`) | a draft **Quotation** |
| `Order` | `O` (e.g. `O260909-0201`) | a draft **Sales Order** |

Anything else (another `doc_type`, or a number that does not match) gives an **Error**, and nothing is created.

- The document is saved as **Draft** (never submitted). A Sales Order is then made from the Quotation
  in ERPNext, with the standard **Create → Sales Order** button.
- The Klaes number is saved in the **Klaes Doc Number** field (`klaes_doc_number`) of the Quotation or Sales Order
  (you can filter lists on it). It is carried over when a Sales Order is made from the Quotation.
- One line per item of the JSON: Item Code = `SAP_Item_Number`, Quantity = `quantity`.
  ERPNext fills in the rest (name, unit, price, warehouse).
- The items must **already exist** in ERPNext. Creating new items is step 3, so the real Klaes
  files (with items like `ALU-NSHWIN-001_Q241023-001A-2`) will fail until then: use `sample_order.json` to test.
- The customer comes from `config.ini` (`test_customer`), not from the JSON yet.

After updating the app, run `bench --site <site> migrate`: it adds the new fields to Klaes Import
and creates the **Klaes Doc Number** field on Quotation and Sales Order.

This field is a standard Frappe **fixture**: it is stored in `erpnext_klaes/fixtures/custom_field.json`
(declared by `fixtures` in `hooks.py`) and imported by every `install-app` and `migrate`. To change it:

1. On the dev site, change the field in **Customize Form** (Quotation or Sales Order).
   Keep its **Module** set to `Erpnext Klaes`.
2. Export it back to the app, then commit the JSON file:
   ```bash
   bench --site erpnext-dev.saintlu.lc export-fixtures --app erpnext_klaes
   ```

#### 1. Create an API user in ERPNext

1. Create a user, e.g. `klaes@saintlu.lc`, with the role **Sales User**
   (this role can create Klaes Import records, Quotations and Sales Orders).
2. Open the user → **Settings** → **API Access** → **Generate Keys**.
3. Copy the **API Key** and **API Secret** (the secret is shown only once).

#### 2. Configure klaes_sender

The settings are in a file called **`config.ini`**, which must be in the **same folder** as
`klaes_sender.exe` (or `klaes_sender.py`).

`config.ini` contains the API secret, so it is **not stored in Git** (see `.gitignore`).
The repository only contains an example, `config.example.ini`:

1. Copy `config.example.ini` to `config.ini` (same folder).
2. Open `config.ini` with a text editor and fill in the values:

```ini
[erpnext]
url = https://erpnext-dev.saintlu.lc
api_key = 1a2b3c4d5e6f7g8
api_secret = 9h8g7f6e5d4c3b2
test_customer = C22-0012
```

| Setting | What to put |
|---|---|
| `url` | Address of the ERPNext site (dev or production) |
| `api_key` | API Key of the Klaes user (step 1) |
| `api_secret` | API Secret of the Klaes user (step 1) |
| `test_customer` | **Step 1 only:** the ID of a Customer that exists in ERPNext |

To switch from the dev site to production later, only `url`, `api_key` and `api_secret` change.

Then open `sample_order.json` and replace `PUT_EXISTING_ITEM_CODE_HERE` with the **Item Code of an
item that exists in ERPNext** (Stock → Item). You can change `quantity` too, or add more items.

#### 3. Test from Linux (optional, quickest)

Any machine with Python 3 can run the program directly, without building the exe:

```bash
cd klaes_sender
cp config.example.ini config.ini      # then edit config.ini
python3 klaes_sender.py                  # sends sample_order.json
python3 klaes_sender.py my_file.json     # sends another JSON file
echo $?                                  # 0 = OK, 1 = error
```

#### 4. Build the exe and install it on Windows Server 2019

On any Windows machine with Python installed:

1. Copy the `klaes_sender` folder.
2. Double-click `build_exe.bat`.
3. The `dist` folder now contains `klaes_sender.exe`, `config.example.ini` and `sample_order.json`.

On the Windows server:

1. Copy `klaes_sender.exe`, `config.example.ini` and `sample_order.json` to a folder, e.g. `C:\KlaesSender\`.
2. Create `config.ini` and edit `sample_order.json`, as explained in step 2.
3. **Test** (no file given, so it sends `sample_order.json`): open a command prompt and run
   ```
   C:\KlaesSender\klaes_sender.exe
   ```
   Expected: `Klaes Import created: KLAES-00002 (Q-TEST-001)`
4. In ERPNext, open **Klaes Import**: the record should have status **Done** after a few seconds,
   with a link to a new **Draft** Quotation containing the sample item, and **Klaes Doc Number** `Q-TEST-001`.
   To test a Sales Order, change `sample_order.json` to `"doc_type": "Order"` and a number starting with `O`.
5. Later (from step 3), Klaes will run the program after each export, with the JSON file path as argument:
   ```
   C:\KlaesSender\klaes_sender.exe "C:\path\to\Q241023-001A_ItemsList.JSON"
   ```

#### If something fails

On the sender side, read `klaes_sender.log` (same folder as the program):

| Message in the log | Meaning |
|---|---|
| `Config file not found` | Create `config.ini` from `config.example.ini` (step 2) |
| `HTTP 401` / `HTTP 403` | API key/secret wrong, or user lacks the Sales User role |
| `HTTP 404` | App not installed on the site, or `migrate` / `bench restart` not done |
| `URLError` / timeout | This machine cannot reach the ERPNext URL (firewall/proxy) |

On the ERPNext side, open the Klaes Import record:

| What you see | Meaning |
|---|---|
| Status **Error**, e.g. `Customer ... not found` | Fix the cause, then click **Process again** |
| `Unknown Klaes document type '...'` | `doc_type` in the JSON must be `Quotation` or `Order` |
| `Klaes document type '...' does not match document number '...'` | A Quotation number must start with `Q`, an Order number with `O` |
| `Item '...' does not exist in ERPNext` | Put an existing Item Code in the JSON (step 1 does not create items) |
| `Delivery warehouse required for stock item ...` | Set a default warehouse on the item, or in Stock Settings |
| Status stays **Pending** | Background workers are not running on the server (`bench doctor` to check) |

---

### Tests

The tests are in `erpnext_klaes/erpnext_klaes/doctype/klaes_import/test_klaes_import.py`:

```bash
bench --site dev.localhost set-config allow_tests true   # first time only
bench --site dev.localhost run-tests --app erpnext_klaes
```

- Everything the tests create (customer, items, quotations, orders) is **rolled back** at the end.
- Run `migrate` before the tests: they need the **Klaes Doc Number** field.
- **Real Klaes files** are in the `test_data/` folder next to the tests, and are imported exactly as Klaes
  sends them: `Q241023-001A_ItemsList.JSON` (a real Klaes quotation, 49 items) and
  `O241023-001_ItemsList.JSON` (an order in the same layout, 2 items).
  To test a new Klaes file (for example one that caused a problem), put it in `test_data/`
  and copy one of the `test_real_klaes_..._file` tests.

---

### Next steps (one at a time, each tested before the next)

3. Create the items that do not exist yet (`SAP_Item_Number`, descriptions, item group).
4. Read `customer_number` from the JSON instead of `config.ini`.
5. Create the BOM of each item from `bill_of_material`.
6. Daily XML file of validated orders, emailed to the production manager.

---

### Contributing

This app uses `pre-commit` for code formatting and linting. Please [install pre-commit](https://pre-commit.com/#installation) and enable it for this repository:

```bash
cd apps/erpnext_klaes
pre-commit install
```

Pre-commit is configured to use the following tools for checking and formatting your code:

- ruff
- eslint
- prettier
- pyupgrade

### License

mit
