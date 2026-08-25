"""The translation round trip, and the guarantee that makes it worth using.

Nothing here calls a real model. The provider is exercised against a local
stand-in that speaks both request dialects, so the client's own behaviour --
retrying a short reply, resuming from cache, refusing a mismatched file -- is
what gets tested rather than any vendor's uptime.
"""
import json
import os
import threading
import zipfile
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

from bilingual_epub import merge_bilingual, textio, translate

# --------------------------------------------------------------------------- #
# export / import
# --------------------------------------------------------------------------- #

def test_export_numbers_every_block(en_epub):
    payload = textio.export_text(en_epub)
    assert payload['format'] == textio.FORMAT
    assert payload['source_lang'] == 'en'
    assert [b['i'] for b in payload['blocks']] == list(range(len(payload['blocks'])))
    assert any(b['tag'].startswith('h') for b in payload['blocks']), 'headings kept'
    assert all(b['text'].strip() for b in payload['blocks']), 'no empty blocks'


def test_export_strips_inline_markup(en_epub):
    payload = textio.export_text(en_epub)
    assert not any('<' in b['text'] for b in payload['blocks'])


def test_a_translation_built_this_way_aligns_perfectly(en_epub, fr_epub, tmp_path):
    """The reason this route exists: structure is preserved, so merge has
    nothing left to guess and every paragraph pairs with its own translation."""
    src = textio.export_text(en_epub)
    other = textio.export_text(fr_epub)
    built = textio.build_epub(src, [b['text'] for b in other['blocks']],
                              str(tmp_path / 'fr.epub'), 'fr')
    _out, stats = merge_bilingual(en_epub, built, str(tmp_path / 'bi.epub'))
    n11 = sum(r[3] for r in stats)
    rest = sum(r[4] + r[5] + r[6] for r in stats)
    assert rest == 0 and n11 == len(src['blocks']), 'expected a clean 1:1 book'


def test_import_refuses_a_short_translation(en_epub, tmp_path):
    payload = textio.export_text(en_epub)
    short = [b['text'] for b in payload['blocks']][:-2]
    with pytest.raises(SystemExit) as e:
        textio.build_epub(payload, short, str(tmp_path / 'x.epub'), 'fr')
    assert 'one to one' in str(e.value)


def test_import_refuses_empty_blocks(en_epub, tmp_path):
    payload = textio.export_text(en_epub)
    texts = [b['text'] for b in payload['blocks']]
    texts[3] = '   '
    with pytest.raises(SystemExit) as e:
        textio.build_epub(payload, texts, str(tmp_path / 'x.epub'), 'fr')
    assert 'empty' in str(e.value).lower()


@pytest.mark.parametrize('shape', ['array', 'object', 'lines'])
def test_translation_file_shapes(en_epub, tmp_path, shape):
    payload = textio.export_text(en_epub)
    textio.write_export(payload, str(tmp_path / 'src.json'))
    texts = ['ZH ' + b['text'] for b in payload['blocks']]

    path = tmp_path / 'tr'
    if shape == 'array':
        path.write_text(json.dumps(texts, ensure_ascii=False), encoding='utf-8')
    elif shape == 'object':
        path.write_text(json.dumps(
            {'target_lang': 'zh',
             'blocks': [{'i': i, 'text': t} for i, t in enumerate(texts)]},
            ensure_ascii=False), encoding='utf-8')
    else:
        path.write_text('\n'.join(texts), encoding='utf-8')

    out = textio.import_text(str(tmp_path / 'src.json'), str(path),
                             str(tmp_path / 'o.epub'), lang='zh')
    with zipfile.ZipFile(out) as zf:
        assert 'lang="zh"' in zf.read('OEBPS/text/ch001.xhtml').decode('utf-8')


def test_line_file_starting_with_a_bracket_is_not_read_as_json(en_epub, tmp_path):
    """Regression: sniffing the first character alone misread a plain-text
    translation whose first line legitimately opens with '['."""
    payload = textio.export_text(en_epub)
    textio.write_export(payload, str(tmp_path / 'src.json'))
    texts = ['[%d] %s' % (i, b['text']) for i, b in enumerate(payload['blocks'])]
    (tmp_path / 'tr.txt').write_text('\n'.join(texts), encoding='utf-8')
    out = textio.import_text(str(tmp_path / 'src.json'), str(tmp_path / 'tr.txt'),
                             str(tmp_path / 'o.epub'), lang='zh')
    assert os.path.exists(out)


# --------------------------------------------------------------------------- #
# reply parsing
# --------------------------------------------------------------------------- #

def test_parses_a_bare_array():
    assert translate.parse_reply('["a", "b"]', 2) == ['a', 'b']


def test_parses_through_a_code_fence():
    assert translate.parse_reply('```json\n["a","b"]\n```', 2) == ['a', 'b']


def test_parses_an_array_buried_in_prose():
    reply = 'Sure, here you go:\n["a","b"]\nHope that helps!'
    assert translate.parse_reply(reply, 2) == ['a', 'b']


def test_parses_numbered_lines_when_there_is_no_json():
    assert translate.parse_reply('1. first\n2. second', 2) == ['first', 'second']


def test_a_wrong_count_is_an_error_not_a_guess():
    with pytest.raises(translate.TranslationError):
        translate.parse_reply('["only one"]', 3)


# --------------------------------------------------------------------------- #
# the provider, against a local stand-in
# --------------------------------------------------------------------------- #

class _Handler(BaseHTTPRequestHandler):
    short_once = True

    def log_message(self, *a):
        pass

    def do_POST(self):
        n = int(self.headers.get('Content-Length', 0))
        body = json.loads(self.rfile.read(n).decode())
        anthropic = self.path.endswith('/v1/messages')
        auth = (self.headers.get('x-api-key') if anthropic
                else self.headers.get('Authorization', ''))
        if 'GOOD' not in (auth or ''):
            self.send_response(401)
            self.end_headers()
            self.wfile.write(b'{"error":"bad key"}')
            return
        user = body['messages'][-1]['content']
        items = ['ZH:' + ln.split('] ', 1)[1]
                 for ln in user.splitlines() if ln.startswith('[')]
        if type(self).short_once and len(items) > 1:
            type(self).short_once = False       # exercise the retry ladder once
            items = items[:-1]
        text = json.dumps(items, ensure_ascii=False)
        payload = ({'content': [{'type': 'text', 'text': text}]} if anthropic
                   else {'choices': [{'message': {'content': text}}]})
        data = json.dumps(payload).encode()
        self.send_response(200)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Content-Length', str(len(data)))
        self.end_headers()
        self.wfile.write(data)


@pytest.fixture
def stub_api():
    _Handler.short_once = True
    srv = HTTPServer(('127.0.0.1', 0), _Handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield 'http://127.0.0.1:%d' % srv.server_port
    srv.shutdown()


@pytest.mark.parametrize('dialect', ['openai', 'anthropic'])
def test_translates_a_book_through_either_dialect(en_epub, tmp_path, stub_api, dialect):
    payload = textio.export_text(en_epub)
    base = stub_api + ('' if dialect == 'anthropic' else '/v1')
    provider = translate.Provider(dialect=dialect, base_url=base,
                                  api_key='GOOD', model='stub')
    texts = translate.translate_payload(payload, provider, 'zh', batch_size=5,
                                        cache_path=str(tmp_path / 'c.json'))
    assert len(texts) == len(payload['blocks'])
    assert all(t.startswith('ZH:') for t in texts)


def test_resumes_from_cache_without_calling_again(en_epub, tmp_path, stub_api):
    payload = textio.export_text(en_epub)
    cache = tmp_path / 'c.json'
    done = {str(b['i']): 'cached' for b in payload['blocks']}
    cache.write_text(json.dumps(done), encoding='utf-8')
    # a provider pointed at a dead port: any request at all would fail
    provider = translate.Provider(base_url='http://127.0.0.1:1/v1',
                                  api_key='GOOD', model='stub')
    texts = translate.translate_payload(payload, provider, 'zh',
                                        cache_path=str(cache))
    assert texts == ['cached'] * len(payload['blocks'])


def test_a_bad_key_fails_loudly(en_epub, tmp_path, stub_api):
    payload = textio.export_text(en_epub)
    provider = translate.Provider(base_url=stub_api + '/v1', api_key='WRONG',
                                  model='stub', timeout=5)
    with pytest.raises(SystemExit) as e:
        translate.translate_payload(payload, provider, 'zh', batch_size=5,
                                    retries=1, cache_path=str(tmp_path / 'c.json'))
    assert '401' in str(e.value)


def test_estimate_does_not_call_anything(en_epub):
    est = translate.estimate(textio.export_text(en_epub), batch_size=5)
    assert est['blocks'] > 0 and est['chars'] > 0
    assert est['requests'] == -(-est['blocks'] // 5)


def test_provider_requires_a_model():
    with pytest.raises(SystemExit):
        translate.Provider(model='')


def test_unknown_dialect_is_refused():
    with pytest.raises(SystemExit):
        translate.Provider(dialect='nonsense', model='m')
