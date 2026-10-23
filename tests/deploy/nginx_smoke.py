"""Test the real release on Debian Nginx, under CI's 1 CPU / 1 GiB limit."""
import gzip
import json
import os
from pathlib import Path
import signal
import socket
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request

repo = Path(__file__).resolve().parents[2]
with tempfile.TemporaryDirectory() as temporary:
    work = Path(temporary)
    work.chmod(0o755)
    root = work / 'site'
    subprocess.run([sys.executable, str(repo / 'deploy/site.py'), '--root', str(root),
                    'install', sys.argv[1]], check=True)
    with socket.socket() as listener:
        listener.bind(('127.0.0.1', 0))
        port = listener.getsockname()[1]
    site = (repo / 'deploy/nginx.conf').read_text().replace('__DOMAIN__', 'localhost')
    site = site.replace('listen 80;', f'listen 127.0.0.1:{port};').replace('listen [::]:80;', '')
    site = site.replace('/srv/n4ml/current', str(root / 'current'))
    config = work / 'nginx.conf'
    config.write_text(f'worker_processes 1;\npid {work}/nginx.pid;\nerror_log stderr;\n'
                      f'events {{ worker_connections 128; }}\nhttp {{ include /etc/nginx/mime.types; {site} }}\n')
    subprocess.run(['nginx', '-t', '-c', str(config)], check=True)
    server = subprocess.Popen(['nginx', '-c', str(config), '-g', 'daemon off;'])
    try:
        base = f'http://127.0.0.1:{port}'

        def get(path, headers=None):
            return urllib.request.urlopen(urllib.request.Request(base + path, headers=headers or {}), timeout=10)

        for attempt in range(50):
            try:
                with get('/healthz') as response:
                    assert response.read() == b'ok\n'
                break
            except urllib.error.URLError:
                if server.poll() is not None:
                    raise RuntimeError('Nginx exited during startup')
                time.sleep(0.1)
        else:
            raise RuntimeError('Nginx never became ready')
        for path in ('/', '/projects/mb4x-radio-archive/', '/projects/expeditionops/'):
            with get(path) as response:
                assert response.status == 200
                assert 'text/html' in response.headers['Content-Type']
                assert response.headers['Cache-Control'] == 'no-cache'
        with get('/release.json') as response:
            assert json.load(response)['commit']
        asset = next((root / 'current/assets').glob('*.js')).name
        with get('/assets/' + asset, {'Accept-Encoding': 'gzip'}) as response:
            assert response.headers['Content-Encoding'] == 'gzip'
            assert gzip.decompress(response.read()) == (root / 'current/assets' / asset).read_bytes()
            assert 'immutable' in response.headers['Cache-Control']
        with get('/data/contacts.json', {'Accept-Encoding': 'gzip'}) as response:
            assert len(json.loads(gzip.decompress(response.read()))['contacts']) == 4606
        for number in range(1, 9):
            with get(f'/audio/recording-{number:02}.mp3', {'Range': 'bytes=0-15'}) as response:
                assert response.status == 206
                assert response.headers['Content-Type'] == 'audio/mpeg'
                assert len(response.read()) == 16
                assert 'Content-Encoding' not in response.headers
        for path in ('/assets/missing.js', '/data/missing.json', '/audio/missing.mp3', '/unknown/'):
            try:
                get(path)
                raise AssertionError(f'Missing file did not return 404: {path}')
            except urllib.error.HTTPError as error:
                assert error.code == 404
        print('Debian Nginx: routes, caching, precompression, JSON, all 8 audio ranges, and 404s passed.')
    finally:
        os.kill(server.pid, signal.SIGQUIT)
        server.wait(timeout=10)
