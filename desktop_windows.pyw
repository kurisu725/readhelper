"""Windows launcher for the embedded Python distribution. One service per user session."""
import ctypes
import os
from pathlib import Path
import sys
import traceback
import urllib.request
import webbrowser

ROOT = Path(__file__).resolve().parent
SUPPORT = Path(os.environ['LOCALAPPDATA']) / 'ResearchDesk'
SUPPORT.mkdir(parents=True, exist_ok=True)
os.environ.setdefault('PAPER_DATA_DIR', str(SUPPORT / 'data'))
os.environ.setdefault('PAPER_CONFIG_FILE', str(SUPPORT / '.env'))
os.environ['PAPER_NATIVE'] = '1'
sys.path.insert(0, str(ROOT))
sys.stdout = sys.stderr = (SUPPORT / '运行日志.txt').open('a', encoding='utf-8', buffering=1)
kernel = ctypes.WinDLL('kernel32', use_last_error=True)
kernel.CreateMutexW.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_wchar_p]
kernel.CreateMutexW.restype = ctypes.c_void_p
mutex = kernel.CreateMutexW(None, False, 'Local\\ResearchDesk')
ready = SUPPORT / 'ready.txt'


def main():
    if ctypes.get_last_error() == 183:
        try:
            url = ready.read_text(encoding='utf-8')
            if not url.startswith('http://127.0.0.1:'):
                raise ValueError()
            with urllib.request.urlopen(url + '/api/settings', timeout=3):
                webbrowser.open(url)
        except Exception:
            ctypes.windll.user32.MessageBoxW(None, '研读助手正在启动，请稍后再试。', '研读助手', 0)
        return
    ready.unlink(missing_ok=True)
    import app
    sys.argv = [str(ROOT / 'app.py'), '--port', '0', '--ready-file', str(ready)]
    app.main()


if __name__ == '__main__':
    try:
        main()
    except Exception:
        traceback.print_exc()
        ctypes.windll.user32.MessageBoxW(None, '启动失败，请查看本机资料目录中的运行日志。\n' + str(SUPPORT), '研读助手', 0)
