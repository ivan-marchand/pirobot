import sys
import os

# apt-installed packages (picamera2, libcamera) have no dist-info metadata
# and cannot be bundled by PyInstaller. Add the system Python package paths
# so they are importable at runtime from the host system.
_sys_paths = [
    '/usr/lib/python3/dist-packages',
    '/usr/lib/python3.9/dist-packages',
]
for _p in _sys_paths:
    if os.path.isdir(_p) and _p not in sys.path:
        sys.path.append(_p)
