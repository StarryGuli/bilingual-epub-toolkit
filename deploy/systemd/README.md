# Scheduled failure digest

A hosted instance fails for ordinary reasons — someone uploads the wrong
file, a download was truncated — and a message for each one trains its reader
to ignore them. This sends one summary a night, and nothing at all on a quiet
night.

## Install

```bash
sudo cp bilingual-epub-digest.* /etc/systemd/system/
sudo systemctl edit bilingual-epub-digest.service   # set BILINGUAL_EPUB_TO
sudo systemctl daemon-reload
sudo systemctl enable --now bilingual-epub-digest.timer
```

Check it before trusting it to a timer:

```bash
bilingual-epub-reports digest --since 7d            # prints, sends nothing
bilingual-epub-reports digest --since 7d --to you@example.com --dry-run
```

## Closing a case

`resolve` marks the report handled and, if the person left an address, sends
them the one message they were promised. Closing and notifying are the same
command so they cannot drift apart:

```bash
bilingual-epub-reports list
bilingual-epub-reports resolve 20260911-142641-1b3bb2 \
    --message "Archives containing a book are now accepted."
```

The address is removed from the report at that moment. Resolving twice does
not reach anyone twice.

## Sending

Delivery goes through the local MTA (`/usr/sbin/sendmail`) by default. Set
`BILINGUAL_EPUB_SMTP=host:port` to use SMTP instead, and
`BILINGUAL_EPUB_FROM` to choose the sender. With neither an MTA nor an SMTP
host, sending raises rather than failing silently — a digest nobody receives
is worse than no digest.
