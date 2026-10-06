from datetime import datetime

from models import db, Subscriber


def record_consent(email, name=None, newsletter=False, sneak_peek=False, source=None):
    """Create or update a subscriber. Only called when the person actively
    chose at least one list; returns the Subscriber (or None if neither)."""
    if not (newsletter or sneak_peek):
        return None
    email = email.strip().lower()
    sub = Subscriber.query.filter_by(email=email).first()
    if sub is None:
        sub = Subscriber(email=email)
        db.session.add(sub)
    if name and not sub.name:
        sub.name = name.strip()
    sub.newsletter = bool(newsletter) or (sub.newsletter and sub.unsubscribed_at is None)
    sub.sneak_peek = bool(sneak_peek) or (sub.sneak_peek and sub.unsubscribed_at is None)
    sub.unsubscribed_at = None
    sub.consent_source = source
    sub.consented_at = datetime.utcnow()
    return sub
