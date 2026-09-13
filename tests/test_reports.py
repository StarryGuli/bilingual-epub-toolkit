"""The digest, and the one message a reporter is promised.

The address is collected with a narrow promise printed next to the field:
used once, to say this failure is fixed, deleted with the report. These check
the code keeps it -- in particular that resolving a case removes the address,
so a second resolve cannot mail the same person again.
"""
import datetime
import json
import os

import pytest

from bilingual_epub import diagnostics, notify
from bilingual_epub.reportcli import main as reports_main


@pytest.fixture
def store(tmp_path):
    log = tmp_path / 'failures.jsonl'
    reports = tmp_path / 'reports'
    reports.mkdir()
    return str(log), str(reports)


def add_failure(log, at, error):
    with open(log, 'a', encoding='utf-8') as f:
        f.write(json.dumps({'at': at, 'endpoint': '/api/merge',
                            'error_type': 'UserFacing', 'error': error}) + '\n')


def add_report(reports_dir, error, notify_to=None):
    report = {'endpoint': '/api/merge', 'error': error}
    if notify_to:
        report['notify'] = notify_to
    return diagnostics.save_report(reports_dir, report)


def test_digest_groups_by_reason(store):
    log, reports = store
    add_failure(log, '2026-09-11T03:51:33+00:00', 'No book was found inside this file.')
    add_failure(log, '2026-09-11T03:54:25+00:00', 'No book was found inside this file.')
    add_failure(log, '2026-09-11T04:05:15+00:00', 'This file could not be opened.')
    summary = notify.summarise(notify.read_failures(log), notify.read_reports(reports))
    assert summary['failures'] == 3
    assert summary['by_reason'][0] == ('No book was found inside this file.', 2)


def test_digest_is_quiet_when_nothing_happened(store, capsys):
    log, reports = store
    rc = reports_main(['--log', log, '--reports', reports,
                       'digest', '--quiet-when-idle'])
    assert rc == 0
    assert capsys.readouterr().out == '', 'a silent night still sent something'


def test_resolving_notifies_once_and_then_forgets_the_address(store):
    _log, reports = store
    rid = add_report(reports, 'No book was found.', notify_to='reader@example.com')
    mailer = notify.Mailer(dry_run=True)

    notified, address = notify.resolve(reports, rid, 'Archives are now accepted.',
                                       mailer=mailer)
    assert notified and address == 'reader@example.com'
    assert len(mailer.sent) == 1
    assert 'fixed' in mailer.sent[0]['Subject'].lower()
    assert 'Archives are now accepted.' in mailer.sent[0].get_content()

    saved = json.load(open(os.path.join(reports, rid, 'report.json'),
                           encoding='utf-8'))
    assert saved['resolved_at']
    assert 'notify' not in saved, 'the address outlived its one purpose'

    # closing it again must not reach them a second time
    notify.resolve(reports, rid, 'Still fixed.', mailer=mailer)
    assert len(mailer.sent) == 1


def test_a_report_without_an_address_still_closes(store):
    _log, reports = store
    rid = add_report(reports, 'Something.')
    notified, address = notify.resolve(reports, rid, 'Fixed.',
                                       mailer=notify.Mailer(dry_run=True))
    assert not notified and address is None
    saved = json.load(open(os.path.join(reports, rid, 'report.json'),
                           encoding='utf-8'))
    assert saved['resolved_at']


def test_resolved_reports_drop_out_of_the_digest(store):
    _log, reports = store
    rid = add_report(reports, 'A problem.', notify_to='x@example.com')
    before = notify.summarise([], notify.read_reports(reports))
    assert before['reports_open'] == 1
    assert before['reports_awaiting_reply'] == 1
    notify.resolve(reports, rid, 'Done.', mailer=notify.Mailer(dry_run=True))
    after = notify.summarise([], notify.read_reports(reports))
    assert after['reports_open'] == 0


def test_nothing_is_mailed_without_a_destination(store, capsys):
    log, reports = store
    now = datetime.datetime.now(datetime.timezone.utc).isoformat(timespec='seconds')
    add_failure(log, now, 'Something failed.')
    reports_main(['--log', log, '--reports', reports, 'digest'])
    out = capsys.readouterr().out
    assert 'Something failed.' in out, 'digest should print when --to is absent'


def test_since_window_excludes_older_records(store):
    log, _reports = store
    add_failure(log, '2020-01-01T00:00:00+00:00', 'Ancient.')
    add_failure(log, '2099-01-01T00:00:00+00:00', 'Recent.')
    from bilingual_epub.reportcli import _since
    recent = notify.read_failures(log, _since('1d'))
    assert [e['error'] for e in recent] == ['Recent.']


def test_old_open_reports_do_not_retrigger_the_digest(store, capsys):
    """Open is not the same as new. Three cases left open for a week must not
    produce a mail every night; only fresh activity should."""
    _log, reports = store
    rid = add_report(reports, 'An old problem.')
    path = os.path.join(reports, rid, 'report.json')
    stale = json.load(open(path, encoding='utf-8'))
    stale['saved_at'] = '2020-01-01T00:00:00+00:00'
    json.dump(stale, open(path, 'w', encoding='utf-8'))

    rc = reports_main(['--log', _log, '--reports', reports,
                       'digest', '--since', '1d', '--quiet-when-idle'])
    assert rc == 0
    assert capsys.readouterr().out == '', 'an old open case woke the digest'


def test_a_new_report_does_trigger_the_digest(store, capsys):
    _log, reports = store
    add_report(reports, 'A problem reported just now.')
    reports_main(['--log', _log, '--reports', reports,
                  'digest', '--since', '1d', '--quiet-when-idle'])
    assert 'report(s) open' in capsys.readouterr().out
