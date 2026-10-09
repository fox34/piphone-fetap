#!/usr/bin/python3

"""
Test für das Schreiben der Konfigurationsdatei (lib/config.py und save_config
in piphone.py). Läuft ohne Hardware und ohne RPi.GPIO.

    python3 tests/test-config.py
"""

import sys
import tomllib
from copy import deepcopy
from pathlib import Path
from tempfile import TemporaryDirectory

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lib import config as configlib

EXAMPLE = Path(__file__).resolve().parent.parent / 'support' / 'config-example.toml'

OK = 0
FAILED = 0


def check(label: str, condition: bool, detail: str = '') -> None:
    global OK, FAILED
    if condition:
        OK += 1
        print(f"  ok  {label}")
    else:
        FAILED += 1
        print(f"FAIL  {label} {detail}")


def test_roundtrip() -> dict:
    print("Beispielkonfiguration einlesen und wieder schreiben")
    original = configlib.read(EXAMPLE)

    cleaned, errors = configlib.validate(original)
    check('Beispielkonfiguration ist gültig', not errors, str(errors))

    text = configlib.dump(cleaned)
    check('geschriebenes TOML ist lesbar', tomllib.loads(text) == cleaned)

    check('Kommentare vorhanden', text.count('# ') > 30, str(text.count('# ')))
    check('Kommentar je Option', '# GPIO-Pin für Nachtlicht (0 = deaktiviert).' in text)
    check('Kopfzeile mit Hinweis', 'selbst geschriebene Kommentare werden dabei nicht beibehalten' in text)
    check('Abschnitte in Reihenfolge',
          [line for line in text.splitlines() if line.startswith('[')] ==
          ['[network]', '[sip]', '[pins]', '[numbers]', '[ringtones]', '[sounds]', '[misc]', '[web]'])
    check('Kurzwahlen in Anführungszeichen', '"01" = "01234567"' in text)
    check('Uhrzeiten als Liste',
          'wake_up_times = ["06:30", "06:30", "06:30", "06:30", "06:30", "07:30", "07:30"]' in text)

    return original


def test_defaults(original: dict) -> None:
    print("Standardwerte")
    empty, errors = configlib.validate({})
    check('Pflichtfelder als Fehler gemeldet',
          set(errors) == {'sip.host', 'sip.user', 'sip.pass', 'pins.nsi', 'pins.nsa', 'pins.gabel'}, str(errors))
    check('Wähl-Timeout als Standardwert', empty['sip']['dial_timeout'] == 60)
    check('Webserver standardmäßig aus', empty['web']['port'] == 0)
    check('Whitelist standardmäßig aus', empty['sip']['whitelist_active'] is False)
    check('Aufstehzeiten standardmäßig leer', empty['misc']['wake_up_times'] == [])
    check('Nachtlicht standardmäßig aus', empty['misc']['night_light_pin'] == 0)
    check('Einschlafmusik standardmäßig leer', empty['sounds']['sleep_music'] == [])

    print("Werte aus der Oberfläche übernehmen")
    cleaned, errors = configlib.validate(original)
    check('Zahlen aus dem Formular werden Ganzzahlen',
          cleaned['sip']['dial_timeout'] == 60 and isinstance(cleaned['sip']['dial_timeout'], int))
    check('Checkbox wird zu Boolean', cleaned['sip']['whitelist_active'] is False)
    check('Textfelder bleiben Text',
          cleaned['sip']['pass'] == 'test' and cleaned['ringtones']['08912345'].endswith('.wav'))
    check('Helligkeit bleibt Ganzzahl', cleaned['misc']['night_light_duty'] == 50
          and isinstance(cleaned['misc']['night_light_duty'], int))
    check('Listen werden zu Python-Listen',
          isinstance(cleaned['misc']['wake_up_times'], list)
          and isinstance(cleaned['sounds']['sleep_music'], list))


def test_validation() -> None:
    print("Eingabeprüfung")
    base = {'sip': {'host': 'h', 'user': 'u', 'pass': 'p'},
            'pins': {'nsi': '23', 'nsa': '24', 'gabel': '15'}}

    def errors_of(**sections):
        merged = {name: dict(values) for name, values in base.items()}
        for name, values in sections.items():
            merged.setdefault(name, {}).update(values)
        return configlib.validate(merged)[1]

    check('gültige Mindestangabe wird akzeptiert', not configlib.validate(base)[1])

    check('leeres Pflichtfeld abgelehnt', errors_of(sip={'host': ''}) == {'sip.host': 'Pflichtangabe'})
    check('Text in Zahlenfeld abgelehnt',
          errors_of(pins={'nsi': 'abc'}) == {'pins.nsi': 'muss eine ganze Zahl sein'})
    check('GPIO-Pin außerhalb des Bereichs abgelehnt',
          errors_of(pins={'nsa': '28'}) == {'pins.nsa': 'darf nicht größer als 27 sein'})
    check('negative Stunde abgelehnt',
          'sip.dnd_from' in errors_of(sip={'dnd_from': '-1'}))
    check('Stunde 24 abgelehnt', 'sip.dnd_from' in errors_of(sip={'dnd_from': '24'}))
    check('Stunde 23 erlaubt', not errors_of(sip={'dnd_from': '23'}))
    check('Checkbox-Schalterwerte akzeptiert',
          not errors_of(sip={'whitelist_active': 'ja'})
          and configlib.validate({**base, 'sip': {**base['sip'], 'whitelist_active': 'an'}})[0]['sip']['whitelist_active'] is True)
    check('Unsinnige Checkbox abgelehnt',
          'sip.whitelist_active' in errors_of(sip={'whitelist_active': 'vielleicht'}))
    check('Port außerhalb des Bereichs abgelehnt', 'web.port' in errors_of(web={'port': '70000'}))
    check('Helligkeit über 100 abgelehnt', 'misc.night_light_duty' in errors_of(misc={'night_light_duty': '120'}))
    check('Dezimalwert bei Helligkeit erlaubt',
          not errors_of(misc={'night_light_duty': '33.5'}))
    check('Passwort bleibt auch Ziffernfolge Text',
          not errors_of(sip={'pass': '4711'})
          and configlib.validate({**base, 'sip': {'pass': '4711'}})[0]['sip']['pass'] == '4711')

    print("Listen")
    seven = ['06:30', '06:30', '06:30', '06:30', '06:30', '07:30', '07:30']
    check('7 Uhrzeiten akzeptiert', not errors_of(misc={'wake_up_times': seven}))
    check('6 Uhrzeiten abgelehnt', 'misc.wake_up_times' in errors_of(misc={'wake_up_times': seven[:6]}))
    check('8 Uhrzeiten abgelehnt', 'misc.wake_up_times' in errors_of(misc={'wake_up_times': seven + ['07:30']}))
    check('Uhrzeit ohne führende Null abgelehnt',
          'misc.wake_up_times' in errors_of(misc={'wake_up_times': ['6:30'] + seven[1:]}))
    check('Uhrzeit 25 Uhr abgelehnt',
          'misc.wake_up_times' in errors_of(misc={'wake_up_times': ['25:00'] + seven[1:]}))
    check('leere Schlafliedliste akzeptiert', not errors_of(sounds={'sleep_music': []}))
    check('mehrere Schlaflieder akzeptiert', not errors_of(sounds={'sleep_music': ['/a.mp3', '/b.mp3']}))

    print("Kurzwahlen")
    check('Kurzwahl mit führender Null akzeptiert', not errors_of(numbers={'01': '01234567'}))
    check('Kurzwahl bis 5 Ziffern akzeptiert', not errors_of(numbers={'12345': '0123'}))
    check('6-stellige Kurzwahl abgelehnt', 'numbers.123456' in errors_of(numbers={'123456': '0123'}))
    check('Kurzwahl mit Buchstaben abgelehnt', 'numbers.ab' in errors_of(numbers={'ab': '0123'}))
    check('beliebige Kurzbefehle akzeptiert',
          not errors_of(numbers={'11': 'enable-night-mode', '12': 'play-sleep-music',
                                 '18': 'reboot', '19': 'shutdown',
                                 '21': 'test-loudspeaker', '22': 'test-earpiece'}))
    check('unbekannter Befehl als Rufnummer behandelt',
          not errors_of(numbers={'01': '01234567'})
          and configlib.validate({**base, 'numbers': {'01': '01234567'}})[0]['numbers']['01'] == '01234567')
    check('Freitext abgelehnt', 'numbers.01' in errors_of(numbers={'01': 'Hallo Welt'}))
    check('Rufnummer mit Länderpräfix akzeptiert',
          not errors_of(numbers={'01': '+49 89 1234567', '02': '0049891234567'}))
    check('leeres Ziel abgelehnt', 'numbers.01' in errors_of(numbers={'01': '  '}))

    print("Klingeltöne")
    check('Klingelton akzeptiert', not errors_of(ringtones={'0891234': '/opt/ring.wav'}))
    check('Klingelton ohne Datei abgelehnt', 'ringtones.089' in errors_of(ringtones={'089': ''}))
    check('Klingelton für beliebige Nummern',
          not errors_of(ringtones={'+49891234': '/a.wav', '0049891234': '/b.wav'}))

    print("Unbekanntes bleibt erhalten")
    data = {**base, 'sip': {'host': 'h', 'user': 'u', 'pass': 'p', 'zusatz': 42},
            'eigener_abschnitt': {'x': 'y'}}
    cleaned, errors = configlib.validate(data)
    check('unbekannte Option bleibt erhalten', cleaned['sip']['zusatz'] == 42)
    check('unbekannter Abschnitt bleibt erhalten', cleaned['eigener_abschnitt'] == {'x': 'y'})
    check('unbekanntes überlebt den Schreibvorgang',
          tomllib.loads(configlib.dump(cleaned)) == cleaned)


def test_writing() -> None:
    print("Schreiben in die Datei")
    with TemporaryDirectory() as directory:
        path = Path(directory) / 'config.toml'
        path.write_text(EXAMPLE.read_text(encoding='utf-8'), encoding='utf-8')

        cleaned, errors = configlib.validate(configlib.read(path))
        check('Ausgangsdatei gültig', not errors)

        temporary = path.with_name(path.name + '.tmp')
        baseline = deepcopy(cleaned)

        temporary.write_text(configlib.dump(cleaned), encoding='utf-8')
        check('temporäre Datei gültig', configlib.read(temporary) == cleaned)
        temporary.replace(path)
        check('Datei ersetzt und gültig', configlib.read(path) == cleaned)
        check('alle Abschnitte vorhanden',
              set(configlib.read(path)) == {'network', 'sip', 'pins', 'numbers', 'ringtones', 'sounds', 'misc', 'web'})

        # Ergänzte Kurzwahlen
        cleaned['numbers']['42'] = '01299999'
        del cleaned['numbers']['03']
        cleaned['sip']['dial_timeout'] = 45
        cleaned['misc']['wake_light_duty'] = 25.5

        temporary.write_text(configlib.dump(cleaned), encoding='utf-8')
        check('ergänzte Konfiguration gültig', configlib.read(temporary) == cleaned)
        temporary.replace(path)

        stored = configlib.read(path)
        check('Kurzwahl hinzugefügt', stored['numbers']['42'] == '01299999')
        check('Kurzwahl entfernt', '03' not in stored['numbers'])
        check('geänderter Wert übernommen', stored['sip']['dial_timeout'] == 45)
        check('Dezimalwert übernommen', stored['misc']['wake_light_duty'] == 25.5)

        print("Neustart-Hinweis")
        changed = [f"[{s.name}]" for s in configlib.SECTIONS if stored.get(s.name) != baseline.get(s.name)]
        check('nur geänderte Abschnitte gemeldet', set(changed) == {'[sip]', '[numbers]', '[misc]'}, str(changed))
        check('unveränderte Abschnitte nicht gemeldet', 'pins' not in changed and 'web' not in changed)


def main() -> None:
    original = test_roundtrip()
    test_defaults(original)
    test_validation()
    test_writing()
    print(f"\n{OK} ok, {FAILED} fehlgeschlagen")
    sys.exit(1 if FAILED else 0)


if __name__ == '__main__':
    main()