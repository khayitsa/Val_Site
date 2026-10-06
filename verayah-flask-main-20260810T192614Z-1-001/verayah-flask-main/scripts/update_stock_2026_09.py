"""
Applies the real stock counts from the Sept 2026 inventory spreadsheet to
your EXISTING database, in place - it does not touch admin accounts,
orders, prices, or anything else. Safe to run once; running it again just
re-applies the same numbers.

Run from your project folder with:  python scripts/update_stock_2026_09.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import app
from models import db, Product, ProductVariant

# (product name, shade) -> stock count from the spreadsheet
STOCK_UPDATES = {
    ("Peace in Mind Body Chain", "Oceanic"): 1,
    ("Trinity Hand Chain", "Blushed"): 1,
    ("Trinity Hand Chain", "Oceanic"): 1,
    ("Trinity Body Chain", "Blushed"): 1,
    ("Twin Souls Anklet", "Blushed"): 1,
    ("Two Paths Waist Chain", "Seafoam"): 1,
    ("Wishes Body Chain", "Seafoam"): 2,  # two sheet rows for this one, summed
    ("High Tide Body Chain", "Seafoam"): 1,
    ("Starfish Hand Chain", "Seafoam"): 1,
    ("Serenity Waist Chain", "Blushed"): 1,
    ("Dream Catcher Earring Set", "Seafoam"): 2,
}

with app.app_context():
    touched = set()
    for (name, shade), qty in STOCK_UPDATES.items():
        variant = (ProductVariant.query.join(Product)
                   .filter(Product.name == name, ProductVariant.shade == shade).first())
        if variant:
            variant.stock_quantity = qty
            touched.add((name, shade))
        else:
            print(f"Skipped (not found in your database): {name} / {shade}")

    zeroed = []
    for p in Product.query.all():
        for v in p.variants:
            if (p.name, v.shade) not in touched:
                v.stock_quantity = 0
                zeroed.append(f"{p.name} / {v.shade}")

    db.session.commit()

    print("Updated:")
    for name, shade in sorted(touched):
        print(" -", name, "/", shade, "->", STOCK_UPDATES[(name, shade)])
    print()
    print("Set to 0 (not mentioned in the spreadsheet):")
    for item in zeroed:
        print(" -", item)
