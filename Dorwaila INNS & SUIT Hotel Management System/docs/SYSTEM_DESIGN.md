# DORWAILA INN'S & SUIT HOTEL Management System

**Location:** Reservation Road, Kenema
**Purpose:** Secure hotel records for guest reservations, staff and shifts, department operations, payments, expenditure, attendance, and leave.

## Users, roles, and account setup

The first General Manager (GM) registers once through a protected first-run setup page. The installer supplies a one-time `GM_SETUP_KEY`; registration is disabled after the first GM exists. The form is prefilled with the supplied John Vandi name, email, contact, staff ID and username. The manager enters the password and first shift details in the form. The GM can create and deactivate department accounts, assign duties and shifts, schedule staff, and access all department reports from the manager dashboard. Deactivation is used instead of permanent deletion so historical records remain available for audit.

Account fields are name, address, contact number (optional for staff; required for the GM setup form), email, ID number, username, password, department, assigned duties, and shift start/end. Passwords are hashed before storage and never returned from the API. The hotel address may be used for the GM's work address if appropriate; the manager's personal address and shift dates must be supplied during setup.

Department accounts can read and create operational records only in their own department. Admin & Finance has specific HR operations for staff attendance corrections and leave tracking. That does not grant it access to GM report endpoints. Staff can view their own shifts and attendance and submit their own leave requests. The GM and Admin & Finance can review leaves; neither may approve their own leave. Only the GM can create accounts, schedule shifts, and generate all-department reports.

## Department responsibilities

| Department | Main responsibilities recorded in the system | Access boundary |
|---|---|---|
| General Manager | Direct hotel operations and service quality; create/deactivate accounts; assign duties and work shifts; review expenditure and leave decisions; monitor attendance; inspect audit history; generate department, staff, shift, finance, reservation, and attendance reports. | Sole global account manager, scheduler, and cross-department report user. |
| Admin & Finance Management | Record invoices and expenditures; document cash, cheque, bank and online payments; reconcile receipts; maintain finance records; manage staff attendance corrections and leave updates; approve/reject expenditure when the GM grants the approver permission. | Finance and specific HR operations; no account administration or global report generation. |
| Front Desk Staff / Receptionist | Record guest name, phone and email; create bookings; select rooms and booking method; track check-in/out and reservation status; record payments with currency and method, and bank, cheque or online reference details. | Front Desk reservations, guest and payment records only. |
| Kitchen Management | Plan food preparation; log hygiene/food safety checks, meal service, ingredient use, waste, supply requests, incidents and kitchen expenses. | Kitchen operations and expenditure only. |
| Housekeeping Management | Schedule and record room cleaning/readiness, linen and amenity use, inspections, lost property, damage, maintenance requests and housekeeping expenses. | Housekeeping operations and expenditure only. |
| Bar Attendance Management | Record bar service and sales activity, payment reconciliation, stock consumption/waste, responsible-service incidents and bar expenses. | Bar operations and expenditure only. |
| Security System Management | Record patrols, key/access control, safety checks, incidents, emergency responses, shift handovers and security expenses. | Security records only; CCTV footage remains separately controlled. |
| Storekeeping / Warehouse Management | Record deliveries, stock receipts/issues, counts, damaged/expired goods, reorder needs, authorized department requisitions and supporting expenses. | Warehouse records only. Item-level stock ledger is a planned extension. |
| Operations Management | Coordinate maintenance and facilities; log faults, service requests, utilities, equipment checks, quality inspections, follow-ups and operational expenditure. | Operations records only. |

Assigned duties are recorded in the staff account and shown in GM shift reports. Department boundaries are enforced by API checks. Further per-task permission codes should be added as operations grow beyond the current department-level access model.

## Records and report rules

- **Reservations:** Guest contacts, room, check-in/out, booking channel (online, walk-in, phone, travel agent, other), status, room rate/currency, and record time.
- **Payments:** Amount and original currency, method (cash, cheque, bank transfer, online), status and paid time. Cheque records require bank and cheque numbers; bank transfer and online payments require a transaction reference. Never store card numbers or security codes.
- **Expenses:** Department, description, payee, amount, currency, submitter, submission time, status and approval decision. A submitter cannot approve their own expense.
- **Attendance:** Each record links to an assigned shift and worker. Staff clock their own time; authorized Admin & Finance users may correct or record attendance with a required note and audit log.
- **Staff leave:** Employee, start/end, reason, status, submitter, reviewer, review time and decision note. Staff can create their own requests; Admin & Finance and the GM can maintain decisions.
- **Currency:** SLE, USD and EUR. Totals remain grouped by currency until an approved, auditable exchange-rate table is implemented.
- **Reports:** GM-only report APIs cover activities, expenditure, payment methods, guest/reservation detail, employees, duties, shifts and attendance. Admin & Finance HR pages are operational record forms, not cross-department report generation.

## API map

| Endpoint | Purpose | Access |
|---|---|---|
| `GET /setup`, `POST /api/v1/auth/register-general-manager` | First GM registration | One-time; POST requires setup key |
| `POST /api/v1/auth/token`, `GET /api/v1/auth/me`, `GET /api/v1/welcome` | Login/profile/welcome | Public login; authenticated profile |
| `GET /login`, `GET /dashboard` | Login and staff dashboard | Dashboard data requires bearer token |
| `GET/POST /api/v1/gm/accounts`; `/api/v1/gm/accounts/{id}` | Create/list/deactivate/restore staff accounts | GM only |
| `/api/v1/rooms`, `/api/v1/reservations`, `/api/v1/reservations/{id}/payments` | Front Desk operations | Front Desk and GM |
| `/api/v1/departments/{department}/activities` | Department activity | Assigned department; GM may access across departments |
| `/api/v1/attendance/shifts`, `/api/v1/attendance/clock-in`, `/clock-out` | Scheduling and employee attendance | GM schedules; staff records own attendance |
| `/api/v1/hr/staff`, `/api/v1/hr/shifts`, `/api/v1/hr/attendance` | Attendance form and corrections | Admin & Finance and GM |
| `/api/v1/hr/leaves` and `/api/v1/hr/leaves/{id}/decision` | Submit and update leave requests | Staff own request; Admin & Finance/GM review |
| `/api/v1/expenses` | Submit and decide expenditures | Assigned department submits; GM/authorized finance approves |
| `/api/v1/gm/reports/summary`, `/finance`, `/attendance`, `/departments/{department}` | Cross-department reporting | GM only |

## Architecture and deployment

- FastAPI with Pydantic request validation and SQLAlchemy data access.
- PostgreSQL for hosted multi-user use; SQLite only for local learning.
- Signed bearer tokens and one-way password hashes; authorization checks at each protected API route.
- Render web service and PostgreSQL for deployment. Keep secrets in environment variables, use HTTPS, and configure backups before real use.

## Completion checks

1. First-run GM registration requires the setup key and closes after initial registration.
2. The GM can create staff accounts with department, duties, and shift details; deactivated accounts cannot sign in.
3. Staff cannot write operational activity or expenditure for another department.
4. Only the GM can access cross-department reporting and account management.
5. The Admin & Finance dashboard can view and update staff attendance and leave records; each change is audited.
6. Reservation records preserve guest, room, stay, channel, and payment method/reference details in SLE, USD or EUR.

## Current limits

This is an API starter with login/setup, a General Manager account/report workspace, and an Admin & Finance attendance/leave dashboard; it is not a complete property-management product. Item-level warehouse stock, payroll, leave balances, automated overtime, report exports, exchange-rate conversion, receipt attachments, refunds, database migrations, and robust concurrent room reservation locks still need implementation. Use versioned database migrations, security review, backups with restore checks, monitoring, and privacy retention rules before real hotel operations.
