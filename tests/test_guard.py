"""Guard rails for public deployment.

The Turnstile tests hit Cloudflare's documented always-pass / always-fail test
keys, so they exercise the real verification endpoint rather than a stub. They
skip rather than fail when there is no network, because a missing internet
connection is not a defect in this code.
"""
import urllib.error
import urllib.request

import pytest

from bilingual_epub import guard

ALWAYS_PASS = ('1x00000000000000000000AA', '1x0000000000000000000000000000000AA')
ALWAYS_FAIL = ('2x00000000000000000000AB', '2x0000000000000000000000000000000AA')


def _online():
    try:
        urllib.request.urlopen('https://challenges.cloudflare.com/', timeout=5)
        return True
    except (urllib.error.URLError, OSError):
        return False


# --------------------------------------------------------------------------- #
# rate limiting
# --------------------------------------------------------------------------- #

def test_bucket_allows_a_burst_then_refuses():
    rl = guard.RateLimit(rate=1, per=600.0, burst=3)
    assert [rl.check('ip')[0] for _ in range(3)] == [True, True, True]
    allowed, wait = rl.check('ip')
    assert allowed is False
    assert wait > 0


def test_buckets_are_per_key():
    rl = guard.RateLimit(rate=1, per=600.0, burst=1)
    assert rl.check('a')[0] is True
    assert rl.check('a')[0] is False
    assert rl.check('b')[0] is True, 'one client must not spend another\'s budget'


# --------------------------------------------------------------------------- #
# sessions
# --------------------------------------------------------------------------- #

def test_a_session_cannot_resolve_another_sessions_file(tmp_path):
    ss = guard.Sessions(str(tmp_path / 's'))
    a, b = ss.issue(), ss.issue()
    f = tmp_path / 'book.epub'
    f.write_bytes(b'x' * 10)
    token = ss.register(a, str(f))
    assert ss.resolve(a, token) == str(f)
    assert ss.resolve(b, token) is None, 'cross-session read'
    assert ss.resolve('', token) is None, 'anonymous read'


def test_session_file_count_is_capped(tmp_path):
    ss = guard.Sessions(str(tmp_path / 's'), max_files=2)
    sid = ss.issue()
    f = tmp_path / 'b.epub'
    f.write_bytes(b'x')
    assert ss.register(sid, str(f)) is not None
    assert ss.register(sid, str(f)) is not None
    assert ss.register(sid, str(f)) is None, 'third file should exceed the cap'


def test_reap_drops_idle_sessions_and_their_files(tmp_path):
    ss = guard.Sessions(str(tmp_path / 's'), ttl=0.0)
    sid = ss.issue()
    where = ss.get(sid)['dir']
    assert ss.reap() == 1
    assert ss.get(sid) is None
    import os
    assert not os.path.exists(where), 'scratch directory should be gone'


# --------------------------------------------------------------------------- #
# Turnstile
# --------------------------------------------------------------------------- #

def test_turnstile_is_off_without_keys():
    ts = guard.Turnstile('', '')
    assert ts.enabled is False
    assert ts.verify('') == (True, ''), 'unconfigured must not block anything'
    assert ts.widget_html() == ''
    assert ts.script_tag() == ''


def test_turnstile_renders_only_when_configured():
    ts = guard.Turnstile(*ALWAYS_PASS)
    assert ts.enabled is True
    assert ALWAYS_PASS[0] in ts.widget_html()
    assert 'challenges.cloudflare.com' in ts.script_tag()


def test_turnstile_rejects_a_missing_token_without_a_round_trip():
    ok, why = guard.Turnstile(*ALWAYS_PASS).verify('')
    assert (ok, why) == (False, 'missing')


@pytest.mark.skipif(not _online(), reason='needs network to reach Cloudflare')
def test_turnstile_accepts_against_the_always_pass_key():
    ok, why = guard.Turnstile(*ALWAYS_PASS).verify('XXXX.DUMMY.TOKEN.XXXX')
    assert ok is True, why


@pytest.mark.skipif(not _online(), reason='needs network to reach Cloudflare')
def test_turnstile_refuses_against_the_always_fail_key():
    ok, _why = guard.Turnstile(*ALWAYS_FAIL).verify('XXXX.DUMMY.TOKEN.XXXX')
    assert ok is False


def test_turnstile_fails_closed_when_cloudflare_is_unreachable(monkeypatch):
    """An outage must not silently disable the check."""
    ts = guard.Turnstile(*ALWAYS_PASS)
    monkeypatch.setattr(ts, 'VERIFY_URL', 'https://127.0.0.1:1/nope')
    ok, why = ts.verify('token')
    assert (ok, why) == (False, 'unreachable')
