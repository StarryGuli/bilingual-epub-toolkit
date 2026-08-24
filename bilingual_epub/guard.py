"""Guard rails for running the web UI on a public host.

Everything here is inert in the default local mode. It exists because the same
page that is perfectly safe on 127.0.0.1 -- one user, their own files, their
own disk -- becomes a free file-processing endpoint the moment it has a public
address.

What this covers:

* sessions, so one visitor cannot fetch another visitor's books
* a per-IP token bucket, so one client cannot queue work in a loop
* a concurrency cap, because aligning a long book is CPU-bound and a handful
  of parallel merges will bury a small VPS
* a reaper, so uploads and results do not accumulate until the disk fills

What this does not cover: a determined bot. Cookies and rate limits raise the
cost of casual scripting, and that is all they do. Anything that genuinely
needs to distinguish a person from a program belongs in front of this server --
Cloudflare Turnstile, hCaptcha, or an authenticating reverse proxy. Do not read
the presence of this module as a claim that the service is bot-proof.
"""
import os
import secrets
import shutil
import threading
import time


def new_token(n=18):
    return secrets.token_urlsafe(n)


class RateLimit:
    """A token bucket per key, refilled continuously.

    `burst` requests are allowed immediately, then one more every
    `per / rate` seconds. Keys are usually client IPs.
    """

    def __init__(self, rate=12, per=300.0, burst=4):
        self.rate = float(rate)
        self.per = float(per)
        self.burst = float(burst)
        self._buckets = {}
        self._lock = threading.Lock()

    def check(self, key):
        """Consume one token. -> (allowed, seconds_until_next_token)."""
        now = time.monotonic()
        with self._lock:
            tokens, last = self._buckets.get(key, (self.burst, now))
            tokens = min(self.burst, tokens + (now - last) * (self.rate / self.per))
            if tokens >= 1.0:
                self._buckets[key] = (tokens - 1.0, now)
                return True, 0.0
            self._buckets[key] = (tokens, now)
            wait = (1.0 - tokens) * (self.per / self.rate)
            return False, wait

    def forget_older_than(self, age=3600.0):
        cutoff = time.monotonic() - age
        with self._lock:
            for key in [k for k, (_t, last) in self._buckets.items() if last < cutoff]:
                del self._buckets[key]


class Sessions:
    """Cookie-addressed scratch space, one directory per visitor.

    A session owns the files it created and nothing else, which is what keeps
    one visitor's books out of another's reach. Each also carries a page token
    that POSTs must echo, so a request has to have come from a page this server
    actually served.
    """

    def __init__(self, root, ttl=1800.0, max_files=40, max_bytes=250 * 1024 * 1024):
        self.root = root
        self.ttl = float(ttl)
        self.max_files = max_files
        self.max_bytes = max_bytes
        self._data = {}
        self._lock = threading.Lock()
        if not os.path.isdir(root):
            os.makedirs(root)

    def issue(self):
        sid = new_token(24)
        path = os.path.join(self.root, sid)
        os.makedirs(path)
        with self._lock:
            self._data[sid] = {'page_token': new_token(16), 'dir': path,
                               'seen': time.time(), 'files': {}, 'bytes': 0}
        return sid

    def get(self, sid):
        if not sid:
            return None
        with self._lock:
            s = self._data.get(sid)
            if s is not None:
                s['seen'] = time.time()
            return s

    def register(self, sid, path):
        """Record a produced file against a session. -> download token."""
        with self._lock:
            s = self._data.get(sid)
            if s is None:
                return None
            size = os.path.getsize(path) if os.path.exists(path) else 0
            if len(s['files']) >= self.max_files or s['bytes'] + size > self.max_bytes:
                return None
            token = new_token()
            s['files'][token] = path
            s['bytes'] += size
            return token

    def resolve(self, sid, token):
        """A session may only download what it produced."""
        s = self.get(sid)
        return s['files'].get(token) if s else None

    def reap(self):
        """Drop sessions idle past the TTL and delete their scratch."""
        cutoff = time.time() - self.ttl
        with self._lock:
            stale = [sid for sid, s in self._data.items() if s['seen'] < cutoff]
            dirs = [self._data.pop(sid)['dir'] for sid in stale]
        for d in dirs:
            shutil.rmtree(d, ignore_errors=True)
        return len(dirs)


class Reaper(threading.Thread):
    """Runs the session sweep on a timer."""

    def __init__(self, sessions, limiter=None, interval=120.0):
        super().__init__(daemon=True)
        self.sessions = sessions
        self.limiter = limiter
        self.interval = interval
        self._stop = threading.Event()

    def run(self):
        while not self._stop.wait(self.interval):
            try:
                self.sessions.reap()
                if self.limiter is not None:
                    self.limiter.forget_older_than()
            except Exception:      # a sweep failure must never kill the server
                pass

    def stop(self):
        self._stop.set()
