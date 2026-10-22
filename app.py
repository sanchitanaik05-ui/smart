import re
from datetime import datetime
from pathlib import Path

import pandas as pd
import streamlit as st

DATA_DIR = Path("data")
DATA_DIR.mkdir(exist_ok=True)
DATA_FILE = DATA_DIR / "expenses.csv"

CATEGORIES = {
    "Food & Dining": ["restaurant", "cafe", "coffee", "pizza", "burger", "food", "bakery", "hotel", "swiggy", "zomato"],
    "Groceries": ["grocery", "supermarket", "mart", "vegetables", "fruits", "milk", "dmart", "reliance fresh"],
    "Transport": ["uber", "ola", "taxi", "petrol", "fuel", "metro", "bus", "train", "parking", "rapido"],
    "Shopping": ["amazon", "flipkart", "mall", "store", "clothing", "fashion", "retail"],
    "Utilities": ["electricity", "water", "internet", "broadband", "mobile", "recharge", "gas bill"],
    "Healthcare": ["pharmacy", "medical", "hospital", "clinic", "doctor", "medicine"],
    "Travel": ["airlines", "flight", "airways", "booking", "hotel booking", "irctc"],
    "Office & Business": ["stationery", "office", "software", "subscription", "printer"],
}

def categorize(vendor, raw_text=""):
    text = f"{vendor} {raw_text}".lower()
    for category, keywords in CATEGORIES.items():
        if any(word in text for word in keywords):
            return category
    return "Other"

def extract_fields(text):
    """Best-effort field extraction from OCR text; user can correct fields before saving."""
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    vendor = lines[0][:80] if lines else ""
    # Pick a date in common formats.
    date_value = datetime.today().date().isoformat()
    patterns = [
        (r"\b(20\d{2}[-/]\d{1,2}[-/]\d{1,2})\b", "%Y-%m-%d"),
        (r"\b(\d{1,2}[-/]\d{1,2}[-/](?:20)?\d{2})\b", None),
    ]
    for pattern, fmt in patterns:
        match = re.search(pattern, text)
        if match:
            raw = match.group(1).replace("/", "-")
            try:
                if fmt:
                    date_value = datetime.strptime(raw, fmt).date().isoformat()
                else:
                    parts = raw.split("-")
                    a, b, c = map(int, parts)
                    year = c + 2000 if c < 100 else c
                    # Assume DD-MM-YYYY when the first number cannot be a month.
                    day, month = (a, b) if a > 12 else (b, a)
                    date_value = datetime(year, month, day).date().isoformat()
                break
            except ValueError:
                pass
    amounts = []
    for match in re.finditer(r"(?:₹|INR|Rs\.?|TOTAL|AMOUNT|GRAND TOTAL)?\s*([0-9]{1,7}(?:,[0-9]{3})*(?:\.[0-9]{1,2})?)", text, re.I):
        raw = match.group(1).replace(",", "")
        try:
            value = float(raw)
            if value > 0:
                amounts.append(value)
        except ValueError:
            pass
    # Usually the total is the largest amount on a receipt; confirm it in the form.
    amount = max(amounts) if amounts else 0.0
    tax_match = re.search(r"(?:tax|gst|vat)\D{0,12}([0-9]+(?:\.[0-9]{1,2})?)", text, re.I)
    tax = float(tax_match.group(1)) if tax_match else 0.0
    return {"vendor": vendor, "date": date_value, "amount": amount, "tax": tax}

def load_data():
    if DATA_FILE.exists():
        try:
            df = pd.read_csv(DATA_FILE)
            for col in ["vendor", "date", "amount", "tax", "category", "receipt_text", "receipt_hash"]:
                if col not in df.columns:
                    df[col] = ""
            return df
        except Exception:
            pass
    return pd.DataFrame(columns=["vendor", "date", "amount", "tax", "category", "receipt_text", "receipt_hash"])

def anomaly_flags(df, amount):
    flags = []
    if amount <= 0:
        flags.append("Amount is missing or zero")
    if len(df) >= 3:
        mean = pd.to_numeric(df["amount"], errors="coerce").dropna().mean()
        std = pd.to_numeric(df["amount"], errors="coerce").dropna().std()
        if pd.notna(mean) and pd.notna(std) and std > 0 and amount > mean + 2 * std:
            flags.append(f"Unusually high amount (past average ₹{mean:,.2f})")
    return flags

st.set_page_config(page_title="Smart Receipt Expense AI", page_icon="🧾", layout="wide")
st.title("🧾 Smart Receipt-to-Expense Categorizer & Anomaly Detector")
st.caption("Upload a receipt, extract fields, categorize the expense, and check for duplicates or unusual spending.")

df = load_data()
tab_add, tab_dashboard, tab_history, tab_help = st.tabs(["➕ Add receipt", "📊 Dashboard", "🗂️ Expense history", "ℹ️ How it works"])

with tab_add:
    st.subheader("1. Upload a receipt or enter its text")
    upload = st.file_uploader("Receipt image (PNG, JPG, JPEG)", type=["png", "jpg", "jpeg"])
    ocr_text = ""
    if upload is not None:
        st.image(upload, caption="Uploaded receipt", width=350)
        try:
            from PIL import Image
            import pytesseract
            import io
            image = Image.open(io.BytesIO(upload.getvalue()))
            ocr_text = pytesseract.image_to_string(image)
            st.success("OCR completed. Please verify the extracted text and fields.")
        except Exception as exc:
            st.warning("Automatic OCR could not run. Install the Tesseract OCR engine (see README), or paste/type the receipt text below.")
            st.caption(f"Technical detail: {exc}")
    typed_text = st.text_area("Extracted / pasted receipt text", value=ocr_text, height=150,
        placeholder="Example:\nFresh Mart\nDate: 2026-10-20\nMilk 60\nTOTAL ₹250.00\nGST 12.00")
    parsed = extract_fields(typed_text) if typed_text.strip() else {
        "vendor": "", "date": datetime.today().date().isoformat(), "amount": 0.0, "tax": 0.0
    }

    with st.form("expense_form"):
        col1, col2 = st.columns(2)
        with col1:
            vendor = st.text_input("Vendor / shop name", value=parsed["vendor"])
            date_value = st.date_input("Expense date", value=datetime.fromisoformat(parsed["date"]).date())
            amount = st.number_input("Total amount (₹)", min_value=0.0, value=float(parsed["amount"]), step=1.0)
        with col2:
            tax = st.number_input("Tax / GST (₹)", min_value=0.0, value=float(parsed["tax"]), step=1.0)
            suggested = categorize(vendor, typed_text)
            category = st.selectbox("Expense category", options=list(CATEGORIES.keys()) + ["Other"],
                index=(list(CATEGORIES.keys()) + ["Other"]).index(suggested))
            st.write("Suggested category:", f"**{suggested}**")
        submitted = st.form_submit_button("Save expense and run checks", type="primary")

    if submitted:
        import hashlib
        if not vendor.strip():
            st.error("Please enter a vendor/shop name.")
        elif amount <= 0:
            st.error("Please enter a total amount greater than zero.")
        else:
            receipt_hash = hashlib.sha256((vendor.strip().lower() + "|" + str(date_value) + "|" + f"{amount:.2f}").encode()).hexdigest()
            duplicate = not df.empty and (df["receipt_hash"].astype(str) == receipt_hash).any()
            flags = anomaly_flags(df, amount)
            if duplicate:
                st.error("Possible duplicate detected: same vendor, date, and amount already exist.")
            if flags:
                st.warning("Anomaly check: " + "; ".join(flags))
            new_row = {
                "vendor": vendor.strip(), "date": date_value.isoformat(), "amount": round(float(amount), 2),
                "tax": round(float(tax), 2), "category": category, "receipt_text": typed_text,
                "receipt_hash": receipt_hash
            }
            updated = pd.concat([df, pd.DataFrame([new_row])], ignore_index=True)
            updated.to_csv(DATA_FILE, index=False)
            st.success("Expense saved. You can review it in Expense history.")
            st.rerun()

with tab_dashboard:
    st.subheader("Spending overview")
    if df.empty:
        st.info("No expenses saved yet. Add your first receipt in the Add receipt tab.")
    else:
        df["amount"] = pd.to_numeric(df["amount"], errors="coerce").fillna(0)
        c1, c2, c3 = st.columns(3)
        c1.metric("Total expenses", f"₹{df['amount'].sum():,.2f}")
        c2.metric("Receipts", len(df))
        c3.metric("Average expense", f"₹{df['amount'].mean():,.2f}")
        chart_data = df.groupby("category", dropna=False)["amount"].sum().sort_values(ascending=False)
        st.bar_chart(chart_data)
        st.subheader("Potential unusual expenses")
        mean = df["amount"].mean()
        std = df["amount"].std()
        if pd.notna(std) and std > 0:
            unusual = df[df["amount"] > mean + 2 * std]
        else:
            unusual = df.iloc[0:0]
        if unusual.empty:
            st.write("No statistical outliers identified using the simple mean + 2 standard deviations rule.")
        else:
            st.dataframe(unusual[["date", "vendor", "amount", "category"]], use_container_width=True)

with tab_history:
    st.subheader("Saved expense records")
    if df.empty:
        st.info("Your expense history is empty.")
    else:
        display = df[["date", "vendor", "amount", "tax", "category"]].copy()
        st.dataframe(display.sort_values("date", ascending=False), use_container_width=True)
        st.download_button("⬇️ Download expenses as CSV", data=df.to_csv(index=False).encode("utf-8"),
            file_name="expenses_export.csv", mime="text/csv")
        st.caption("To remove a record, edit data/expenses.csv while the app is stopped. Keep a backup first.")

with tab_help:
    st.subheader("Features included")
    st.markdown("""
    - Receipt image upload (PNG/JPG).
    - OCR text extraction using Tesseract when installed.
    - Best-effort vendor, date, total, and tax extraction; fields remain editable because OCR can make mistakes.
    - Rule-based expense category suggestion.
    - Possible duplicate detection using vendor + date + amount.
    - Basic unusual-spending detection using historical mean + 2 standard deviations.
    - Dashboard, history table, and CSV export.

    **Important:** This is a student prototype, not accounting or fraud-detection software. Review all extracted values. The first version stores records locally in `data/expenses.csv`.
    """)
