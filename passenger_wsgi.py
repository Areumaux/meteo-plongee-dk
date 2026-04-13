import os
import sys
import glob

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# Activate the .venv virtualenv so Passenger finds Flask and other deps.
_venv = os.path.join(BASE_DIR, ".venv")
_site_pkgs = glob.glob(os.path.join(_venv, "lib", "python*", "site-packages"))
for _sp in _site_pkgs:
    if _sp not in sys.path:
        sys.path.insert(0, _sp)

if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from app import app as application  # noqa: E402

