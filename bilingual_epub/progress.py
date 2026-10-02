"""How far a job has got, and whether anyone still wants it.

Two questions with one answer. A web reader waiting on a long book needs to
see that it is moving -- a silent spinner for several minutes is
indistinguishable from a hung server, and on the hosted instance people
abandoned jobs that were, in fact, nearly done. And a job whose reader has
left should stop, rather than keep the only slot busy for a quarter of an
hour on a result nobody will collect.

Both are the business of whoever started the job, not of the code doing the
work. So the engine reports into a Job bound to the current thread and checks
it for a stop request, and does neither when nothing is bound -- the command
line and the tests run exactly as before.

Reporting is cheap by construction: a few attribute stores every 64 rows of
the alignment. The reader of a Job polls it; nothing here pushes, blocks or
allocates.
"""
import contextvars
import threading


class Cancelled(Exception):
    """The job was abandoned; stop and give the slot back."""


class Job:
    """One job's progress, written by the worker and read by the server.

    Plain attributes, written from one thread and read from another. Under
    the GIL each store is atomic, and a reader that catches `done` from one
    tick and `total` from the next draws a progress bar a hair off for one
    frame, which is not worth a lock in the inner loop.
    """

    def __init__(self):
        self.stop = threading.Event()
        self.stage = 'queued'
        self.done = 0
        self.total = 0
        self.attempt = 1        # alignment passes; above 1 means it widened
        self.ahead = 0          # jobs in front, while queued
        self.version = 0        # bumped on every change, so a reader can
                                # tell whether there is anything new to send

    def snapshot(self):
        return {'stage': self.stage, 'done': self.done, 'total': self.total,
                'attempt': self.attempt, 'ahead': self.ahead}


_job = contextvars.ContextVar('bilingual_epub_job', default=None)


def bind(job):
    """Report the current thread's work into `job`. Returns a reset token."""
    return _job.set(job)


def unbind(token):
    _job.reset(token)


def check():
    """Raise Cancelled if the job has been abandoned."""
    job = _job.get()
    if job is not None and job.stop.is_set():
        raise Cancelled()


def stage(name, total=0, attempt=None):
    """Enter a new phase of the work, and check whether to carry on."""
    job = _job.get()
    if job is None:
        return
    if job.stop.is_set():
        raise Cancelled()
    job.stage = name
    job.done = 0
    job.total = total
    if attempt is not None:
        job.attempt = attempt
    job.version += 1


def tick(done, total):
    """Record progress within the current phase, and check whether to carry on."""
    job = _job.get()
    if job is None:
        return
    if job.stop.is_set():
        raise Cancelled()
    job.done = done
    job.total = total
    job.version += 1
