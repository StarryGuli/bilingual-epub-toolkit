"""A long job, someone waiting for it, and someone who stops waiting.

Every job longer than five minutes failed on the hosted instance. A stream
proxy in front of nginx closed connections that had carried no bytes for 300
seconds, and an aligning job sends nothing until it is done. The job then ran
on regardless, in the only slot there is, and the reader's retry queued behind
their own abandoned attempt -- thirty-three minutes of that slot went to two
copies of one book on one afternoon, with nobody waiting for either.

These run a real server on a real socket, with the expensive part replaced by
a loop that behaves like the aligner: it does work, and it checks whether it
should stop.
"""
import http.client
import json
import os
import re
import socket
import threading
import time
from http.server import ThreadingHTTPServer

import pytest

from bilingual_epub import align_engine as ae
from bilingual_epub import guard, progress, webui


class _Open:
    def check(self, _key):
        return True, 0


@pytest.fixture
def server(tmp_path, monkeypatch):
    monkeypatch.setattr(webui.Handler, 'KEEPALIVE', 0.2, raising=False)
    monkeypatch.setattr(webui.Handler, 'POLL', 0.05, raising=False)
    srv = ThreadingHTTPServer(('127.0.0.1', 0), webui.Handler)
    srv.cfg = webui.Config(public=True)
    for name in ('uploads', 'outputs', 'reports', 'sessions'):
        os.makedirs(tmp_path / name)
    srv.uploads, srv.outputs = str(tmp_path / 'uploads'), str(tmp_path / 'outputs')
    srv.reports_dir = str(tmp_path / 'reports')
    srv.error_log = str(tmp_path / 'failures.jsonl')
    srv.offered = []
    srv.sessions = guard.Sessions(str(tmp_path / 'sessions'), ttl=600)
    srv.limiter = _Open()
    srv.slots = threading.BoundedSemaphore(1)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield srv
    srv.shutdown()


def _session(srv):
    conn = http.client.HTTPConnection('127.0.0.1', srv.server_address[1], timeout=10)
    conn.request('GET', '/')
    res = conn.getresponse()
    cookie = res.getheader('Set-Cookie').split(';', 1)[0]
    token = re.search(r'name="page_token" value="([^"]+)"',
                      res.read().decode()).group(1)
    conn.close()
    return cookie, token


def _post_bytes(srv, cookie, token):
    boundary = 'xYzBoUnDaRy'
    parts = []
    for name, value in (('page_token', token),):
        parts.append('--%s\r\nContent-Disposition: form-data; name="%s"\r\n\r\n%s\r\n'
                     % (boundary, name, value))
    for name in ('a_file', 'b_file'):
        parts.append('--%s\r\nContent-Disposition: form-data; name="%s"; '
                     'filename="%s.epub"\r\nContent-Type: application/epub+zip\r\n\r\n'
                     'not really a book\r\n' % (boundary, name, name))
    parts.append('--%s--\r\n' % boundary)
    body = ''.join(parts).encode()
    head = ('POST /api/merge HTTP/1.1\r\nHost: x\r\nCookie: %s\r\n'
            'Content-Type: multipart/form-data; boundary=%s\r\n'
            'Content-Length: %d\r\n\r\n' % (cookie, boundary, len(body))).encode()
    return head + body


def _slow_job(seconds, started=None, stopped=None):
    """Stands in for the aligner: does work, and honours the stop signal."""
    def fake(self, fields, files):
        if started is not None:
            started.set()
        end = time.monotonic() + seconds
        steps = max(1, int(seconds * 100))
        try:
            progress.stage('aligning', steps, attempt=1)
            k = 0
            while time.monotonic() < end:
                progress.tick(min(k, steps), steps)
                k += 1
                time.sleep(0.01)
        except progress.Cancelled:
            if stopped is not None:
                stopped.set()
            raise
        return {'title': 'done', 'files': []}
    return fake


def test_a_slow_job_keeps_the_connection_alive(server, monkeypatch):
    """Bytes must flow while the job runs, or a proxy will call it idle."""
    monkeypatch.setattr(webui.Handler, '_do_merge', _slow_job(1.2))
    cookie, token = _session(server)
    sock = socket.create_connection(server.server_address, timeout=5)
    sock.sendall(_post_bytes(server, cookie, token))

    arrivals, data = [], b''
    sock.settimeout(5)
    while True:
        chunk = sock.recv(4096)
        if not chunk:
            break
        arrivals.append(time.monotonic())
        data += chunk
    sock.close()

    head, _, body = data.partition(b'\r\n\r\n')
    assert b' 200 ' in head.split(b'\r\n')[0]
    assert b'X-Accel-Buffering: no' in head, 'nginx would hold the progress back'
    assert b'application/x-ndjson' in head
    lines = [json.loads(line) for line in body.splitlines() if line.strip()]
    assert any('progress' in o for o in lines), 'no progress was sent'
    assert lines[-1].get('ok') is True, 'the last line is not the result'

    gaps = [b - a for a, b in zip(arrivals, arrivals[1:])]
    assert gaps and max(gaps) < 0.8, \
        'the connection went quiet for %.2fs at a 0.2s keepalive' % max(gaps)


def test_a_reader_who_leaves_stops_the_job(server, monkeypatch):
    started, stopped = threading.Event(), threading.Event()
    monkeypatch.setattr(webui.Handler, '_do_merge', _slow_job(30, started, stopped))
    cookie, token = _session(server)

    sock = socket.create_connection(server.server_address, timeout=5)
    sock.sendall(_post_bytes(server, cookie, token))
    assert started.wait(5), 'the job never started'
    sock.close()                                   # the reader walks away

    assert stopped.wait(5), 'the job kept running after its reader had gone'
    assert server.slots.acquire(timeout=5), 'the slot was never given back'
    server.slots.release()

    with open(server.error_log, encoding='utf-8') as f:
        kinds = [json.loads(line)['error_type'] for line in f]
    assert 'ClientGone' in kinds, 'an abandoned job left no record'


def test_a_reader_who_leaves_while_queued_is_never_started(server, monkeypatch):
    """The retry that sat behind its own abandoned attempt."""
    ran = []

    def counting(self, fields, files):
        ran.append(1)
        return {'title': 'done', 'files': []}

    monkeypatch.setattr(webui.Handler, '_do_merge', counting)
    cookie, token = _session(server)

    server.slots.acquire()                         # someone else's long job
    sock = socket.create_connection(server.server_address, timeout=5)
    sock.sendall(_post_bytes(server, cookie, token))
    time.sleep(0.3)                                # queued, kept alive
    sock.close()                                   # gives up waiting
    time.sleep(0.8)                                # long enough to notice
    server.slots.release()                         # the other job finishes
    time.sleep(0.5)

    assert ran == [], 'a job was started for a reader who had already left'


def test_a_quick_job_still_answers_normally(server, monkeypatch):
    monkeypatch.setattr(webui.Handler, '_do_merge', _slow_job(0))
    cookie, token = _session(server)
    conn = http.client.HTTPConnection('127.0.0.1', server.server_address[1], timeout=10)
    raw = _post_bytes(server, cookie, token)
    head, body = raw.split(b'\r\n\r\n', 1)
    headers = dict(line.split(': ', 1) for line in head.decode().split('\r\n')[1:])
    conn.request('POST', '/api/merge', body=body, headers=headers)
    res = conn.getresponse()
    lines = [json.loads(line) for line in res.read().splitlines() if line.strip()]
    assert res.status == 200 and lines[-1]['ok'] is True


def test_cancellation_reaches_the_real_aligner():
    """The stand-in above checks the flag; this proves the DP does too."""
    job = progress.Job()
    job.stop.set()
    token = progress.bind(job)
    try:
        a = [('p', 'Line %d %s' % (i, 'w' * (i % 30)), 'x') for i in range(500)]
        with pytest.raises(ae.Cancelled):
            ae.align(a, list(a))
    finally:
        progress.unbind(token)


def test_a_departure_is_noticed_without_waiting_for_a_keepalive(server, monkeypatch):
    """Measured on the deploy host: noticed 31 seconds late.

    The first write after the far end closes usually lands in the kernel's
    buffer and succeeds, so relying on the keepalive to fail cost a whole
    interval -- during which the next reader sat queued behind a job nobody
    wanted. With the keepalive pushed out of reach, only the socket can tell.
    """
    monkeypatch.setattr(webui.Handler, 'KEEPALIVE', 30.0, raising=False)
    started, stopped = threading.Event(), threading.Event()
    monkeypatch.setattr(webui.Handler, '_do_merge', _slow_job(30, started, stopped))
    cookie, token = _session(server)

    sock = socket.create_connection(server.server_address, timeout=5)
    sock.sendall(_post_bytes(server, cookie, token))
    assert started.wait(5)
    left = time.monotonic()
    sock.close()

    assert stopped.wait(3), 'the departure went unnoticed until a keepalive'
    assert time.monotonic() - left < 1.5, \
        'took %.1fs to notice the reader had gone' % (time.monotonic() - left)


# --------------------------------------------------------------------------- #
# what the reader is shown while it runs
# --------------------------------------------------------------------------- #

def _read_stream(server, cookie, token, until=None):
    sock = socket.create_connection(server.server_address, timeout=5)
    sock.sendall(_post_bytes(server, cookie, token))
    data = b''
    sock.settimeout(10)
    while True:
        chunk = sock.recv(4096)
        if not chunk:
            break
        data += chunk
        if until and until(data):
            break
    sock.close()
    body = data.partition(b'\r\n\r\n')[2]
    return [json.loads(line) for line in body.splitlines() if line.strip()]


def test_progress_moves_forward_and_ends_in_a_result(server, monkeypatch):
    monkeypatch.setattr(webui.Handler, '_do_merge', _slow_job(1.0))
    cookie, token = _session(server)
    lines = _read_stream(server, cookie, token)
    seen = [o['progress'] for o in lines if 'progress' in o]
    aligning = [p['done'] for p in seen if p['stage'] == 'aligning']
    assert len(aligning) >= 3, 'too few updates to look alive: %r' % aligning
    assert aligning == sorted(aligning), 'progress went backwards'
    assert lines[-1]['ok'] is True


def test_a_queued_reader_is_told_how_many_are_ahead(server, monkeypatch):
    monkeypatch.setattr(webui.Handler, '_do_merge', _slow_job(0.2))
    cookie, token = _session(server)
    server.slots.acquire()                      # a job is already running
    try:
        q, lock = webui.Handler._queue(type('H', (), {'server': server})())
        with lock:
            q.append(object())                  # ...and it is in the queue
        lines = _read_stream(server, cookie, token,
                             until=lambda d: b'"queued"' in d)
    finally:
        with lock:
            q.clear()
        server.slots.release()
    queued = [o['progress'] for o in lines
              if 'progress' in o and o['progress']['stage'] == 'queued']
    assert queued and queued[-1]['ahead'] == 1, queued


def test_the_real_aligner_reports_progress():
    job = progress.Job()
    token = progress.bind(job)
    seen = []
    real_tick = progress.tick

    def recording_tick(done, total):
        seen.append((job.stage, done, total))
        real_tick(done, total)

    progress.tick = recording_tick
    try:
        a = [('p', 'Line %d %s' % (i, 'w' * (i % 30)), 'x') for i in range(300)]
        beads = ae.align(a, list(a))
        ae.confidence(a, list(a), beads)
    finally:
        progress.tick = real_tick
        progress.unbind(token)
    stages = [st for st, _d, _t in seen]
    assert 'aligning' in stages and 'checking' in stages
    checking = [d for st, d, _t in seen if st == 'checking']
    assert checking == sorted(checking), 'the checking bar ran backwards'
