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
    if sub is None:
        sub = Subscriber(email=email)
        db.session.add(sub)
    elif sub.unsubscribed_at is not None:
        return sub  # they opted out - leave that decision alone
    if name and not sub.name:
        sub.name = name.strip()
    already_consented = sub.consented_at is not None
    sub.newsletter = bool(newsletter) or bool(sub.newsletter)
    sub.sneak_peek = bool(sneak_peek) or bool(sub.sneak_peek)
    if not already_consented:
        sub.consent_source = source
        sub.consented_at = datetime.utcnow()
    return sub
