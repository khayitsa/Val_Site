"""
Tiny, safe schema upgrader for the existing SQLite database.

db.create_all() creates brand-new tables (customers, subscribers, ...) but
never adds columns to a table that already exists. The orders table gained
columns for website checkout, so this adds any that are missing. It only ever
ADDs columns - it never drops or rewrites data - and is a no-op once up to date.
"""
import secrets

from sqlalchemy import inspect, text

# column name -> SQL definition
ORDER_COLUMNS = {
    "customer_id": "INTEGER",
    "public_token": "VARCHAR(64)",
    "source": "VARCHAR(20) NOT NULL DEFAULT 'admin'",
    "delivery_method": "VARCHAR(20) NOT NULL DEFAULT 'courier'",
    "delivery_fee": "NUMERIC(10, 2) NOT NULL DEFAULT 0",
    "payment_method": "VARCHAR(20)",
    "payment_status": "VARCHAR(20) NOT NULL DEFAULT 'unpaid'",
}


def upgrade_schema(db):
    inspector = inspect(db.engine)
    if "orders" not in inspector.get_table_names():
        return  # fresh database: create_all() already built the final shape
    existing = {c["name"] for c in inspector.get_columns("orders")}
    with db.engine.begin() as conn:
        for name, ddl in ORDER_COLUMNS.items():
            if name not in existing:
                conn.execute(text(f"ALTER TABLE orders ADD COLUMN {name} {ddl}"))
        # Give old orders a confirmation token too.
        rows = conn.execute(text("SELECT id FROM orders WHERE public_token IS NULL")).fetchall()
        for (order_id,) in rows:
            conn.execute(text("UPDATE orders SET public_token = :t WHERE id = :i"),
                         {"t": secrets.token_urlsafe(24), "i": order_id})
        conn.execute(text("CREATE UNIQUE INDEX IF NOT EXISTS ix_orders_public_token ON orders (public_token)"))
