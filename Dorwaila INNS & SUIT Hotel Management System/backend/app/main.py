from datetime import datetime, timezone
import hmac
from pathlib import Path
from typing import Annotated
from uuid import UUID

from fastapi import Depends, FastAPI, Header, HTTPException
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.database import Base, engine, get_db
from app.models import (
    AttendanceRecord, AuditLog, DepartmentActivity, DepartmentCode, Expense, ExpenseDecision, ExpenseStatus,
    LeaveStatus, StaffLeave,
    Guest, Payment, Reservation, ReservationStatus, Room, User, now_utc,
    ShiftAssignment,
)
from app.config import settings
from app.schemas import (
    ActiveDepartmentCode, ActivityCreate, ActivityRead, AttendanceCorrection, AttendanceRead, ExpenseCreate, ExpenseDecisionInput,
    ExpenseRead, GeneralManagerRegistration, PaymentCreate, PaymentRead,
    ReservationCreate, ReservationRead, ReservationStatusUpdate, RoomCreate,
    RoomRead, ShiftCreate, ShiftRead, StaffLeaveCreate, StaffLeaveDecision, StaffLeaveRead, UserCreate, UserRead, WelcomeRead,
)
from app.security import (
    _dummy_password_hash, create_access_token, current_user, hash_password,
    require_admin, verify_password,
)

app = FastAPI(title="DORWAILA INN'S & SUIT HOTEL, Reservation Road, Kenema", version="0.3.0")
app.mount("/static", StaticFiles(directory=Path(__file__).parent / "static"), name="static")
Db = Annotated[Session, Depends(get_db)]
CurrentUser = Annotated[User, Depends(current_user)]
AdminUser = Annotated[User, Depends(require_admin)]
DEPARTMENT_CODES = (
    DepartmentCode.general_manager,
    DepartmentCode.admin_finance,
    DepartmentCode.front_desk,
    DepartmentCode.kitchen,
    DepartmentCode.housekeeping,
    DepartmentCode.bar,
    DepartmentCode.security,
    DepartmentCode.storekeeping,
    DepartmentCode.operations,
)

BRAND = "DORWAILA INN'S & SUIT HOTEL"
HOTEL_ADDRESS = "Reservation Road, Kenema"

FIRST_RUN_SETUP_HTML = f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>First-time General Manager setup</title>
<style>body{{font:16px system-ui;background:#f4f6f8;color:#17202a;margin:0}}main{{max-width:680px;margin:4vh auto;background:white;padding:2rem;border-radius:14px;box-shadow:0 8px 32px #15253618}}h1{{margin-bottom:.2rem}}.muted{{color:#52606d}}.hotel-image{{width:100%;height:210px;object-fit:cover;border-radius:10px;margin-bottom:1rem}}form{{display:grid;grid-template-columns:1fr 1fr;gap:1rem}}label{{display:grid;gap:.35rem}}input{{padding:.7rem;border:1px solid #aab4bf;border-radius:7px;font:inherit}}.wide{{grid-column:1/-1}}button{{padding:.8rem;border:0;border-radius:7px;background:#155e55;color:white;font-weight:700;font:inherit;cursor:pointer}}#message{{margin-top:1rem;white-space:pre-wrap}}@media(max-width:600px){{form{{grid-template-columns:1fr}}.wide{{grid-column:auto}}}}</style></head>
<body><main><img class="hotel-image" src="/static/hotel.jpg" alt="Dorwaila Inn's & Suit Hotel in Kenema"><img src="/static/hotel-logo.jpeg" alt="Dorwaila Inn and Suites Hotel logo" style="width:96px;height:96px;object-fit:contain"><h1>{BRAND}</h1><p class="muted">{HOTEL_ADDRESS} · First-time General Manager registration</p>
<p>Register the first General Manager account. The setup key is supplied by the system installer and this setup closes after registration.</p>
<form id="setup"><label>Full name<input name="full_name" value="John Vandi" required autocomplete="name"></label>
<label>Username<input name="username" value="john.vandi" required minlength="3" autocomplete="username"></label>
<label>Email<input name="email" type="email" value="john.vandi@dorwaila.com" required autocomplete="email"></label>
<label>Contact number<input name="contact_number" type="tel" value="+23273734444" required autocomplete="tel"></label>
<label>ID number<input name="id_number" value="0001" required></label>
<label class="wide">Address<input name="address" required value="Reservation Road, Kenema" autocomplete="street-address"></label>
<label>Password<input name="password" type="password" required minlength="11" autocomplete="new-password"></label>
<label>One-time setup key<input name="setup_key" type="password" required autocomplete="off"></label>
<label>Shift starts<input name="shift_start_at" type="datetime-local" required></label>
<label>Shift ends<input name="shift_end_at" type="datetime-local" required></label>
<button class="wide" type="submit">Create General Manager account</button></form><div id="message" role="status"></div></main>
<script>const form=document.querySelector('#setup'),message=document.querySelector('#message');form.addEventListener('submit',async e=>{{e.preventDefault();message.textContent='Registering…';const d=new FormData(form);const data=Object.fromEntries(d.entries());const key=data.setup_key;delete data.setup_key;data.shift_start_at=new Date(data.shift_start_at).toISOString();data.shift_end_at=new Date(data.shift_end_at).toISOString();try{{const r=await fetch('/api/v1/auth/register-general-manager',{{method:'POST',headers:{{'Content-Type':'application/json','X-GM-Setup-Key':key}},body:JSON.stringify(data)}});const result=await r.json();if(!r.ok)throw new Error(result.detail||'Registration failed');message.textContent='Account created. Sign in with your username at /login.';form.reset();}}catch(err){{message.textContent=err.message;}}}});</script></body></html>"""

LOGIN_HTML = f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Hotel staff sign in</title>
<style>body{{font:16px system-ui;background:#f4f6f8;color:#17202a;margin:0}}main{{max-width:520px;margin:6vh auto;background:white;padding:2rem;border-radius:14px;box-shadow:0 8px 32px #15253618}}.hotel-image{{width:100%;height:230px;object-fit:cover;border-radius:10px}}form{{display:grid;gap:1rem}}label{{display:grid;gap:.35rem}}input{{padding:.75rem;border:1px solid #aab4bf;border-radius:7px;font:inherit}}button{{padding:.8rem;border:0;border-radius:7px;background:#155e55;color:white;font-weight:700;font:inherit;cursor:pointer}}#message{{margin-top:1rem;white-space:pre-wrap}}</style></head>
<body><main><img class="hotel-image" src="/static/hotel.jpg" alt="Dorwaila Inn's & Suit Hotel in Kenema"><p><img src="/static/hotel-logo.jpeg" alt="Dorwaila Inn and Suites Hotel logo" style="width:92px;height:92px;object-fit:contain"></p><h1>{BRAND}</h1><p>{HOTEL_ADDRESS}</p><h2>Sign in</h2><form id="login"><label>Username or email<input name="username" required autocomplete="username"></label><label>Password<input name="password" type="password" required autocomplete="current-password"></label><button>Sign in</button></form><p id="message" role="status"></p><a href="/setup">First-time GM setup</a> · <a href="/docs">Open API interface</a></main>
<script>const form=document.querySelector('#login'),message=document.querySelector('#message');form.addEventListener('submit',async e=>{{e.preventDefault();message.textContent='Signing in…';const data=new URLSearchParams(new FormData(form));try{{const r=await fetch('/api/v1/auth/token',{{method:'POST',headers:{{'Content-Type':'application/x-www-form-urlencoded'}},body:data}});const token=await r.json();if(!r.ok)throw new Error(token.detail||'Sign-in failed');sessionStorage.setItem('hotel_token',token.access_token);window.location.href='/dashboard';}}catch(err){{message.textContent=err.message;}}}});</script></body></html>"""

DASHBOARD_HTML = """<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>__BRAND__ | Staff dashboard</title><style>
*{box-sizing:border-box}body{margin:0;background:#f4f6f8;color:#17202a;font:15px system-ui,sans-serif}header{background:#103f3a;color:white;padding:1rem max(1rem,calc((100vw - 1180px)/2));display:flex;align-items:center;justify-content:space-between;gap:1rem}header img{width:92px;height:58px;object-fit:cover;border-radius:8px}main{max-width:1180px;margin:1.5rem auto;padding:0 1rem}.hero,.card{background:#fff;border-radius:14px;padding:1.2rem;margin-bottom:1rem;box-shadow:0 4px 22px #102a3310}.hero{display:flex;align-items:center;gap:1rem}.hero img{width:180px;height:120px;object-fit:cover;border-radius:10px}h1,h2{margin:.2rem 0 .7rem}.muted{color:#5e6a71}.grid{display:grid;grid-template-columns:1fr 1fr;gap:1rem}label{display:grid;gap:.35rem;margin:.5rem 0}input,select,textarea{width:100%;padding:.65rem;border:1px solid #b9c2c7;border-radius:7px;font:inherit}button,.button{border:0;border-radius:7px;background:#17665d;color:#fff;padding:.7rem 1rem;font:inherit;font-weight:650;cursor:pointer}button.secondary{background:#46545d}button.reject{background:#9b3939}.row{display:flex;gap:.75rem;align-items:end;flex-wrap:wrap}.row label{flex:1;min-width:180px}table{width:100%;border-collapse:collapse;margin-top:.6rem}th,td{text-align:left;padding:.6rem;border-bottom:1px solid #e4e8ea;vertical-align:top}th{background:#f5f8f8}.scroll{overflow:auto}#notice{white-space:pre-wrap;margin:.5rem 0}a{color:#155c55}@media(max-width:760px){.grid{grid-template-columns:1fr}.hero{align-items:flex-start;flex-direction:column}header{flex-wrap:wrap}}
</style></head><body><header><div><strong>__BRAND__</strong><div>Reservation Road, Kenema</div></div><div><a href="/docs" style="color:white;margin-right:1rem">API docs</a><button class="secondary" id="logout">Sign out</button></div></header>
<main><section class="hero"><img src="/static/hotel.jpg" alt="Hotel exterior"><div><img src="/static/hotel-logo.jpeg" alt="Hotel logo" style="width:84px;height:84px;object-fit:contain"><h1 id="welcome">Loading your dashboard…</h1><p class="muted" id="profile"></p><p id="notice" role="status"></p></div></section>
<section id="manager" hidden><div class="grid"><section class="card"><h2>Create staff account</h2><p class="muted">Assign one department, duties, and the staff member’s first shift. The password is stored as a one-way hash.</p><form id="account-form"><label>Full name<input name="full_name" required minlength="2"></label><label>Address<input name="address" required></label><label>Email<input name="email" type="email" required></label><label>Contact number<input name="contact_number" type="tel"></label><label>ID number<input name="id_number" required></label><label>Username<input name="username" required minlength="3"></label><label>Temporary password<input name="password" type="password" required minlength="12" autocomplete="new-password"></label><label>Department<select name="department" required><option value="admin_finance">Admin &amp; Finance</option><option value="front_desk">Front Desk / Reception</option><option value="kitchen">Kitchen</option><option value="housekeeping">Housekeeping</option><option value="bar">Bar</option><option value="security">Security</option><option value="storekeeping">Storekeeping / Warehouse</option><option value="operations">Operations</option></select></label><label class="wide">Assigned duties<textarea name="duties" required minlength="5" rows="3"></textarea></label><div class="row"><label>Shift starts<input name="shift_start_at" type="datetime-local" required></label><label>Shift ends<input name="shift_end_at" type="datetime-local" required></label></div><label class="wide">Shift notes<input name="shift_notes"></label><button class="wide">Create account and assign shift</button></form></section>
<section class="card"><h2>Hotel reports</h2><p class="muted">Reports contain guest and financial records. Keep report access restricted to the General Manager.</p><div class="row"><label>From<input id="report-from" type="datetime-local"></label><label>To<input id="report-to" type="datetime-local"></label></div><label>Department<select id="report-department"><option value="admin_finance">Admin &amp; Finance</option><option value="front_desk">Front Desk / Reception</option><option value="kitchen">Kitchen</option><option value="housekeeping">Housekeeping</option><option value="bar">Bar</option><option value="security">Security</option><option value="storekeeping">Storekeeping / Warehouse</option><option value="operations">Operations</option></select></label><div class="row"><button type="button" id="report-summary">All-department summary</button><button type="button" id="report-department-button">Department report</button><button type="button" id="report-finance">Finance report</button><button type="button" id="report-attendance">Attendance report</button></div><pre id="report-output" style="white-space:pre-wrap;overflow:auto;max-height:440px;background:#f5f8f8;padding:1rem;border-radius:8px" aria-live="polite">Choose a report to view its data.</pre></section></div>
<section class="card"><div class="row" style="justify-content:space-between"><h2>Staff accounts</h2><button type="button" class="secondary" id="refresh-accounts">Refresh accounts</button></div><div class="scroll"><table><thead><tr><th>Name</th><th>Username</th><th>Department</th><th>ID number</th><th>Duties</th><th>Status</th><th>Action</th></tr></thead><tbody id="account-rows"></tbody></table></div></section></section>
<section id="finance" hidden><div class="grid"><section class="card"><h2>Staff Attendance</h2><p class="muted">Review scheduled shifts and update attendance records. Changes are audit logged.</p><form id="attendance-form"><label>Staff shift<select name="shift_id" id="shift-select" required></select></label><div class="row"><label>Clock in<input name="clock_in_at" type="datetime-local" required></label><label>Clock out<input name="clock_out_at" type="datetime-local"></label></div><label>Update note<input name="note" required minlength="3" placeholder="Reason for entry or correction"></label><button>Save attendance update</button></form></section>
<section class="card"><h2>Staff Leave Updates</h2><form id="leave-form"><label>Staff member<select name="employee_id" id="employee-select" required></select></label><div class="row"><label>Leave starts<input name="starts_at" type="datetime-local" required></label><label>Leave ends<input name="ends_at" type="datetime-local" required></label></div><label>Reason<textarea name="reason" required minlength="3" rows="2"></textarea></label><button>Record leave request</button></form></section></div>
<section class="card"><div class="row" style="justify-content:space-between"><h2>Attendance records</h2><button type="button" class="secondary" id="refresh">Refresh records</button></div><div class="scroll"><table><thead><tr><th>Staff</th><th>Department</th><th>Shift</th><th>Clock in</th><th>Clock out</th><th>Note</th></tr></thead><tbody id="attendance-rows"></tbody></table></div></section>
<section class="card"><h2>Leave requests</h2><div class="scroll"><table><thead><tr><th>Staff</th><th>Leave period</th><th>Reason</th><th>Status</th><th>Update</th></tr></thead><tbody id="leave-rows"></tbody></table></div></section></section>
<section class="card" id="department-message" hidden><h2>Department workspace</h2><p>Your login is active. Use the API documentation for operations available to your department.</p><a href="/docs">Open department API</a></section></main>
<script>
const token=sessionStorage.getItem('hotel_token');if(!token)location.href='/login';
const notice=document.querySelector('#notice'),headers={'Authorization':'Bearer '+token,'Content-Type':'application/json'};
const esc=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
async function api(url,options={}){const r=await fetch(url,{...options,headers:{...headers,...options.headers}});let d={};try{d=await r.json()}catch{}if(!r.ok)throw new Error(d.detail||'Request failed');return d}
function localValue(value){if(!value)return '';const d=new Date(value);return new Date(d.getTime()-d.getTimezoneOffset()*60000).toISOString().slice(0,16)}
function human(value){return value?new Date(value).toLocaleString():'—'}
document.querySelector('#logout').onclick=()=>{sessionStorage.removeItem('hotel_token');location.href='/login'};
async function init(){try{const me=await api('/api/v1/auth/me');const w=await api('/api/v1/welcome');document.querySelector('#welcome').textContent=w.welcome_message;document.querySelector('#profile').textContent=`${me.full_name} · ${me.department||'General Manager'} · ${me.username||me.email}`;if(me.is_admin){document.querySelector('#manager').hidden=false;await loadAccounts()}if(me.is_admin||me.department==='admin_finance'){document.querySelector('#finance').hidden=false;await loadHr()}else if(!me.is_admin)document.querySelector('#department-message').hidden=false}catch(e){notice.textContent=e.message;if(e.message.includes('token')||e.message.includes('sign-in')){sessionStorage.removeItem('hotel_token');location.href='/login'}}}
async function loadAccounts(){const accounts=await api('/api/v1/gm/accounts');document.querySelector('#account-rows').innerHTML=accounts.map(a=>`<tr><td>${esc(a.full_name)}</td><td>${esc(a.username)}</td><td>${esc(a.department)}</td><td>${esc(a.id_number)}</td><td>${esc(a.duties)}</td><td>${a.is_active?'Active':'Disabled'}</td><td>${a.is_active?`<button class="reject" data-disable="${esc(a.id)}">Disable</button>`:`<button data-enable="${esc(a.id)}">Enable</button>`}</td></tr>`).join('')||'<tr><td colspan="7">No accounts found.</td></tr>';document.querySelectorAll('[data-disable]').forEach(b=>b.onclick=async()=>{try{await api(`/api/v1/gm/accounts/${b.dataset.disable}/disable`,{method:'PATCH'});notice.textContent='Account disabled.';await loadAccounts()}catch(e){notice.textContent=e.message}});document.querySelectorAll('[data-enable]').forEach(b=>b.onclick=async()=>{try{await api(`/api/v1/gm/accounts/${b.dataset.enable}/enable`,{method:'PATCH'});notice.textContent='Account enabled.';await loadAccounts()}catch(e){notice.textContent=e.message}})}
document.querySelector('#account-form').onsubmit=async e=>{e.preventDefault();const o=Object.fromEntries(new FormData(e.target));o.shift_start_at=new Date(o.shift_start_at).toISOString();o.shift_end_at=new Date(o.shift_end_at).toISOString();try{await api('/api/v1/gm/accounts',{method:'POST',body:JSON.stringify(o)});notice.textContent='Staff account created and first shift assigned.';e.target.reset();await loadAccounts()}catch(err){notice.textContent=err.message}};
document.querySelector('#refresh-accounts').onclick=async()=>{try{await loadAccounts();notice.textContent='Accounts refreshed.'}catch(e){notice.textContent=e.message}};
async function showReport(path){const out=document.querySelector('#report-output');out.textContent='Loading report…';const q=new URLSearchParams();const from=document.querySelector('#report-from').value,to=document.querySelector('#report-to').value;if(from)q.set('from_at',new Date(from).toISOString());if(to)q.set('to_at',new Date(to).toISOString());try{out.textContent=JSON.stringify(await api(path+(q.size?'?'+q:'')),null,2)}catch(e){out.textContent=e.message}}
document.querySelector('#report-summary').onclick=()=>showReport('/api/v1/gm/reports/summary');document.querySelector('#report-department-button').onclick=()=>showReport('/api/v1/gm/reports/departments/'+document.querySelector('#report-department').value);document.querySelector('#report-finance').onclick=()=>showReport('/api/v1/gm/reports/finance');document.querySelector('#report-attendance').onclick=()=>showReport('/api/v1/gm/reports/attendance');
async function loadHr(){const [staff,shifts,attendance,leaves]=await Promise.all([api('/api/v1/hr/staff'),api('/api/v1/hr/shifts'),api('/api/v1/hr/attendance'),api('/api/v1/hr/leaves')]);
const staffSelect=document.querySelector('#employee-select');staffSelect.innerHTML=staff.map(s=>`<option value="${esc(s.id)}">${esc(s.full_name)} — ${esc(s.department)}</option>`).join('');
const shiftSelect=document.querySelector('#shift-select');shiftSelect.innerHTML=shifts.map(s=>`<option value="${esc(s.id)}" data-in="${esc(s.clock_in_at||'')}" data-out="${esc(s.clock_out_at||'')}">${esc(s.employee_name)} · ${esc(s.department)} · ${esc(human(s.shift_start_at))}</option>`).join('');
document.querySelector('#attendance-rows').innerHTML=attendance.map(a=>`<tr><td>${esc(a.employee_name)}</td><td>${esc(a.department)}</td><td>${esc(human(a.shift_start_at))} – ${esc(human(a.shift_end_at))}</td><td>${esc(human(a.clock_in_at))}</td><td>${esc(human(a.clock_out_at))}</td><td>${esc(a.note)}</td></tr>`).join('')||'<tr><td colspan="6">No attendance records found.</td></tr>';
document.querySelector('#leave-rows').innerHTML=leaves.map(l=>`<tr><td>${esc(l.employee_name)}</td><td>${esc(human(l.starts_at))} – ${esc(human(l.ends_at))}</td><td>${esc(l.reason)}</td><td>${esc(l.status)}</td><td>${l.status==='pending'?`<button data-id="${esc(l.id)}" data-status="approved">Approve</button> <button class="reject" data-id="${esc(l.id)}" data-status="rejected">Reject</button>`:'—'}</td></tr>`).join('')||'<tr><td colspan="5">No leave requests found.</td></tr>';
document.querySelectorAll('#leave-rows button').forEach(b=>b.onclick=async()=>{try{await api(`/api/v1/hr/leaves/${b.dataset.id}/decision`,{method:'PATCH',body:JSON.stringify({status:b.dataset.status})});notice.textContent='Leave request updated.';await loadHr()}catch(e){notice.textContent=e.message}});
}
document.querySelector('#shift-select').addEventListener('change',e=>{const o=e.target.selectedOptions[0];document.querySelector('[name=clock_in_at]').value=localValue(o.dataset.in);document.querySelector('[name=clock_out_at]').value=localValue(o.dataset.out)});
document.querySelector('#attendance-form').onsubmit=async e=>{e.preventDefault();const d=new FormData(e.target),o=Object.fromEntries(d);try{await api('/api/v1/hr/attendance',{method:'POST',body:JSON.stringify({shift_id:o.shift_id,clock_in_at:new Date(o.clock_in_at).toISOString(),clock_out_at:o.clock_out_at?new Date(o.clock_out_at).toISOString():null,note:o.note})});notice.textContent='Attendance saved.';await loadHr()}catch(err){notice.textContent=err.message}};
document.querySelector('#leave-form').onsubmit=async e=>{e.preventDefault();const d=new FormData(e.target),o=Object.fromEntries(d);try{await api('/api/v1/hr/leaves',{method:'POST',body:JSON.stringify({employee_id:o.employee_id,starts_at:new Date(o.starts_at).toISOString(),ends_at:new Date(o.ends_at).toISOString(),reason:o.reason})});notice.textContent='Leave request recorded.';e.target.reset();await loadHr()}catch(err){notice.textContent=err.message}};
document.querySelector('#refresh').onclick=async()=>{try{await loadHr();notice.textContent='Records refreshed.'}catch(e){notice.textContent=e.message}};init();
</script></body></html>"""


def write_audit(db: Session, actor_id: UUID | None, action: str, target_type: str, target_id: str, details: str = "") -> None:
    db.add(AuditLog(actor_id=actor_id, action=action, target_type=target_type, target_id=target_id, details=details[:4000]))


def require_front_desk(user: User) -> None:
    if not user.is_admin and user.department != DepartmentCode.front_desk:
        raise HTTPException(status_code=403, detail="Front desk permission required")


def require_hr_manager(user: User) -> None:
    if not user.is_admin and user.department != DepartmentCode.admin_finance:
        raise HTTPException(status_code=403, detail="Admin & Finance or General Manager permission required")


@app.get("/api/v1/health")
def health():
    return {"status": "ok"}


@app.get("/", include_in_schema=False)
def root():
    return HTMLResponse(LOGIN_HTML)


@app.get("/setup", response_class=HTMLResponse, include_in_schema=False)
def setup_page(db: Db):
    registered = db.scalar(select(User.id).where(User.is_admin.is_(True))) is not None
    if registered:
        return HTMLResponse(
            "<main><h1>General Manager registration is complete</h1><a href='/login'>Go to login</a></main>",
            status_code=409,
        )
    return HTMLResponse(FIRST_RUN_SETUP_HTML)


@app.get("/login", response_class=HTMLResponse, include_in_schema=False)
def login_page():
    return HTMLResponse(LOGIN_HTML)


@app.get("/dashboard", response_class=HTMLResponse, include_in_schema=False)
def dashboard_page():
    return HTMLResponse(DASHBOARD_HTML.replace("__BRAND__", BRAND))


@app.post("/api/v1/auth/token")
def login(form: Annotated[OAuth2PasswordRequestForm, Depends()], db: Db):
    username = form.username.strip().lower()
    user = db.scalar(select(User).where(or_(User.username == username, User.email == username)))
    # Hash a dummy value on unknown accounts to reduce account-enumeration timing differences.
    if not verify_password(form.password, user.password_hash if user else _dummy_password_hash):
        raise HTTPException(status_code=401, detail="Incorrect email or password", headers={"WWW-Authenticate": "Bearer"})
    if not user:
        raise HTTPException(status_code=401, detail="Incorrect email or password", headers={"WWW-Authenticate": "Bearer"})
    if not user.is_active:
        raise HTTPException(status_code=403, detail="This account is disabled")
    write_audit(db, user.id, "sign_in", "user", str(user.id))
    db.commit()
    return {"access_token": create_access_token(user.id), "token_type": "bearer"}


@app.post("/api/v1/auth/register-general-manager", response_model=UserRead, status_code=201)
def register_general_manager(
    payload: GeneralManagerRegistration,
    db: Db,
    setup_key: Annotated[str | None, Header(alias="X-GM-Setup-Key")] = None,
):
    if not settings.gm_setup_key:
        raise HTTPException(status_code=503, detail="GM_SETUP_KEY is not configured")
    if not setup_key or not hmac.compare_digest(setup_key, settings.gm_setup_key):
        raise HTTPException(status_code=403, detail="Invalid setup key")
    if db.scalar(select(User.id).where(User.is_admin.is_(True))):
        raise HTTPException(status_code=409, detail="The General Manager account is already registered")
    email = payload.email.strip().lower()
    username = payload.username.strip().lower()
    id_number = payload.id_number.strip()
    duplicate = db.scalar(
        select(User.id).where(or_(User.email == email, User.username == username, User.id_number == id_number)).limit(1)
    )
    if duplicate:
        raise HTTPException(status_code=409, detail="Email, username, or ID number is already registered")
    manager = User(
        email=email,
        username=username,
        full_name=payload.full_name.strip(),
        address=payload.address.strip(),
        contact_number=payload.contact_number.strip(),
        id_number=id_number,
        duties="Leads hotel operations, staff, service quality, compliance, and departmental reporting.",
        password_hash=hash_password(payload.password),
        is_admin=True,
        is_active=True,
        department=DepartmentCode.general_manager,
    )
    db.add(manager)
    db.flush()
    db.add(ShiftAssignment(
        employee_id=manager.id,
        department=DepartmentCode.general_manager,
        shift_start_at=payload.shift_start_at,
        shift_end_at=payload.shift_end_at,
        assigned_by=manager.id,
        notes="Initial General Manager shift",
    ))
    write_audit(db, manager.id, "register_general_manager", "user", str(manager.id))
    db.commit()
    db.refresh(manager)
    return manager


@app.get("/api/v1/auth/me", response_model=UserRead)
def me(user: CurrentUser):
    return user


@app.get("/api/v1/welcome", response_model=WelcomeRead)
def department_welcome(user: CurrentUser):
    names = {
        DepartmentCode.general_manager: "General Manager",
        DepartmentCode.admin_finance: "Admin & Finance Management",
        DepartmentCode.front_desk: "Front Desk / Reception",
        DepartmentCode.kitchen: "Kitchen Management",
        DepartmentCode.housekeeping: "Housekeeping Management",
        DepartmentCode.bar: "Bar Attendance Management",
        DepartmentCode.security: "Security System Management",
        DepartmentCode.storekeeping: "Storekeeping / Warehouse Management",
        DepartmentCode.operations: "Operations Management",
    }
    department = "General Manager" if user.is_admin else names.get(user.department, "Department")
    return WelcomeRead(
        hotel_name=BRAND,
        address=HOTEL_ADDRESS,
        department=department,
        welcome_message=f"Welcome to {department} at {BRAND}, {HOTEL_ADDRESS}.",
        reservation_endpoint="/api/v1/reservations",
    )


@app.get("/api/v1/gm/accounts", response_model=list[UserRead])
def list_users(db: Db, admin: AdminUser):
    return list(db.scalars(select(User).order_by(User.created_at.desc())))


@app.post("/api/v1/gm/accounts", response_model=UserRead, status_code=201)
def create_user(payload: UserCreate, db: Db, admin: AdminUser):
    if payload.department == ActiveDepartmentCode.general_manager:
        raise HTTPException(status_code=422, detail="The protected first-run flow is used to register the sole General Manager")
    if payload.expense_approver and payload.department != ActiveDepartmentCode.admin_finance:
        raise HTTPException(status_code=422, detail="Expense approver permission is limited to Admin & Finance accounts")
    email = payload.email.strip().lower()
    username = payload.username.strip().lower()
    id_number = payload.id_number.strip()
    duplicate = db.scalar(
        select(User.id).where(or_(User.email == email, User.username == username, User.id_number == id_number)).limit(1)
    )
    if duplicate:
        raise HTTPException(status_code=409, detail="Email, username, or ID number is already registered")
    user = User(
        email=email,
        username=username,
        full_name=payload.full_name.strip(),
        address=payload.address.strip(),
        contact_number=payload.contact_number.strip() if payload.contact_number else None,
        id_number=id_number,
        duties=payload.duties.strip(),
        password_hash=hash_password(payload.password),
        department=DepartmentCode(payload.department.value),
        expense_approver=payload.expense_approver,
        is_admin=False,
    )
    db.add(user)
    db.flush()
    shift = ShiftAssignment(
        employee_id=user.id,
        department=user.department,
        shift_start_at=payload.shift_start_at,
        shift_end_at=payload.shift_end_at,
        notes=payload.shift_notes,
        assigned_by=admin.id,
    )
    db.add(shift)
    write_audit(db, admin.id, "create_user", "user", str(user.id), f"department={payload.department.value}")
    write_audit(db, admin.id, "assign_shift", "shift", str(shift.id), f"employee={user.id}")
    db.commit()
    db.refresh(user)
    return user


@app.patch("/api/v1/gm/accounts/{user_id}/disable", response_model=UserRead)
def disable_user(user_id: UUID, db: Db, admin: AdminUser):
    user = db.get(User, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    if user.id == admin.id:
        raise HTTPException(status_code=400, detail="The General Manager cannot deactivate the account currently in use")
    if user.is_admin:
        active_admins = db.scalar(select(func.count(User.id)).where(User.is_admin.is_(True), User.is_active.is_(True))) or 0
        if active_admins <= 1:
            raise HTTPException(status_code=400, detail="Cannot deactivate the last active General Manager account")
    user.is_active = False
    write_audit(db, admin.id, "disable_user", "user", str(user.id))
    db.commit()
    db.refresh(user)
    return user


@app.delete("/api/v1/gm/accounts/{user_id}", response_model=UserRead)
def delete_user(user_id: UUID, db: Db, admin: AdminUser):
    return disable_user(user_id, db, admin)


@app.patch("/api/v1/gm/accounts/{user_id}/enable", response_model=UserRead)
def enable_user(user_id: UUID, db: Db, admin: AdminUser):
    user = db.get(User, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    user.is_active = True
    write_audit(db, admin.id, "enable_user", "user", str(user.id))
    db.commit()
    db.refresh(user)
    return user


@app.post("/api/v1/gm/rooms", response_model=RoomRead, status_code=201)
def create_room(payload: RoomCreate, db: Db, admin: AdminUser):
    room_number = payload.room_number.strip()
    if db.scalar(select(Room.id).where(Room.room_number == room_number)):
        raise HTTPException(status_code=409, detail="Room number already exists")
    room = Room(room_number=room_number, room_type=payload.room_type.strip())
    db.add(room)
    db.flush()
    write_audit(db, admin.id, "create_room", "room", str(room.id))
    db.commit()
    db.refresh(room)
    return room


@app.get("/api/v1/rooms", response_model=list[RoomRead])
def list_rooms(db: Db, user: CurrentUser):
    require_front_desk(user)
    return list(db.scalars(select(Room).where(Room.is_active.is_(True)).order_by(Room.room_number)))


def room_is_available(db: Session, room_id: UUID, check_in: datetime, check_out: datetime, exclude_id: UUID | None = None) -> bool:
    conflicts = select(Reservation.id).where(
        Reservation.room_id == room_id,
        Reservation.status.in_([ReservationStatus.pending, ReservationStatus.confirmed, ReservationStatus.checked_in]),
        Reservation.check_in_at < check_out,
        Reservation.check_out_at > check_in,
    )
    if exclude_id:
        conflicts = conflicts.where(Reservation.id != exclude_id)
    return db.scalar(conflicts.limit(1)) is None


@app.post("/api/v1/reservations", response_model=ReservationRead, status_code=201)
def create_reservation(payload: ReservationCreate, db: Db, user: CurrentUser):
    require_front_desk(user)
    room = db.get(Room, payload.room_id)
    if not room or not room.is_active:
        raise HTTPException(status_code=404, detail="Active room not found")
    if not room_is_available(db, room.id, payload.check_in_at, payload.check_out_at):
        raise HTTPException(status_code=409, detail="Room is already reserved for part of this time")
    guest_data = payload.guest
    guest = Guest(name=guest_data.name.strip(), phone=guest_data.phone.strip(), email=guest_data.email)
    db.add(guest)
    db.flush()
    reservation = Reservation(
        guest_id=guest.id,
        room_id=room.id,
        check_in_at=payload.check_in_at,
        check_out_at=payload.check_out_at,
        booking_channel=payload.booking_channel,
        room_rate=payload.room_rate,
        currency=payload.currency,
        notes=payload.notes,
        created_by=user.id,
        status=ReservationStatus.pending,
    )
    db.add(reservation)
    db.flush()
    write_audit(db, user.id, "create_reservation", "reservation", str(reservation.id))
    db.commit()
    db.refresh(reservation)
    return reservation


@app.get("/api/v1/reservations", response_model=list[ReservationRead])
def list_reservations(db: Db, user: CurrentUser, from_at: datetime | None = None, to_at: datetime | None = None):
    require_front_desk(user)
    query = select(Reservation).order_by(Reservation.check_in_at)
    if from_at:
        query = query.where(Reservation.check_out_at >= from_at)
    if to_at:
        query = query.where(Reservation.check_in_at <= to_at)
    return list(db.scalars(query.limit(500)))


@app.get("/api/v1/reservations/{reservation_id}", response_model=ReservationRead)
def get_reservation(reservation_id: UUID, db: Db, user: CurrentUser):
    require_front_desk(user)
    reservation = db.get(Reservation, reservation_id)
    if not reservation:
        raise HTTPException(status_code=404, detail="Reservation not found")
    return reservation


@app.patch("/api/v1/reservations/{reservation_id}/status", response_model=ReservationRead)
def update_reservation_status(reservation_id: UUID, payload: ReservationStatusUpdate, db: Db, user: CurrentUser):
    require_front_desk(user)
    reservation = db.get(Reservation, reservation_id)
    if not reservation:
        raise HTTPException(status_code=404, detail="Reservation not found")
    allowed_transitions = {
        ReservationStatus.pending: {ReservationStatus.confirmed, ReservationStatus.cancelled},
        ReservationStatus.confirmed: {ReservationStatus.checked_in, ReservationStatus.cancelled},
        ReservationStatus.checked_in: {ReservationStatus.checked_out},
        ReservationStatus.checked_out: set(),
        ReservationStatus.cancelled: set(),
    }
    if payload.status != reservation.status and payload.status not in allowed_transitions[reservation.status]:
        raise HTTPException(status_code=409, detail="Invalid reservation status transition")
    if payload.status == ReservationStatus.confirmed and not room_is_available(
        db, reservation.room_id, reservation.check_in_at, reservation.check_out_at, reservation.id
    ):
        raise HTTPException(status_code=409, detail="Room is already reserved for part of this time")
    reservation.status = payload.status
    write_audit(db, user.id, "update_reservation_status", "reservation", str(reservation.id), payload.status.value)
    db.commit()
    db.refresh(reservation)
    return reservation


@app.post("/api/v1/reservations/{reservation_id}/payments", response_model=PaymentRead, status_code=201)
def record_payment(reservation_id: UUID, payload: PaymentCreate, db: Db, user: CurrentUser):
    require_front_desk(user)
    reservation = db.get(Reservation, reservation_id)
    if not reservation:
        raise HTTPException(status_code=404, detail="Reservation not found")
    payment = Payment(reservation_id=reservation.id, recorded_by=user.id, **payload.model_dump())
    db.add(payment)
    db.flush()
    write_audit(db, user.id, "record_payment", "payment", str(payment.id), f"reservation={reservation.id};currency={payment.currency}")
    db.commit()
    db.refresh(payment)
    return payment


@app.get("/api/v1/reservations/{reservation_id}/payments", response_model=list[PaymentRead])
def list_reservation_payments(reservation_id: UUID, db: Db, user: CurrentUser):
    require_front_desk(user)
    if not db.get(Reservation, reservation_id):
        raise HTTPException(status_code=404, detail="Reservation not found")
    return list(db.scalars(select(Payment).where(Payment.reservation_id == reservation_id).order_by(Payment.paid_at)))


@app.post("/api/v1/departments/{department}/activities", response_model=ActivityRead, status_code=201)
def create_department_activity(department: ActiveDepartmentCode, payload: ActivityCreate, db: Db, user: CurrentUser):
    department_code = DepartmentCode(department.value)
    if not user.is_admin and user.department != department_code:
        raise HTTPException(status_code=403, detail="You may only record activity for your department")
    activity = DepartmentActivity(
        department=department_code,
        title=payload.title.strip(),
        details=payload.details.strip(),
        recorded_by=user.id,
    )
    db.add(activity)
    db.flush()
    write_audit(db, user.id, "record_department_activity", "department_activity", str(activity.id))
    db.commit()
    db.refresh(activity)
    return activity


@app.get("/api/v1/departments/{department}/activities", response_model=list[ActivityRead])
def list_department_activities(department: ActiveDepartmentCode, db: Db, user: CurrentUser, limit: int = 100):
    department_code = DepartmentCode(department.value)
    if not user.is_admin and user.department != department_code:
        raise HTTPException(status_code=403, detail="You may only access activity for your department")
    safe_limit = max(1, min(limit, 500))
    query = select(DepartmentActivity).where(DepartmentActivity.department == department_code)
    return list(db.scalars(query.order_by(DepartmentActivity.recorded_at.desc()).limit(safe_limit)))


@app.post("/api/v1/attendance/shifts", response_model=ShiftRead, status_code=201)
def assign_shift(payload: ShiftCreate, db: Db, user: AdminUser):
    employee = db.get(User, payload.employee_id)
    if not employee or not employee.is_active or employee.department not in DEPARTMENT_CODES:
        raise HTTPException(status_code=404, detail="Active department employee not found")
    overlapping = db.scalar(
        select(ShiftAssignment.id).where(
            ShiftAssignment.employee_id == employee.id,
            ShiftAssignment.shift_start_at < payload.shift_end_at,
            ShiftAssignment.shift_end_at > payload.shift_start_at,
        ).limit(1)
    )
    if overlapping:
        raise HTTPException(status_code=409, detail="This employee already has an overlapping shift")
    shift = ShiftAssignment(
        employee_id=employee.id,
        department=employee.department,
        shift_start_at=payload.shift_start_at,
        shift_end_at=payload.shift_end_at,
        notes=payload.notes,
        assigned_by=user.id,
    )
    db.add(shift)
    db.flush()
    write_audit(db, user.id, "assign_shift", "shift", str(shift.id), f"employee={employee.id};department={employee.department.value}")
    db.commit()
    db.refresh(shift)
    return shift


@app.get("/api/v1/attendance/shifts", response_model=list[ShiftRead])
def list_shifts(db: Db, user: CurrentUser, from_at: datetime | None = None, to_at: datetime | None = None):
    query = select(ShiftAssignment).order_by(ShiftAssignment.shift_start_at)
    if not user.is_admin:
        query = query.where(ShiftAssignment.employee_id == user.id)
    if from_at:
        query = query.where(ShiftAssignment.shift_end_at >= from_at)
    if to_at:
        query = query.where(ShiftAssignment.shift_start_at <= to_at)
    return list(db.scalars(query.limit(500)))


@app.get("/api/v1/attendance/my/records", response_model=list[AttendanceRead])
def my_attendance_records(db: Db, user: CurrentUser, limit: int = 100):
    safe_limit = max(1, min(limit, 500))
    query = select(AttendanceRecord).where(AttendanceRecord.employee_id == user.id)
    return list(db.scalars(query.order_by(AttendanceRecord.clock_in_at.desc()).limit(safe_limit)))


@app.get("/api/v1/hr/staff")
def hr_staff_list(db: Db, user: CurrentUser):
    require_hr_manager(user)
    staff = db.scalars(select(User).where(User.is_active.is_(True)).order_by(User.full_name)).all()
    return [{"id": str(employee.id), "full_name": employee.full_name,
             "department": employee.department.value if employee.department else None,
             "id_number": employee.id_number}
            for employee in staff]


@app.get("/api/v1/hr/shifts")
def hr_shift_list(db: Db, user: CurrentUser, limit: int = 500):
    require_hr_manager(user)
    rows = db.execute(
        select(ShiftAssignment, User, AttendanceRecord)
        .join(User, ShiftAssignment.employee_id == User.id)
        .outerjoin(AttendanceRecord, AttendanceRecord.shift_id == ShiftAssignment.id)
        .order_by(ShiftAssignment.shift_start_at.desc()).limit(max(1, min(limit, 500)))
    ).all()
    return [{"id": str(shift.id), "employee_id": str(employee.id), "employee_name": employee.full_name,
             "department": shift.department.value, "shift_start_at": shift.shift_start_at,
             "shift_end_at": shift.shift_end_at, "clock_in_at": attendance.clock_in_at if attendance else None,
             "clock_out_at": attendance.clock_out_at if attendance else None}
            for shift, employee, attendance in rows]


@app.get("/api/v1/hr/attendance")
def hr_attendance_list(db: Db, user: CurrentUser, limit: int = 500):
    require_hr_manager(user)
    rows = db.execute(
        select(AttendanceRecord, ShiftAssignment, User)
        .join(ShiftAssignment, AttendanceRecord.shift_id == ShiftAssignment.id)
        .join(User, AttendanceRecord.employee_id == User.id)
        .order_by(AttendanceRecord.clock_in_at.desc()).limit(max(1, min(limit, 500)))
    ).all()
    return [{"id": str(record.id), "employee_id": str(employee.id), "employee_name": employee.full_name,
             "department": shift.department.value, "shift_start_at": shift.shift_start_at,
             "shift_end_at": shift.shift_end_at, "clock_in_at": record.clock_in_at,
             "clock_out_at": record.clock_out_at, "note": record.note}
            for record, shift, employee in rows]


@app.post("/api/v1/hr/attendance", status_code=200)
def hr_attendance_update(payload: AttendanceCorrection, db: Db, user: CurrentUser):
    require_hr_manager(user)
    shift = db.get(ShiftAssignment, payload.shift_id)
    if not shift:
        raise HTTPException(status_code=404, detail="Shift not found")
    record = db.scalar(select(AttendanceRecord).where(AttendanceRecord.shift_id == shift.id))
    if record:
        record.clock_in_at = payload.clock_in_at
        record.clock_out_at = payload.clock_out_at
        record.note = payload.note.strip()
        action = "correct_staff_attendance"
    else:
        record = AttendanceRecord(
            shift_id=shift.id,
            employee_id=shift.employee_id,
            clock_in_at=payload.clock_in_at,
            clock_out_at=payload.clock_out_at,
            note=payload.note.strip(),
        )
        db.add(record)
        action = "record_staff_attendance"
    db.flush()
    write_audit(db, user.id, action, "attendance", str(record.id), f"shift={shift.id}")
    db.commit()
    db.refresh(record)
    return record


@app.post("/api/v1/hr/leaves", response_model=StaffLeaveRead, status_code=201)
def create_staff_leave(payload: StaffLeaveCreate, db: Db, user: CurrentUser):
    manager = user.is_admin or user.department == DepartmentCode.admin_finance
    employee_id = payload.employee_id or user.id
    if employee_id != user.id and not manager:
        raise HTTPException(status_code=403, detail="You may submit leave only for your own account")
    employee = db.get(User, employee_id)
    if not employee:
        raise HTTPException(status_code=404, detail="Staff account not found")
    leave = StaffLeave(
        employee_id=employee_id, starts_at=payload.starts_at, ends_at=payload.ends_at,
        reason=payload.reason.strip(), submitted_by=user.id,
    )
    db.add(leave)
    db.flush()
    write_audit(db, user.id, "submit_staff_leave", "staff_leave", str(leave.id))
    db.commit()
    db.refresh(leave)
    return leave


@app.get("/api/v1/hr/leaves")
def list_staff_leaves(db: Db, user: CurrentUser, limit: int = 500):
    manager = user.is_admin or user.department == DepartmentCode.admin_finance
    query = select(StaffLeave, User).join(User, StaffLeave.employee_id == User.id)
    if not manager:
        query = query.where(StaffLeave.employee_id == user.id)
    rows = db.execute(query.order_by(StaffLeave.submitted_at.desc()).limit(max(1, min(limit, 500)))).all()
    return [{"id": str(leave.id), "employee_id": str(employee.id), "employee_name": employee.full_name,
             "starts_at": leave.starts_at, "ends_at": leave.ends_at, "reason": leave.reason,
             "status": leave.status.value, "submitted_by": str(leave.submitted_by),
             "submitted_at": leave.submitted_at, "reviewed_by": str(leave.reviewed_by) if leave.reviewed_by else None,
             "reviewed_at": leave.reviewed_at, "decision_note": leave.decision_note}
            for leave, employee in rows]


@app.patch("/api/v1/hr/leaves/{leave_id}/decision", response_model=StaffLeaveRead)
def decide_staff_leave(leave_id: UUID, payload: StaffLeaveDecision, db: Db, user: CurrentUser):
    require_hr_manager(user)
    leave = db.get(StaffLeave, leave_id)
    if not leave:
        raise HTTPException(status_code=404, detail="Leave request not found")
    if leave.status != LeaveStatus.pending:
        raise HTTPException(status_code=409, detail="Only pending leave requests can be decided")
    if leave.employee_id == user.id:
        raise HTTPException(status_code=403, detail="You cannot approve or reject your own leave request")
    leave.status = payload.status
    leave.reviewed_by = user.id
    leave.reviewed_at = now_utc()
    leave.decision_note = payload.decision_note
    write_audit(db, user.id, "decide_staff_leave", "staff_leave", str(leave.id), payload.status.value)
    db.commit()
    db.refresh(leave)
    return leave


@app.post("/api/v1/attendance/clock-in", response_model=AttendanceRead, status_code=201)
def clock_in(db: Db, user: CurrentUser):
    now = now_utc()
    shift = db.scalar(
        select(ShiftAssignment).where(
            ShiftAssignment.employee_id == user.id,
            ShiftAssignment.shift_start_at <= now,
            ShiftAssignment.shift_end_at >= now,
        ).order_by(ShiftAssignment.shift_start_at).limit(1)
    )
    if not shift:
        raise HTTPException(status_code=409, detail="No assigned shift is active at this time")
    if db.scalar(select(AttendanceRecord.id).where(AttendanceRecord.shift_id == shift.id)):
        raise HTTPException(status_code=409, detail="Attendance has already been recorded for this shift")
    attendance = AttendanceRecord(shift_id=shift.id, employee_id=user.id, clock_in_at=now)
    db.add(attendance)
    db.flush()
    write_audit(db, user.id, "clock_in", "attendance", str(attendance.id), f"shift={shift.id}")
    db.commit()
    db.refresh(attendance)
    return attendance


@app.post("/api/v1/attendance/clock-out", response_model=AttendanceRead)
def clock_out(db: Db, user: CurrentUser):
    open_record = db.scalar(
        select(AttendanceRecord).where(
            AttendanceRecord.employee_id == user.id,
            AttendanceRecord.clock_out_at.is_(None),
        ).order_by(AttendanceRecord.clock_in_at.desc()).limit(1)
    )
    if not open_record:
        raise HTTPException(status_code=409, detail="No open attendance record to clock out")
    now = now_utc()
    if now <= open_record.clock_in_at:
        raise HTTPException(status_code=409, detail="Clock-out must be after clock-in")
    open_record.clock_out_at = now
    write_audit(db, user.id, "clock_out", "attendance", str(open_record.id))
    db.commit()
    db.refresh(open_record)
    return open_record


@app.post("/api/v1/expenses", response_model=ExpenseRead, status_code=201)
def submit_expense(payload: ExpenseCreate, db: Db, user: CurrentUser):
    department = DepartmentCode(payload.department.value) if payload.department else user.department
    if department is not None and department not in DEPARTMENT_CODES:
        raise HTTPException(status_code=422, detail="Department is not active")
    if not user.is_admin and (department is None or user.department != department):
        raise HTTPException(status_code=403, detail="Expense must belong to your assigned department")
    if department is None:
        raise HTTPException(status_code=422, detail="department is required")
    expense = Expense(
        department=department,
        description=payload.description.strip(),
        payee=payload.payee,
        amount=payload.amount,
        currency=payload.currency,
        submitted_by=user.id,
        status=ExpenseStatus.pending,
    )
    db.add(expense)
    db.flush()
    write_audit(db, user.id, "submit_expense", "expense", str(expense.id))
    db.commit()
    db.refresh(expense)
    return expense


@app.get("/api/v1/expenses", response_model=list[ExpenseRead])
def list_expenses(db: Db, user: CurrentUser, status_filter: ExpenseStatus | None = None):
    if not user.is_admin and user.department is None:
        raise HTTPException(status_code=403, detail="Department permission required")
    query = select(Expense).order_by(Expense.submitted_at.desc())
    if not user.is_admin and not user.expense_approver:
        query = query.where(Expense.department == user.department)
    if status_filter:
        query = query.where(Expense.status == status_filter)
    return list(db.scalars(query.limit(500)))


@app.post("/api/v1/expenses/{expense_id}/decision", response_model=ExpenseRead)
def decide_expense(expense_id: UUID, payload: ExpenseDecisionInput, db: Db, user: CurrentUser):
    if not user.is_admin and not user.expense_approver:
        raise HTTPException(status_code=403, detail="Expense approver permission required")
    expense = db.get(Expense, expense_id)
    if not expense:
        raise HTTPException(status_code=404, detail="Expense not found")
    if expense.status != ExpenseStatus.pending:
        raise HTTPException(status_code=409, detail="Only pending expenses can be decided")
    if expense.submitted_by == user.id:
        raise HTTPException(status_code=403, detail="A user cannot approve their own expense")
    expense.status = payload.decision
    decision = ExpenseDecision(expense_id=expense.id, decision=payload.decision, note=payload.note, decided_by=user.id)
    db.add(decision)
    write_audit(db, user.id, "expense_decision", "expense", str(expense.id), payload.decision.value)
    db.commit()
    db.refresh(expense)
    return expense


@app.get("/api/v1/gm/reports/finance")
def finance_report(db: Db, admin: AdminUser, from_at: datetime | None = None, to_at: datetime | None = None):
    expense_query = select(Expense.department, Expense.currency, Expense.status, func.sum(Expense.amount).label("total"))
    if from_at:
        expense_query = expense_query.where(Expense.submitted_at >= from_at)
    if to_at:
        expense_query = expense_query.where(Expense.submitted_at <= to_at)
    expense_rows = db.execute(expense_query.group_by(Expense.department, Expense.currency, Expense.status)).all()
    payment_query = select(Payment.currency, Payment.method, Payment.status, func.sum(Payment.amount).label("total"))
    if from_at:
        payment_query = payment_query.where(Payment.paid_at >= from_at)
    if to_at:
        payment_query = payment_query.where(Payment.paid_at <= to_at)
    payment_rows = db.execute(payment_query.group_by(Payment.currency, Payment.method, Payment.status)).all()
    write_audit(db, admin.id, "generate_finance_report", "report", "finance", f"from={from_at};to={to_at}")
    db.commit()
    return {
        "period": {"from": from_at, "to": to_at},
        "reporting_currency": settings.reporting_currency,
        "expense_totals_by_department_currency_status": [
            {"department": dept.value, "currency": currency, "status": state.value, "amount": str(total)}
            for dept, currency, state, total in expense_rows
        ],
        "payment_totals_by_currency_method_status": [
            {"currency": currency, "method": method.value, "status": state.value, "amount": str(total)}
            for currency, method, state, total in payment_rows
        ],
        "note": "Totals remain grouped by original currency. Exchange-rate conversion is not implemented yet.",
    }


def _front_desk_report(db: Session, from_at: datetime | None, to_at: datetime | None):
    query = select(Reservation).order_by(Reservation.recorded_at.desc()).limit(500)
    if from_at:
        query = query.where(Reservation.recorded_at >= from_at)
    if to_at:
        query = query.where(Reservation.recorded_at <= to_at)
    reservations = db.scalars(query).all()
    results = []
    for reservation in reservations:
        guest = db.get(Guest, reservation.guest_id)
        room = db.get(Room, reservation.room_id)
        payments = db.scalars(
            select(Payment).where(Payment.reservation_id == reservation.id).order_by(Payment.paid_at)
        ).all()
        results.append({
            "reservation_id": str(reservation.id),
            "guest": {"name": guest.name, "phone": guest.phone, "email": guest.email} if guest else None,
            "room": {"room_number": room.room_number, "room_type": room.room_type} if room else None,
            "check_in_at": reservation.check_in_at,
            "check_out_at": reservation.check_out_at,
            "recorded_at": reservation.recorded_at,
            "booking_channel": reservation.booking_channel.value,
            "status": reservation.status.value,
            "payments": [
                {"amount": str(payment.amount), "currency": payment.currency,
                 "method": payment.method.value, "status": payment.status.value,
                 "bank_name": payment.bank_name, "cheque_number": payment.cheque_number,
                 "transaction_reference": payment.transaction_reference, "paid_at": payment.paid_at}
                for payment in payments
            ],
        })
    return results


@app.get("/api/v1/gm/reports/departments/{department}")
def department_report(
    department: ActiveDepartmentCode,
    db: Db,
    admin: AdminUser,
    from_at: datetime | None = None,
    to_at: datetime | None = None,
):
    department_code = DepartmentCode(department.value)
    activity_filter = [DepartmentActivity.department == department_code]
    expense_filter = [Expense.department == department_code]
    shift_filter = [ShiftAssignment.department == department_code]
    if from_at:
        activity_filter.append(DepartmentActivity.recorded_at >= from_at)
        expense_filter.append(Expense.submitted_at >= from_at)
        shift_filter.append(ShiftAssignment.shift_start_at >= from_at)
    if to_at:
        activity_filter.append(DepartmentActivity.recorded_at <= to_at)
        expense_filter.append(Expense.submitted_at <= to_at)
        shift_filter.append(ShiftAssignment.shift_start_at <= to_at)

    activities = db.scalars(
        select(DepartmentActivity).where(*activity_filter)
        .order_by(DepartmentActivity.recorded_at.desc()).limit(500)
    ).all()
    activity_count = db.scalar(
        select(func.count(DepartmentActivity.id)).where(*activity_filter)
    ) or 0
    expense_count = db.scalar(select(func.count(Expense.id)).where(*expense_filter)) or 0
    expenses = db.execute(
        select(Expense.currency, Expense.status, func.sum(Expense.amount))
        .where(*expense_filter)
        .group_by(Expense.currency, Expense.status)
    ).all()
    shifts = db.scalars(
        select(ShiftAssignment).where(*shift_filter)
        .order_by(ShiftAssignment.shift_start_at.desc()).limit(500)
    ).all()
    shift_count = db.scalar(select(func.count(ShiftAssignment.id)).where(*shift_filter)) or 0
    attendance_filter = [ShiftAssignment.department == department_code]
    if from_at:
        attendance_filter.append(ShiftAssignment.shift_start_at >= from_at)
    if to_at:
        attendance_filter.append(ShiftAssignment.shift_start_at <= to_at)
    attendance_count = db.scalar(
        select(func.count(AttendanceRecord.id))
        .join(ShiftAssignment, AttendanceRecord.shift_id == ShiftAssignment.id)
        .where(*attendance_filter)
    ) or 0
    leave_conditions = [User.department == department_code]
    if from_at:
        leave_conditions.append(StaffLeave.starts_at >= from_at)
    if to_at:
        leave_conditions.append(StaffLeave.starts_at <= to_at)
    leave_count = db.scalar(
        select(func.count(StaffLeave.id)).join(User, StaffLeave.employee_id == User.id).where(*leave_conditions)
    ) or 0
    leave_rows = db.execute(
        select(StaffLeave, User).join(User, StaffLeave.employee_id == User.id)
        .where(*leave_conditions).order_by(StaffLeave.starts_at.desc()).limit(500)
    ).all()
    attendance_rows = db.execute(
        select(AttendanceRecord, User)
        .join(ShiftAssignment, AttendanceRecord.shift_id == ShiftAssignment.id)
        .join(User, AttendanceRecord.employee_id == User.id)
        .where(*attendance_filter)
        .order_by(AttendanceRecord.clock_in_at.desc()).limit(500)
    ).all()
    attendance_by_shift = {record.shift_id: record for record, _employee in attendance_rows}
    employee_by_id = {employee.id: employee for _record, employee in attendance_rows}
    for shift in shifts:
        if shift.employee_id not in employee_by_id:
            employee = db.get(User, shift.employee_id)
            if employee:
                employee_by_id[employee.id] = employee
    write_audit(db, admin.id, "generate_department_report", "department", department_code.value)
    db.commit()
    return {
        "department": department_code.value,
        "period": {"from": from_at, "to": to_at},
        "activity_count": activity_count,
        "activities": [
            {"id": str(activity.id), "title": activity.title, "details": activity.details,
             "recorded_by": str(activity.recorded_by), "recorded_at": activity.recorded_at}
            for activity in activities
        ],
        "expense_count": expense_count,
        "shift_count": shift_count,
        "attendance_count": attendance_count,
        "shifts_without_attendance": shift_count - attendance_count,
        "leave_count": leave_count,
        "staff_leaves": [
            {"employee_id": str(employee.id), "employee_name": employee.full_name,
             "starts_at": leave.starts_at, "ends_at": leave.ends_at,
             "reason": leave.reason, "status": leave.status.value,
             "decision_note": leave.decision_note}
            for leave, employee in leave_rows
        ],
        "expense_totals": [
            {"currency": currency, "status": state.value, "amount": str(total)}
            for currency, state, total in expenses
        ],
        "shift_assignments": [
            {"id": str(shift.id), "employee_id": str(shift.employee_id),
             "employee_name": employee_by_id.get(shift.employee_id).full_name if employee_by_id.get(shift.employee_id) else None,
             "employee_username": employee_by_id.get(shift.employee_id).username if employee_by_id.get(shift.employee_id) else None,
             "employee_id_number": employee_by_id.get(shift.employee_id).id_number if employee_by_id.get(shift.employee_id) else None,
             "duties": employee_by_id.get(shift.employee_id).duties if employee_by_id.get(shift.employee_id) else None,
             "shift_start_at": shift.shift_start_at, "shift_end_at": shift.shift_end_at,
             "attendance": ({"clock_in_at": attendance_by_shift[shift.id].clock_in_at,
                             "clock_out_at": attendance_by_shift[shift.id].clock_out_at}
                            if shift.id in attendance_by_shift else None)}
            for shift in shifts
        ],
        "front_desk_reservations": _front_desk_report(db, from_at, to_at) if department_code == DepartmentCode.front_desk else None,
    }


@app.get("/api/v1/gm/reports/summary")
def admin_summary(db: Db, admin: AdminUser):
    summary = []
    for department in DEPARTMENT_CODES:
        activity_count = db.scalar(select(func.count(DepartmentActivity.id)).where(DepartmentActivity.department == department)) or 0
        expense_count = db.scalar(select(func.count(Expense.id)).where(Expense.department == department)) or 0
        pending_expense_count = db.scalar(
            select(func.count(Expense.id)).where(
                Expense.department == department,
                Expense.status == ExpenseStatus.pending,
            )
        ) or 0
        shift_count = db.scalar(select(func.count(ShiftAssignment.id)).where(ShiftAssignment.department == department)) or 0
        attendance_count = db.scalar(
            select(func.count(AttendanceRecord.id))
            .join(ShiftAssignment, AttendanceRecord.shift_id == ShiftAssignment.id)
            .where(ShiftAssignment.department == department)
        ) or 0
        summary.append({
            "department": department.value,
            "activity_count": activity_count,
            "expense_count": expense_count,
            "pending_expense_count": pending_expense_count,
            "shift_count": shift_count,
            "attendance_count": attendance_count,
            "shifts_without_attendance": shift_count - attendance_count,
        })
    write_audit(db, admin.id, "generate_summary_report", "report", "summary")
    db.commit()
    return {"departments": summary}


@app.get("/api/v1/gm/reports/attendance")
def attendance_report(db: Db, admin: AdminUser, from_at: datetime | None = None, to_at: datetime | None = None):
    report = []
    for department in DEPARTMENT_CODES:
        shifts_query = select(func.count(ShiftAssignment.id)).where(ShiftAssignment.department == department)
        records_query = (
            select(func.count(AttendanceRecord.id))
            .join(ShiftAssignment, AttendanceRecord.shift_id == ShiftAssignment.id)
            .where(ShiftAssignment.department == department)
        )
        if from_at:
            shifts_query = shifts_query.where(ShiftAssignment.shift_start_at >= from_at)
            records_query = records_query.where(ShiftAssignment.shift_start_at >= from_at)
        if to_at:
            shifts_query = shifts_query.where(ShiftAssignment.shift_start_at <= to_at)
            records_query = records_query.where(ShiftAssignment.shift_start_at <= to_at)
        shift_count = db.scalar(shifts_query) or 0
        attendance_count = db.scalar(records_query) or 0
        report.append({
            "department": department.value,
            "scheduled_shifts": shift_count,
            "attendance_records": attendance_count,
            "shifts_without_clock_in": shift_count - attendance_count,
        })
    write_audit(db, admin.id, "generate_attendance_report", "report", "attendance", f"from={from_at};to={to_at}")
    db.commit()
    return {"period": {"from": from_at, "to": to_at}, "departments": report}


@app.get("/api/v1/gm/audit-logs")
def audit_logs(db: Db, admin: AdminUser, limit: int = 100):
    safe_limit = max(1, min(limit, 500))
    entries = db.scalars(select(AuditLog).order_by(AuditLog.created_at.desc()).limit(safe_limit)).all()
    return [
        {"id": str(entry.id), "actor_id": str(entry.actor_id) if entry.actor_id else None,
         "action": entry.action, "target_type": entry.target_type, "target_id": entry.target_id,
         "details": entry.details, "created_at": entry.created_at}
        for entry in entries
    ]

