#!/usr/bin/python3

"""
Einmaliges Migrationsskript: Konvertiert eine alte INI-Konfiguration nach TOML.

Aufruf (z.B. auf dem Telefon):

    python3 support/convert-config.py /boot/piphone/config.ini /boot/piphone/config.toml

Anschließend die TOML-Datei prüfen und ggf. Kommentare ergänzen.
"""

from argparse import ArgumentParser
from configparser import ConfigParser
from pathlib import Path
import re
import sys
import tomllib

# INI-Sektion -> TOML-Tabelle
SECTIONS = {
    'Network': 'network',
    'SIP': 'sip',
    'Pins': 'pins',
    'Numbers': 'numbers',
    'Ringtones': 'ringtones',
    'Sounds': 'sounds',
    'Misc': 'misc',
    'Web': 'web',
}

# Komma-getrennte INI-Werte -> TOML-Listen
LISTS = {
    'sleep_music',
    'wake_up_times',
}

# Kommentare für Werte, die beim Konvertieren ihre Bedeutung ändern
COMMENTS = {
    'sleep_music': 'Mehrere Dateien werden in zufälliger Reihenfolge abgespielt.',
    'wake_up_times': 'Uhrzeiten zum Aufstehen: Mo, Di, Mi, Do, Fr, Sa, So',
}

# Die INI-Datei kennt keine Datentypen, alle Werte sind Zeichenketten. TOML dagegen -
# deshalb wird nur diesen Optionen ein Typ zugewiesen. Alle anderen Werte bleiben
# Zeichenketten, damit z.B. das SIP-Passwort "4711" nicht zur Zahl 4711 wird.
BOOLS = {
    'whitelist_active',
}

INTS = {
    'dial_timeout', 'dnd_from', 'dnd_to', 'max_call_duration',
    'nsi', 'nsa', 'gabel',
    'night_light_pin', 'wake_light_pin',
    'port',
}

FLOATS = {
    'night_light_duty', 'wake_light_duty',
}

# TOML-Zahlen dürfen keine führenden Nullen haben, sonst sind Rufnummern wie 01234567
# nicht von Zahlen zu unterscheiden - solche Werte bleiben daher Zeichenketten.
INTEGER = re.compile(r'[+-]?(0|[1-9][0-9]*)')
FLOAT = re.compile(r'[+-]?(0|[1-9][0-9]*)?(\.[0-9]+)([eE][+-]?[0-9]+)?|[+-]?(0|[1-9][0-9]*)[eE][+-]?[0-9]+')


def is_float(value: str) -> bool:
    """Prüft, ob der Wert als TOML-Zahl mit Punkt oder Exponent geschrieben werden kann"""
    return bool(FLOAT.fullmatch(value))


def strip_quotes(value: str) -> str:
    """Anführungszeichen entfernen, die in der INI-Datei von Hand mitgeschrieben wurden"""
    if len(value) > 1 and value[0] == value[-1] and value[0] in ('"', "'"):
        return value[1:-1]
    return value


def toml_key(key: str) -> str:
    """TOML-Schlüssel: In Anführungszeichen, sofern kein einfacher Schlüssel möglich ist"""
    if re.fullmatch('[A-Za-z_][A-Za-z0-9_-]*', key):
        return key
    return '"' + key.replace('\\', '\\\\').replace('"', '\\"') + '"'


def toml_string(value: str) -> str:
    """Zeichenkette in TOML-Schreibweise"""
    return '"' + value.replace('\\', '\\\\').replace('"', '\\"') + '"'


def encode(value: str, key: str) -> tuple[str, object]:
    """INI-Wert in TOML-Schreibweise und erwarteten Python-Wert umwandeln"""
    if value == '':
        return '""', ''

    if key in BOOLS and value.lower() in ('true', 'yes', 'on', 'false', 'no', 'off'):
        return ('true' if value.lower() in ('true', 'yes', 'on') else 'false'), \
            value.lower() in ('true', 'yes', 'on')

    if key in INTS and INTEGER.fullmatch(value):
        return value, int(value)

    if key in FLOATS:
        if INTEGER.fullmatch(value):
            return value, int(value)
        if is_float(value):
            return value, float(value)

    if key in BOOLS | INTS | FLOATS:
        print(f"Warnung: {key} = {value} hat nicht den erwarteten Typ, wird als Zeichenkette geschrieben.")

    return toml_string(value), value


def encode_list(value: str) -> tuple[str, list]:
    """Kommagetrennten INI-Wert in TOML-Liste und erwartete Python-Liste umwandeln"""
    items = [strip_quotes(item.strip()) for item in value.split(',')]
    return '[' + ', '.join(toml_string(item) for item in items) + ']', items


def convert(source: Path, target: Path, force: bool) -> None:
    """INI-Datei einlesen und als TOML-Datei schreiben"""

    if target.exists() and not force:
        sys.exit(f"{target} existiert bereits. Mit --force überschreiben oder Zieldatei erst löschen.")

    config = ConfigParser()
    if not config.read(source, encoding='utf-8'):
        sys.exit(f"Konfigurationsdatei {source} nicht gefunden oder nicht lesbar.")

    lines = [
        '# Konvertiert von support/convert-config.py aus einer INI-Konfiguration.',
        '# Die Kommentare der Originaldatei sind dabei verloren gegangen.',
    ]
    expected = {}

    for section in config.sections():
        table = SECTIONS.get(section, section.lower())
        lines += ['', f'[{table}]']
        expected[table] = {}

        for option in config[section]:
            key = strip_quotes(option.strip())
            value = strip_quotes(config[section][option].strip())

            if key in LISTS:
                literal, expected[table][key] = encode_list(value)
                lines.append(f'# {COMMENTS[key]}')
            else:
                literal, expected[table][key] = encode(value, key)

            lines.append(f'{toml_key(key)} = {literal}')

    target.write_text('\n'.join(lines) + '\n', encoding='utf-8')

    # Kontrollieren, ob die erzeugte Datei gültiges TOML ist und alle Werte übernommen wurden
    with target.open('rb') as target_file:
        converted = tomllib.load(target_file)

    wrong = [
        f'[{table}] {key}'
        for table, options in expected.items()
        for key, value in options.items()
        if converted.get(table, {}).get(key) != value
    ]

    if wrong:
        sys.exit(f"Konvertierung fehlgeschlagen, bitte manuell prüfen: {', '.join(wrong)}")

    print(f"{source} -> {target} konvertiert. Bitte prüfen.")


if __name__ == '__main__':
    parser = ArgumentParser(description=__doc__.splitlines()[1])
    parser.add_argument('source', type=Path, help='Pfad zur INI-Konfiguration (alt)')
    parser.add_argument('target', type=Path, help='Pfad zur TOML-Konfiguration (neu)')
    parser.add_argument('--force', action='store_true', help='Zieldatei überschreiben')
    args = parser.parse_args()
    convert(args.source, args.target, args.force)