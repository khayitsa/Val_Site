"""
One-time setup: loads your 10 products - each with its shades tracked as
individual stock counts - into a fresh database.

Run once with:  python scripts/seed_products.py
Safe to re-run - it skips any product name that already exists.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import app
from models import db, Product, ProductVariant

STARTING_STOCK = 10  # placeholder - adjust real counts in the admin panel

# (image, category, name, price, description, [shades...])
PRODUCTS = [
    ("product_peace_in_mind_body_chain.jpg", "Body Chain", "Peace in Mind Body Chain", "40.00",
     "Deep and bold, the oceanic shade evokes the strength of the sea. Handcrafted in 18k gold coated chain, this body chain is a statement of elegance and resilience.",
     ["Oceanic"]),
    ("product_trinity_hand_chain_v3.jpg", "Hand Chain", "Trinity Hand Chain", "25.00",
     "Handcrafted in radiant 18k gold coated chains, the Trinity Hand Chain drapes delicately across the hand — each shade reflecting a different facet of elegance, from tender romance to oceanic strength.",
     ["Blushed", "Seafoam", "Oceanic"]),
    ("product_serenity_waist_chain.jpg", "Waist Chain", "Serenity Waist Chain", "35.00",
     "An adornment of calm and grace, the Serenity Waist Chain is shaped with artisanal care in 18k gold coated chain, embodying balance and serenity across every tone.",
     ["Blushed", "Seafoam", "Oceanic"]),
    ("product_trinity_body_chain_v2.jpg", "Body Chain", "Trinity Body Chain", "45.00",
     "Fluid and empowering, the Trinity Body Chain flows seamlessly with the body's movement. Handcrafted in 18k gold coated chain, each shade carries its own symbolism of romance, vitality, or resilience.",
     ["Blushed", "Seafoam", "Oceanic"]),
    ("product_wishes_body_chain_v2.jpg", "Body Chain", "Wishes Body Chain", "55.00",
     "A symbolic piece where each handcrafted link represents a wish. Made in 18k gold coated chain, the Wishes Body Chain is a luminous emblem of harmony and aspiration.",
     ["Seafoam"]),
    ("product_twin_souls_anklet.jpg", "Anklet", "Twin Souls Anklet", "25.00",
     "A delicate anklet symbolizing connection and balance. Handcrafted in 18k gold coated chain, each one is a crafted expression of individuality.",
     ["Blushed", "Seafoam", "Oceanic"]),
    ("product_two_paths_waist_chain_v2.jpg", "Waist Chain", "Two Paths Waist Chain", "50.00",
     "Representing choice and harmony, the Two Paths Waist Chain is sculpted in 18k gold coated chains with artisanal precision, embodying the convergence of strength and serenity.",
     ["Blushed", "Seafoam", "Oceanic"]),
    ("product_high_tide_body_chain_v2.jpg", "Body Chain", "High Tide Body Chain", "65.00",
     "Ocean-inspired elegance in 18k gold coated chains and pearls — the High Tide Body Chain features pearls draping along the back, a luminous statement of fluidity and resilience.",
     ["Seafoam"]),
    ("product_starfish_hand_chain_v2.jpg", "Hand Chain", "Starfish Hand Chain", "25.00",
     "Inspired by the starfish's resilience, this hand chain is delicately handcrafted in 18k gold coated chain, symbolizing renewal and strength.",
     ["Blushed", "Seafoam", "Oceanic"]),
    ("product_dream_catcher_earrings.jpg", "Earring", "Dream Catcher Earring Set", "30.00",
     "A luminous ode to protection and harmony, handcrafted in 18k gold coating — it filters away negativity while embracing serenity and elegance.",
     ["Seafoam", "Blushed"]),
]

with app.app_context():
    db.create_all()
    added = 0
    for i, (img, cat, name, price, desc, shades) in enumerate(PRODUCTS):
        if Product.query.filter_by(name=name).first():
            continue
        product = Product(
            image_filename=img, category=cat, name=name, price=price,
            description=desc, sort_order=i, is_active=True,
        )
        for shade in shades:
            product.variants.append(ProductVariant(shade=shade, stock_quantity=STARTING_STOCK))
        db.session.add(product)
        added += 1
    db.session.commit()
    print(f"Seeded {added} new product(s). Total products in DB: {Product.query.count()}")
    if added:
        print(f"Each shade starts with {STARTING_STOCK} in stock as a placeholder - "
              f"adjust to your real counts in the admin panel under Products.")