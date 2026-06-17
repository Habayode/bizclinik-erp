"""Guard the authorization model: every mutating page must enforce a role
permission (not just login), and the permission matrix must keep low-privilege
roles away from destructive/posting actions. A page shipping without a gate is
the exact regression the bug hunt found — this keeps it from coming back."""
from __future__ import annotations

import pathlib

PAGES = pathlib.Path(__file__).resolve().parent.parent / "app" / "pages"

# Page -> the permission(s) at least one of which must be required to open it.
GATED_PAGES = {
    "1_Sales.py": ["post.invoice"],
    "2_Purchases.py": ["post.bill"],
    "3_Inventory.py": ["manage.products"],
    "4_Banking.py": ["manage.banks"],
    "5_Payroll.py": ["run.payroll"],
    "6_Fixed_Assets.py": ["manage.assets"],
    "7_Bank_Reconciliation.py": ["manage.banks"],
    "8_Recurring.py": ["post.journal"],
    "9_FIRS_Einvoice.py": ["post.invoice"],
    "10_General_Ledger.py": ["post.journal"],
    "11_Month_End.py": ["close.period"],
    "16_Data.py": ["import.data"],
    "17_Settings.py": ["manage.company", "manage.settings", "manage.customers",
                       "manage.suppliers", "manage.banks"],
    "18_Onboarding.py": ["manage.company"],
    "19_Admin.py": ["manage.users"],
    # Operator-only consoles: stronger than any tenant role permission, so they
    # are gated by require_platform_admin() rather than require_perm().
    "21_Tenants.py": ["require_platform_admin"],
    "22_Billing.py": ["require_platform_admin"],
    "23_CRM.py": ["manage.customers"],
    "24_Employees.py": ["manage.employees"],
    "25_Recruitment.py": ["manage.employees"],
    "26_Leave.py": ["manage.employees"],
    "28_Approvals.py": ["post.journal"],
}


_GATE_CALLS = ("require_perm", "require_any_perm", "require_platform_admin")


def test_every_mutating_page_enforces_a_permission():
    missing = []
    for fn, perms in GATED_PAGES.items():
        src = (PAGES / fn).read_text(encoding="utf-8")
        if not any(g in src for g in _GATE_CALLS):
            missing.append(f"{fn}: no {'/'.join(_GATE_CALLS)} call")
            continue
        if not any(p in src for p in perms):
            missing.append(f"{fn}: gated, but none of {perms} referenced")
    assert not missing, "Ungated/mis-gated pages:\n" + "\n".join(missing)


def test_gate_comes_after_login_not_instead_of_it():
    for fn in GATED_PAGES:
        src = (PAGES / fn).read_text(encoding="utf-8")
        assert "require_login()" in src, f"{fn}: lost its require_login()"


def test_db_reset_button_requires_reset_db_perm():
    src = (PAGES / "16_Data.py").read_text(encoding="utf-8")
    # The destructive reset must be guarded by the reset.db permission inline.
    assert 'has_perm("reset.db")' in src


def test_permission_matrix_keeps_low_roles_out_of_danger():
    from bizclinik_erp.models.users import PERMISSIONS, Role
    viewer = PERMISSIONS[Role.VIEWER]
    for danger in ("reset.db", "import.data", "post.journal", "post.invoice",
                   "run.payroll", "close.period", "manage.users"):
        assert danger not in viewer, f"VIEWER must not have {danger}"
    # SALES/AP are scoped to their own posting only.
    assert "post.bill" not in PERMISSIONS[Role.SALES]
    assert "post.invoice" not in PERMISSIONS[Role.AP]
    # ADMIN retains the destructive ones (so they remain reachable at all).
    for p in ("reset.db", "close.period", "manage.users", "post.journal"):
        assert p in PERMISSIONS[Role.ADMIN]
