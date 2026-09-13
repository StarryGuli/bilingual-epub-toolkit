"""The operator's view of what has been failing.

Run on a timer for the daily digest, or by hand to close a case:

    bilingual-epub-reports digest --to me@example.com --since 1d
    bilingual-epub-reports list
    bilingual-epub-reports resolve 20260911-142641-1b3bb2 \\
        --message "Archives containing a book are now accepted."

`resolve` is what sends a reporter their one message, so closing the case and
telling the person are the same action and cannot drift apart.
"""
import argparse
import datetime
import os
import sys

from . import notify

DEFAULT_LOG = '/var/log/bilingual-epub/failures.jsonl'
DEFAULT_REPORTS = '/var/lib/bilingual-epub/reports'


def _since(spec):
    """'1d', '12h', '7d' -> an ISO timestamp to compare records against."""
    if not spec:
        return None
    unit, n = spec[-1], spec[:-1]
    hours = {'h': 1, 'd': 24}.get(unit)
    if hours is None or not n.isdigit():
        raise SystemExit('--since looks like 12h or 7d, not %r' % spec)
    at = (datetime.datetime.now(datetime.timezone.utc)
          - datetime.timedelta(hours=hours * int(n)))
    return at.isoformat(timespec='seconds')


def main(argv=None):
    p = argparse.ArgumentParser(prog='bilingual-epub-reports',
                                description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument('--log', default=os.environ.get('BILINGUAL_EPUB_LOG', DEFAULT_LOG))
    p.add_argument('--reports', default=os.environ.get('BILINGUAL_EPUB_REPORTS',
                                                       DEFAULT_REPORTS))
    p.add_argument('--dry-run', action='store_true',
                   help='render any mail and print it instead of sending')
    sub = p.add_subparsers(dest='cmd', required=True)

    pd = sub.add_parser('digest', help='summarise recent failures')
    pd.add_argument('--since', default='1d', help='12h, 7d ... (default 1d)')
    pd.add_argument('--to', default=os.environ.get('BILINGUAL_EPUB_TO'),
                    help='where to send it; prints to stdout if omitted')
    pd.add_argument('--quiet-when-idle', action='store_true',
                    help='send nothing when there is nothing to report')

    sub.add_parser('list', help='every report, open ones first')

    pr = sub.add_parser('resolve', help='close a report and notify its author')
    pr.add_argument('id')
    pr.add_argument('--message', required=True,
                    help='what to tell them, in one or two sentences')

    args = p.parse_args(argv)
    mailer = notify.Mailer(dry_run=args.dry_run)

    if args.cmd == 'digest':
        since = _since(args.since)
        failures = notify.read_failures(args.log, since)
        reports = notify.read_reports(args.reports)
        summary = notify.summarise(failures, reports)
        text = notify.format_digest(summary, failures, reports, args.since)
        # "idle" means nothing new happened, not "nothing is outstanding".
        # A report stays open until someone closes it, so counting open ones
        # as activity would mail the same three cases every night forever --
        # which is the noise a daily digest exists to avoid.
        fresh = [r for r in reports
                 if since is None or (r.get('saved_at') or '') >= since]
        idle = not summary['failures'] and not fresh
        if idle and args.quiet_when_idle:
            return 0
        if args.to:
            mailer.send(args.to, 'EPUB toolkit: %d failure(s), %d report(s) open'
                        % (summary['failures'], summary['reports_open']), text)
            if args.dry_run:
                print(mailer.sent[-1])
            else:
                print('sent to %s' % args.to)
        else:
            print(text)
        return 0

    if args.cmd == 'list':
        reports = notify.read_reports(args.reports)
        if not reports:
            print('no reports')
            return 0
        for r in sorted(reports, key=lambda r: (bool(r.get('resolved_at')), r['id'])):
            state = 'resolved' if r.get('resolved_at') else 'open'
            print('%-26s %-8s %s%s' % (r['id'], state,
                                       (r.get('error') or '')[:80],
                                       '  [address on file]' if r.get('notify') else ''))
        return 0

    notified, address = notify.resolve(args.reports, args.id, args.message,
                                       mailer=mailer)
    if notified and args.dry_run:
        print(mailer.sent[-1])
    elif notified:
        print('closed %s and notified %s' % (args.id, address))
    else:
        print('closed %s (no address was left)' % args.id)
    return 0


if __name__ == '__main__':
    sys.exit(main())
