import psycopg2
from psycopg2.extras import Json
import hmac
import os
from datetime import datetime, timedelta, timezone
from dotenv import load_dotenv

from services.password_service import hash_password

load_dotenv()

DATABASE_URL = os.environ.get("DATABASE_URL")


def get_connection():
    return psycopg2.connect(DATABASE_URL)


def init_db():
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id SERIAL PRIMARY KEY,
                email TEXT UNIQUE NOT NULL,
                password_hash TEXT NOT NULL,
                name TEXT,
                age INTEGER,
                gender TEXT,
                weight REAL,
                height REAL,
                bmi REAL,
                diabetes_status INTEGER DEFAULT 0,
                hypertension INTEGER DEFAULT 0,
                previous_liver_disease INTEGER DEFAULT 0,
                family_history INTEGER DEFAULT 0,
                activity_level TEXT,
                exercise_frequency TEXT,
                alcohol_consumption TEXT,
                smoking_status TEXT,
                terms_accepted_at TIMESTAMPTZ,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
            """)
            cur.execute(
                "ALTER TABLE users ADD COLUMN IF NOT EXISTS password_hash TEXT"
            )
            cur.execute(
                """
                ALTER TABLE users
                ADD COLUMN IF NOT EXISTS terms_accepted_at TIMESTAMPTZ
                """
            )
            cur.execute(
                """
                ALTER TABLE users
                ADD COLUMN IF NOT EXISTS created_at TIMESTAMPTZ
                NOT NULL DEFAULT NOW()
                """
            )
            cur.execute(
                """
                ALTER TABLE users
                ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ
                NOT NULL DEFAULT NOW()
                """
            )

            cur.execute(
                """
                SELECT EXISTS (
                    SELECT 1
                    FROM information_schema.columns
                    WHERE table_schema = current_schema()
                      AND table_name = 'users'
                      AND column_name = 'password'
                )
                """
            )
            has_legacy_password_column = cur.fetchone()[0]

            if has_legacy_password_column:
                cur.execute(
                    """
                    SELECT id, password
                    FROM users
                    WHERE password_hash IS NULL AND password IS NOT NULL
                    """
                )
                for user_id, legacy_password in cur.fetchall():
                    cur.execute(
                        """
                        UPDATE users
                        SET password_hash = %s
                        WHERE id = %s
                        """,
                        (hash_password(legacy_password), user_id)
                    )

            cur.execute(
                "SELECT COUNT(*) FROM users WHERE password_hash IS NULL"
            )
            if cur.fetchone()[0]:
                raise RuntimeError(
                    "Users without passwords require an account reset"
                )

            cur.execute(
                """
                SELECT LOWER(TRIM(email))
                FROM users
                GROUP BY LOWER(TRIM(email))
                HAVING COUNT(*) > 1
                LIMIT 1
                """
            )
            if cur.fetchone() is not None:
                raise RuntimeError(
                    "Duplicate user emails must be resolved before startup"
                )

            cur.execute(
                "UPDATE users SET email = LOWER(TRIM(email))"
            )
            cur.execute(
                """
                CREATE UNIQUE INDEX IF NOT EXISTS users_email_lower_unique
                ON users (LOWER(email))
                """
            )
            cur.execute(
                "ALTER TABLE users ALTER COLUMN password_hash SET NOT NULL"
            )
            if has_legacy_password_column:
                cur.execute(
                    "ALTER TABLE users DROP COLUMN password"
                )
        conn.commit()


def init_auth_tables():
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("""
            CREATE TABLE IF NOT EXISTS auth_sessions (
                id TEXT PRIMARY KEY,
                user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                refresh_token_hash TEXT NOT NULL,
                created_at TIMESTAMPTZ NOT NULL,
                expires_at TIMESTAMPTZ NOT NULL,
                last_used_at TIMESTAMPTZ,
                revoked_at TIMESTAMPTZ
            )
            """)
            cur.execute("""
            CREATE INDEX IF NOT EXISTS auth_sessions_user_idx
            ON auth_sessions (user_id, expires_at DESC)
            """)
            cur.execute("""
            CREATE TABLE IF NOT EXISTS auth_rate_limits (
                rate_key TEXT PRIMARY KEY,
                window_started_at TIMESTAMPTZ NOT NULL,
                attempts INTEGER NOT NULL,
                blocked_until TIMESTAMPTZ
            )
            """)
        conn.commit()


def get_auth_user_by_email(email):
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT id, password_hash, name, email, age, gender
                FROM users
                WHERE LOWER(email) = LOWER(%s)
                """,
                (email,)
            )
            return cur.fetchone()
    finally:
        conn.close()


def get_auth_user_by_id(user_id):
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT id, name, email, age, gender
                FROM users
                WHERE id = %s
                """,
                (user_id,)
            )
            row = cur.fetchone()
        if row is None:
            return None
        return {
            "user_id": row[0],
            "full_name": row[1],
            "email": row[2],
            "age": row[3],
            "gender": row[4],
        }
    finally:
        conn.close()


def update_password_hash(user_id, password_hash):
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE users
                SET password_hash = %s, updated_at = %s
                WHERE id = %s
                """,
                (password_hash, datetime.now(timezone.utc), user_id)
            )
        conn.commit()


def create_auth_session(
    session_id,
    user_id,
    refresh_token_hash,
    expires_at,
):
    now = datetime.now(timezone.utc)
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO auth_sessions
                    (
                        id,
                        user_id,
                        refresh_token_hash,
                        created_at,
                        expires_at
                    )
                VALUES (%s, %s, %s, %s, %s)
                """,
                (
                    session_id,
                    user_id,
                    refresh_token_hash,
                    now,
                    expires_at,
                )
            )
        conn.commit()


def get_auth_session(session_id):
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT
                    id,
                    user_id,
                    refresh_token_hash,
                    expires_at,
                    revoked_at
                FROM auth_sessions
                WHERE id = %s
                """,
                (session_id,)
            )
            return cur.fetchone()
    finally:
        conn.close()


def rotate_auth_session(
    session_id,
    presented_token_hash,
    new_session_id,
    new_token_hash,
    new_expires_at,
):
    now = datetime.now(timezone.utc)
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT user_id, refresh_token_hash, expires_at, revoked_at
                FROM auth_sessions
                WHERE id = %s
                FOR UPDATE
                """,
                (session_id,)
            )
            row = cur.fetchone()
            if row is None:
                return {"status": "invalid", "user_id": None}

            user_id, stored_hash, expires_at, revoked_at = row
            token_matches = hmac.compare_digest(
                stored_hash,
                presented_token_hash,
            )

            if not token_matches:
                return {"status": "invalid", "user_id": user_id}

            if revoked_at is not None:
                cur.execute(
                    """
                    UPDATE auth_sessions
                    SET revoked_at = COALESCE(revoked_at, %s)
                    WHERE user_id = %s
                    """,
                    (now, user_id)
                )
                return {"status": "reused", "user_id": user_id}

            if expires_at <= now:
                cur.execute(
                    """
                    UPDATE auth_sessions
                    SET revoked_at = %s
                    WHERE id = %s
                    """,
                    (now, session_id)
                )
                return {"status": "expired", "user_id": user_id}

            cur.execute(
                """
                UPDATE auth_sessions
                SET revoked_at = %s, last_used_at = %s
                WHERE id = %s
                """,
                (now, now, session_id)
            )
            cur.execute(
                """
                INSERT INTO auth_sessions
                    (
                        id,
                        user_id,
                        refresh_token_hash,
                        created_at,
                        expires_at
                    )
                VALUES (%s, %s, %s, %s, %s)
                """,
                (
                    new_session_id,
                    user_id,
                    new_token_hash,
                    now,
                    new_expires_at,
                )
            )
        conn.commit()
    return {"status": "rotated", "user_id": user_id}


def is_auth_session_active(session_id, user_id):
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT 1
                FROM auth_sessions
                WHERE id = %s
                  AND user_id = %s
                  AND revoked_at IS NULL
                  AND expires_at > %s
                """,
                (session_id, user_id, datetime.now(timezone.utc))
            )
            return cur.fetchone() is not None
    finally:
        conn.close()


def revoke_auth_session(session_id, user_id):
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE auth_sessions
                SET revoked_at = COALESCE(revoked_at, %s)
                WHERE id = %s AND user_id = %s
                """,
                (datetime.now(timezone.utc), session_id, user_id)
            )
        conn.commit()


def consume_auth_rate_limit(
    rate_key,
    limit,
    window_seconds,
    block_seconds,
):
    now = datetime.now(timezone.utc)
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO auth_rate_limits
                    (
                        rate_key,
                        window_started_at,
                        attempts,
                        blocked_until
                    )
                VALUES (%s, %s, 0, NULL)
                ON CONFLICT (rate_key) DO NOTHING
                """,
                (rate_key, now)
            )
            cur.execute(
                """
                SELECT window_started_at, attempts, blocked_until
                FROM auth_rate_limits
                WHERE rate_key = %s
                FOR UPDATE
                """,
                (rate_key,)
            )
            window_started_at, attempts, blocked_until = cur.fetchone()

            if blocked_until is not None and blocked_until > now:
                retry_after = max(
                    1,
                    int((blocked_until - now).total_seconds()),
                )
                return False, retry_after

            window = timedelta(seconds=window_seconds)
            if now - window_started_at >= window:
                window_started_at = now
                attempts = 1
                blocked_until = None
            else:
                attempts += 1
                if attempts > limit:
                    blocked_until = now + timedelta(
                        seconds=block_seconds
                    )

            cur.execute(
                """
                UPDATE auth_rate_limits
                SET
                    window_started_at = %s,
                    attempts = %s,
                    blocked_until = %s
                WHERE rate_key = %s
                """,
                (
                    window_started_at,
                    attempts,
                    blocked_until,
                    rate_key,
                )
            )
        conn.commit()

    if blocked_until is not None:
        return False, max(
            1,
            int((blocked_until - now).total_seconds()),
        )
    return True, 0


def clear_auth_rate_limit(rate_key):
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "DELETE FROM auth_rate_limits WHERE rate_key = %s",
                (rate_key,)
            )
        conn.commit()


def calculate_bmi(weight_kg, height_cm):
    if weight_kg is None or height_cm is None or height_cm <= 0:
        return None
    height_m = height_cm / 100
    return round(weight_kg / (height_m ** 2), 1)


def init_reports_table():
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("""
            CREATE TABLE IF NOT EXISTS reports (
                id SERIAL PRIMARY KEY,
                user_id INTEGER NOT NULL REFERENCES users(id),
                age INTEGER,
                platelets REAL,
                ast REAL,
                alt REAL,
                ggt REAL,
                bilirubin REAL,
                albumin REAL,
                inr REAL,
                pt REAL,
                afp REAL,
                hbsag INTEGER,
                anti_hcv INTEGER,
                ast_uln REAL,
                apri REAL,
                fib4 REAL,
                ultrasound_prediction TEXT,
                date_added TEXT NOT NULL
            )
            """)
            cur.execute(
                "ALTER TABLE reports ADD COLUMN IF NOT EXISTS ggt REAL"
            )
        conn.commit()


def init_upload_history_table():
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("""
            CREATE TABLE IF NOT EXISTS upload_history (
                id SERIAL PRIMARY KEY,
                user_id INTEGER NOT NULL REFERENCES users(id),
                report_type TEXT NOT NULL,
                date_uploaded TEXT NOT NULL
            )
            """)
        conn.commit()


def init_report_batch_tables():
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("""
            CREATE TABLE IF NOT EXISTS report_batches (
                id TEXT PRIMARY KEY,
                user_id INTEGER NOT NULL
                    REFERENCES users(id) ON DELETE CASCADE,
                idempotency_key TEXT NOT NULL,
                status TEXT NOT NULL
                    CHECK (status IN ('processing', 'completed', 'failed')),
                file_count INTEGER NOT NULL,
                report_id INTEGER REFERENCES reports(id) ON DELETE SET NULL,
                response_json JSONB,
                error_message TEXT,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                completed_at TIMESTAMPTZ,
                UNIQUE (user_id, idempotency_key)
            )
            """)
            cur.execute("""
            CREATE TABLE IF NOT EXISTS report_batch_files (
                id SERIAL PRIMARY KEY,
                batch_id TEXT NOT NULL
                    REFERENCES report_batches(id) ON DELETE CASCADE,
                file_index INTEGER NOT NULL,
                report_type TEXT NOT NULL,
                processing_status TEXT NOT NULL
                    CHECK (processing_status IN ('processed', 'failed')),
                extracted_data JSONB,
                error_message TEXT,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                UNIQUE (batch_id, file_index)
            )
            """)
            cur.execute(
                """
                ALTER TABLE reports
                ADD COLUMN IF NOT EXISTS batch_id TEXT
                REFERENCES report_batches(id) ON DELETE SET NULL
                """
            )
            cur.execute(
                """
                CREATE UNIQUE INDEX IF NOT EXISTS reports_batch_unique
                ON reports (batch_id)
                WHERE batch_id IS NOT NULL
                """
            )
            cur.execute(
                """
                ALTER TABLE upload_history
                ADD COLUMN IF NOT EXISTS batch_id TEXT
                REFERENCES report_batches(id) ON DELETE SET NULL
                """
            )
            cur.execute(
                """
                CREATE INDEX IF NOT EXISTS report_batches_user_created_idx
                ON report_batches (user_id, created_at DESC)
                """
            )
        conn.commit()


def init_report_documents_table():
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("""
            CREATE TABLE IF NOT EXISTS report_documents (
                id TEXT PRIMARY KEY,
                user_id INTEGER NOT NULL
                    REFERENCES users(id) ON DELETE CASCADE,
                report_id INTEGER NOT NULL
                    REFERENCES reports(id) ON DELETE CASCADE,
                batch_id TEXT NOT NULL
                    REFERENCES report_batches(id) ON DELETE CASCADE,
                file_index INTEGER NOT NULL,
                report_type TEXT NOT NULL,
                original_filename TEXT NOT NULL,
                storage_key TEXT NOT NULL UNIQUE,
                mime_type TEXT NOT NULL,
                size_bytes BIGINT NOT NULL CHECK (size_bytes >= 0),
                sha256 TEXT NOT NULL,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                UNIQUE (batch_id, file_index)
            )
            """)
            cur.execute(
                """
                CREATE INDEX IF NOT EXISTS
                    report_documents_user_created_idx
                ON report_documents (user_id, created_at DESC)
                """
            )
            cur.execute(
                """
                CREATE INDEX IF NOT EXISTS
                    report_documents_report_idx
                ON report_documents (report_id)
                """
            )
        conn.commit()


def init_report_analyses_table():
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("""
            CREATE TABLE IF NOT EXISTS report_analyses (
                report_id INTEGER PRIMARY KEY REFERENCES reports(id) ON DELETE CASCADE,
                analysis_version INTEGER NOT NULL,
                analysis_json JSONB NOT NULL,
                date_created TIMESTAMP NOT NULL
            )
            """)
        conn.commit()


def init_assistant_tables():
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("""
            CREATE TABLE IF NOT EXISTS assistant_conversations (
                id TEXT PRIMARY KEY,
                user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                context_report_id INTEGER REFERENCES reports(id) ON DELETE SET NULL,
                created_at TIMESTAMP NOT NULL,
                updated_at TIMESTAMP NOT NULL
            )
            """)
            cur.execute("""
            CREATE TABLE IF NOT EXISTS assistant_messages (
                id SERIAL PRIMARY KEY,
                conversation_id TEXT NOT NULL
                    REFERENCES assistant_conversations(id) ON DELETE CASCADE,
                role TEXT NOT NULL CHECK (role IN ('user', 'assistant')),
                content TEXT NOT NULL,
                created_at TIMESTAMP NOT NULL
            )
            """)
            cur.execute("""
            CREATE INDEX IF NOT EXISTS assistant_messages_conversation_idx
            ON assistant_messages (conversation_id, id DESC)
            """)
        conn.commit()


def init_support_tickets_table():
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("""
            CREATE TABLE IF NOT EXISTS support_tickets (
                id SERIAL PRIMARY KEY,
                user_id INTEGER NOT NULL
                    REFERENCES users(id) ON DELETE CASCADE,
                subject TEXT NOT NULL CHECK (
                    subject IN (
                        'Application Issue',
                        'Report Upload Query',
                        'AI Health Assessment Explanation',
                        'Other Support Query'
                    )
                ),
                description TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'open' CHECK (
                    status IN (
                        'open',
                        'in_progress',
                        'resolved',
                        'closed'
                    )
                ),
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
            """)
            cur.execute("""
            CREATE INDEX IF NOT EXISTS support_tickets_user_created_idx
            ON support_tickets (user_id, created_at DESC)
            """)
            cur.execute("""
            CREATE INDEX IF NOT EXISTS support_tickets_status_created_idx
            ON support_tickets (status, created_at ASC)
            """)
        conn.commit()


def init_user_achievements_table():
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("""
            CREATE TABLE IF NOT EXISTS user_achievements (
                user_id INTEGER NOT NULL
                    REFERENCES users(id) ON DELETE CASCADE,
                achievement_key TEXT NOT NULL,
                unlocked_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                PRIMARY KEY (user_id, achievement_key)
            )
            """)
            cur.execute(
                """
                CREATE INDEX IF NOT EXISTS
                    user_achievements_unlocked_idx
                ON user_achievements (user_id, unlocked_at DESC)
                """
            )
        conn.commit()


def unlock_user_achievements(user_id, achievement_keys):
    keys = list(dict.fromkeys(
        key
        for key in achievement_keys
        if isinstance(key, str) and key
    ))
    if not keys:
        return

    with get_connection() as conn:
        with conn.cursor() as cur:
            for key in keys:
                cur.execute(
                    """
                    INSERT INTO user_achievements
                        (user_id, achievement_key)
                    VALUES (%s, %s)
                    ON CONFLICT (user_id, achievement_key) DO NOTHING
                    """,
                    (user_id, key),
                )
        conn.commit()


def get_user_achievement_unlocks(user_id):
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT achievement_key, unlocked_at
                FROM user_achievements
                WHERE user_id = %s
                ORDER BY unlocked_at ASC, achievement_key ASC
                """,
                (user_id,),
            )
            return {
                key: unlocked_at
                for key, unlocked_at in cur.fetchall()
            }
    finally:
        conn.close()


def create_support_ticket(user_id, subject, description):
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO support_tickets
                    (user_id, subject, description)
                VALUES (%s, %s, %s)
                RETURNING id, subject, status, created_at
                """,
                (user_id, subject, description)
            )
            row = cur.fetchone()
        conn.commit()

    return {
        "ticket_id": row[0],
        "subject": row[1],
        "status": row[2],
        "created_at": row[3],
    }


def create_assistant_conversation_with_exchange(
    conversation_id,
    user_id,
    context_report_id,
    user_message,
    assistant_message,
):
    """Atomically create a conversation and save its first complete turn."""
    now = datetime.now()
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO assistant_conversations
                    (id, user_id, context_report_id, created_at, updated_at)
                VALUES (%s, %s, %s, %s, %s)
                """,
                (
                    conversation_id,
                    user_id,
                    context_report_id,
                    now,
                    now,
                )
            )
            cur.execute(
                """
                INSERT INTO assistant_messages
                    (conversation_id, role, content, created_at)
                VALUES
                    (%s, 'user', %s, %s),
                    (%s, 'assistant', %s, %s)
                """,
                (
                    conversation_id,
                    user_message,
                    now,
                    conversation_id,
                    assistant_message,
                    now,
                )
            )
        conn.commit()


def get_assistant_conversation(conversation_id, user_id):
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT id, user_id, context_report_id, created_at, updated_at
                FROM assistant_conversations
                WHERE id = %s AND user_id = %s
                """,
                (conversation_id, user_id)
            )
            row = cur.fetchone()
        return row
    finally:
        conn.close()


def get_assistant_messages(conversation_id, limit=12):
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT role, content
                FROM (
                    SELECT id, role, content
                    FROM assistant_messages
                    WHERE conversation_id = %s
                    ORDER BY id DESC
                    LIMIT %s
                ) AS recent_messages
                ORDER BY id ASC
                """,
                (conversation_id, limit)
            )
            rows = cur.fetchall()
        return [
            {"role": role, "content": content}
            for role, content in rows
        ]
    finally:
        conn.close()


def add_assistant_exchange(conversation_id, user_message, assistant_message):
    """Save one complete turn so failed provider calls do not leave half-turns."""
    now = datetime.now()
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO assistant_messages
                    (conversation_id, role, content, created_at)
                VALUES
                    (%s, 'user', %s, %s),
                    (%s, 'assistant', %s, %s)
                """,
                (
                    conversation_id,
                    user_message,
                    now,
                    conversation_id,
                    assistant_message,
                    now,
                )
            )
            cur.execute(
                """
                UPDATE assistant_conversations
                SET updated_at = %s
                WHERE id = %s
                """,
                (now, conversation_id)
            )
        conn.commit()


def add_uploaded_report(user_id, report_type):
    date_uploaded = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """INSERT INTO upload_history (user_id, report_type, date_uploaded)
                   VALUES (%s, %s, %s)""",
                (user_id, report_type, date_uploaded)
            )
        conn.commit()


def get_recent_reports(user_id, limit=3):
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT
                    history.report_type,
                    history.date_uploaded,
                    document.id,
                    document.report_id,
                    document.original_filename,
                    document.mime_type,
                    document.size_bytes
                FROM upload_history AS history
                LEFT JOIN report_documents AS document
                  ON document.batch_id = history.batch_id
                 AND document.report_type = history.report_type
                WHERE history.user_id = %s
                ORDER BY history.date_uploaded DESC, history.id DESC
                LIMIT %s
                """,
                (user_id, limit)
            )
            rows = cur.fetchall()
        return [
            {
                "report_type": row[0],
                "date_uploaded": row[1],
                "document_id": row[2],
                "report_id": row[3],
                "filename": row[4],
                "mime_type": row[5],
                "size_bytes": row[6],
                "file_available": row[2] is not None,
            }
            for row in rows
        ]
    finally:
        conn.close()


def get_report_document_for_user(document_id, user_id):
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT
                    id,
                    report_id,
                    report_type,
                    original_filename,
                    storage_key,
                    mime_type,
                    size_bytes,
                    created_at
                FROM report_documents
                WHERE id = %s AND user_id = %s
                """,
                (document_id, user_id),
            )
            row = cur.fetchone()
        if row is None:
            return None
        return {
            "document_id": row[0],
            "report_id": row[1],
            "report_type": row[2],
            "filename": row[3],
            "storage_key": row[4],
            "mime_type": row[5],
            "size_bytes": row[6],
            "created_at": row[7],
        }
    finally:
        conn.close()


def create_or_get_report_batch(
    batch_id,
    user_id,
    idempotency_key,
    file_count,
):
    """Create a processing batch or return the existing idempotent request."""
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO report_batches
                    (
                        id,
                        user_id,
                        idempotency_key,
                        status,
                        file_count
                    )
                VALUES (%s, %s, %s, 'processing', %s)
                ON CONFLICT (user_id, idempotency_key) DO NOTHING
                RETURNING
                    id,
                    status,
                    report_id,
                    response_json,
                    error_message,
                    file_count
                """,
                (
                    batch_id,
                    user_id,
                    idempotency_key,
                    file_count,
                ),
            )
            row = cur.fetchone()
            created = row is not None

            if row is None:
                cur.execute(
                    """
                    SELECT
                        id,
                        status,
                        report_id,
                        response_json,
                        error_message,
                        file_count
                    FROM report_batches
                    WHERE user_id = %s AND idempotency_key = %s
                    """,
                    (user_id, idempotency_key),
                )
                row = cur.fetchone()
        conn.commit()

    if row is None:
        raise RuntimeError("Could not create or retrieve report batch")
    return {
        "created": created,
        "batch_id": row[0],
        "status": row[1],
        "report_id": row[2],
        "response": row[3],
        "error_message": row[4],
        "file_count": row[5],
    }


def mark_report_batch_failed(
    batch_id,
    user_id,
    error_message,
    file_results=None,
):
    """Persist a safe batch failure and any completed per-file results."""
    file_results = file_results or []
    with get_connection() as conn:
        with conn.cursor() as cur:
            for item in file_results:
                cur.execute(
                    """
                    INSERT INTO report_batch_files
                        (
                            batch_id,
                            file_index,
                            report_type,
                            processing_status,
                            extracted_data,
                            error_message
                        )
                    VALUES (%s, %s, %s, %s, %s, %s)
                    ON CONFLICT (batch_id, file_index)
                    DO UPDATE SET
                        processing_status = EXCLUDED.processing_status,
                        extracted_data = EXCLUDED.extracted_data,
                        error_message = EXCLUDED.error_message
                    """,
                    (
                        batch_id,
                        item["file_index"],
                        item["report_type"],
                        item.get("status", "failed"),
                        Json(item.get("extracted_data", {})),
                        item.get("error"),
                    ),
                )
            cur.execute(
                """
                UPDATE report_batches
                SET
                    status = 'failed',
                    error_message = %s,
                    completed_at = %s
                WHERE id = %s
                  AND user_id = %s
                  AND status = 'processing'
                """,
                (
                    str(error_message)[:500],
                    datetime.now(timezone.utc),
                    batch_id,
                    user_id,
                ),
            )
        conn.commit()


def complete_report_batch(
    batch_id,
    user_id,
    age,
    report_data,
    file_results,
    response_payload,
    document_results=None,
):
    """Atomically save one report snapshot and complete its upload batch."""
    now = datetime.now(timezone.utc)
    date_added = now.strftime("%Y-%m-%d %H:%M:%S")
    document_results = document_results or []

    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT status
                FROM report_batches
                WHERE id = %s AND user_id = %s
                FOR UPDATE
                """,
                (batch_id, user_id),
            )
            row = cur.fetchone()
            if row is None or row[0] != "processing":
                raise RuntimeError("Report batch is not available for completion")

            cur.execute(
                """
                INSERT INTO reports
                    (
                        user_id,
                        age,
                        platelets,
                        ast,
                        alt,
                        ggt,
                        bilirubin,
                        albumin,
                        inr,
                        pt,
                        afp,
                        hbsag,
                        anti_hcv,
                        ast_uln,
                        apri,
                        fib4,
                        ultrasound_prediction,
                        date_added,
                        batch_id
                    )
                VALUES (
                    %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                    %s, %s, %s, %s, %s, %s, %s, %s, %s
                )
                RETURNING id
                """,
                (
                    user_id,
                    age,
                    report_data.get("platelets"),
                    report_data.get("ast"),
                    report_data.get("alt"),
                    report_data.get("ggt"),
                    report_data.get("bilirubin"),
                    report_data.get("albumin"),
                    report_data.get("inr"),
                    report_data.get("pt"),
                    report_data.get("afp"),
                    report_data.get("hbsag"),
                    report_data.get("anti_hcv"),
                    report_data.get("ast_uln"),
                    report_data.get("apri"),
                    report_data.get("fib4"),
                    report_data.get("ultrasound_prediction"),
                    date_added,
                    batch_id,
                ),
            )
            report_id = cur.fetchone()[0]

            for item in file_results:
                cur.execute(
                    """
                    INSERT INTO report_batch_files
                        (
                            batch_id,
                            file_index,
                            report_type,
                            processing_status,
                            extracted_data,
                            error_message
                        )
                    VALUES (%s, %s, %s, 'processed', %s, NULL)
                    """,
                    (
                        batch_id,
                        item["file_index"],
                        item["report_type"],
                        Json(item.get("extracted_data", {})),
                    ),
                )
                cur.execute(
                    """
                    INSERT INTO upload_history
                        (user_id, report_type, date_uploaded, batch_id)
                    VALUES (%s, %s, %s, %s)
                    """,
                    (
                        user_id,
                        item["report_type"],
                        date_added,
                        batch_id,
                    ),
                )

            for document in document_results:
                cur.execute(
                    """
                    INSERT INTO report_documents
                        (
                            id,
                            user_id,
                            report_id,
                            batch_id,
                            file_index,
                            report_type,
                            original_filename,
                            storage_key,
                            mime_type,
                            size_bytes,
                            sha256
                        )
                    VALUES (
                        %s, %s, %s, %s, %s, %s,
                        %s, %s, %s, %s, %s
                    )
                    """,
                    (
                        document["document_id"],
                        user_id,
                        report_id,
                        batch_id,
                        document["file_index"],
                        document["report_type"],
                        document["original_filename"],
                        document["storage_key"],
                        document["mime_type"],
                        document["size_bytes"],
                        document["sha256"],
                    ),
                )

            response_payload["report"]["report_id"] = report_id
            cur.execute(
                """
                UPDATE report_batches
                SET
                    status = 'completed',
                    report_id = %s,
                    response_json = %s,
                    error_message = NULL,
                    completed_at = %s
                WHERE id = %s AND user_id = %s
                """,
                (
                    report_id,
                    Json(response_payload),
                    now,
                    batch_id,
                    user_id,
                ),
            )
        conn.commit()

    return response_payload


def get_dashboard_records(user_id):
    """Return the profile, report history, and latest upload per report type."""
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT
                    name,
                    age,
                    gender,
                    weight,
                    height,
                    bmi,
                    diabetes_status,
                    hypertension,
                    previous_liver_disease,
                    family_history,
                    activity_level,
                    exercise_frequency,
                    alcohol_consumption,
                    smoking_status
                FROM users
                WHERE id = %s
                """,
                (user_id,)
            )
            user_row = cur.fetchone()

            cur.execute(
                """
                SELECT
                    ast,
                    alt,
                    ggt,
                    bilirubin,
                    albumin,
                    platelets,
                    inr,
                    pt,
                    afp,
                    hbsag,
                    anti_hcv,
                    apri,
                    fib4,
                    ultrasound_prediction,
                    date_added
                FROM reports
                WHERE user_id = %s
                ORDER BY date_added ASC, id ASC
                """,
                (user_id,)
            )
            report_rows = cur.fetchall()

            cur.execute(
                """
                SELECT LOWER(report_type), MAX(date_uploaded)
                FROM upload_history
                WHERE user_id = %s
                GROUP BY LOWER(report_type)
                """,
                (user_id,)
            )
            upload_rows = cur.fetchall()

        return {
            "user": user_row,
            "reports": report_rows,
            "uploads": {
                report_type: date_uploaded
                for report_type, date_uploaded in upload_rows
            }
        }
    finally:
        conn.close()


def get_profile_summary_records(user_id):
    """Return the authenticated profile, latest report, and upload count."""
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT
                    name,
                    age,
                    gender,
                    weight,
                    height,
                    bmi,
                    diabetes_status,
                    hypertension,
                    previous_liver_disease,
                    family_history,
                    activity_level,
                    exercise_frequency,
                    alcohol_consumption,
                    smoking_status
                FROM users
                WHERE id = %s
                """,
                (user_id,),
            )
            user_row = cur.fetchone()

            cur.execute(
                """
                SELECT
                    ast,
                    alt,
                    ggt,
                    bilirubin,
                    albumin,
                    platelets,
                    inr,
                    pt,
                    afp,
                    hbsag,
                    anti_hcv,
                    apri,
                    fib4,
                    ultrasound_prediction,
                    date_added
                FROM reports
                WHERE user_id = %s
                ORDER BY date_added DESC, id DESC
                LIMIT 1
                """,
                (user_id,),
            )
            latest_report = cur.fetchone()

            cur.execute(
                """
                SELECT COUNT(*), MAX(date_uploaded)
                FROM upload_history
                WHERE user_id = %s
                """,
                (user_id,),
            )
            upload_count, latest_upload_date = cur.fetchone()

        return {
            "user": user_row,
            "latest_report": latest_report,
            "total_uploaded_reports": upload_count,
            "latest_upload_date": latest_upload_date,
        }
    finally:
        conn.close()


def get_timeline_records(user_id):
    """Return a profile and complete dated report history for timeline charts."""
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT
                    name,
                    age,
                    gender,
                    weight,
                    height,
                    bmi,
                    diabetes_status,
                    hypertension,
                    previous_liver_disease,
                    family_history,
                    activity_level,
                    exercise_frequency,
                    alcohol_consumption,
                    smoking_status
                FROM users
                WHERE id = %s
                """,
                (user_id,),
            )
            user_row = cur.fetchone()

            cur.execute(
                """
                SELECT
                    id,
                    ast,
                    alt,
                    ggt,
                    bilirubin,
                    albumin,
                    platelets,
                    inr,
                    pt,
                    afp,
                    hbsag,
                    anti_hcv,
                    apri,
                    fib4,
                    ultrasound_prediction,
                    date_added
                FROM reports
                WHERE user_id = %s
                ORDER BY date_added ASC, id ASC
                """,
                (user_id,),
            )
            columns = (
                "id",
                "ast",
                "alt",
                "ggt",
                "bilirubin",
                "albumin",
                "platelets",
                "inr",
                "pt",
                "afp",
                "hbsag",
                "anti_hcv",
                "apri",
                "fib4",
                "ultrasound_prediction",
                "date_added",
            )
            reports = [
                dict(zip(columns, row))
                for row in cur.fetchall()
            ]

        return {
            "user": user_row,
            "reports": reports,
        }
    finally:
        conn.close()


def get_report_analysis_records(user_id, report_id=None):
    """Return a user and one current/previous report pair for analysis."""
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT
                    name,
                    age,
                    gender,
                    weight,
                    height,
                    bmi,
                    diabetes_status,
                    hypertension,
                    previous_liver_disease,
                    family_history,
                    activity_level,
                    exercise_frequency,
                    alcohol_consumption,
                    smoking_status
                FROM users
                WHERE id = %s
                """,
                (user_id,)
            )
            user_row = cur.fetchone()

            if user_row is None:
                return {
                    "user": None,
                    "current": None,
                    "previous": None,
                }

            report_columns = """
                id,
                ast,
                alt,
                ggt,
                bilirubin,
                albumin,
                platelets,
                inr,
                pt,
                afp,
                hbsag,
                anti_hcv,
                apri,
                fib4,
                ultrasound_prediction,
                date_added
            """

            if report_id is None:
                cur.execute(
                    f"""
                    SELECT {report_columns}
                    FROM reports
                    WHERE user_id = %s
                    ORDER BY date_added DESC, id DESC
                    LIMIT 2
                    """,
                    (user_id,)
                )
                rows = cur.fetchall()
                current_report = rows[0] if rows else None
                previous_report = rows[1] if len(rows) > 1 else None
            else:
                cur.execute(
                    f"""
                    SELECT {report_columns}
                    FROM reports
                    WHERE id = %s AND user_id = %s
                    """,
                    (report_id, user_id)
                )
                current_report = cur.fetchone()
                previous_report = None

                if current_report is not None:
                    cur.execute(
                        f"""
                        SELECT {report_columns}
                        FROM reports
                        WHERE user_id = %s AND id < %s
                        ORDER BY date_added DESC, id DESC
                        LIMIT 1
                        """,
                        (user_id, current_report[0])
                    )
                    previous_report = cur.fetchone()

        return {
            "user": user_row,
            "current": current_report,
            "previous": previous_report,
        }
    finally:
        conn.close()


def get_user_profile_record(user_id):
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT
                    name,
                    age,
                    gender,
                    weight,
                    height,
                    bmi,
                    diabetes_status,
                    hypertension,
                    previous_liver_disease,
                    family_history,
                    activity_level,
                    exercise_frequency,
                    alcohol_consumption,
                    smoking_status
                FROM users
                WHERE id = %s
                """,
                (user_id,)
            )
            return cur.fetchone()
    finally:
        conn.close()


def update_user_personal_info(user_id, updates):
    """Update an allowlisted subset of personal profile fields."""
    column_names = {
        "full_name": "name",
        "age": "age",
        "gender": "gender",
    }
    assignments = [
        f"{column_names[field]} = %s"
        for field in updates
    ]
    values = [updates[field] for field in updates]
    assignments.append("updated_at = %s")
    values.extend((datetime.now(timezone.utc), user_id))

    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                f"""
                UPDATE users
                SET {", ".join(assignments)}
                WHERE id = %s
                RETURNING name, age, gender
                """,
                values,
            )
            row = cur.fetchone()
        conn.commit()

    if row is None:
        return None
    return {
        "full_name": row[0],
        "age": row[1],
        "gender": row[2],
    }


def get_cached_report_analysis(report_id, analysis_version):
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT analysis_json
                FROM report_analyses
                WHERE report_id = %s AND analysis_version = %s
                """,
                (report_id, analysis_version)
            )
            row = cur.fetchone()
        return row[0] if row else None
    finally:
        conn.close()


def save_report_analysis(report_id, analysis_version, analysis):
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO report_analyses
                    (report_id, analysis_version, analysis_json, date_created)
                VALUES (%s, %s, %s, %s)
                ON CONFLICT (report_id)
                DO UPDATE SET
                    analysis_version = EXCLUDED.analysis_version,
                    analysis_json = EXCLUDED.analysis_json,
                    date_created = EXCLUDED.date_created
                """,
                (
                    report_id,
                    analysis_version,
                    Json(analysis),
                    datetime.now(),
                )
            )
        conn.commit()
    finally:
        conn.close()


def _safe_float(value):
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (ValueError, TypeError):
        return None


def _safe_int(value):
    if value is None or value == "":
        return None
    try:
        return int(value)
    except (ValueError, TypeError):
        return None


def _safe_str(value):
    if value is None or value == "":
        return None
    return str(value).strip()


def normalize(value):
    if value is None:
        return None
    return str(value).strip().lower()


def _safe_bool(value):
    return 1 if str(value).lower() in ["true", "1", "yes"] else 0


def validate_choice(value, allowed):
    return value if value in allowed else None


def add_report(user_id, age=None, platelets=None, ast=None, alt=None, ggt=None,
               bilirubin=None, albumin=None, inr=None, pt=None,
               afp=None, hbsag=None, anti_hcv=None, ast_uln=40,
               apri=None, fib4=None, ultrasound_prediction=None):
    date_added = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    age = _safe_int(age)
    platelets = _safe_float(platelets)
    ast = _safe_float(ast)
    alt = _safe_float(alt)
    ggt = _safe_float(ggt)
    bilirubin = _safe_float(bilirubin)
    albumin = _safe_float(albumin)
    inr = _safe_float(inr)
    pt = _safe_float(pt)
    afp = _safe_float(afp)
    hbsag = _safe_int(hbsag)
    anti_hcv = _safe_int(anti_hcv)
    ast_uln = _safe_float(ast_uln)
    apri = _safe_float(apri)
    fib4 = _safe_float(fib4)
    ultrasound_prediction = _safe_str(ultrasound_prediction)

    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """INSERT INTO reports
                   (user_id, age, platelets, ast, alt, ggt, bilirubin, albumin,
                    inr, pt, afp, hbsag, anti_hcv, ast_uln, apri, fib4,
                    ultrasound_prediction, date_added)
                   VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                   RETURNING id""",
                (user_id, age, platelets, ast, alt, ggt, bilirubin, albumin,
                 inr, pt, afp, hbsag, anti_hcv, ast_uln, apri, fib4,
                 ultrasound_prediction, date_added)
            )
            new_id = cur.fetchone()[0]
        conn.commit()
        return new_id
    except psycopg2.Error as e:
        print(f"DB error in add_report: {e}")
        conn.rollback()
        return None
    finally:
        conn.close()


def signup(email, password_hash, name, terms_accepted_at):
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO users
                    (
                        email,
                        password_hash,
                        name,
                        terms_accepted_at,
                        created_at,
                        updated_at
                    )
                VALUES (%s, %s, %s, %s, %s, %s)
                RETURNING id
                """,
                (
                    email,
                    password_hash,
                    name,
                    terms_accepted_at,
                    datetime.now(timezone.utc),
                    datetime.now(timezone.utc),
                )
            )
            new_id = cur.fetchone()[0]
        conn.commit()
        return new_id
    except psycopg2.IntegrityError:
        conn.rollback()
        return None
    finally:
        conn.close()


def update_user_profile(user_id, age, gender, weight, height, diabetes_status,
                         hypertension, previous_liver_disease, family_history,
                         activity_level, exercise_frequency, alcohol_consumption,
                         smoking_status):
    bmi = calculate_bmi(weight, height)

    diabetes_status = _safe_bool(diabetes_status)
    hypertension = _safe_bool(hypertension)
    previous_liver_disease = _safe_bool(previous_liver_disease)
    family_history = _safe_bool(family_history)

    activity_level = normalize(activity_level)
    exercise_frequency = normalize(exercise_frequency)
    alcohol_consumption = normalize(alcohol_consumption)
    smoking_status = normalize(smoking_status)

    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """UPDATE users
                   SET age=%s, gender=%s, weight=%s, height=%s, bmi=%s,
                       diabetes_status=%s, hypertension=%s, previous_liver_disease=%s,
                       family_history=%s, activity_level=%s, exercise_frequency=%s,
                       alcohol_consumption=%s, smoking_status=%s, updated_at=%s
                   WHERE id=%s""",
                (age, gender, weight, height, bmi, diabetes_status, hypertension,
                 previous_liver_disease, family_history, activity_level,
                 exercise_frequency, alcohol_consumption, smoking_status,
                 datetime.now(timezone.utc), user_id)
            )
            updated = cur.rowcount == 1
        conn.commit()
        return updated
    except psycopg2.Error as e:
        print("Profile update error:", e)
        conn.rollback()
        return False
    finally:
        conn.close()


init_db()
init_auth_tables()
init_reports_table()
init_upload_history_table()
init_report_batch_tables()
init_report_documents_table()
init_report_analyses_table()
init_assistant_tables()
init_support_tickets_table()
init_user_achievements_table()
