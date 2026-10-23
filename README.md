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
│   ├── install.py                   ← creates the generic customer "klaes import" (C99-9999)
│   ├── modules.txt
│   ├── fixtures/custom_field.json   ← "Klaes Doc Number" field on Quotation and Sales Order
│   └── erpnext_klaes/doctype/klaes_import/
│       ├── klaes_import.json        ← fields of the Klaes Import DocType
│       ├── klaes_import.py          ← the processing: Quotation or Sales Order
│       ├── klaes_items.py           ← the items: variants of their template
│       └── klaes_import.js          ← "Process again" button
└── klaes_sender/                    ← the Windows program (not installed on the server)
    ├── klaes_sender.py
    ├── config.example.ini
    ├── Samples/                     ← Klaes JSON files to test by hand
    │   └── sample_order.json        ← sent when no file is given (one sample window)
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

### Steps 1 to 3 — create the items and a draft Quotation or Sales Order  ← current step

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
- The items are created first (step 3), see below.
- The customer is always the generic customer **`klaes import`** (ID **`C99-9999`**): the sales team
  sets the real customer on the draft document in ERPNext. This customer is created automatically
  when the app is installed and on each `migrate` (see `install.py`), and again by the import if it was deleted.

#### Items: variants of their template (step 3)

Each item of the JSON becomes a **variant** of its `template` (e.g. `ALU-NSHWIN-001`):

- Item Code = `SAP_Item_Number`, Item Name = `short_description`,
  Description = `long_description` (one line per `||` part).
- The variant copies the rest from its template (item group, unit...), as usual in ERPNext.
- It has 5 attributes:

| JSON field | ERPNext attribute (Stock → Item Attribute) | Type |
|---|---|---|
| `SAP_Item_Number` | Klaes SAP Item Number | list: each new SAP number is added |
| `height` | Klaes Height | number, 0 to 100000 (mm), 2 decimals |
| `width` | Klaes Width | number, 0 to 100000 (mm), 2 decimals |
| `color` | Klaes Color | list: each new color is added |
| `OPTION_YN_colonial` | Klaes Colonial | list: `Yes` (true) / `No` (false or null) |

Created automatically when missing:
- the 5 **Item Attributes**;
- the **template**: "Has Variants" ticked, with the 5 attributes, unit `Nos`, item group = `item_group_name`
  of the JSON if that group exists in ERPNext, otherwise `All Item Groups`.

If the item **already exists** (same `SAP_Item_Number`, e.g. Klaes sends it again), its attributes and
description are **updated** from the new JSON. It must be a variant of the same template, otherwise: Error.

If a template exists but is not set up (Has Variants not ticked, or attributes missing): Error.
Fix it in ERPNext, then click **Process again**. The attribute names are at the top of `klaes_items.py`.

ERPNext must name items by their code: **Stock Settings → Item Naming By = Item Code**.

#### Migrate

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

1. Create a user, e.g. `klaes@saintlu.lc`, with the roles **Sales User**
   (Klaes Import records, Quotations and Sales Orders) and **Item Manager** (items, templates, attributes).
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
```

| Setting | What to put |
|---|---|
| `url` | Address of the ERPNext site (dev or production) |
| `api_key` | API Key of the Klaes user (step 1) |
| `api_secret` | API Secret of the Klaes user (step 1) |

An old `config.ini` with a `test_customer` line still works: that line is ignored now.

To switch from the dev site to production later, only `url`, `api_key` and `api_secret` change.

The `Samples` folder holds Klaes JSON files to test by hand. `Samples/sample_order.json` is sent when
no file is given: one sample window, whose template `SAMPLE-WIN-001` is created automatically.

#### 3. Test from Linux (optional, quickest)

Any machine with Python 3 can run the program directly, without building the exe:

```bash
cd klaes_sender
cp config.example.ini config.ini      # then edit config.ini
python3 klaes_sender.py                  # sends Samples/sample_order.json
python3 klaes_sender.py my_file.json     # sends another JSON file
echo $?                                  # 0 = OK, 1 = error
```

#### 4. Build the exe and install it on Windows Server 2019

On any Windows machine with Python installed:

1. Copy the `klaes_sender` folder.
2. Double-click `build_exe.bat`.
3. The `dist` folder now contains `klaes_sender.exe`, `config.example.ini` and the `Samples` folder.

On the Windows server:

1. Copy `klaes_sender.exe`, `config.example.ini` and the `Samples` folder to a folder, e.g. `C:\KlaesSender\`.
2. Create `config.ini`, as explained in step 2.
3. **Test** (no file given, so it sends `Samples\sample_order.json`): open a command prompt and run
   ```
   C:\KlaesSender\klaes_sender.exe
   ```
   Expected: `Klaes Import created: KLAES-00002 (O261022-0012)`
4. In ERPNext, open **Klaes Import**: the record should have status **Done** after a few seconds,
   with a link to a new **Draft** Sales Order, **Klaes Doc Number** `O261022-0012`, and one line:
   the new item `SAMPLE-WIN-001_O261022-0012-1`, a variant of the new template `SAMPLE-WIN-001`.
   To test a Quotation, change `Samples\sample_order.json` to `"doc_type": "Quotation"` and a number starting with `Q`.
5. Klaes runs the program after each export, with the JSON file path as argument:
   ```
   C:\KlaesSender\klaes_sender.exe "C:\path\to\Q241023-001A_ItemsList.JSON"
   ```

#### If something fails

On the sender side, read `klaes_sender.log` (same folder as the program):

| Message in the log | Meaning |
|---|---|
| `Config file not found` | Create `config.ini` from `config.example.ini` (step 2) |
| `HTTP 401` / `HTTP 403` | API key/secret wrong, or user lacks the Sales User / Item Manager role |
| `HTTP 404` | App not installed on the site, or `migrate` / `bench restart` not done |
| `URLError` / timeout | This machine cannot reach the ERPNext URL (firewall/proxy) |

On the ERPNext side, open the Klaes Import record:

| What you see | Meaning |
|---|---|
| Status **Error** | Fix the cause shown in the Error Message, then click **Process again** |
| `Complete the ERPNext setup wizard first` | The generic customer can only be created once ERPNext is set up |
| `Unknown Klaes document type '...'` | `doc_type` in the JSON must be `Quotation` or `Order` |
| `Klaes document type '...' does not match document number '...'` | A Quotation number must start with `Q`, an Order number with `O` |
| `Item '...' has no template in the Klaes JSON` | The item has no `template` in the Klaes export |
| `Item '...' exists but is not a template` | Tick **Has Variants** on that item (it must have no transactions yet) |
| `Template '...' is missing these attributes: ...` | Add the listed Klaes attributes to the template's Attributes table |
| `Item '...' already exists but is not a variant of template '...'` | An item with this code was created by hand, or with another template |
| `Template '...' was created as '...'` | Stock Settings: set **Item Naming By** to **Item Code** |
| `No permission` on Item or Item Attribute | Give the Klaes API user the **Item Manager** role |
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
- The created items are stock items: the site needs a **default warehouse** in Stock Settings
  for the Sales Order tests.
- **Real Klaes files** are in the `test_data/` folder next to the tests, and are imported exactly as Klaes
  sends them: `Q241023-001A_ItemsList.JSON` (a real Klaes quotation, 49 items) and
  `O241023-001B_ItemsList.JSON` (an order in the same layout, 2 items). The tests check that every
  item is created as a variant of its template, with the right attributes.
  To test a new Klaes file (for example one that caused a problem), put it in `test_data/`
  and copy one of the `test_real_klaes_..._file` tests.

---

### Next steps (one at a time, each tested before the next)

4. Create the BOM of each item from `bill_of_material`.
5. Daily XML file of validated orders, emailed to the production manager.

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
