# Keihäänheitto-palvelin. Pelkkä Python-standardikirjasto.
# Render: python app.py   |   Paikallisesti (esim. Pydroid): python app.py -> http://localhost:8765
import os, re, json, time, base64, secrets, threading, mimetypes, urllib.request, urllib.error
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler

BASE = os.path.dirname(os.path.abspath(__file__))
STATIC = os.path.join(BASE, 'static')
PORT = int(os.environ.get('PORT', 8765))
TOKEN = os.environ.get('GITHUB_TOKEN', '').strip()
REPO = os.environ.get('GITHUB_REPO', '').strip()          # esim. "kayttaja/keihaanheitto"
BRANCH = os.environ.get('GITHUB_BRANCH', 'scores').strip()  # oma haara, ettei Render deployaa joka tuloksesta
FPATH = os.environ.get('GITHUB_PATH', 'scores.json').strip()
LOCAL = os.path.join(BASE, 'scores_local.json')            # käytetään, jos GITHUB_TOKEN puuttuu
KEEP = 20
USE_GH = bool(TOKEN and REPO)
LOCK = threading.Lock()
cache = {'t': 0, 'data': {'items': []}}


def gh(method, url, body=None):
    req = urllib.request.Request('https://api.github.com' + url, method=method,
                                 data=json.dumps(body).encode() if body is not None else None)
    req.add_header('Authorization', 'Bearer ' + TOKEN)
    req.add_header('Accept', 'application/vnd.github+json')
    req.add_header('X-GitHub-Api-Version', '2022-11-28')
    req.add_header('User-Agent', 'keihaanheitto')
    if body is not None:
        req.add_header('Content-Type', 'application/json')
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            return r.status, json.loads(r.read() or b'null')
    except urllib.error.HTTPError as e:
        try:
            d = json.loads(e.read())
        except Exception:
            d = None
        return e.code, d


def ensure_branch():
    s, _ = gh('GET', f'/repos/{REPO}/git/ref/heads/{BRANCH}')
    if s == 200:
        return
    s, r = gh('GET', f'/repos/{REPO}')
    default = r['default_branch']
    s, r = gh('GET', f'/repos/{REPO}/git/ref/heads/{default}')
    s, r = gh('POST', f'/repos/{REPO}/git/refs', {'ref': 'refs/heads/' + BRANCH, 'sha': r['object']['sha']})
    print('Haara luotu:', BRANCH, s)


def load():
    if not USE_GH:
        try:
            with open(LOCAL, encoding='utf-8') as f:
                return json.load(f), None
        except Exception:
            return {'items': []}, None
    s, r = gh('GET', f'/repos/{REPO}/contents/{FPATH}?ref={BRANCH}')
    if s == 404:
        return {'items': []}, None
    if s != 200:
        raise RuntimeError(f'GitHub lukuvirhe {s}: {r}')
    return json.loads(base64.b64decode(r['content']).decode('utf-8')), r['sha']


def store(data, sha):
    raw = json.dumps(data, ensure_ascii=False, separators=(',', ':'))
    if not USE_GH:
        with open(LOCAL, 'w', encoding='utf-8') as f:
            f.write(raw)
        return True
    body = {'message': 'Päivitä ennätykset', 'branch': BRANCH,
            'content': base64.b64encode(raw.encode('utf-8')).decode()}
    if sha:
        body['sha'] = sha
    s, r = gh('PUT', f'/repos/{REPO}/contents/{FPATH}', body)
    if s not in (200, 201):
        print('GitHub kirjoitusvirhe', s, r)
    return s in (200, 201)


BAD = re.compile(r'[<>&"\'`\\]')
def txt(v, n):
    return BAD.sub('', str(v)).strip()[:n]


def clean(e):
    R = float(e['R'])
    if not 0 < R <= 100:
        raise ValueError('R')
    k = e.get('k')
    if k not in ('p', 0, 1, 2, 3):
        raise ValueError('k')
    N = float(e.get('N', 25))
    df = float(e.get('df', 1))
    o = {'id': re.sub(r'[^\w-]', '', str(e.get('id', '')))[:20] or secrets.token_hex(5),
         'n': txt(e.get('n', ''), 14) or 'Pelaaja', 'R': round(R, 2), 'k': k,
         'N': N, 'df': df, 'std': (N == 25 and df == 1), 'd': txt(e.get('d', ''), 30), 'ts': int(time.time())}
    for f in ('a', 'tot', 'dl'):
        if e.get(f) is not None:
            o[f] = round(float(e[f]), 2)
    if isinstance(e.get('c'), list):
        o['c'] = [int(x) for x in e['c'][:5]]
    if isinstance(e.get('errs'), list):
        o['errs'] = [round(float(x), 1) for x in e['errs'][:3]]
    if isinstance(e.get('w'), dict):
        o['w'] = {f: round(float(e['w'][f]), 2) for f in ('s', 'h', 'c')}
    if isinstance(e.get('L'), dict):
        o['L'] = {txt(a, 24): round(float(b), 2) for a, b in list(e['L'].items())[:8]}
    return o


def add_score(e):
    with LOCK:
        for _ in range(4):
            data, sha = load()
            items = data.setdefault('items', [])
            if any(x.get('id') == e['id'] for x in items):
                return 'dup'
            grp = [x for x in items if bool(x.get('std')) == e['std'] and x.get('k') == e['k']]
            if len(grp) >= KEEP and e['R'] <= min(x['R'] for x in grp):
                return 'low'          # ei top 20:ssä -> ei turhaa commitia
            items.append(e)
            cnt, keep = {}, []
            for x in sorted(items, key=lambda x: -x['R']):
                key = (bool(x.get('std')), x.get('k'))
                cnt[key] = cnt.get(key, 0) + 1
                if cnt[key] <= KEEP:
                    keep.append(x)
            data['items'] = keep
            if store(data, sha):
                cache.update(t=time.time(), data=data)
                return 'ok'
            time.sleep(.6)
    raise RuntimeError('tallennus epäonnistui')


def get_scores():
    if time.time() - cache['t'] < 20:
        return cache['data']
    with LOCK:
        try:
            data, _ = load()
            cache.update(t=time.time(), data=data)
        except Exception as ex:
            print('Latausvirhe:', ex)
    return cache['data']


class Hd(BaseHTTPRequestHandler):
    def send(self, code, body, ct, cc='no-store'):
        self.send_response(code)
        self.send_header('Content-Type', ct)
        self.send_header('Content-Length', str(len(body)))
        self.send_header('Cache-Control', cc)
        self.end_headers()
        if self.command != 'HEAD':
            self.wfile.write(body)

    def js(self, code, obj):
        self.send(code, json.dumps(obj, ensure_ascii=False).encode('utf-8'), 'application/json; charset=utf-8')

    def do_HEAD(self):
        self.do_GET()

    def do_GET(self):
        p = self.path.split('?')[0]
        if p == '/healthz':
            return self.send(200, b'ok', 'text/plain')
        if p == '/scores':
            return self.js(200, get_scores())
        name = 'index.html' if p == '/' else os.path.basename(p)
        fp = os.path.join(STATIC, name)
        if not os.path.isfile(fp):
            return self.send(404, b'404', 'text/plain')
        with open(fp, 'rb') as f:
            b = f.read()
        ct = 'application/manifest+json' if name == 'manifest.json' else (mimetypes.guess_type(name)[0] or 'application/octet-stream')
        if ct.startswith('text/') or ct.endswith('javascript') or ct.endswith('json'):
            ct += '; charset=utf-8'
        cc = 'no-cache' if name in ('index.html', 'sw.js', 'manifest.json') else 'public, max-age=86400'
        self.send(200, b, ct, cc)

    def do_POST(self):
        if self.path.split('?')[0] != '/score':
            return self.send(404, b'404', 'text/plain')
        try:
            n = int(self.headers.get('Content-Length', 0))
            if n > 20000:
                raise ValueError('iso')
            e = clean(json.loads(self.rfile.read(n)))
        except Exception:
            return self.js(400, {'ok': False})
        try:
            self.js(200, {'ok': True, 'status': add_score(e)})
        except Exception as ex:
            print('Tallennusvirhe:', ex)
            self.js(503, {'ok': False})

    def log_message(self, *a):
        pass


if __name__ == '__main__':
    if USE_GH:
        try:
            ensure_branch()
        except Exception as ex:
            print('Haaran tarkistus epäonnistui:', ex)
    print('Tallennus:', f'GitHub {REPO}@{BRANCH}/{FPATH}' if USE_GH else 'paikallinen tiedosto ' + LOCAL)
    print(f'Peli käynnissä portissa {PORT}')
    ThreadingHTTPServer(('0.0.0.0', PORT), Hd).serve_forever()
