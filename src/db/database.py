from sqlalchemy import create_engine, inspect, text, event
from sqlalchemy.orm import sessionmaker, scoped_session
from config import DATABASE_URL

engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = scoped_session(sessionmaker(autocommit=False, autoflush=False, bind=engine))


@event.listens_for(engine, "connect")
def _set_sqlite_pragma(dbapi_connection, connection_record):
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA journal_mode=WAL")
    cursor.execute("PRAGMA busy_timeout=5000")
    cursor.close()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def _migrate_add_invoice_details():
    try:
        inspector = inspect(engine)
        if 'reimbursements' not in inspector.get_table_names():
            return
        existing_columns = [col['name'] for col in inspector.get_columns('reimbursements')]
        if 'invoice_details' not in existing_columns:
            with engine.connect() as conn:
                conn.execute(text("ALTER TABLE reimbursements ADD COLUMN invoice_details TEXT"))
                conn.commit()
            print("[MIGRATION] Added invoice_details column to reimbursements")
    except Exception as e:
        print(f"[MIGRATION WARNING] {e}")


def _migrate_add_applicant_email():
    try:
        inspector = inspect(engine)
        if 'reimbursements' not in inspector.get_table_names():
            return
        existing_columns = [col['name'] for col in inspector.get_columns('reimbursements')]
        if 'applicant_email' not in existing_columns:
            with engine.connect() as conn:
                conn.execute(text("ALTER TABLE reimbursements ADD COLUMN applicant_email VARCHAR(100)"))
                conn.commit()
            print("[MIGRATION] Added applicant_email column to reimbursements")
    except Exception as e:
        print(f"[MIGRATION WARNING] {e}")


def init_db():
    from src.db.models import Base
    Base.metadata.create_all(bind=engine)
    _migrate_add_invoice_details()
    _migrate_add_applicant_email()
    print("Database initialized successfully")
