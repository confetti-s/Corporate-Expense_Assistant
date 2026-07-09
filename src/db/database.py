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

def _migrate_ensure_user_id_unique():
    """确保 users.user_id 有唯一索引，清理重复数据"""
    try:
        inspector = inspect(engine)
        if 'users' not in inspector.get_table_names():
            return

        # 先清理重复的 user_id，保留 id 最小的那条
        with engine.connect() as conn:
            result = conn.execute(text("""
                SELECT user_id, COUNT(*) as cnt
                FROM users
                GROUP BY user_id
                HAVING cnt > 1
            """))
            duplicates = result.fetchall()
            for row in duplicates:
                dup_user_id = row[0]
                # 找出这个 user_id 的所有记录，保留 id 最小的，删除其余
                conn.execute(text("""
                    DELETE FROM users
                    WHERE user_id = :uid
                      AND id NOT IN (
                          SELECT MIN(id) FROM users WHERE user_id = :uid
                      )
                """), {"uid": dup_user_id})
                conn.commit()
                print(f"[MIGRATION] Removed duplicate user_id: {dup_user_id}")

        # 确保唯一索引存在
        with engine.connect() as conn:
            indexes = inspector.get_indexes('users')
            has_unique = any(
                idx.get('unique') and 'user_id' in idx.get('column_names', [])
                for idx in indexes
            )
            if not has_unique:
                conn.execute(text("CREATE UNIQUE INDEX IF NOT EXISTS ix_users_user_id ON users(user_id)"))
                conn.commit()
                print("[MIGRATION] Added unique index on users.user_id")
    except Exception as e:
        print(f"[MIGRATION WARNING] ensure_user_id_unique: {e}")


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
                        session_id VARCHAR(64),
                        role VARCHAR(20) NOT NULL,
                        content TEXT NOT NULL,
                        reimbursement_id INTEGER NULL,
                        created_at DATETIME DEFAULT CURRENT_TIMESTAMP
                    )
                """))
                conn.execute(text("CREATE INDEX idx_chat_user_session ON chat_history(user_id, session_id)"))
                conn.execute(text("CREATE INDEX idx_chat_created_at ON chat_history(created_at)"))
                conn.commit()
            print("[MIGRATION] Created chat_history table with session_id and composite index")
    except Exception as e:
        print(f"[MIGRATION WARNING] chat_history migration failed: {e}")


def _migrate_add_session_id():
    """为已有的 chat_history 表新增 session_id 列和联合索引"""
    try:
        inspector = inspect(engine)
        if 'chat_history' not in inspector.get_table_names():
            return
        existing_columns = [col['name'] for col in inspector.get_columns('chat_history')]
        with engine.connect() as conn:
            if 'session_id' not in existing_columns:
                conn.execute(text("ALTER TABLE chat_history ADD COLUMN session_id VARCHAR(64)"))
                print("[MIGRATION] Added session_id column to chat_history")
            conn.commit()
        # 确保联合索引存在
        indexes = inspector.get_indexes('chat_history')
        has_composite = any(
            set(idx.get('column_names', [])) == {'user_id', 'session_id'}
            for idx in indexes
        )
        if not has_composite:
            with engine.connect() as conn:
                conn.execute(text("CREATE INDEX IF NOT EXISTS idx_chat_user_session ON chat_history(user_id, session_id)"))
                conn.commit()
            print("[MIGRATION] Added composite index on (user_id, session_id)")
    except Exception as e:
        print(f"[MIGRATION WARNING] add_session_id: {e}")

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


def _migrate_add_source_reimbursement_no():
    try:
        inspector = inspect(engine)
        if 'reimbursements' not in inspector.get_table_names():
            return
        existing_columns = [col['name'] for col in inspector.get_columns('reimbursements')]
        
        with engine.connect() as conn:
            if 'source_reimbursement_no' not in existing_columns:
                conn.execute(text("ALTER TABLE reimbursements ADD COLUMN source_reimbursement_no VARCHAR(32)"))
                conn.commit()
                print("[MIGRATION] Added source_reimbursement_no column to reimbursements")
    except Exception as e:
        print(f"[MIGRATION WARNING] {e}")


def _migrate_add_ai_suggestion():
    try:
        inspector = inspect(engine)
        if 'reimbursements' not in inspector.get_table_names():
            return
        existing_columns = [col['name'] for col in inspector.get_columns('reimbursements')]
        
        with engine.connect() as conn:
            if 'ai_suggestion' not in existing_columns:
                conn.execute(text("ALTER TABLE reimbursements ADD COLUMN ai_suggestion TEXT"))
                conn.commit()
                print("[MIGRATION] Added ai_suggestion column to reimbursements")
    except Exception as e:
        print(f"[MIGRATION WARNING] {e}")


def init_db():
    from src.db.models import Base
    Base.metadata.create_all(bind=engine)
    _migrate_ensure_user_id_unique()
    _migrate_add_invoice_details()
    _migrate_add_applicant_email()
    _migrate_add_chat_history()
    _migrate_add_session_id()
    _migrate_add_invoice_valid_fields()
    _migrate_add_source_reimbursement_no()
    _migrate_add_ai_suggestion()
    print("Database initialized successfully")
