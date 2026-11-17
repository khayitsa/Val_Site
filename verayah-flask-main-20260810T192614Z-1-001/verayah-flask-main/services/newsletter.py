from datetime import datetime

from models import db, Subscriber


def record_consent(email, name=None, newsletter=False, sneak_peek=False, source=None):
    """Create or update a subscriber. Only called when the person actively
    chose at least one list; returns the Subscriber (or None if neither).

    Nobody can prove, from a web form alone, that the email address they typed
    is theirs. So an anonymous form can ADD a new address, but it can never
    undo someone's unsubscribe or rewrite the consent record of an existing
    subscriber. (A person who unsubscribed and wants back in contacts the shop.)"""
    if not (newsletter or sneak_peek):
        return None
    email = email.strip().lower()
    sub = Subscriber.query.filter_by(email=email).first()
    if sub is not None:
        # Already on file (subscribed, or opted out): an anonymous form changes nothing,
        # not even to add a second list - anyone could type someone else's address.
        return sub
    sub = Subscriber(email=email, name=(name or "").strip() or None,
                     newsletter=bool(newsletter), sneak_peek=bool(sneak_peek),
                     consent_source=source, consented_at=datetime.utcnow())
    db.session.add(sub)
    return sub
