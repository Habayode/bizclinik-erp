# Trakit365 ERP

A Nigerian SME ERP built around a SQLite system-of-record with proper
double-entry general ledger. Modules: Sales (quote → order → invoice →
receipt), Purchases (PO → bill → payment), Inventory (weighted-avg cost),
Banking (transfers · charges · reconciliation), Payroll (PAYE · pension ·
net), General Ledger (TB · journal entry · account inquiry), and Reports
(P&L · Balance Sheet · Cash Flow · AR/AP Aging · VAT return).

Compatible with the original **BizClinik xlsx** template — workbooks can be
imported to seed the database.

## Run locally

```powershell
python -m venv venv
.\venv\Scripts\Activate.ps1
pip install -r requirements.txt
python -m bizclinik_erp init
python -m streamlit run app/Home.py
```

Open http://localhost:8501.

To gate access with a password, set `BIZCLINIK_APP_PASSWORD` before launching:

```powershell
$env:BIZCLINIK_APP_PASSWORD = "your-secret"
python -m streamlit run app/Home.py
```

## Deploy to a Windows VPS

See [`deploy/RUNBOOK.md`](deploy/RUNBOOK.md). The flow is:

```powershell
git clone https://github.com/Habayode/bizclinik-erp.git C:\opt\bizclinik-erp
cd C:\opt\bizclinik-erp
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
.\deploy\bootstrap.ps1 -Subdomain "erp.hagai.online" -Password "<your-password>"
```

`bootstrap.ps1` provisions Python deps, a Cloudflare named tunnel, DNS, and
auto-starting Windows services for both the Streamlit app and `cloudflared`.

## CLI

```powershell
python -m bizclinik_erp init
python -m bizclinik_erp import-bizclinik path\to\workbook.xlsx
python -m bizclinik_erp pnl --from 2026-01-01 --to 2026-12-31
python -m bizclinik_erp balance-sheet --as-of 2026-12-31
python -m bizclinik_erp invoice-pdf <id> path\to\out.pdf
```
