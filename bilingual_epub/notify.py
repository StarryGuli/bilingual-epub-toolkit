"""Mail, and the periodic look at what has been failing.

Two decisions shape this file, both of them the operator's.

Failures are reviewed on a schedule rather than announced as they happen. A
public instance fails for ordinary reasons -- someone uploads the wrong file,
a download was truncated -- and a message for each one trains its reader to
ignore them. A digest once a day is read; an alert per failure is filtered.

And the person who reported a failure is told when it is fixed, if they chose
to leave an address. That is the only thing an address is used for, and
resolving a report is what sends it, so there is no separate list to forget
about and nothing that keeps sending after the case is closed.

Sending is off unless a destination is configured. Nothing here will quietly
mail anyone because a default said so.
"""
import json
import os
import smtplib
import subprocess
from email.message import EmailMessage

SENDMAIL = '/usr/sbin/sendmail'


class Mailer:
    """Delivers through the local MTA, or over SMTP, or not at all.

    `dry_run` renders the message and returns it without sending, which is
    what the tests use and what `--dry-run` gives an operator who wants to see
    the digest before committing to a cron entry.
    """

    def __init__(self, sender=None, smtp_url=None, dry_run=False):
        self.sender = sender or os.environ.get('BILINGUAL_EPUB_FROM')
        self.smtp_url = smtp_url or os.environ.get('BILINGUAL_EPUB_SMTP')
        self.dry_run = dry_run
        self.sent = []

    def send(self, to, subject, body):
        msg = EmailMessage()
        msg['To'] = to
        msg['From'] = self.sender or 'bilingual-epub@localhost'
        msg['Subject'] = subject
        msg.set_content(body)
        if self.dry_run:
            self.sent.append(msg)
            return True
        if self.smtp_url:
            host, _, port = self.smtp_url.partition(':')
            with smtplib.SMTP(host, int(port or 25), timeout=30) as s:
                s.send_message(msg)
        else:
            if not os.path.exists(SENDMAIL):
                raise RuntimeError(
                    'no way to send mail: %s is missing and no SMTP host was '
                    'given (set BILINGUAL_EPUB_SMTP)' % SENDMAIL)
            subprocess.run([SENDMAIL, '-t', '-oi'],
                           input=msg.as_bytes(), check=True, timeout=60)
        self.sent.append(msg)
        return True


# --------------------------------------------------------------------------- #
# reading what has happened
# --------------------------------------------------------------------------- #

def read_failures(log_path, since=None):
    """Failure records, newest last. `since` is an ISO date string."""
    out = []
    if not log_path or not os.path.exists(log_path):
        return out
    with open(log_path, encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                entry = json.loads(line)
            except ValueError:
                continue
            if since and entry.get('at', '') < since:
                continue
            out.append(entry)
    return out


def read_reports(reports_dir):
    """Every saved report, with the id and whether it is still open."""
    out = []
    if not reports_dir or not os.path.isdir(reports_dir):
        return out
    for rid in sorted(os.listdir(reports_dir)):
        path = os.path.join(reports_dir, rid, 'report.json')
        if not os.path.exists(path):
            continue
        try:
            with open(path, encoding='utf-8') as f:
                data = json.load(f)
        except ValueError:
            continue
        data['id'] = data.get('id') or rid
        data['_path'] = path
        out.append(data)
    return out


def summarise(failures, reports):
    """Group failures by the reason a reader was given, commonest first."""
    by_reason = {}
    for entry in failures:
        key = entry.get('error') or entry.get('error_type') or 'unknown'
        by_reason[key] = by_reason.get(key, 0) + 1
    ranked = sorted(by_reason.items(), key=lambda kv: -kv[1])
    open_reports = [r for r in reports if not r.get('resolved_at')]
    return {
        'failures': len(failures),
        'by_reason': ranked,
        'reports_open': len(open_reports),
        'reports_awaiting_reply': sum(1 for r in open_reports if r.get('notify')),
    }


def format_digest(summary, failures, reports, window):
    lines = ['Bilingual EPUB Toolkit -- failures in the last %s' % window, '']
    if not summary['failures'] and not summary['reports_open']:
        lines.append('Nothing failed and no reports are open.')
        return '\n'.join(lines)

    lines.append('%d failure(s) recorded.' % summary['failures'])
    for reason, count in summary['by_reason']:
        lines.append('  %4d  %s' % (count, reason[:150]))

    if summary['reports_open']:
        lines += ['', '%d report(s) open, %d of which left an address:'
                  % (summary['reports_open'],
                     summary['reports_awaiting_reply'])]
        for r in reports:
            if r.get('resolved_at'):
                continue
            lines.append('  %s  %s%s'
                         % (r['id'],
                            (r.get('error') or '')[:90],
                            '  [will be notified]' if r.get('notify') else ''))
        lines += ['', 'Close one with:',
                  '  bilingual-epub-reports resolve <id> --message "..."']
    return '\n'.join(lines)


def resolve(reports_dir, rid, message, mailer=None, now=None):
    """Mark a report fixed and, if an address was left, say so.

    Returns (notified, address). The report is marked either way, so a case
    with no address still stops appearing in the digest.
    """
    import datetime
    path = os.path.join(reports_dir, rid, 'report.json')
    if not os.path.exists(path):
        raise FileNotFoundError('no such report: %s' % rid)
    with open(path, encoding='utf-8') as f:
        report = json.load(f)

    stamp = now or datetime.datetime.now(
        datetime.timezone.utc).isoformat(timespec='seconds')
    report['resolved_at'] = stamp
    report['resolution'] = message

    address = report.get('notify')
    notified = False
    if address and mailer is not None:
        mailer.send(address,
                    'The EPUB failure you reported has been fixed',
                    'You reported a failure at the Bilingual EPUB Toolkit '
                    '(reference %s).\n\n%s\n\nThe file you sent was used only '
                    'to reproduce and fix this, and your address was kept '
                    'only to send this one message. Both are now being '
                    'removed.\n' % (rid, message))
        notified = True
        # the promise made at collection: used once, then gone
        report.pop('notify', None)

    with open(path, 'w', encoding='utf-8') as f:
        json.dump(report, f, ensure_ascii=False, indent=1)
    return notified, address
