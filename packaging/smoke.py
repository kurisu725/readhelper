"""Run a packaged server in isolated storage and exercise its HTTP/plugin API."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import tempfile
import time
import urllib.request


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('command', nargs=argparse.REMAINDER)
    args = parser.parse_args()
    with tempfile.TemporaryDirectory(prefix='researchdesk-smoke-') as root:
        root = Path(root); ready = root / 'ready.txt'
        env = {**os.environ, 'PAPER_DATA_DIR': str(root / 'data'), 'PAPER_CONFIG_FILE': str(root / '.env'),
               'PAPER_API_KEY': '', 'OPENAI_API_KEY': '', 'PYTHONUTF8': '1'}
        with (root / 'log.txt').open('w') as log:
            process = subprocess.Popen(args.command + ['--port', '0', '--no-browser', '--ready-file', str(ready)],
                                       env=env, stdout=log, stderr=log)
            try:
                for _ in range(150):
                    if ready.exists(): break
                    if process.poll() is not None: raise RuntimeError((root / 'log.txt').read_text())
                    time.sleep(.2)
                url = ready.read_text()
                def request(path, data=None):
                    req = urllib.request.Request(url + path, data=json.dumps(data).encode() if data is not None else None,
                        headers={'X-Requested-With': 'ResearchDesk', 'Content-Type': 'application/json'})
                    with urllib.request.urlopen(req, timeout=10) as response:
                        return response.read()
                assert b'<html' in request('/')
                state = json.loads(request('/api/state'))
                assert state['config']['research_mode'] == 'general'
                assert not state['config']['has_key']
                assert b'initExtensions' in request('/extensions.js')
                request('/api/plugins/architecture-history', {'enabled': True})
                assert b'initHistory' in request('/plugins/architecture-history/history.js')
                assert json.loads(request('/api/history'))['records'] == []
                request('/api/research-mode', {'mode': 'history'})
                request('/api/plugins/architecture-history', {'enabled': False})
                assert json.loads(request('/api/settings'))['research_mode'] == 'general'
                assert json.loads(request('/api/updates'))['version']
                request('/api/quit', {})
                process.wait(timeout=10)
                assert process.returncode == 0
                print('Packaged server smoke check passed: startup, assets, isolated data, plugin activation, mode, shutdown.')
            finally:
                if process.poll() is None:
                    process.terminate(); process.wait(timeout=10)


if __name__ == '__main__': main()
