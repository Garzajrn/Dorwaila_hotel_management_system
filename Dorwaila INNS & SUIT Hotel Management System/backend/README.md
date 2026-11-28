# Dorwaila Hotel Management API

FastAPI starter for **DORWAILA INN'S & SUIT HOTEL, Reservation Road, Kenema**. The first General Manager (GM) registers using a setup key. The GM then creates department accounts, assigns duties and shifts, and alone can view cross-department reports. Staff can access only their own department's operational records. Passwords are stored as hashes.

## Run locally (PowerShell)

From this `backend` directory:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
Copy-Item .env.example .env
```

Edit `.env`: set `SECRET_KEY` to a random value of at least 32 characters, `DATABASE_URL=sqlite:///./dorwaila_dev.db`, and `GM_SETUP_KEY` to a long one-time setup secret. Do not commit `.env`.

```powershell
python -m pip install -r requirements.txt
python -m app.init_db
uvicorn app.main:app --reload
```

Open `http://127.0.0.1:8000/setup` for the first GM registration form. Enter the same `GM_SETUP_KEY`; then sign in at `/login`. Setup closes once a GM account exists. Sign-in opens `/dashboard`; Admin & Finance and the GM see the Staff Attendance and Staff Leave Updates workspace. Other departments see their role landing page and can use `/docs` for permitted API operations. Use timestamps with timezone offsets (for Kenema, UTC is a practical API input); the hotel timezone is `Africa/Freetown`.

The first GM setup form is pre-filled with John Vandi's requested name, email, contact, ID and username. Confirm the address, enter the supplied password in the browser, and set the GM's first shift. The setup form requires at least 11 characters to accept the supplied password; it is submitted through the protected form and stored only as a hash, never placed in source code. Staff accounts add department, assigned duties, shift, optional contact number, and optionally the Admin & Finance expense-approver permission. Staff account deletion is a soft delete (deactivation) so historical reports remain intact. The manager dashboard provides account creation/deactivation, report filters and report results after sign-in.

If the setup page is unavailable, use the CLI bootstrap instead. Set `BOOTSTRAP_GM_EMAIL`, `BOOTSTRAP_GM_USERNAME`, `BOOTSTRAP_GM_NAME`, `BOOTSTRAP_GM_ADDRESS`, `BOOTSTRAP_GM_CONTACT`, `BOOTSTRAP_GM_ID_NUMBER`, `BOOTSTRAP_GM_PASSWORD`, `BOOTSTRAP_GM_SHIFT_START`, and `BOOTSTRAP_GM_SHIFT_END` in the shell, then run `python -m app.bootstrap_admin`. Shift values must be ISO timestamps with a timezone offset.

## API overview

- Authentication: `POST /api/v1/auth/token` (username or email), `GET /api/v1/auth/me`, `GET /api/v1/welcome`.
- First GM setup: `GET /setup`, `POST /api/v1/auth/register-general-manager` (requires `X-GM-Setup-Key`).
- GM account and room setup: `/api/v1/gm/accounts`, `/api/v1/gm/rooms`.
- Front Desk reservations and payments: `/api/v1/rooms`, `/api/v1/reservations`, `/api/v1/reservations/{id}/payments`.
- Department activity: `/api/v1/departments/{department}/activities`.
- Schedules and attendance: `/api/v1/attendance/shifts`, `/api/v1/attendance/clock-in`, `/api/v1/attendance/clock-out`.
- Admin & Finance HR workspace: `/dashboard` includes Staff Attendance updates and Staff Leave Updates. The corresponding `/api/v1/hr/*` endpoints allow Admin & Finance and GM to view staff, correct attendance with an audit note, and review leave; ordinary staff can submit and view their own leave requests.
- Expenses: `/api/v1/expenses`; GM or an explicitly authorized Admin & Finance officer can approve/reject.
- GM-only reports and audit logs: `/api/v1/gm/reports/summary`, `/finance`, `/attendance`, `/departments/{department}`, `/api/v1/gm/audit-logs`.

Currency values are SLE, USD, and EUR. Finance totals stay separated by original currency; no exchange rates are guessed. Reservation records include guest name, phone, email, room, check-in/out, booking channel, record time, and payment method/details (including bank and cheque reference when applicable).

## Docker Compose

Copy `.env.example` to `.env`, set unique secrets and a strong database password, then from this directory:

```powershell
docker compose up --build -d
```

Open `http://localhost:8000/setup`. The container runs the table initializer on startup.

## Deploy with Render

The repository includes a root `render.yaml` Blueprint. Push the repository to a Git provider, then in Render choose **New → Blueprint**, connect it, review the web service and PostgreSQL resources, and deploy. Render sets `SECRET_KEY`, `DATABASE_URL`, and `GM_SETUP_KEY`; check the web service environment page and copy the generated `GM_SETUP_KEY` securely. Open `https://YOUR-SERVICE.onrender.com/setup`, register the first GM, and then use `/login` or `/docs`.

For a managed business system, use a paid persistent PostgreSQL plan with backups and a paid web service. Render's free web services can sleep and free Postgres expires after 30 days without managed backups. Check Render's [Free instance limits](https://render.com/docs/free), [Blueprint reference](https://render.com/docs/blueprint-spec), and [FastAPI deployment guide](https://render.com/docs/deploy-fastapi) before deployment because plan details can change.

## Scope and production work

This is an API starter with login/setup pages and a basic staff/HR dashboard, not a complete hotel front-end. It does not yet implement inventory item/stock workflows, payroll, exchange-rate conversion, receipt uploads, refunds, advanced room locking, or automated absence/overtime rules. Before storing real records, add versioned database migrations, HTTPS, backups and restore checks, monitoring, rate limiting, MFA for GM, privacy retention rules, and security review. Do not use free hosting for real guest or financial records.

See [`../docs/SYSTEM_DESIGN.md`](../docs/SYSTEM_DESIGN.md) for the department duties and access model.
