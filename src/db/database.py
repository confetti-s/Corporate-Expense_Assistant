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

def _migrate_add_chat_history():
    """创建 chat_history 表（如果不存在）"""
    try:
        from src.db.models import ChatHistory
        inspector = inspect(engine)
        if 'chat_history' not in inspector.get_table_names():
            with engine.connect() as conn:
                conn.execute(text("""
                    CREATE TABLE chat_history (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        user_id VARCHAR(32) NOT NULL,
                        role VARCHAR(20) NOT NULL,
                        content TEXT NOT NULL,
                        reimbursement_id INTEGER NULL,
                        created_at DATETIME DEFAULT CURRENT_TIMESTAMP
                    )
                """))
                conn.execute(text("CREATE INDEX idx_chat_user_id ON chat_history(user_id)"))
                conn.execute(text("CREATE INDEX idx_chat_created_at ON chat_history(created_at)"))
                conn.commit()
            print("[MIGRATION] Created chat_history table")
    except Exception as e:
        print(f"[MIGRATION WARNING] chat_history migration failed: {e}")

def _migrate_add_invoice_valid_fields():
    try:
        inspector = inspect(engine)
        if 'invoices' not in inspector.get_table_names():
            return
        existing_columns = [col['name'] for col in inspector.get_columns('invoices')]
        
        with engine.connect() as conn:
            if 'is_valid' not in existing_columns:
                conn.execute(text("ALTER TABLE invoices ADD COLUMN is_valid INTEGER DEFAULT 1"))
                print("[MIGRATION] Added is_valid column to invoices")
            
            if 'invalid_reason' not in existing_columns:
                conn.execute(text("ALTER TABLE invoices ADD COLUMN invalid_reason VARCHAR(200)"))
                print("[MIGRATION] Added invalid_reason column to invoices")
            
            conn.commit()
    except Exception as e:
        print(f"[MIGRATION WARNING] {e}")


def init_db():
    from src.db.models import Base
    Base.metadata.create_all(bind=engine)
    _migrate_add_invoice_details()
    _migrate_add_applicant_email()
    _migrate_add_chat_history()
    _migrate_add_invoice_valid_fields()
    print("Database initialized successfully")
