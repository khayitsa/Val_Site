"""List every English phrase in the site that has no Spanish entry yet.

Run from the project folder:   python scripts/check_translations.py

Prints nothing but "All good" when services/translations_es.py covers every phrase
used in the templates and Python code. Otherwise it lists the missing phrases and
where they are used, so they can be added to services/translations_es.py.
"""
import ast
import os
import sys

from jinja2 import Environment, nodes

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from services.translations_es import ES  # noqa: E402

# Phrases chosen at run time (from the database or a status), so they never appear
# as plain text in a template: categories, order statuses and similar.
DYNAMIC = [
    "Body Chain", "Hand Chain", "Waist Chain", "Anklet", "Earring", "Necklace", "Swimsuit Charm", "Bag Charm",
    "Pending", "Processing", "Shipped", "Delivered", "Cancelled", "Admin", "Website", "Courier", "Collection",
    "Not set", "Bank transfer", "Yappy", "Paid", "Unpaid",
    "General Inquiry", "Custom Jewellery", "Order Question", "Wholesale",
]

found = {}


def add(key, where):
    found.setdefault(key, set()).add(where)


env = Environment()
for dirpath, _dirs, files in os.walk(os.path.join(ROOT, "templates")):
    if os.sep + "legal" in dirpath:
        continue  # long legal pages are written out in full as *.es.html files
    for name in files:
        if not name.endswith(".html"):
            continue
        path = os.path.join(dirpath, name)
        with open(path, encoding="utf-8") as fh:
            tree = env.parse(fh.read())
        for call in tree.find_all(nodes.Call):
            if (isinstance(call.node, nodes.Name) and call.node.name in ("_", "_h", "t")
                    and call.args and isinstance(call.args[0], nodes.Const)
                    and isinstance(call.args[0].value, str)):
                add(call.args[0].value, os.path.relpath(path, ROOT))

for dirpath, _dirs, files in os.walk(ROOT):
    if any(part in dirpath for part in ("venv", ".git", "static", "instance", "__pycache__")):
        continue
    for name in files:
        if not name.endswith(".py") or name == "translations_es.py":
            continue
        path = os.path.join(dirpath, name)
        with open(path, encoding="utf-8") as fh:
            tree = ast.parse(fh.read())
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                fn = node.func.id if isinstance(node.func, ast.Name) else (
                    node.func.attr if isinstance(node.func, ast.Attribute) else None)
                if (fn in ("t", "L", "lazy", "translate") and node.args
                        and isinstance(node.args[0], ast.Constant) and isinstance(node.args[0].value, str)):
                    add(node.args[0].value, os.path.relpath(path, ROOT))

for key in DYNAMIC:
    add(key, "(chosen at run time)")

missing = sorted(k for k in found if k not in ES)
if not missing:
    print("All good: every phrase has a Spanish entry.")
else:
    print(f"{len(missing)} phrase(s) have no Spanish entry yet:\n")
    for key in missing:
        print(f"  {key!r}\n      used in: {', '.join(sorted(found[key]))}")
    sys.exit(1)
