#!/usr/bin/python3

"""
End-to-End-Test der Konfigurationsbearbeitung: Anfragen wie der Browser sie
sendet, durch WebServer und save_config aus piphone.py - ohne Hardware.

    python3 tests/test-config-web.py
"""

import asyncio
import sys
from copy import deepcopy
from json import dumps, loads
from pathlib import Path
from tempfile import TemporaryDirectory

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lib import config as configlib
from lib.webserver import WebServer

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
        return status, payload.decode('utf-8')
    return status, loads(payload.decode('utf-8')) if payload.strip() else {}


# Nachbildung von collect() und renderSection() aus der Konfigurationsseite
def as_browser_sends(config_payload: dict, changes: dict) -> dict:
    """Bau das Formular aus /api/config nach und wende Änderungen an, wie der Browser es tut"""

    form = {}
    for section in config_payload['sections']:
        if section['kind'] == 'entries':
            # Zeilen, die der Benutzer entfernt hat, fehlen auch in der Anfrage
            rows = {entry['key']: entry['value'] for entry in section['entries']}
            form[section['name']] = changes.get(section['name'], rows)
        else:
            values = {}
            for field in section['fields']:
                if field['key'] in changes.get(section['name'], {}):
                    values[field['key']] = changes[section['name']][field['key']]
                elif field['type'] == 'bool':
                    values[field['key']] = field['value'] is True
                elif field['type'] == 'list':
                    values[field['key']] = list(field['value'] or [])
                else:
                    values[field['key']] = '' if field['value'] is None else str(field['value'])
            form[section['name']] = values
    return form


async def main() -> None:
    with TemporaryDirectory() as directory:
        path = Path(directory) / 'config.toml'
        path.write_text(EXAMPLE.read_text(encoding='utf-8'), encoding='utf-8')

        # Stand, mit dem das Telefon läuft - bleibt während der Tests unverändert
        running = configlib.validate(configlib.read(path))[0]

        # Stand der Datei, wie in piphone.py getrennt geführt
        baseline = deepcopy(running)
        restart_required = False

        def get_state() -> dict:
            return {'uptime': 1, 'config_changed': restart_required}

        def get_config() -> dict:
            return {
                'sections': configlib.describe(baseline),
                'mtime': path.stat().st_mtime,
                'restart_required': restart_required,
            }

        def save_config(payload: dict) -> dict:
            nonlocal baseline, restart_required

            cleaned, errors = configlib.validate(payload, keep=baseline)
            if errors:
                return {'ok': False, 'errors': errors}

            changed = [f"[{s.name}]" for s in configlib.SECTIONS
                       if cleaned.get(s.name) != baseline.get(s.name)]

            temporary = path.with_name(path.name + '.tmp')
            temporary.write_text(configlib.dump(cleaned), encoding='utf-8')
            if configlib.read(temporary) != cleaned:
                return {'ok': False, 'errors': {'_': 'Kontrolle fehlgeschlagen'}}
            temporary.replace(path)

            baseline = cleaned
            restart_required = restart_required or bool(changed)
            return {'ok': True, 'changed': changed, 'restart_required': bool(changed)}

        port = 8231
        server = WebServer(port=port, get_state=get_state, actions={'reboot': lambda: None},
                           get_config=get_config, save_config=save_config)
        await server.start()
        await asyncio.sleep(0.1)

        print("Oberfläche liest die laufende Konfiguration")
        status, payload = await request(port, 'GET', '/api/config')
        check('GET /api/config liefert 200', status == 200)
        check('alle Optionen aus der Datei angezeigt',
              next(s for s in payload['sections'] if s['name'] == 'sip')['fields'][0]['value'] == '10.0.0.1')
        check('Kurzwahlen angezeigt',
              [e['key'] for e in next(s for s in payload['sections'] if s['name'] == 'numbers')['entries']]
              == ['01', '02', '03', '11', '12', '18', '19', '21', '22'])
        check('Kurzbefehle als Vorschläge',
              'shutdown' in next(s for s in payload['sections'] if s['name'] == 'numbers')['choices'])

        print("Kurzwahl hinzufügen und entfernen")
        form = as_browser_sends(payload, {'numbers': {'01': '01234567', '02': '02345678', '03': '03456789',
                                                      '11': 'enable-night-mode', '12': 'play-sleep-music',
                                                      '18': 'reboot', '19': 'shutdown',
                                                      '21': 'test-loudspeaker', '22': 'test-earpiece',
                                                      '42': '01299999'}})
        status, result = await request(port, 'POST', '/api/config', dumps(form))
        check('Kurzwahl hinzugefügt', result['ok'] is True, str(result))

        stored = configlib.read(path)
        check('neue Kurzwahl in der Datei', stored['numbers']['42'] == '01299999')
        check('bestehende Kurzwahlen erhalten', len(stored['numbers']) == 10, str(len(stored['numbers'])))

        payload = (await request(port, 'GET', '/api/config'))[1]
        form = as_browser_sends(payload, {'numbers': {'01': '01234567', '11': 'enable-night-mode'}})
        status, result = await request(port, 'POST', '/api/config', dumps(form))
        check('Kurzwahlen entfernt', result['ok'] is True, str(result))
        check('nur noch zwei Kurzwahlen', len(configlib.read(path)['numbers']) == 2)

        print("Einzelne Option ändern")
        payload = (await request(port, 'GET', '/api/config'))[1]
        form = as_browser_sends(payload, {'sip': {'dial_timeout': '90'}, 'misc': {'night_light_pin': '17'}})
        status, result = await request(port, 'POST', '/api/config', dumps(form))
        check('Änderung gespeichert', result['ok'] is True, str(result))
        check('nur betroffene Abschnitte gemeldet',
              set(result['changed']) == {'[sip]', '[misc]'}, str(result['changed']))
        check('Neustart wird verlangt', result['restart_required'] is True)

        stored = configlib.read(path)
        check('Wert übernommen', stored['sip']['dial_timeout'] == 90)
        check('GPIO-Pin übernommen', stored['misc']['night_light_pin'] == 17)
        check('unveränderte Option bleibt', stored['sip']['host'] == '10.0.0.1')
        check('unveränderter Abschnitt bleibt', stored['pins']['nsi'] == 23)

        status, state = await request(port, 'GET', '/api/state')
        check('Status meldet geänderte Konfiguration', state['config_changed'] is True)
        status, payload = await request(port, 'GET', '/api/config')
        check('Oberfläche meldet Neustartbedarf', payload['restart_required'] is True)

        print("Ohne Änderung bleibt alles unberührt")
        payload = (await request(port, 'GET', '/api/config'))[1]
        before = path.read_text(encoding='utf-8')
        form = as_browser_sends(payload, {})
        status, result = await request(port, 'POST', '/api/config', dumps(form))
        check('unverändertes Speichern erfolgreich', result['ok'] is True, str(result))
        check('keine Änderung gemeldet', result['changed'] == [], str(result['changed']))
        check('Datei inhaltlich unverändert', path.read_text(encoding='utf-8') == before)

        print("Ungültige Eingaben")
        payload = (await request(port, 'GET', '/api/config'))[1]
        form = as_browser_sends(payload, {'pins': {'nsi': '50'}, 'misc': {'wake_up_times': ['06:30'] * 3},
                                          'sip': {'host': ''}})
        status, result = await request(port, 'POST', '/api/config', dumps(form))
        check('ungültige Eingaben abgelehnt', result['ok'] is False)
        check('Fehler für jeden betroffenen Abschnitt',
              {'pins.nsi', 'misc.wake_up_times', 'sip.host'} <= set(result['errors']), str(result['errors']))
        check('Datei unverändert geblieben', path.read_text(encoding='utf-8') == before)
        check('keine temporäre Datei zurückgeblieben', not path.with_name(path.name + '.tmp').exists())

        print("Klingeltöne bearbeiten")
        form = as_browser_sends(payload, {'ringtones': {'08912345': '/opt/piphone/sounds/ring-02.wav',
                                                        '01701234567': '/opt/piphone/sounds/ring-03.wav'}})
        status, result = await request(port, 'POST', '/api/config', dumps(form))
        check('Klingeltöne gespeichert', result['ok'] is True, str(result))
        ringtones = configlib.read(path)['ringtones']
        check('zweiter Klingelton ergänzt', ringtones['01701234567'] == '/opt/piphone/sounds/ring-03.wav')
        check('Klingeltöne als Schlüssel in Anführungszeichen', '"01701234567"' in path.read_text(encoding='utf-8'))

        form = as_browser_sends(payload, {'ringtones': {'08912345': ''}})
        status, result = await request(port, 'POST', '/api/config', dumps(form))
        check('Klingelton ohne Datei abgelehnt', result['ok'] is False)
        check('Fehler benennt den Klingelton', 'ringtones.08912345' in result['errors'], str(result['errors']))

        print("Listen bearbeiten")
        form = as_browser_sends(payload, {'sounds': {'sleep_music': ['/opt/a.mp3', '/opt/b.mp3', '/opt/c.mp3']}})
        status, result = await request(port, 'POST', '/api/config', dumps(form))
        check('Schlafliedliste gespeichert', result['ok'] is True, str(result))
        check('drei Lieder übernommen',
              configlib.read(path)['sounds']['sleep_music'] == ['/opt/a.mp3', '/opt/b.mp3', '/opt/c.mp3'])

        form = as_browser_sends(payload, {'sounds': {'sleep_music': []}})
        status, result = await request(port, 'POST', '/api/config', dumps(form))
        check('leere Liste gespeichert', result['ok'] is True and configlib.read(path)['sounds']['sleep_music'] == [])

        print("Passwörter")
        form = as_browser_sends(payload, {'sip': {'pass': 'neues passwort mit Umlaut ä'}})
        status, result = await request(port, 'POST', '/api/config', dumps(form))
        check('Passwort mit Sonderzeichen gespeichert', result['ok'] is True, str(result))
        check('Passwort korrekt in der Datei', configlib.read(path)['sip']['pass'] == 'neues passwort mit Umlaut ä')
        check('Passwort als Feld markiert',
              next(f for f in next(s for s in payload['sections'] if s['name'] == 'sip')['fields']
                   if f['key'] == 'pass')['secret'] is True)

        print("Kommentare in der geschriebenen Datei")
        text = path.read_text(encoding='utf-8')
        check('Kommentar über Option vorhanden', '# GPIO-Pin für Nachtlicht (0 = deaktiviert).' in text)
        check('Hinweis auf nicht beibehaltene Kommentare',
              'selbst geschriebene Kommentare werden dabei nicht beibehalten' in text)
        check('jeder Abschnitt kommentiert',
              all(f'[{s}]' in text for s in ['network', 'sip', 'pins', 'numbers', 'ringtones', 'sounds', 'misc', 'web']))
        check('Dateiende mit Zeilenumbruch', text.endswith('\n'))

        print("Neustart wird nicht automatisch ausgelöst")
        status, result = await request(port, 'POST', '/api/config', dumps(as_browser_sends(payload, {})))
        check('Speichern löst keine Aktion aus', result['ok'] is True)
        status, state = await request(port, 'GET', '/api/state')
        check('Telefon läuft weiter', state['uptime'] == 1)

        await server.stop()

    await test_unknown_preserved()


async def test_unknown_preserved() -> None:
    """Angaben, die das Schema nicht kennt, dürfen beim Speichern nicht verloren gehen"""

    print("Unbekannte Angaben bleiben erhalten")
    with TemporaryDirectory() as directory:
        path = Path(directory) / 'config.toml'
        path.write_text(EXAMPLE.read_text(encoding='utf-8') + '\n[sonder]\nx = 1\n', encoding='utf-8')

        baseline = configlib.validate(configlib.read(path))[0]
        check('Sonderabschnitt beim Start gelesen', baseline['sonder'] == {'x': 1})

        def save_config(payload: dict) -> dict:
            cleaned, errors = configlib.validate(payload, keep=baseline)
            if errors:
                return {'ok': False, 'errors': errors}
            temporary = path.with_name(path.name + '.tmp')
            temporary.write_text(configlib.dump(cleaned), encoding='utf-8')
            temporary.replace(path)
            return {'ok': True, 'changed': []}

        port = 8232
        server = WebServer(port=port, get_state=lambda: {}, actions={},
                           get_config=lambda: {'sections': configlib.describe(baseline)},
                           save_config=save_config)
        await server.start()
        await asyncio.sleep(0.1)

        status, payload = await request(port, 'GET', '/api/config')
        form = as_browser_sends(payload, {'network': {'wifi_test_host': '192.168.178.1'},
                                          'sip': {'zusatz': 'bleibt erhalten'}})
        status, result = await request(port, 'POST', '/api/config', dumps(form))

        stored = configlib.read(path)
        check('Sonderabschnitt nicht verloren', result['ok'] is True and stored.get('sonder') == {'x': 1},
              str(stored.get('sonder')))
        check('Änderung übernommen', stored['network']['wifi_test_host'] == '192.168.178.1')
        check('Sonderabschnitt in der geschriebenen Datei',
              '[sonder]' in path.read_text(encoding='utf-8'))

        await server.stop()

    print(f"\n{OK} ok, {FAILED} fehlgeschlagen")
    sys.exit(1 if FAILED else 0)


if __name__ == '__main__':
    asyncio.run(main())