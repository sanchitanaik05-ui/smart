import re
import hashlib
from datetime import datetime
from pathlib import Path

import pandas as pd
import streamlit as st
import pytesseract

# Use the local Tesseract installation if available.
# On Streamlit Cloud, Tesseract should be installed through packages.txt.
local_tesseract = Path(r"C:\Program Files\Tesseract-OCR\tesseract.exe")
if local_tesseract.exists():
    pytesseract.pytesseract.tesseract_cmd = str(local_tesseract)

DATA_DIR = Path("data")
DATA_DIR.mkdir(exist_ok=True)
DATA_FILE = DATA_DIR / "expenses.csv"

CATEGORIES = {
    "Food & Dining": [
        "restaurant", "cafe", "coffee", "pizza", "burger",
        "food", "bakery", "hotel", "swiggy", "zomato"
    ],
    "Groceries": [
        "grocery", "supermarket", "mart", "vegetables",
        "fruits", "milk", "dmart", "reliance fresh"
    ],
    "Transport": [
        "uber", "ola", "taxi", "petrol", "fuel", "metro",
        "bus", "train", "parking", "rapido"
    ],
    "Shopping": [
        "amazon", "flipkart", "mall", "store", "clothing",
        "fashion", "retail"
    ],
    "Utilities": [
        "electricity", "water", "internet", "broadband",
        "mobile", "recharge", "gas bill"
    ],
    "Healthcare": [
        "pharmacy", "medical", "hospital", "clinic",
        "doctor", "medicine"
    ],
    "Travel": [
        "airlines", "flight", "airways", "booking",
        "hotel booking", "irctc"
    ],
    "Office & Business": [
        "stationery", "office", "software",
        "subscription", "printer"
    ],
}


def categorize(vendor, raw_text=""):
    text = f"{vendor} {raw_text}".lower()

    for category, keywords in CATEGORIES.items():
        if any(word in text for word in keywords):
            return category

    return "Other"


def parse_amount(value):
    """Convert an amount such as ₹1,250.50 into a number."""
    value = value.replace(",", "").strip()

    try:
        amount = float(value)
        return amount if amount > 0 else None
    except ValueError:
        return None


def extract_total(lines):
    """
    Prioritize clearly labelled totals.
    Avoid using invoice numbers or unrelated numbers as totals.
    """

    priority_labels = [
        r"grand\s*total",
        r"total\s*amount\s*payable",
        r"amount\s*payable",
        r"net\s*payable",
        r"balance\s*due",
        r"invoice\s*total",
        r"total\s*due",
        r"net\s*amount",
        r"total"
    ]

    amount_pattern = (
        r"(?:₹|rs\.?|inr)?\s*"
        r"(\d[\d,]*(?:\.\d{1,2})?)"
    )

    for label in priority_labels:
        label_pattern = re.compile(
            r"\b" + label + r"\b",
            re.IGNORECASE
        )

        for index, line in enumerate(lines):
            match = label_pattern.search(line)

            if not match:
                continue

            # Look for an amount after the total label
            # on the same line.
            remaining = line[match.end():]
            amount_match = re.search(
                r"^\s*[:=\-]?\s*" + amount_pattern,
                remaining,
                re.IGNORECASE
            )

            if amount_match:
                value = parse_amount(amount_match.group(1))
                if value is not None:
                    return value

            # Some receipts put the amount on the next line.
            # Only accept a next line that starts with an amount.
            if index + 1 < len(lines):
                next_line = lines[index + 1].strip()

                next_match = re.match(
                    r"^(?:₹|rs\.?|inr)?\s*"
                    r"(\d[\d,]*(?:\.\d{1,2})?)"
                    r"\s*$",
                    next_line,
                    re.IGNORECASE
                )

                if next_match:
                    value = parse_amount(next_match.group(1))
                    if value is not None:
                        return value

    # Fallback: use currency-marked amounts only.
    # If no reliable amount is found, request manual entry.
    currency_values = []

    for line in lines:
        for match in re.finditer(
            r"(?:₹|INR|Rs\.?)\s*"
            r"(\d[\d,]*(?:\.\d{1,2})?)",
            line,
            re.IGNORECASE
        ):
            value = parse_amount(match.group(1))
            if value is not None:
                currency_values.append(value)

    if currency_values:
        return max(currency_values)

    return 0.0


def extract_fields(text):
    """Extract receipt details for the editable form."""

    lines = [
        line.strip()
        for line in text.splitlines()
        if line.strip()
    ]

    vendor = lines[0][:80] if lines else ""

    # Extract date.
    date_value = datetime.today().date().isoformat()

    date_patterns = [
        (r"\b(20\d{2}[-/]\d{1,2}[-/]\d{1,2})\b",
         "%Y-%m-%d"),
        (r"\b(\d{1,2}[-/]\d{1,2}[-/]\d{4})\b",
         None),
        (r"\b(\d{1,2}[-/]\d{1,2}[-/]\d{2})\b",
         None),
    ]

    for pattern, fmt in date_patterns:
        match = re.search(pattern, text)

        if not match:
            continue

        raw = match.group(1).replace("/", "-")

        try:
            if fmt:
                date_value = datetime.strptime(
                    raw, fmt
                ).date().isoformat()
            else:
                a, b, c = map(int, raw.split("-"))
                year = c + 2000 if c < 100 else c

                # Assume DD-MM-YYYY unless the first
                # number cannot be a month.
                day, month = (a, b) if a > 12 else (b, a)

                date_value = datetime(
                    year, month, day
                ).date().isoformat()

            break
        except ValueError:
            continue

    # Extract the total amount.
    amount = extract_total(lines)

    # Extract tax/GST.
    tax = 0.0
    tax_pattern = re.compile(
        r"\b(?:GST|tax|VAT)\b"
        r"[^0-9\n]{0,15}"
        r"(\d[\d,]*(?:\.\d{1,2})?)",
        re.IGNORECASE
    )

    tax_match = tax_pattern.search(text)

    if tax_match:
        parsed_tax = parse_amount(tax_match.group(1))
        if parsed_tax is not None:
            tax = parsed_tax

    return {
        "vendor": vendor,
        "date": date_value,
        "amount": amount,
        "tax": tax
    }


def load_data():
    columns = [
        "vendor", "date", "amount", "tax",
        "category", "receipt_text", "receipt_hash"
    ]

    if DATA_FILE.exists():
        try:
            df = pd.read_csv(DATA_FILE)

            for col in columns:
                if col not in df.columns:
                    df[col] = ""

            return df[columns]

        except Exception:
            pass

    return pd.DataFrame(columns=columns)


def anomaly_flags(df, amount):
    flags = []

    if amount <= 0:
        flags.append("Amount is missing or zero")

    if len(df) >= 3:
        previous = pd.to_numeric(
            df["amount"], errors="coerce"
        ).dropna()

        mean = previous.mean()
        std = previous.std()

        if (
            pd.notna(mean)
            and pd.notna(std)
            and std > 0
            and amount > mean + 2 * std
        ):
            flags.append(
                f"Unusually high amount "
                f"(past average ₹{mean:,.2f})"
            )

    return flags


# ---------------- STREAMLIT APP ----------------

st.set_page_config(
    page_title="Smart Receipt Expense AI",
    page_icon="🧾",
    layout="wide"
)

st.title("🧾 Smart Receipt-to-Expense Categorizer & Anomaly Detector")

st.caption(
    "Upload a receipt, extract fields, categorize expenses, "
    "and check for duplicates or unusual spending."
)

df = load_data()

tab_add, tab_dashboard, tab_history, tab_help = st.tabs([
    "➕ Add receipt",
    "📊 Dashboard",
    "🗂️ Expense history",
    "ℹ️ How it works"
])


with tab_add:
    st.subheader("1. Upload a receipt or enter its text")

    upload = st.file_uploader(
        "Receipt image (PNG, JPG, JPEG)",
        type=["png", "jpg", "jpeg"]
    )

    ocr_text = ""

    if upload is not None:
        st.image(
            upload,
            caption="Uploaded receipt",
            width=350
        )

        try:
            from PIL import Image
            import io

            image = Image.open(
                io.BytesIO(upload.getvalue())
            )

            ocr_text = pytesseract.image_to_string(image)

            st.success(
                "OCR completed. Verify the extracted text and fields."
            )

        except Exception as exc:
            st.warning(
                "Automatic OCR could not run. Check that "
                "Tesseract OCR is installed on the app server."
            )
            st.caption(f"Technical detail: {exc}")

    typed_text = st.text_area(
        "Extracted / pasted receipt text",
        value=ocr_text,
        height=150,
        placeholder=(
            "Example:\nFresh Mart\nDate: 2026-10-20\n"
            "Milk 60\nSubtotal ₹238.00\n"
            "GST ₹12.00\nGRAND TOTAL ₹250.00"
        )
    )

    if typed_text.strip():
        parsed = extract_fields(typed_text)
    else:
        parsed = {
            "vendor": "",
            "date": datetime.today().date().isoformat(),
            "amount": 0.0,
            "tax": 0.0
        }

    with st.form("expense_form"):
        col1, col2 = st.columns(2)

        with col1:
            vendor = st.text_input(
                "Vendor / shop name",
                value=parsed["vendor"]
            )

            date_value = st.date_input(
                "Expense date",
                value=datetime.fromisoformat(
                    parsed["date"]
                ).date()
            )

            amount = st.number_input(
                "Total amount (₹)",
                min_value=0.0,
                value=float(parsed["amount"]),
                step=1.0
            )

        with col2:
            tax = st.number_input(
                "Tax / GST (₹)",
                min_value=0.0,
                value=float(parsed["tax"]),
                step=1.0
            )

            suggested = categorize(vendor, typed_text)

            category_options = list(CATEGORIES.keys()) + ["Other"]

            category = st.selectbox(
                "Expense category",
                options=category_options,
                index=category_options.index(suggested)
            )

            st.write(
                "Suggested category:",
                f"**{suggested}**"
            )

        submitted = st.form_submit_button(
            "Save expense and run checks",
            type="primary"
        )

    if submitted:
        if not vendor.strip():
            st.error("Please enter a vendor/shop name.")

        elif amount <= 0:
            st.error(
                "Please enter a valid total amount. "
                "Check the receipt and correct the amount first."
            )

        else:
            receipt_hash = hashlib.sha256(
                (
                    vendor.strip().lower()
                    + "|"
                    + str(date_value)
                    + "|"
                    + f"{amount:.2f}"
                ).encode()
            ).hexdigest()

            duplicate = (
                not df.empty
                and (
                    df["receipt_hash"].astype(str)
                    == receipt_hash
                ).any()
            )

            flags = anomaly_flags(df, amount)

            if duplicate:
                st.error(
                    "Possible duplicate detected: same vendor, "
                    "date, and amount already exist."
                )

            if flags:
                st.warning(
                    "Anomaly check: " + "; ".join(flags)
                )

            new_row = {
                "vendor": vendor.strip(),
                "date": date_value.isoformat(),
                "amount": round(float(amount), 2),
                "tax": round(float(tax), 2),
                "category": category,
                "receipt_text": typed_text,
                "receipt_hash": receipt_hash
            }

            updated = pd.concat(
                [df, pd.DataFrame([new_row])],
                ignore_index=True
            )

            updated.to_csv(DATA_FILE, index=False)

            st.success(
                "Expense saved. Review it in Expense history."
            )

            st.rerun()


with tab_dashboard:
    st.subheader("Spending overview")

    if df.empty:
        st.info(
            "No expenses saved yet. Add your first receipt."
        )

    else:
        df["amount"] = pd.to_numeric(
            df["amount"], errors="coerce"
        ).fillna(0)

        c1, c2, c3 = st.columns(3)

        c1.metric(
            "Total expenses",
            f"₹{df['amount'].sum():,.2f}"
        )

        c2.metric("Receipts", len(df))

        c3.metric(
            "Average expense",
            f"₹{df['amount'].mean():,.2f}"
        )

        chart_data = (
            df.groupby("category", dropna=False)["amount"]
            .sum()
            .sort_values(ascending=False)
        )

        st.bar_chart(chart_data)

        st.subheader("Potential unusual expenses")

        mean = df["amount"].mean()
        std = df["amount"].std()

        if pd.notna(std) and std > 0:
            unusual = df[
                df["amount"] > mean + 2 * std
            ]
        else:
            unusual = df.iloc[0:0]

        if unusual.empty:
            st.write(
                "No statistical outliers identified using "
                "the mean + 2 standard deviations rule."
            )
        else:
            st.dataframe(
                unusual[
                    ["date", "vendor", "amount", "category"]
                ],
                use_container_width=True
            )


with tab_history:
    st.subheader("Saved expense records")

    if df.empty:
        st.info("Your expense history is empty.")

    else:
        display = df[
            ["date", "vendor", "amount", "tax", "category"]
        ].copy()

        st.dataframe(
            display.sort_values(
                "date", ascending=False
            ),
            use_container_width=True
        )

        st.download_button(
            "⬇️ Download expenses as CSV",
            data=df.to_csv(index=False).encode("utf-8"),
            file_name="expenses_export.csv",
            mime="text/csv"
        )

        st.caption(
            "Keep a backup before editing data/expenses.csv."
        )


with tab_help:
    st.subheader("Features included")

    st.markdown("""
    - Receipt image upload (PNG/JPG).
    - OCR text extraction using Tesseract.
    - Improved total-amount detection using receipt labels.
    - Editable vendor, date, amount, and tax fields.
    - Rule-based expense categorization.
    - Duplicate receipt checks.
    - Unusual-spending detection.
    - Dashboard, history table, and CSV export.

    **Important:** OCR can misread text and receipt layouts vary.
    Always verify the extracted amount before saving.
    This is a student prototype, not accounting software.
    """)