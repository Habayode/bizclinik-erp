# Staged migration — money columns float8 → NUMERIC(18,2)

**Status: STAGED. Not yet applied to live.** Run deliberately in a maintenance
window. The application already routes money summation through Decimal
(`bizclinik_erp.money.msum`), so the live books are not drifting; this step makes
the *storage* exact as well and closes the float8 hazard from the audit.

Scope: Postgres only (the live backend). SQLite (dev/test) is a no-op.

## Why it's low-risk but still gated
- Each column is converted with `USING (col::numeric(18,2))`, which **rounds any
  float8 artefact to a clean 2dp value** — it does not invent or move money.
- The script wraps each database in **one transaction** and **aborts that DB**
  (rolls back) if `SUM(debit)`/`SUM(credit)` on `journal_line` move by > ₦0.005.
- It is **idempotent**: columns already `numeric` are skipped.
- Python continues to receive floats (SQLAlchemy `Float` reads a NUMERIC column
  fine), so no application redeploy is required for this step.

## Procedure

1. **Announce a short maintenance window** (the ALTERs take a table lock per
   table; on SME-sized data this is seconds per tenant).

2. **Back up every database first** (control + default + each tenant):
   ```bash
   ssh root@165.227.224.154
   mkdir -p /root/predecimal-$(date +%F)
   for db in $(sudo -u postgres psql -tAc "SELECT datname FROM pg_database WHERE datname LIKE 'bizclinik%'"); do
     sudo -u postgres pg_dump -Fc "$db" > /root/predecimal-$(date +%F)/$db.dump
   done
   ```

3. **Dry run** (lists columns to convert per DB; changes nothing):
   ```bash
   cd /opt/bizclinik-erp
   set -a; . /etc/bizclinik/pg.env; . /opt/bizclinik-erp/.env; set +a
   ./venv/bin/python -m deploy.migrations.decimalize_money --all-tenants --dry-run
   ```
   Eyeball the column list. It is derived from the ORM: every `Float` column
   except the quantity/rate/score names in `NON_MONEY_COLUMNS`.

4. **Apply** (transactional per DB; self-aborts a DB if its trial balance moves):
   ```bash
   ./venv/bin/python -m deploy.migrations.decimalize_money --all-tenants
   ```
   Each line of output shows `tb_before` == `tb_after` for that database.

5. **Spot-check** one tenant in the app (Reports → Trial Balance / Balance
   Sheet) — totals must be identical to before. No service restart is needed,
   but restarting is harmless:
   ```bash
   systemctl restart bizclinik-erp bizclinik-api
   ```

## Rollback
If anything looks wrong, restore the affected database from step 2:
```bash
sudo -u postgres dropdb <db> && sudo -u postgres createdb <db>
sudo -u postgres pg_restore -d <db> /root/predecimal-<date>/<db>.dump
```

## Verification checklist (per tenant)
- [ ] `tb_before` == `tb_after` in the script output
- [ ] Reports → Trial Balance: Total DR == Total CR, unchanged
- [ ] Reports → Balance Sheet: A = L + E, unchanged
- [ ] A new invoice + receipt still posts and reconciles
