# hide_console.py
import subprocess
_orig = subprocess.Popen
def _popen(*args, **kwargs):
    kwargs.setdefault('creationflags', subprocess.CREATE_NO_WINDOW)
    return _orig(*args, **kwargs)
subprocess.Popen = _popen
