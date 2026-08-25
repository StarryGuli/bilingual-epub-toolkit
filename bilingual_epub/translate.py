"""Translate a book with whatever model API you already pay for.

Bring your own endpoint. Two request shapes cover almost everything:

* ``openai``    -- /chat/completions. OpenAI, DeepSeek, Moonshot, Zhipu,
                   SiliconFlow, OpenRouter, Groq, Together, and any local
                   server that speaks the same dialect (Ollama, LM Studio,
                   vLLM, llama.cpp).
* ``anthropic`` -- /v1/messages.

Nothing here is bundled with a provider or a key. Point ``--base-url`` at your
endpoint, pass your own ``--api-key`` and ``--model``, and the cost lands on
your account.

Three things matter more than the request format:

**Blocks must come back one for one.** The whole reason to translate through
this tool rather than paste chapters into a chat window is that the output
stays structurally parallel to the input, which is what lets merge pair every
paragraph exactly. So batches are numbered, replies are checked, and a batch
that comes back the wrong length is retried smaller and finally one block at a
time rather than accepted.

**Long books must survive interruption.** A thousand-paragraph book is a lot of
requests; a network blip an hour in must not throw the hour away. Every block
is written to a cache file as it lands, and rerunning the same command picks up
where it stopped.

**You should know the size before you spend.** ``--dry-run`` reports blocks,
characters and request count without calling anything.
"""
import json
import os
import re
import sys
import time
import urllib.error
import urllib.request

DIALECTS = ('openai', 'anthropic')

SYSTEM = (
    'You are translating a book into {target}. You will be given numbered '
    'blocks of text. Translate each block into {target}.\n'
    'Rules:\n'
    '1. Return a JSON array of strings and nothing else.\n'
    '2. The array must have exactly the same number of items as there are '
    'input blocks, in the same order.\n'
    '3. Translate each block on its own. Never merge two blocks, never split '
    'one, never drop one, never add one.\n'
    '4. A block that is a chapter heading stays a heading. Keep it short.\n'
    '5. Translate the prose only. Do not explain, annotate, or comment.\n'
    '6. If a block cannot be translated, return it unchanged rather than '
    'returning an empty string.'
)


class TranslationError(RuntimeError):
    pass


class Provider:
    """One model endpoint."""

    def __init__(self, dialect='openai', base_url=None, api_key=None, model=None,
                 timeout=180.0, temperature=0.2, extra_headers=None):
        if dialect not in DIALECTS:
            raise SystemExit('Unknown API dialect %r. Pick one of: %s'
                             % (dialect, ', '.join(DIALECTS)))
        self.dialect = dialect
        self.base_url = (base_url or self._default_base()).rstrip('/')
        self.api_key = api_key or ''
        self.model = model or ''
        self.timeout = timeout
        self.temperature = temperature
        self.extra_headers = extra_headers or {}
        if not self.model:
            raise SystemExit('No model given. Pass --model.')

    def _default_base(self):
        return ('https://api.anthropic.com' if self.dialect == 'anthropic'
                else 'https://api.openai.com/v1')

    # -- request shapes ---------------------------------------------------- #
    def _openai_request(self, system, user):
        url = self.base_url + '/chat/completions'
        body = {'model': self.model,
                'messages': [{'role': 'system', 'content': system},
                             {'role': 'user', 'content': user}],
                'temperature': self.temperature}
        headers = {'Content-Type': 'application/json'}
        if self.api_key:
            headers['Authorization'] = 'Bearer ' + self.api_key
        return url, body, headers

    def _anthropic_request(self, system, user):
        url = self.base_url + '/v1/messages'
        body = {'model': self.model, 'max_tokens': 8192, 'system': system,
                'temperature': self.temperature,
                'messages': [{'role': 'user', 'content': user}]}
        headers = {'Content-Type': 'application/json',
                   'anthropic-version': '2023-06-01'}
        if self.api_key:
            headers['x-api-key'] = self.api_key
        return url, body, headers

    @staticmethod
    def _openai_text(data):
        return data['choices'][0]['message']['content']

    @staticmethod
    def _anthropic_text(data):
        return ''.join(part.get('text', '') for part in data.get('content', []))

    def complete(self, system, user):
        if self.dialect == 'anthropic':
            url, body, headers = self._anthropic_request(system, user)
            pick = self._anthropic_text
        else:
            url, body, headers = self._openai_request(system, user)
            pick = self._openai_text
        headers.update(self.extra_headers)
        req = urllib.request.Request(
            url, json.dumps(body).encode('utf-8'), headers, method='POST')
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as r:
                data = json.loads(r.read().decode('utf-8'))
        except urllib.error.HTTPError as e:
            detail = e.read().decode('utf-8', 'replace')[:400]
            raise TranslationError('HTTP %s from %s: %s' % (e.code, url, detail)) from e
        except (urllib.error.URLError, OSError) as e:
            raise TranslationError('Cannot reach %s: %s' % (url, e)) from e
        try:
            return pick(data)
        except (KeyError, IndexError, TypeError) as e:
            raise TranslationError(
                'Unexpected reply shape from %s: %s' % (url, json.dumps(data)[:300])) from e


# --------------------------------------------------------------------------- #
# reply parsing
# --------------------------------------------------------------------------- #

def parse_reply(text, want):
    """Pull `want` strings out of a model reply.

    Models wrap JSON in prose or fences often enough that insisting on clean
    JSON would fail constantly. Try progressively looser readings, but never
    invent or drop an item -- a wrong count is returned as a failure so the
    caller can retry, because quietly accepting it would misalign the book.
    """
    body = text.strip()
    fence = re.search(r'```(?:json)?\s*(.*?)```', body, re.S)
    if fence:
        body = fence.group(1).strip()
    for candidate in (body, _first_array(body)):
        if not candidate:
            continue
        try:
            data = json.loads(candidate)
        except ValueError:
            continue
        if isinstance(data, list) and len(data) == want:
            return [_as_text(x) for x in data]
    numbered = _numbered_lines(body)
    if len(numbered) == want:
        return numbered
    raise TranslationError('Model returned %s blocks, expected %d'
                           % (len(numbered) or '?', want))


def _first_array(s):
    depth, start = 0, None
    for i, ch in enumerate(s):
        if ch == '[':
            if depth == 0:
                start = i
            depth += 1
        elif ch == ']' and depth:
            depth -= 1
            if depth == 0:
                return s[start:i + 1]
    return None


def _as_text(x):
    if isinstance(x, str):
        return x
    if isinstance(x, dict):
        for k in ('text', 'translation', 'target'):
            if k in x:
                return str(x[k])
    return str(x)


def _numbered_lines(s):
    out = []
    for line in s.splitlines():
        m = re.match(r'\s*(\d+)\s*[.)：:]\s*(.+)', line)
        if m:
            out.append(m.group(2).strip())
    return out


# --------------------------------------------------------------------------- #
# the run
# --------------------------------------------------------------------------- #

def estimate(payload, batch_size=20):
    blocks = payload['blocks']
    chars = sum(len(b['text']) for b in blocks)
    return {'blocks': len(blocks), 'chars': chars,
            'requests': (len(blocks) + batch_size - 1) // batch_size}


def _load_cache(path):
    if path and os.path.exists(path):
        try:
            with open(path, encoding='utf-8') as f:
                return {int(k): v for k, v in json.load(f).items()}
        except (ValueError, OSError):
            return {}
    return {}


def _save_cache(path, done):
    if not path:
        return
    tmp = path + '.tmp'
    with open(tmp, 'w', encoding='utf-8') as f:
        json.dump({str(k): v for k, v in done.items()}, f, ensure_ascii=False)
    os.replace(tmp, path)


def translate_payload(payload, provider, target_lang, batch_size=20,
                      cache_path=None, retries=3, on_progress=None):
    """Translate every block. Returns the list of translated strings.

    Resumes from cache_path if one is present, so an interrupted run costs only
    the blocks it had not reached.
    """
    blocks = payload['blocks']
    done = _load_cache(cache_path)
    if done and on_progress:
        on_progress('resuming: %d of %d blocks already translated'
                    % (len(done), len(blocks)))

    todo = [b for b in blocks if b['i'] not in done]
    system = SYSTEM.format(target=target_lang)

    for start in range(0, len(todo), batch_size):
        batch = todo[start:start + batch_size]
        texts = _translate_batch(batch, provider, system, retries, on_progress)
        for b, t in zip(batch, texts):
            done[b['i']] = t
        _save_cache(cache_path, done)
        if on_progress:
            on_progress('%d/%d blocks' % (len(done), len(blocks)))

    return [done[b['i']] for b in blocks]


def _translate_batch(batch, provider, system, retries, on_progress):
    """One batch, with the retry ladder: same size, then halves, then singles."""
    prompt = '\n\n'.join('[%d] %s' % (n + 1, b['text']) for n, b in enumerate(batch))
    last = None
    for attempt in range(retries):
        try:
            return parse_reply(provider.complete(system, prompt), len(batch))
        except TranslationError as e:
            last = e
            if on_progress:
                on_progress('retry %d/%d: %s' % (attempt + 1, retries, e))
            time.sleep(min(2 ** attempt, 8))

    if len(batch) > 1:
        # A whole batch failing is usually the model losing count, not the text
        # being untranslatable, so halve it rather than giving up.
        mid = len(batch) // 2
        return (_translate_batch(batch[:mid], provider, system, retries, on_progress)
                + _translate_batch(batch[mid:], provider, system, retries, on_progress))
    raise SystemExit('Could not translate block %d after %d attempts: %s'
                     % (batch[0]['i'], retries, last))


def provider_from_args(args):
    """Build a Provider from CLI args, falling back to the usual env vars."""
    key = (args.api_key
           or os.environ.get('BILINGUAL_API_KEY')
           or os.environ.get('OPENAI_API_KEY')
           or os.environ.get('ANTHROPIC_API_KEY') or '')
    base = args.base_url or os.environ.get('BILINGUAL_API_BASE') or None
    model = args.model or os.environ.get('BILINGUAL_MODEL') or ''
    return Provider(dialect=args.dialect, base_url=base, api_key=key, model=model,
                    timeout=args.timeout)


def progress_printer(quiet=False):
    def report(msg):
        if not quiet:
            print('  ' + msg, file=sys.stderr)
    return report
