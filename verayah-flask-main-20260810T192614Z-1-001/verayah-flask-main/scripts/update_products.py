"""
Brings the products already in your database in line with the photos and
wording agreed with Val. Safe to re-run: it only changes name-matched products
and never touches prices, stock, shades or orders.

Run with:  python scripts/update_products.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import app
from models import db, Product

# product name -> (new image filename or None to keep, new description or None to keep)
UPDATES = {
    'Peace in Mind Body Chain': ('product_peace_in_mind_body_chain_val.jpg', 'Deep and bold, the oceanic shade evokes the strength of the sea. Handcrafted in 18k gold coated chain, this body chain is a statement of elegance and resilience.'),
    'Trinity Hand Chain': ('product_trinity_hand_chain_val.jpg', None),
    'Serenity Waist Chain': ('product_serenity_waist_chain_val.jpg', 'An adornment of calm and grace, the Serenity Waist Chain is shaped with artisanal care in 18k gold coated chain, embodying balance and serenity across every tone.'),
    'Trinity Body Chain': ('product_trinity_body_chain_val.jpg', "Fluid and empowering, the Trinity Body Chain flows seamlessly with the body's movement. Handcrafted in 18k gold coated chain, each shade carries its own symbolism of romance, vitality, or resilience."),
    'Wishes Body Chain': ('product_wishes_body_chain_val.jpg', 'A symbolic piece where each handcrafted link represents a wish. Made in 18k gold coated chain, the Wishes Body Chain is a luminous emblem of harmony and aspiration.'),
    'Twin Souls Anklet': ('product_twin_souls_anklet_val.jpg', 'A delicate anklet symbolizing connection and balance. Handcrafted in 18k gold coated chain, each one is a crafted expression of individuality.'),
    'Two Paths Waist Chain': ('product_two_paths_waist_chain_val.jpg', None),
    'High Tide Body Chain': ('product_high_tide_body_chain_val.jpg', None),
    'Starfish Hand Chain': ('product_starfish_hand_chain_val.jpg', "Inspired by the starfish's resilience, this hand chain is delicately handcrafted in 18k gold coated chain, symbolizing renewal and strength."),
    'Dream Catcher Earring Set': ('product_dream_catcher_earrings_val.jpg', None),
}

with app.app_context():
    changed = 0
    for name, (image, description) in UPDATES.items():
        p = Product.query.filter_by(name=name).first()
        if not p:
            print(f"  not found, skipped: {name}")
            continue
        if image and p.image_filename != image:
            p.image_filename = image
            changed += 1
        if description and p.description != description:
            p.description = description
            changed += 1
    db.session.commit()
    print(f"Done. {changed} field(s) updated.")
