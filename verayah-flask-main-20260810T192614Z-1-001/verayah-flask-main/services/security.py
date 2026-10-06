"""Small in-memory failure throttle (same approach as the admin login).

Fine for a single worker process. If the site is ever run with several
workers, swap for Flask-Limiter + Redis.
"""
import time


class Throttle:
    def __init__(self, max_attempts=5, window_seconds=15 * 60):
        self.max_attempts = max_attempts
        self.window = window_seconds
        self._hits = {}

    def _recent(self, key):
        now = time.time()
        hits = [t for t in self._hits.get(key, []) if now - t < self.window]
        self._hits[key] = hits
        return hits

    def blocked(self, key):
        return len(self._recent(key)) >= self.max_attempts

    def record(self, key):
        self._recent(key)
        self._hits[key].append(time.time())

    def clear(self, key):
        self._hits.pop(key, None)


# one throttle per kind of action
customer_login_throttle = Throttle(max_attempts=5, window_seconds=15 * 60)
signup_throttle = Throttle(max_attempts=10, window_seconds=60 * 60)   # subscribe/contact/register spam brake
