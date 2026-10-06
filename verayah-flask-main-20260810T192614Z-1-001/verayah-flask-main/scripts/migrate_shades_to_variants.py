"""
One-time migration for anyone running the database from BEFORE stock
tracking was added. Fixes two things left over from the old schema:

1. Converts the old free-text `shades` column (e.g. "Blushed, Seafoam,
   Oceanic") into real ProductVariant rows with a stock count you can then
   adjust.
2. Removes the old `products.shades` column entirely. Leaving it in place
   (even unused) causes "NOT NULL constraint failed: products.shades" the
   next time you add a new product, because the current code no longer
   fills that field in - the column itself has to go, not just stop being
   used.

Also adds the order_items.variant_id column needed to link past orders to
the new shade rows, if that's missing too.

Safe to run on:
- a fresh database with no products yet (does nothing)
- a database seeded with scripts/seed_products.py (does nothing - those
  already come with variants, no legacy column)
- an older database that still has the legacy `shades` column (this is the
  case this script exists for)
- a database this script has already been run on once (does nothing the
  second time)

Run with:  python scripts/migrate_shades_to_variants.py
"""
import os
import re
import sqlite3
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import app
from models import db, Product, ProductVariant

DEFAULT_STARTING_STOCK = 10


def parse_shade_names(raw_text):
    """'Blushed, Seafoam, Oceanic & other shades' -> ['Blushed', 'Seafoam', 'Oceanic']"""
    if not raw_text:
        return []
    text = raw_text.replace("only", "").replace("& other shades", "")
    names = [s.strip() for s in re.split(r",| and ", text) if s.strip()]
    return names


with app.app_context():
    # Step 1: create any brand-new tables (product_variants) that the ORM
    # models now define but this database doesn't have yet.
    db.create_all()

    db_path = app.config["SQLALCHEMY_DATABASE_URI"].replace("sqlite:///", "")
    if not os.path.exists(db_path):
        print("No database file found yet - nothing to migrate.")
        raise SystemExit(0)

    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA foreign_keys=OFF")
    cur = conn.cursor()

    # Step 2: add order_items.variant_id if this database predates it.
    cur.execute("PRAGMA table_info(order_items)")
    order_item_columns = [row[1] for row in cur.fetchall()]
    if order_item_columns and "variant_id" not in order_item_columns:
        cur.execute("ALTER TABLE order_items ADD COLUMN variant_id INTEGER REFERENCES product_variants(id)")
        conn.commit()
        print("Added the missing variant_id column to order_items.")

    # Step 3: if products.shades still exists, rebuild the table without it
    # (SQLite can't drop a column directly - this renames the old table,
    # lets SQLAlchemy create a fresh one from the current model, copies the
    # real data across preserving every id, then drops the old table).
    cur.execute("PRAGMA table_info(products)")
    columns = [row[1] for row in cur.fetchall()]
    has_legacy_column = "shades" in columns
    legacy_shades_by_id = {}

    if has_legacy_column:
        cur.execute("""
            SELECT id, name, category, price, description, shades, image_filename,
                   is_active, sort_order, created_at, updated_at
            FROM products
        """)
        old_rows = cur.fetchall()
        legacy_shades_by_id = {row[0]: row[5] for row in old_rows}

        cur.execute("ALTER TABLE products RENAME TO products_legacy_migration")
        conn.commit()
        conn.close()

        db.create_all()  # recreates 'products' fresh, matching the current model (no shades column)

        conn = sqlite3.connect(db_path)
        cur = conn.cursor()
        for row in old_rows:
            pid, name, category, price, description, _shades, image_filename, is_active, sort_order, created_at, updated_at = row
            cur.execute("""
                INSERT INTO products (id, name, category, price, description, image_filename,
                                       is_active, sort_order, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (pid, name, category, price, description, image_filename, is_active, sort_order, created_at, updated_at))
        cur.execute("DROP TABLE products_legacy_migration")
        conn.commit()
        print(f"Rebuilt the products table without the old 'shades' column ({len(old_rows)} product(s) preserved).")

    conn.close()

    if not has_legacy_column:
        print("No legacy 'shades' column found - nothing to migrate.")
    else:
        migrated = 0
        for product in Product.query.all():
            if product.variants:
                continue  # already has variants, leave it alone
            raw = legacy_shades_by_id.get(product.id, "")
            names = parse_shade_names(raw)
            for shade in names:
                db.session.add(ProductVariant(
                    product_id=product.id, shade=shade, stock_quantity=DEFAULT_STARTING_STOCK
                ))
            if names:
                migrated += 1
        db.session.commit()
        print(f"Migrated {migrated} product(s) to the new shade/stock system.")
        if migrated:
            print(f"Each shade was given a starting stock of {DEFAULT_STARTING_STOCK} - "
                  f"go to Products in the admin panel and adjust these to your real counts.")
