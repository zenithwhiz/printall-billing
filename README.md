# PrintAll Billing v1

A local-first billing app for one computer at the press. It creates simple non-GST invoices, stores them in SQLite, supports invoice history/search, downloads PDF bills, and prints from the browser.

## Public showcase version\n\nThis repository version has sample/default contact details removed and the personal payment QR/UPI ID removed. A blank GPay/UPI QR placeholder is reserved on the invoice. Add the correct business QR locally through your own customization before issuing real invoices. Do not commit customer records, generated invoices, backups, or payment QR images.\n\n## Requirements
- Python 3.10 or newer
- Internet for the first dependency installation only
- A printer installed in the computer for physical printing

## Windows setup
1. Install Python from https://www.python.org/downloads/ if needed. During installation, enable **Add Python to PATH**.
2. Extract this folder somewhere convenient, e.g. `Documents\PrintAllBilling`.
3. Double-click `run_windows.bat`.
4. The first run installs Flask and ReportLab. It may take a minute.
5. The app opens at `http://127.0.0.1:5000`.
6. Go to **Business Settings** and enter PrintAll's correct business details.
7. Create a test invoice and check the PDF and print layout before using it for real bills.

## Linux setup
Run `chmod +x run_linux.sh`, then `./run_linux.sh`. If Python's venv module is missing on Ubuntu/Debian, install it using your system package manager (often `python3-venv`).

## Data and backups
- The database is `printall.db` in this project folder. It is created when the app starts.
- Use **Download Backup** regularly. Keep backup copies somewhere other than this computer too.
- Do not delete `printall.db` while the app is in use.
- This first version is designed for one trusted local computer. It does not have user accounts, encryption, or multi-computer synchronization.

## Printing
Open a saved invoice and click **Print invoice** to open the browser print dialog. Choose the press printer, paper size A5, and scale 100%. Use **Download PDF** to save a PDF instead.

## Important v1 limitations
- This is a simple non-GST bill template, not a certified accounting package.
- Review invoice wording, business details, local recordkeeping requirements, and invoice-numbering practices before production use.
- Invoice totals are calculated by the app; always test with sample data before issuing customer bills.
- The current invoice IDs are sequential within this database. Keep backups and do not manually edit the database.
- For future versions, add edit/cancel workflows, stronger backup/restore, amount-in-words, payment tracking, and configurable invoice terms.


## Prototype update: A5 Print All layout
- PDF output is configured for A5 portrait.
- The invoice PDF and preview do not include a logo, as requested.
- The footer reserves space for a physical stamp and handwritten signature; no digital stamp/signature is printed.
- This remains a prototype. Verify the header spacing, printer margins, and exact layout using test paper before real billing.

Update: removed the Rate field from invoice entry, invoice display, and PDF export. Enter the line Amount directly; the saved bill total is calculated from line amounts. Existing database schema is retained for compatibility.
