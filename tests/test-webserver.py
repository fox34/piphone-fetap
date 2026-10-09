#!/usr/bin/python3

"""
Test für den Webserver: Konfiguration lesen und über HTTP schreiben.
Läuft ohne Hardware und ohne RPi.GPIO.

    python3 tests/test-webserver.py
"""

import asyncio
import sys
from json import loads, dumps
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lib import config as configlib
from lib.webserver import WebServer

TEST_CONFIG = {
    'sip': {'host': '10.0.0.1', 'user': 'test', 'pass': 'test'},
    'pins': {'nsi': 23, 'nsa': 24, 'gabel': 15},
    'numbers': {'01': '01234567'},
    'web': {'port': 8123},
}

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


async def request(port: int, method: str, path: str, body: str = None) -> tuple:
    reader, writer = await asyncio.open_connection('127.0.0.1', port)
    header = f"{method} {path} HTTP/1.1\r\nHost: localhost\r\n"
    if body is not None:
        header += f"Content-Type: application/json\r\nContent-Length: {len(body.encode('utf-8'))}\r\n"
    writer.write((header + "Connection: close\r\n\r\n" + (body or '')).encode('utf-8'))
    await writer.drain()

    response = await reader.read()
    writer.close()

    head, _, payload = response.partition(b'\r\n\r\n')
    status = int(head.split(b' ')[1])
    if b'application/json' not in head:
        return status, {}
    return status, loads(payload.decode('utf-8')) if payload.strip() else {}


async def main() -> None:
    saved = []

    def get_config() -> dict:
        return {'sections': configlib.describe(TEST_CONFIG), 'mtime': 1000.0, 'restart_required': False}

    def save_config(payload: dict) -> dict:
        cleaned, errors = configlib.validate(payload)
        saved.append(cleaned)
        return {'ok': not errors, 'errors': errors, 'changed': ['[sip]'] if not errors else []}

    server = WebServer(port=8123, get_state=lambda: {'uptime': 1}, actions={},
                       get_config=get_config, save_config=save_config)
    await server.start()
    await asyncio.sleep(0.1)

    print("Statusseite und Konfigurationsseite")
    reader, writer = await asyncio.open_connection('127.0.0.1', 8123)
    writer.write(b"GET / HTTP/1.1\r\nHost: x\r\nConnection: close\r\n\r\n")
    await writer.drain()
    page = (await reader.read()).decode('utf-8')
    writer.close()
    check("GET / liefert HTML", page.startswith('HTTP/1.1 200') and '<h1>PiPhone</h1>' in page)

    status, _ = await request(8123, 'GET', '/config')
    check("GET /config liefert 200", status == 200)

    print("Konfiguration lesen")
    status, data = await request(8123, 'GET', '/api/config')
    check("GET /api/config liefert 200", status == 200)
    check("alle 8 Abschnitte vorhanden", len(data['sections']) == 8, str([s['name'] for s in data['sections']]))
    names = [s['name'] for s in data['sections']]
    check("Reihenfolge der Abschnitte", names == ['network', 'sip', 'pins', 'numbers', 'ringtones', 'sounds', 'misc', 'web'], str(names))

    sip = next(s for s in data['sections'] if s['name'] == 'sip')
    fields = {f['key']: f for f in sip['fields']}
    check("alle SIP-Optionen vorhanden",
          set(fields) == {'host', 'user', 'pass', 'dial_timeout', 'dnd_from', 'dnd_to',
                          'whitelist_active', 'max_call_duration'}, str(sorted(fields)))
    check("Passwort als Geheimfeld markiert", fields['pass']['secret'] is True)
    check("bool-Typ erkannt", fields['whitelist_active']['type'] == 'bool')
    check("int-Grenzen mitgegeben", fields['dnd_from']['maximum'] == 23)

    pins = {f['key']: f for f in next(s for s in data['sections'] if s['name'] == 'pins')['fields']}
    check("Pflichtfelder markiert", all(pins[k]['required'] for k in ('nsi', 'nsa', 'gabel')))

    numbers = next(s for s in data['sections'] if s['name'] == 'numbers')
    check("Kurzwahlen als Einträge", numbers['kind'] == 'entries' and numbers['entries'] == [{'key': '01', 'value': '01234567'}])
    check("Kurzbefehle als Vorschläge", 'reboot' in numbers['choices'])

    sounds = {f['key']: f for f in next(s for s in data['sections'] if s['name'] == 'sounds')['fields']}
    check("Einschlafmusik als Liste", sounds['sleep_music']['type'] == 'list')
    check("Aufstehzeiten als Liste", next(s for s in data['sections'] if s['name'] == 'misc')['fields'][-1]['key'] == 'wake_up_times')

    print("Konfiguration gültig speichern")
    payload = {
        'network': {'wifi_test_host': '10.0.0.1'},
        'sip': {'host': 'fritz.box', 'user': '621', 'pass': 'geheim', 'dial_timeout': '45',
                'dnd_from': '21', 'dnd_to': '7', 'whitelist_active': 'true', 'max_call_duration': '10'},
        'pins': {'nsi': '23', 'nsa': '24', 'gabel': '15'},
        'numbers': {'01': '01234567', '07': '+4989123456', '11': 'enable-night-mode'},
        'ringtones': {'08912345': '/opt/piphone/sounds/ring-02.wav'},
        'sounds': {'ring': '/opt/piphone/sounds/ring-01.wav',
                   'sleep_music': ['/opt/a.mp3', '/opt/b.mp3'], 'waehlen_frei': '/opt/frei.mp3'},
        'misc': {'wake_up_times': ['06:30', '06:30', '06:30', '06:30', '06:30', '07:30', '07:30']},
        'web': {'port': '8123', 'user': '', 'pass': ''},
    }
    status, result = await request(8123, 'POST', '/api/config', dumps(payload))
    check("POST /api/config liefert 200", status == 200)
    check("gültige Konfiguration gespeichert", result['ok'] is True, str(result))

    stored = saved[-1]
    check("Typen korrekt übernommen",
          stored['sip']['dial_timeout'] == 45 and isinstance(stored['sip']['dial_timeout'], int)
          and stored['sip']['whitelist_active'] is True
          and stored['misc']['night_light_duty'] == 50, str(stored['sip']))
    check("Kurzwahlen hinzugefügt", stored['numbers']['07'] == '+4989123456')
    check("Kurzbefehl als Wert erlaubt", stored['numbers']['11'] == 'enable-night-mode')
    check('Pflichtwerte ergänzt', stored['sounds']['boot'] == '' and stored['misc']['wake_light_duty'] == 100)

    print("Konfiguration fehlerhaft speichern")
    broken = {**payload, 'pins': {'nsi': '99', 'nsa': 'x', 'gabel': '15'},
              'numbers': {'1234567': '0123'},
              'misc': {'wake_up_times': ['06:30']}}
    status, result = await request(8123, 'POST', '/api/config', dumps(broken))
    check("POST mit Fehlern liefert ok=false", result['ok'] is False)
    check("Pin zu groß gemeldet", 'darf nicht größer als 27' in result['errors'].get('pins.nsi', ''), str(result['errors']))
    check("Pin kein Integer gemeldet", 'ganze Zahl' in result['errors'].get('pins.nsa', ''))
    check("Kurzwahl zu lang gemeldet", 'numbers.1234567' in result['errors'], str(result['errors']))
    check("fehlende Uhrzeiten gemeldet", 'genau 7' in result['errors'].get('misc.wake_up_times', ''))

    print("Ungültige Anfragen")
    status, result = await request(8123, 'POST', '/api/config', 'kein json')
    check("kaputtes JSON abgewiesen", status == 400)
    status, result = await request(8123, 'POST', '/api/action/shutdown')
    check("unbekannte Aktion abgewiesen", status == 404)
    status, result = await request(8123, 'GET', '/gibtsnicht')
    check("unbekannter Pfad abgewiesen", status == 404)

    await server.stop()

    print(f"\n{OK} ok, {FAILED} fehlgeschlagen")
    sys.exit(1 if FAILED else 0)


if __name__ == '__main__':
    asyncio.run(main())