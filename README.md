# Smart Receipt-to-Expense Categorizer & Anomaly Detector

A beginner-friendly Python + Streamlit mini-project. It lets a user upload a receipt image, attempts OCR with Tesseract, extracts likely vendor/date/total/tax values, suggests an expense category, detects possible duplicate receipts, flags unusually large amounts, and exports expenses to CSV.

## 1. Requirements
- Windows 10/11
- Python 3.10 or newer
- Internet for installing Python packages
- Optional: Tesseract OCR engine for automatic text extraction

## 2. Run on Windows

1. Download and extract the ZIP file.
2. Open the extracted `smart_receipt_expense_ai` folder.
3. Click the folder address bar in File Explorer, type `cmd`, and press Enter.
4. Run these commands one at a time:

```bat
py -m venv .venv
.venv\Scripts\activate
py -m pip install --upgrade pip
pip install -r requirements.txt
streamlit run app.py
```

5. A browser tab should open. If it does not, copy the local URL shown in the terminal (usually `http://localhost:8501`) into your browser.

## 3. Enable OCR on Windows (optional but recommended)

The Python package `pytesseract` is only a connector; it does not install the OCR engine itself.

1. Install the Tesseract OCR engine for Windows from the UB Mannheim Tesseract builds page:
   https://github.com/UB-Mannheim/tesseract/wiki
2. During installation, note the install folder (often `C:\Program Files\Tesseract-OCR`).
3. Ensure `tesseract.exe` is on your Windows PATH, or add the following near the top of `app.py`, before OCR is called:

```python
import pytesseract
pytesseract.pytesseract.tesseract_cmd = r"C:\Program Files\Tesseract-OCR\tesseract.exe"
```

4. Restart the terminal and run `streamlit run app.py` again.

If you cannot install Tesseract, the project still works: upload the image and paste/type the text into the receipt text box, then verify the editable fields.

## 4. Test it
Try this sample text in the receipt text box:

```text
Fresh Mart
Date: 2026-10-20
Milk 60.00
Groceries 178.00
GST 12.00
TOTAL ₹250.00
```

Verify the vendor, date, amount, tax and category before saving. Add the same vendor/date/amount a second time to test duplicate detection. Add several normal expenses and then one much larger amount to test the outlier warning.

## 5. Project workflow
1. Upload receipt image.
2. Tesseract OCR reads text from the image (if installed).
3. Regular expressions make best-effort guesses for vendor, date, total and tax.
4. A keyword ruleset suggests an expense category.
5. User verifies/edits fields and saves the record.
6. Duplicate check compares vendor + date + amount.
7. Outlier check compares the new amount with saved spending history.
8. Streamlit dashboard summarizes expenses and exports CSV.

## 6. Folder structure

```text
smart_receipt_expense_ai/
├── app.py
├── requirements.txt
├── README.md
├── .gitignore
└── data/
    └── .gitkeep
```

The `data/expenses.csv` file is created automatically after the first saved expense.

## 7. Current limitations / future improvements
- OCR results vary with blurry, crumpled, handwritten or low-light receipts.
- Field extraction is heuristic, not a trained receipt-understanding model. Always verify results.
- Category assignment is keyword-based.
- The first version's anomaly detector uses a simple statistical rule; it needs sufficient historical data.
- Duplicate matching uses vendor, date and amount and may flag legitimate repeat purchases.
- Data is stored locally in CSV; there is no login, cloud sync, or multi-user database.

Possible future improvements: EasyOCR support, trained category classifier, Isolation Forest anomaly detection, SQLite database, receipt image archival, login/authentication, tests, and deployment.
