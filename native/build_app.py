"""Compatibility entry point for the self-contained distribution builder."""
import runpy
from pathlib import Path
runpy.run_path(str(Path(__file__).resolve().parents[1]/"packaging/build_macos.py"),run_name="__main__")
