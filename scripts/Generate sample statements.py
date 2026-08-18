"""
Generates synthetic bank statement images for testing the extraction POC.
All data is fictional. Every image carries a visible watermark identifying
it as sample/test data, not a real financial document.
"""

import os
from PIL import Image, ImageDraw, ImageFont, ImageFilter

OUT_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "sample_data")
os.makedirs(OUT_DIR, exist_ok=True)

W, H = 1240, 1080

FONT_DIR = "/usr/share/fonts/truetype/liberation"
F_REG = os.path.join(FONT_DIR, "LiberationSans-Regular.ttf")
F_BOLD = os.path.join(FONT_DIR, "LiberationSans-Bold.ttf")
F_MONO = "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf"

def font(path, size):
    return ImageFont.truetype(path, size)

NAVY = (26, 43, 74)
LIGHT_BAND = (235, 239, 245)
GRID = (210, 214, 220)
TEXT = (30, 30, 30)
MUTED = (110, 116, 128)
GREEN = (30, 120, 70)
RED = (170, 40, 40)


def add_watermark(img):
    layer = Image.new("RGBA", (W * 2, H * 2), (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    f = font(F_BOLD, 40)
    text = "SAMPLE / TEST DATA — NOT A REAL DOCUMENT"
    for y in range(0, H * 2, 160):
        for x in range(-200, W * 2, 620):
            d.text((x, y), text, font=f, fill=(150, 30, 30, 60))
    layer = layer.rotate(-28, resample=Image.BICUBIC, center=(W, H))
    cropped = layer.crop((W // 2, H // 2, W // 2 + W, H // 2 + H))
    base = img.convert("RGBA")
    combined = Image.alpha_composite(base, cropped)
    return combined.convert("RGB")


def draw_statement(
    bank_name, tagline, currency, account_holder, account_type,
    account_number, branch, statement_period, statement_date,
    opening_balance, available_balance_hold,
    transactions, out_path, degrade_field=None,
):
    total_debit = sum(t[3] for t in transactions)
    total_credit = sum(t[4] for t in transactions)
    closing_balance = opening_balance - total_debit + total_credit
    available_balance = closing_balance - available_balance_hold

    img = Image.new("RGB", (W, H), "white")
    d = ImageDraw.Draw(img)

    # Header band
    d.rectangle([0, 0, W, 150], fill=NAVY)
    d.text((50, 35), bank_name, font=font(F_BOLD, 46), fill="white")
    d.text((50, 95), tagline, font=font(F_REG, 20), fill=(200, 210, 225))
    d.text((W - 330, 55), "ACCOUNT STATEMENT", font=font(F_BOLD, 24), fill="white")

    y = 185
    left_x, right_x = 50, 660

    def field(x, y, label, value, mono=False):
        d.text((x, y), label, font=font(F_REG, 15), fill=MUTED)
        d.text((x, y + 20), value, font=font(F_MONO if mono else F_BOLD, 19), fill=TEXT)

    field(left_x, y, "ACCOUNT HOLDER / COMPANY NAME", account_holder)
    field(right_x, y, "ACCOUNT TYPE", account_type)
    y += 65
    field(left_x, y, "ACCOUNT NUMBER", account_number, mono=True)
    field(right_x, y, "CURRENCY", currency)
    y += 65
    field(left_x, y, "BRANCH", branch)
    field(right_x, y, "STATEMENT DATE", statement_date)
    y += 65
    field(left_x, y, "STATEMENT PERIOD", statement_period)

    y += 60
    d.line([(50, y), (W - 50, y)], fill=GRID, width=2)
    y += 25

    # Transactions table
    cols = [("DATE", 50, 110), ("DESCRIPTION", 165, 430), ("REF NO.", 600, 190),
            ("DEBIT", 795, 145), ("CREDIT", 945, 145), ("BALANCE", 1095, 100)]
    d.rectangle([50, y, W - 50, y + 34], fill=LIGHT_BAND)
    for label, x, _w in cols:
        d.text((x + 5, y + 8), label, font=font(F_BOLD, 14), fill=NAVY)
    y += 34

    running = opening_balance
    for i, (t_date, desc, ref, debit, credit) in enumerate(transactions):
        row_h = 38
        if i % 2 == 1:
            d.rectangle([50, y, W - 50, y + row_h], fill=(248, 249, 251))
        running = running - debit + credit
        d.text((cols[0][1] + 5, y + 10), t_date, font=font(F_REG, 14), fill=TEXT)
        d.text((cols[1][1] + 5, y + 10), desc, font=font(F_REG, 14), fill=TEXT)
        d.text((cols[2][1] + 5, y + 10), ref, font=font(F_MONO, 13), fill=MUTED)
        if debit:
            d.text((cols[3][1] + 5, y + 10), f"{debit:,.2f}", font=font(F_REG, 14), fill=RED)
        if credit:
            d.text((cols[4][1] + 5, y + 10), f"{credit:,.2f}", font=font(F_REG, 14), fill=GREEN)
        d.text((cols[5][1] + 5, y + 10), f"{running:,.2f}", font=font(F_REG, 14), fill=TEXT)
        y += row_h

    d.line([(50, y), (W - 50, y)], fill=GRID, width=2)
    y += 30

    assert abs(running - closing_balance) < 0.001, (
        f"Running balance {running:.2f} doesn't match computed closing "
        f"balance {closing_balance:.2f} — transaction math is wrong."
    )

    # Summary box
    summary = [
        ("Opening Balance", f"{currency} {opening_balance:,.2f}"),
        ("Total Debits", f"{currency} {total_debit:,.2f}"),
        ("Total Credits", f"{currency} {total_credit:,.2f}"),
        ("Closing Balance", f"{currency} {closing_balance:,.2f}"),
        ("Available Balance", f"{currency} {available_balance:,.2f}"),
    ]
    box_x = W - 470
    d.rectangle([box_x, y, W - 50, y + 34 + 30 * len(summary)], outline=GRID, width=2)
    d.rectangle([box_x, y, W - 50, y + 34], fill=NAVY)
    d.text((box_x + 15, y + 7), "STATEMENT SUMMARY", font=font(F_BOLD, 16), fill="white")
    sy = y + 34 + 8
    for label, val in summary:
        d.text((box_x + 15, sy), label, font=font(F_REG, 15), fill=MUTED)
        d.text((W - 65, sy), val, font=font(F_BOLD, 15), fill=TEXT, anchor="ra")
        sy += 30

    footer_y = H - 60
    d.line([(50, footer_y - 15), (W - 50, footer_y - 15)], fill=GRID, width=1)
    d.text((50, footer_y), "Synthetic sample document generated for software testing purposes only.",
            font=font(F_REG, 13), fill=MUTED)
    d.text((50, footer_y + 18), "Not issued by any financial institution. Contains no real account or personal data.",
            font=font(F_REG, 13), fill=MUTED)

    # Optional: simulate an unreadable field for null-handling tests
    if degrade_field:
        fx, fy, fw, fh = degrade_field
        region = img.crop((fx, fy, fx + fw, fy + fh)).filter(ImageFilter.GaussianBlur(8))
        img.paste(region, (fx, fy))

    img = add_watermark(img)
    img.save(out_path, "PNG")
    print(f"Wrote {out_path}")


# ---------------------------------------------------------------------------
# Maybank — company account, MYR
draw_statement(
    bank_name="MAYBANK", tagline="Malayan Banking Berhad",
    currency="MYR", account_holder="NIMBUS TRADING SDN BHD", account_type="Current Account-i",
    account_number="5142 1123 4590", branch="Bandar Utama, Petaling Jaya",
    statement_period="01 Aug 2026 - 08 Aug 2026", statement_date="08 August 2026",
    opening_balance=18240.50, available_balance_hold=200.00,
    transactions=[
        ("01 Aug", "Salary Credit - Payroll", "MBB-PAY-88213", 0.00, 6500.00),
        ("02 Aug", "Utility Payment - TNB", "MBB-BIL-10042", 340.20, 0.00),
        ("03 Aug", "Transfer to A/C 6001883210", "MBB-TRF-55871", 1200.00, 0.00),
        ("05 Aug", "POS Purchase - Retail Store", "MBB-POS-93012", 185.55, 0.00),
        ("06 Aug", "Client Payment Received", "MBB-INV-44210", 0.00, 2100.00),
        ("07 Aug", "Monthly Service Charge", "MBB-FEE-00019", 8.00, 0.00),
        ("08 Aug", "ATM Withdrawal", "MBB-ATM-77410", 300.00, 0.00),
    ],
    out_path=f"{OUT_DIR}/maybank_sample.png",
)

# UOB — company account, SGD
draw_statement(
    bank_name="UOB", tagline="United Overseas Bank Limited",
    currency="SGD", account_holder="SOLSTICE CONSULTING PTE LTD", account_type="Business Current",
    account_number="301-234567-8", branch="Raffles Place",
    statement_period="01 Aug 2026 - 08 Aug 2026", statement_date="08 August 2026",
    opening_balance=42310.00, available_balance_hold=0.00,
    transactions=[
        ("01 Aug", "Consulting Fee Received", "UOB-INV-30021", 0.00, 5200.00),
        ("02 Aug", "GIRO - Office Rental", "UOB-GIR-11029", 3800.00, 0.00),
        ("04 Aug", "Payroll Disbursement", "UOB-PAY-88450", 4200.00, 0.00),
        ("05 Aug", "Client Retainer Payment", "UOB-INV-30055", 0.00, 6100.00),
        ("07 Aug", "Bank Charges", "UOB-FEE-00231", 30.60, 0.00),
        ("08 Aug", "Interest Credited", "UOB-INT-00099", 0.00, 100.00),
    ],
    out_path=f"{OUT_DIR}/uob_sample.png",
)

# AmBank — personal account, MYR — this one gets a degraded field (blurred
# account number) to test the "return null when unreadable" behavior
draw_statement(
    bank_name="AmBank", tagline="AmBank (M) Berhad",
    currency="MYR", account_holder="CHEN WEI LING", account_type="Savings Account",
    account_number="098 7654 3212 34", branch="Subang Jaya",
    statement_period="01 Aug 2026 - 08 Aug 2026", statement_date="08 August 2026",
    opening_balance=9540.10, available_balance_hold=0.00,
    transactions=[
        ("01 Aug", "Salary Credit", "AMB-PAY-20213", 0.00, 4800.00),
        ("03 Aug", "Credit Card Payment", "AMB-CCP-11982", 1500.00, 0.00),
        ("04 Aug", "Grocery - POS Purchase", "AMB-POS-40012", 245.60, 0.00),
        ("06 Aug", "Insurance Premium", "AMB-INS-77031", 380.00, 0.00),
        ("07 Aug", "Transfer from Savings", "AMB-TRF-99871", 0.00, 500.00),
        ("08 Aug", "Online Purchase", "AMB-POS-40088", 1801.65, 0.00),
    ],
    out_path=f"{OUT_DIR}/ambank_sample_degraded.png",
    degrade_field=(50 + 5, 185 + 20 - 5, 250, 30),  # blurs the account number field
)

print("\nDone. Files:")
for f in sorted(os.listdir(OUT_DIR)):
    print(" -", f)