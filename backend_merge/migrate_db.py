"""
migrate_db.py - Purani PostgreSQL DB ko naye login schema ke sath upgrade karta hai
BINA Shopify/WooCommerce data delete kiye.

Use:
    python migrate_db.py

DATABASE_URL .env se aata hai. Override karne ke liye:
    DATABASE_URL=postgresql://postgres:PASS@localhost:5432/digital_fte python migrate_db.py
"""
from sqlalchemy import create_engine, inspect, text

from app.config import settings


def main():
    engine = create_engine(settings.DATABASE_URL)
    insp = inspect(engine)
    tables = set(insp.get_table_names())
    print("DB me maujood tables:", sorted(tables))

    with engine.begin() as conn:
        # ── 1. users table ──
        if "users" in tables:
            cols = {c["name"] for c in insp.get_columns("users")}
            print("users table pehle se hai. Columns:", sorted(cols))

            if "username" not in cols:
                conn.execute(text("ALTER TABLE users ADD COLUMN username VARCHAR(50)"))
                # purani rows ke liye dummy username (delete nahi karte)
                conn.execute(text("UPDATE users SET username = 'user_' || id WHERE username IS NULL"))
                conn.execute(text("ALTER TABLE users ALTER COLUMN username SET NOT NULL"))
                conn.execute(text("CREATE UNIQUE INDEX IF NOT EXISTS ix_users_username ON users (username)"))
                print("  + username column add ho gaya")

            for col, ddl in (
                ("full_name", "ALTER TABLE users ADD COLUMN full_name VARCHAR(150)"),
                ("auth_provider", "ALTER TABLE users ADD COLUMN auth_provider VARCHAR(20) DEFAULT 'local' NOT NULL"),
                ("google_id", "ALTER TABLE users ADD COLUMN google_id VARCHAR(255)"),
                ("is_active", "ALTER TABLE users ADD COLUMN is_active BOOLEAN DEFAULT TRUE NOT NULL"),
                ("is_verified", "ALTER TABLE users ADD COLUMN is_verified BOOLEAN DEFAULT FALSE NOT NULL"),
                ("updated_at", "ALTER TABLE users ADD COLUMN updated_at TIMESTAMP WITH TIME ZONE DEFAULT now()"),
            ):
                if col not in cols:
                    conn.execute(text(ddl))
                    print(f"  + {col} column add ho gaya")
        else:
            print("users table nahi hai - app start par khud ban jayegi")

        # ── 2. login_logs table ──
        if "login_logs" not in tables:
            conn.execute(text(
                """
                CREATE TABLE login_logs (
                    id SERIAL PRIMARY KEY,
                    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                    login_method VARCHAR(20) NOT NULL,
                    ip_address VARCHAR(45),
                    user_agent VARCHAR(500),
                    logged_in_at TIMESTAMP WITH TIME ZONE DEFAULT now()
                )
                """
            ))
            conn.execute(text("CREATE INDEX IF NOT EXISTS ix_login_logs_user_id ON login_logs (user_id)"))
            print("login_logs table ban gayi")
        else:
            print("login_logs table pehle se hai - koi change nahi")

        # ── 3. Shopify/WooCommerce stores me FK (agar possible ho) ──
        # user_id column pehle se hai; FK constraint optional hai.
        # Pehle purane TEMP_USER_ID (1) rows ka data delete nahi hota, sirf FK lagti hai
        # agar koi invalid user_id nahi ho.
        for tbl in ("shopify_stores", "woocommerce_stores"):
            if tbl in tables:
                cols = {c["name"] for c in insp.get_columns(tbl)}
                if "user_id" in cols:
                    # invalid user_id rows hatao taake FK fail na ho (sirf orphan rows)
                    conn.execute(text(
                        f"DELETE FROM {tbl} WHERE user_id IS NOT NULL "
                        f"AND user_id NOT IN (SELECT id FROM users)"
                    ))
                    conn.execute(text(
                        f"ALTER TABLE {tbl} "
                        f"ADD CONSTRAINT fk_{tbl}_user FOREIGN KEY (user_id) REFERENCES users(id) "
                        f"ON DELETE CASCADE"
                    ))
                    print(f"  + {tbl} par user_id FK lag gaya")

        # ── 4. generated_posts table ──
        if "generated_posts" not in tables:
            conn.execute(text(
                """
                CREATE TABLE generated_posts (
                    id UUID PRIMARY KEY,
                    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                    prompt TEXT NOT NULL,
                    caption TEXT,
                    image_path VARCHAR(500),
                    image_model VARCHAR(100),
                    status VARCHAR(20) DEFAULT 'draft' NOT NULL,
                    instagram_media_id VARCHAR(100),
                    published_at TIMESTAMP WITH TIME ZONE,
                    created_at TIMESTAMP WITH TIME ZONE DEFAULT now()
                )
                """
            ))
            conn.execute(text("CREATE INDEX IF NOT EXISTS ix_generated_posts_user_id ON generated_posts (user_id)"))
            print("generated_posts table ban gayi")
        else:
            print("generated_posts table pehle se hai - koi change nahi")

        # ── 5. instagram_accounts table ──
        if "instagram_accounts" not in tables:
            conn.execute(text(
                """
                CREATE TABLE instagram_accounts (
                    id UUID PRIMARY KEY,
                    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                    ig_user_id VARCHAR(100) NOT NULL,
                    ig_username VARCHAR(150) NOT NULL,
                    account_type VARCHAR(50),
                    facebook_page_id VARCHAR(100),
                    access_token TEXT NOT NULL,
                    token_expires_at TIMESTAMP WITH TIME ZONE NOT NULL,
                    connected_at TIMESTAMP WITH TIME ZONE DEFAULT now()
                )
                """
            ))
            conn.execute(text("CREATE INDEX IF NOT EXISTS ix_instagram_accounts_user_id ON instagram_accounts (user_id)"))
            print("instagram_accounts table ban gayi")
        else:
            print("instagram_accounts table pehle se hai - koi change nahi")

    print("\nMigration complete! Ab app start karo - sabhi merged tables ready hain.")


if __name__ == "__main__":
    main()

