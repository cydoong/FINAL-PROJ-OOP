# PayrollPro — Python Edition (PyQt6 build)

A complete rewrite of the PayrollPro PHP/MySQL payroll system as a
**single, standalone Python desktop application** — GUI, business
logic, and database access all in Python. No web server, no PHP, no
Apache required to run it.

Built with **PyQt6** (Qt6 for Python) for the interface, **SQLAlchemy**
for the database layer, and a dark neon-purple theme inspired by the
original system's design.

> A PySide6 build of this same app also exists if you ever need it —
> the two are functionally and visually identical; only the Qt binding
> underneath differs.

---

## What's included

Every feature from the original PHP system has a working Python
equivalent:

**Admin side**
- Dashboard — KPI cards, payroll trend chart, department headcount pie
  chart, recent activity feed
- Employees — add/edit, search & filter, archive, passcode generation,
  admin-assisted password reset
- Departments & Positions — full CRUD with the same guard rails
  (can't delete a department with active positions/employees, can't
  archive a position with staff assigned, etc.)
- Pay Periods — CRUD with a delete-guard against periods that already
  have payroll history
- **Attendance** — calendar-driven daily time-in/time-out log. Tap
  "Time In"/"Time Out" and the timestamp is captured automatically;
  once set, that field locks and can't be edited. Picking a date other
  than today prompts a confirmation first. A Reports tab gives a full
  per-employee monthly attendance report (days present/late/absent,
  total & overtime hours). A Holidays tab manages the company holiday
  calendar (name, date, Regular/Special) that drives holiday pay. This
  is the system of record Payroll pulls days-worked/overtime/lateness
  from — no more hand-typing attendance twice.
- Payroll — process & auto-finalize payroll. Days worked/overtime/
  absences/lateness (down to the minute) are pulled straight from
  Attendance (with an Override toggle for manual entry when needed).
  Basic pay is computed from the period's actual standard business
  days, so Late/Absence/Undertime show up as their own transparent
  deduction lines — Late Deduction and Undertime Deduction use the
  employee's minute rate (daily rate ÷ 8 ÷ 60), Absence Deduction uses
  the full daily rate, matching standard PH payroll practice (never a
  flat percentage guess). SSS/PhilHealth/Pag-IBIG are computed
  automatically from DB-backed rate tables (Settings → Gov't Rates),
  and both these and withholding tax are prorated/bracketed off the
  pay period's *actual calendar length* rather than a selectable
  "period type" label — so a mislabeled period can't quietly shrink
  contributions to a fraction of what they should be or push a full
  month's pay through a table meant for a much shorter period (both of
  which used to be possible and produced very wrong numbers). Regular/
  Special holiday pay follows DOLE rules via the Attendance → Holidays
  calendar (regular: 100% unworked / 200% worked; special: no-work-
  no-pay unworked / 130% worked), auto-added as Holiday Premium
  earnings or excluded from standard days as appropriate. Flexible
  payout method per employee (Bank Transfer, GCash, Maya, Cash,
  Check), with a per-run override. Status workflow (draft -> approved
  -> paid / cancelled), payslip viewer with a proper "Save Payslip as
  PDF" that renders an actual professional payslip layout (reportlab),
  not a print-dialog screenshot.
- Allowances & Deductions — manage types (taxable/mandatory flags);
  SSS/PhilHealth/Pag-IBIG/Late/Absence/Undertime and Holiday Premiums
  are flagged as auto-computed and no longer appear in the manual
  checklists
- Reports — 4 report views (by period, by employee, by deduction, by
  department) with a date-range filter and KPI totals
- Notifications & Diagnostics — full email/SMS history + one-click
  test send; email templates use a plain, professional business-letter
  style (no neon gradients) since these are official payroll
  correspondence
- Audit Log — every action in the system, searchable and filterable
- Archive — restore or permanently purge archived employees/positions,
  with the exact same conflict checks as the original (name/email
  collisions, missing department, employee-code re-use, etc.)
- Settings — switch between SQLite and your XAMPP MySQL database,
  configure email/SMS right from the GUI, and edit SSS/PhilHealth/
  Pag-IBIG contribution rates (Gov't Rates tab) without touching code
- **Appearance** — 5 switchable themes (Classic Neon, Emerald, Sky,
  Blossom, and Special), reachable by every role from the topbar's
  \U0001F3A8 menu, applied instantly app-wide with no restart. Special
  is the standout: pure-black base whose accent color changes *by
  section* — gold for Employees/Payroll, red for Attendance/Reports,
  purple for Departments/HR, quiet silver on the Dashboard — see
  `ui/theme.py`'s `SPECIAL_SECTION_ACCENTS` to remap which pages get
  which color.

**Employee side**
- Dashboard, My Payslips (view/Save as PDF), My Attendance (own daily
  time log + monthly summary — read-only; attendance is recorded by
  the admin, front-desk style), My Profile (update contact, banking/
  payout method, change username/password — both gated behind your
  personal passcode, exactly like the original)

**Auth flows** (all pixel-for-logic identical to the PHP version)
- Login with lockout after repeated failed attempts
- Activate Account (passcode -> email/phone -> done)
- Forgot Password (passcode + contact match -> OTP via email/SMS ->
  new password)

---

## Two database options

You choose this in Settings -> Database after first login (or by
editing `data/settings.json` directly):

1. **SQLite** (default) — a single file, zero configuration. Perfect
   for a fresh start or just trying the app out. Created automatically
   at `data/payroll_system.db` on first run, along with the same
   baseline departments/positions/allowance & deduction types the
   original system shipped with, plus a default admin account.

2. **MySQL / MariaDB via XAMPP** — point the app at your existing
   `payroll_db` database. The table and column names match the
   original schema exactly, so if you already have employees, payroll
   history, and audit logs from the PHP system, they show up
   immediately — no migration step needed. Just start XAMPP's MySQL
   service and fill in host/port/database/username/password in
   Settings.

Note: the original MySQL stored procedures/triggers/views aren't
required — all of that logic has been re-implemented in Python
(`core/payroll_engine.py`, `core/audit.py`) so behavior is identical
on both backends. If your existing `payroll_db` still has those
objects installed, that's harmless; they just won't be called.

---

## Getting started

```bash
# 1. Install dependencies
pip install -r requirements.txt

# 2. Run the app
python main.py
```

**Default admin login (fresh SQLite install):** `admin` / `admin123`

**Default employee password** (after activation, or after an admin
password reset): `emp123` — same as the original system.

If you point the app at your existing XAMPP database instead, use
whatever admin/employee credentials already exist there.

---

## Setting up Email & SMS (optional)

Notifications are disabled by default (matching the original system's
safe-by-default posture). To enable them, log in as admin and open
Settings:

- **Mail tab** — enter your SMTP host/port, username, and password.
  For Gmail: turn on 2-Step Verification, then create an App Password
  at myaccount.google.com/apppasswords and use that (not your normal
  Gmail password).
- **SMS tab** — choose Semaphore (Philippines) or Twilio, and enter
  your API key/credentials.

Use the Notifications & Diagnostics page to send yourself a test
email/SMS before relying on it for real payroll runs.

---

## Security notes

- Passwords are hashed with bcrypt for anything created by this
  Python app (a meaningful upgrade over the original's bare MD5).
- If you connect to an existing XAMPP database with legacy MD5
  password hashes, login still works — the verifier auto-detects the
  hash format. The moment a password is changed or reset through this
  app, it's transparently upgraded to bcrypt.
- Passcodes, OTPs, and audit logging all work exactly as before.

---

## Project structure

```
payrollpro/
├── main.py                    Entry point
├── requirements.txt
├── config/
│   └── settings.py             DB/mail/SMS settings, persisted to data/settings.json
├── database/
│   ├── models.py                SQLAlchemy ORM models (matches original MySQL schema)
│   ├── db_manager.py             Engine/session management, backend switching
│   ├── migrations.py             Lightweight additive column/table upgrades for pre-existing DBs
│   └── seed_data.py              Fresh-install seed data (incl. tax brackets & gov't rates)
├── core/                        All business logic (framework-agnostic)
│   ├── security.py, session.py, utils.py, audit.py
│   ├── auth_service.py           Login, activation, OTP, password resets
│   ├── employee_service.py, reference_service.py, pay_period_service.py
│   ├── attendance_service.py     Daily time-in/out log, locking, period aggregation
│   ├── gov_rates.py              SSS/PhilHealth/Pag-IBIG + BIR withholding tax computation
│   ├── payroll_engine.py         Payroll processing & finalization
│   ├── payslip_pdf.py            Professional payslip PDF generator (reportlab)
│   ├── payroll_notify.py, notifications.py
│   ├── archive_service.py, dashboard_service.py, reports_service.py
│   ├── audit_service.py, notification_service.py, profile_service.py
├── ui/
│   ├── theme.py                  App-wide QSS stylesheet (dark neon purple)
│   ├── login_window.py           Login / Activate / Forgot Password
│   ├── main_window.py            Sidebar + topbar + page router
│   ├── settings_dialog.py
│   ├── widgets/                  Shared widgets (cards, badges, tables, dialogs)
│   ├── admin/                    12 admin pages (incl. Attendance)
│   └── employee/                 4 employee pages
└── data/                        SQLite DB file + settings.json (created on first run)
```

---

## Building a standalone executable (optional)

If you'd like a double-clickable app that doesn't require Python
installed, use PyInstaller:

```bash
pip install pyinstaller
pyinstaller --name PayrollPro --windowed --onefile main.py
```

The output will be in `dist/PayrollPro` (or `PayrollPro.exe` on
Windows).
