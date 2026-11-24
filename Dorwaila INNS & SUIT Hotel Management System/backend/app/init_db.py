"""Create tables and add the latest optional user-profile columns."""

from sqlalchemy import inspect, text

from app.database import Base, engine
from app import models  # noqa: F401

Base.metadata.create_all(bind=engine)

def add_missing_user_columns() -> None:
    existing = {column["name"] for column in inspect(engine).get_columns("users")}
    additions = {
        "username": "VARCHAR(80)",
        "address": "VARCHAR(500)",
        "id_number": "VARCHAR(120)",
        "duties": "TEXT",
    }
    with engine.begin() as connection:
        for name, sql_type in additions.items():
            if name not in existing:
                connection.execute(text(f"ALTER TABLE users ADD COLUMN {name} {sql_type}"))
        connection.execute(text("CREATE UNIQUE INDEX IF NOT EXISTS ix_users_username ON users (username)"))
        connection.execute(text("CREATE UNIQUE INDEX IF NOT EXISTS ix_users_id_number ON users (id_number)"))


add_missing_user_columns()
print("Hotel management database schema is ready.")

