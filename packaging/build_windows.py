"""Build Windows x64 NSIS setup on Windows, macOS or Linux using embedded CPython."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tarfile
import tempfile
import urllib.request
import zipfile

ROOT = Path(__file__).resolve().parents[1]
PYTHON_URL = 'https://www.python.org/ftp/python/3.13.13/python-3.13.13-embed-amd64.zip'
PYTHON_SHA = '8766a8775746235e23cf5aee5027ab1060bb981d93110577adcf3508aa0cbd55'
NSIS_URL = 'https://github.com/electron-userland/electron-builder-binaries/releases/download/nsis%402.0.2/nsis-bundle-3.12.tar.gz'
NSIS_SHA = '83d80ee578cb19008b2a99e4fccfb5e7c023cc9bb791eb38f6048fccc875f62c'


def fetch(url, checksum, target):
    if not target.exists():
        with urllib.request.urlopen(url, timeout=60) as response, target.open('wb') as out:
            shutil.copyfileobj(response, out)
    if hashlib.sha256(target.read_bytes()).hexdigest() != checksum:
        raise RuntimeError('Build dependency checksum mismatch: ' + target.name)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', type=Path, default=ROOT / 'release')
    parser.add_argument('--cache', type=Path, default=ROOT / 'build/downloads')
    args = parser.parse_args()
    output = args.output.resolve(); output.mkdir(parents=True, exist_ok=True)
    cache = args.cache.resolve(); cache.mkdir(parents=True, exist_ok=True)
    version = json.loads((ROOT / 'release.json').read_text())['version']
    pyzip = cache / 'python-3.13.13-embed-amd64.zip'; nsis = cache / 'nsis.tar.gz'
    fetch(PYTHON_URL, PYTHON_SHA, pyzip); fetch(NSIS_URL, NSIS_SHA, nsis)
    with tempfile.TemporaryDirectory(prefix='researchdesk-win-') as temp:
        temp = Path(temp); payload = temp / 'payload'; runtime = payload / 'runtime'; server = payload / 'server'
        runtime.mkdir(parents=True); server.mkdir()
        with zipfile.ZipFile(pyzip) as archive: archive.extractall(runtime)
        (runtime / 'python313._pth').write_text('python313.zip\n.\n../server\n../server/lib\nimport site\n')
        subprocess.run([sys.executable, '-m', 'pip', 'install', '--target', str(server / 'lib'), '--only-binary=:all:',
                        '--platform', 'win_amd64', '--python-version', '3.13', '--implementation', 'cp', '--abi', 'cp313',
                        '--no-compile', 'pypdf==6.10.0', 'typing_extensions==4.16.0',
                        '-r', str(ROOT / 'requirements-ocr.txt')], check=True)
        for name in ['app.py', 'knowledge.py', 'online_cases.py', 'briefs.py', 'literature.py', 'research.py',
                     'plugin_manager.py', 'updates.py', 'release.json', '.env.example', 'desktop_windows.pyw', 'ocr_windows.py']:
            shutil.copy2(ROOT / name, server / name)
        for name in ['static', 'plugins', 'licenses']:
            shutil.copytree(ROOT / name, server / name, ignore=shutil.ignore_patterns('__pycache__', '*.pyc'))
        # Reproducible, vetted tool archive; do not extract arbitrary user archives here.
        with tarfile.open(nsis) as archive: archive.extractall(temp / 'nsis', filter='data')
        bundle = temp / 'nsis/nsis-bundle'
        shutil.copy2(bundle / 'windows/COPYING', server / 'licenses/NSIS.txt')
        env = {**os.environ, 'NSISDIR': str(bundle / 'windows')}
        if sys.platform == 'win32':
            compiler = bundle / 'windows/makensis.exe'
            prefix = '/'
        else:
            compiler = bundle / 'makensis'
            compiler.chmod(0o755)
            prefix = '-'
        installer = output / f'ResearchDesk-{version}-windows-x64.exe'
        subprocess.run([str(compiler), prefix+'V3', prefix+'INPUTCHARSET', 'UTF8', prefix+'DVERSION='+version,
                        prefix+'DPAYLOAD_FILES='+str(payload / '*'), prefix+'DINSTALLER='+str(installer),
                        str(ROOT / 'packaging/windows.nsi')], check=True, env=env)
        print(installer)


if __name__ == '__main__': main()
