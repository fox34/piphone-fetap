#!/usr/bin/python3

"""
Hilfsskript für tests/test-webpage.js: HTML-Seite aus lib/webserver.py ausgeben
und Beispielwerte für /api/config erzeugen.

    python3 tests/render-page.py CONFIG_PAGE > /tmp/config.html
    python3 tests/render-page.py fixture        > tests/webpage-config.json
"""

from ast import literal_eval
from pathlib import Path
import re
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lib import config as configlib

if len(sys.argv) < 2:
    raise SystemExit(__doc__)

what = sys.argv[1]

if what == 'fixture':
    from json import dumps
    data = configlib.read(Path(__file__).resolve().parent.parent / 'support' / 'config-example.toml')
    print(dumps({
        'sections': configlib.describe(data),
        'mtime': 1700000000.0,
        'restart_required': False,
    }, ensure_ascii=False, indent=2))
    raise SystemExit(0)

source = (Path(__file__).resolve().parent.parent / 'lib' / 'webserver.py').read_text(encoding='utf-8')
match = re.search(rf'^{what} = """(.*?)"""$', source, re.S | re.M)
if match is None:
    raise SystemExit(f"Seite {what} nicht gefunden")

# Escape-Sequenzen der Python-Zeichenkette auflösen, damit die Seite exakt so
# ausgegeben wird, wie der Webserver sie ausliefert
print(literal_eval(f'"""{match.group(1)}"""'))