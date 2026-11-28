"""Create the first General Manager account for local or emergency setup."""

from datetime import datetime
import os
import sys

from sqlalchemy import func, select

from app.database import Base, SessionLocal, engine
from app import models  # noqa: F401
from app.models import DepartmentCode, ShiftAssignment, User
from app.security import hash_password


def main() -> None:
    Base.metadata.create_all(bind=engine)
    email = os.environ.get("BOOTSTRAP_GM_EMAIL", "").strip().lower()
    username = os.environ.get("BOOTSTRAP_GM_USERNAME", "").strip().lower()
    name = os.environ.get("BOOTSTRAP_GM_NAME", "").strip()
    address = os.environ.get("BOOTSTRAP_GM_ADDRESS", "").strip()
    contact_number = os.environ.get("BOOTSTRAP_GM_CONTACT", "").strip()
    id_number = os.environ.get("BOOTSTRAP_GM_ID_NUMBER", "").strip()
    password = os.environ.get("BOOTSTRAP_GM_PASSWORD", "")
    shift_start = os.environ.get("BOOTSTRAP_GM_SHIFT_START", "")
    shift_end = os.environ.get("BOOTSTRAP_GM_SHIFT_END", "")
    if not all([email, username, name, address, contact_number, id_number, shift_start, shift_end]) or len(password) < 11:
        sys.exit("Set all BOOTSTRAP_GM_* identity and shift fields, plus a password of at least 11 characters.")
    start_at, end_at = datetime.fromisoformat(shift_start), datetime.fromisoformat(shift_end)
    if start_at.utcoffset() is None or end_at.utcoffset() is None or end_at <= start_at:
        sys.exit("Shift timestamps need timezone offsets, and the end must be after the start.")
    with SessionLocal() as db:
        if db.scalar(select(func.count(User.id))) != 0:
            sys.exit("Bootstrap refused: accounts already exist. Sign in as the General Manager.")
        manager = User(
            email=email,
            username=username,
            full_name=name,
            address=address,
            contact_number=contact_number,
            id_number=id_number,
            duties="Leads hotel operations, staff, service quality, compliance, and departmental reporting.",
            password_hash=hash_password(password),
            department=DepartmentCode.general_manager,
            is_admin=True,
            is_active=True,
        )
        db.add(manager)
        db.flush()
        db.add(ShiftAssignment(
            employee_id=manager.id,
            department=DepartmentCode.general_manager,
            shift_start_at=start_at,
            shift_end_at=end_at,
            assigned_by=manager.id,
            notes="Initial General Manager shift",
        ))
        db.commit()
    print(f"Initial General Manager registered as {username}.")


if __name__ == "__main__":
    main()

