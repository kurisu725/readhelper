"""Build a self-contained native macOS application and DMG on a macOS builder."""
import argparse
import json
import os
from pathlib import Path
import platform
import plistlib
import shutil
import subprocess
import sys
import sysconfig
import tempfile
from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[1]


def run(*args, **kwargs):
    subprocess.run(list(map(str, args)), check=True, **kwargs)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', type=Path, default=ROOT / 'release')
    args = parser.parse_args()
    output = args.output.resolve(); output.mkdir(parents=True, exist_ok=True)
    version = json.loads((ROOT / 'release.json').read_text())['version']
    arch = 'arm64' if platform.machine() == 'arm64' else 'x86_64'
    label = 'arm64' if arch == 'arm64' else 'x64'
    with tempfile.TemporaryDirectory(prefix='researchdesk-build-') as temp:
        temp = Path(temp)
        ocr = temp / 'ocr_macos'
        run('xcrun', 'swiftc', '-O', '-swift-version', '5', '-target', arch + '-apple-macosx14.0',
            '-framework', 'Cocoa', '-framework', 'PDFKit', '-framework', 'Vision', ROOT / 'native/OCR.swift', '-o', ocr)
        command = [sys.executable, '-m', 'PyInstaller', '--noconfirm', '--clean', '--onedir', '--name', 'ResearchDeskServer',
                   '--distpath', str(temp / 'dist'), '--workpath', str(temp / 'build'), '--specpath', str(temp),
                   '--add-data', str(ROOT / 'static') + ':static', '--add-data', str(ROOT / 'plugins') + ':plugins',
                   '--add-data', str(ROOT / 'release.json') + ':.', '--add-data', str(ROOT / '.env.example') + ':.',
                   '--add-binary', str(ocr) + ':.', '--collect-data', 'pypdf', str(ROOT / 'app.py')]
        run(*command, cwd=ROOT)
        bundle = temp / 'stage/研读助手.app'
        contents = bundle / 'Contents'; resources = contents / 'Resources'; binary = contents / 'MacOS'
        binary.mkdir(parents=True); resources.mkdir()
        shutil.copytree(temp / 'dist/ResearchDeskServer', resources / 'server')
        shutil.copy2(ROOT / '.env.example', resources / 'server/.env.example')
        shutil.copytree(ROOT / 'licenses', resources / 'licenses')
        for candidate in [Path(sysconfig.get_path('stdlib')) / 'LICENSE.txt', Path(sys.base_prefix) / 'LICENSE.txt']:
            if candidate.is_file():
                shutil.copy2(candidate, resources / 'licenses/Python.txt'); break
        run('xcrun', 'swiftc', '-O', '-swift-version', '5', '-target', arch + '-apple-macosx14.0',
            '-framework', 'Cocoa', '-framework', 'WebKit', '-framework', 'UniformTypeIdentifiers',
            ROOT / 'native/ResearchDesk.swift', '-o', binary / 'ResearchDesk')
        image = Image.new('RGBA', (1024, 1024), (0, 0, 0, 0)); draw = ImageDraw.Draw(image)
        draw.rounded_rectangle((28, 28, 996, 996), radius=218, fill='#2b5546')
        draw.line([(512,330),(454,292),(382,275),(258,278),(258,710),(365,704),(437,723),(512,768),
                   (587,723),(659,704),(766,710),(766,278),(642,275),(570,292),(512,330),(512,768)],
                  fill='#f3f3de', width=27, joint='curve')
        image.save(resources / 'AppIcon.icns')
        info = dict(CFBundleName='研读助手', CFBundleDisplayName='研读助手', CFBundleIdentifier='local.researchdesk.reader',
                    CFBundleExecutable='ResearchDesk', CFBundlePackageType='APPL', CFBundleShortVersionString=version,
                    CFBundleVersion=version, CFBundleIconFile='AppIcon', LSMinimumSystemVersion='14.0',
                    NSHighResolutionCapable=True, NSAppTransportSecurity={'NSAllowsLocalNetworking': True})
        with (contents / 'Info.plist').open('wb') as handle:
            plistlib.dump(info, handle)
        for attribute in ('com.apple.ResourceFork', 'com.apple.FinderInfo'):
            subprocess.run(['xattr', '-dr', attribute, str(bundle)], stderr=subprocess.DEVNULL)
        run('codesign', '--force', '--deep', '--sign', '-', bundle)
        run('codesign', '--verify', '--deep', '--strict', bundle)
        (bundle.parent / 'Applications').symlink_to('/Applications')
        dmg = output / f'ResearchDesk-{version}-macos-{label}.dmg'
        run('hdiutil', 'create', '-ov', '-format', 'UDZO', '-volname', '研读助手 ' + version,
            '-srcfolder', bundle.parent, dmg)
        delivery = output / '研读助手.app'
        if delivery.exists(): shutil.rmtree(delivery)
        shutil.copytree(bundle, delivery, symlinks=True)
        print(dmg)


if __name__ == '__main__': main()
