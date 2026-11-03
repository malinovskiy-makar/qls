"""Read-only HTTP smoke inside web container. Loopback only; never sends mail or bot messages."""
import argparse
import http.client
import json
from pathlib import Path
import re


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--port', type=int, default=8000)
    parser.add_argument('--variants', type=Path, required=True)
    args = parser.parse_args()
    manifest = json.loads((args.variants/'variants-manifest.json').read_text())
    assert len(manifest) == 33
    urls = ['/vp/', '/vp/variants/', '/vp/format/', '/login/', '/register/', '/health/']
    urls += ['/vp/'+Path(row['path']).stem+'/' for row in manifest]
    assets = set()
    def get(path, secure=True):
        con = http.client.HTTPConnection('127.0.0.1', args.port, timeout=30)
        headers = {'Host': 'localhost'}
        if secure:
            headers['X-Forwarded-Proto'] = 'https'
        con.request('GET', path, headers=headers)
        response = con.getresponse()
        result = response.status, dict(response.getheaders()), response.read()
        con.close()
        return result
    status, headers, _ = get('/vp/', False)
    assert status in (301, 302) and headers['Location'].startswith('https://')
    for path in urls:
        status, _, body = get(path)
        assert status == 200, (path, status)
        text = body.decode()
        assets.update(re.findall(r'(?:src|href)=["\x27](/static/[^"\x27?#]+)', text))
        if path == '/health/':
            assert json.loads(text)['status'] == 'ok'
    for path in sorted(assets):
        status, _, body = get(path)
        assert status == 200 and body, (path, status)
    print(json.dumps({'status': 'PASS', 'pages': len(urls), 'static_assets': len(assets), 'https_redirect': True}))


if __name__ == '__main__':
    main()
