"""
Schema der TOML-Konfigurationsdatei: Beschreibung aller Optionen, Prüfung und Schreiben.

Die Weboberfläche (lib/webserver.py) nutzt dieses Modul, um die Konfiguration
anzuzeigen und zu speichern. Jede Option wird im TOML mit einem Kommentar
versehen, der aus diesem Schema erzeugt wird. Kommentare, die von Hand in der
Konfigurationsdatei stehen, werden beim Speichern nicht beibehalten - die Datei
enthält anschließend nur noch die Kommentare aus dem Schema.
"""

from dataclasses import dataclass
from pathlib import Path
import re
import tomllib


# Kurzbefehle, die in [numbers] als Ziel einer Kurzwahl stehen dürfen
COMMANDS = (
    'shutdown',
    'reboot',
    'enable-night-mode',
    'play-sleep-music',
    'test-loudspeaker',
    'test-earpiece',
)

# Wie viele Ziffern eine Kurzwahl höchstens haben darf (längere Folgen bricht der Nummernschalter ab)
MAX_DIAL_CODE = 5

GPIO_PIN_MAX = 27
PORT_MAX = 65535
HOUR_MAX = 23
DUTY_MAX = 100

# Rufnummern dürfen Ziffern, +, Leerzeichen und übliche Trennzeichen enthalten
PHONE_PATTERN = r'\+?[0-9][0-9 +()/.\-]*'
TIME_PATTERN = r'(?:[01]\d|2[0-3]):[0-5]\d'
DIAL_CODE_PATTERN = r'\d{1,%d}' % MAX_DIAL_CODE


@dataclass(frozen=True)
class Option:
    """Eine einzelne Konfigurationsoption mit Typ, Standardwert und Kommentar."""

    key: str
    label: str
    type: str  # string | int | float | bool | list
    default: object = None
    comment: tuple = ()
    secret: bool = False  # Passwörter: in der Oberfläche verdeckt eingeben
    required: bool = False
    minimum: float | None = None
    maximum: float | None = None
    item_pattern: str | None = None  # für type=list: Muster je Eintrag
    item_count: int | None = None  # für type=list: feste Anzahl Einträge
    item_hint: str = ''
    restart: bool = False  # Änderung wird erst nach einem Neustart wirksam


@dataclass(frozen=True)
class Entries:
    """Freie Schlüssel/Wert-Paare einer Tabelle, z.B. [numbers] oder [ringtones]."""

    key_label: str
    value_label: str
    comment: tuple = ()
    key_pattern: str = PHONE_PATTERN
    value_pattern: str | None = None
    key_message: str = 'Siehe Kommentar'
    value_message: str = 'Siehe Kommentar'
    choices: tuple = ()  # Vorschläge für den Wert (datalist)


@dataclass(frozen=True)
class Section:
    """Ein Abschnitt der Konfigurationsdatei."""

    name: str
    title: str
    options: tuple = ()
    entries: Entries | None = None


# --------------------------------------------------------------------------------------------
# Schema: Reihenfolge bestimmt die Reihenfolge in der Weboberfläche und in der Datei
# --------------------------------------------------------------------------------------------

SECTIONS = (
    Section(
        name='network',
        title='Netzwerk',
        options=(
            Option(
                key='wifi_test_host', label='Host für Verbindungstest', type='string',
                default='10.0.0.1',
                comment=('Host, über dessen Erreichbarkeit die WLAN-Verbindung geprüft wird (Port 80).',),
            ),
        ),
    ),
    Section(
        name='sip',
        title='SIP-Telefonie',
        options=(
            Option(
                key='host', label='SIP-Server', type='string', required=True, restart=True,
                comment=('Adresse des SIP-Servers, bspw. die FRITZ!Box.',),
            ),
            Option(
                key='user', label='SIP-Benutzer', type='string', required=True, restart=True,
                comment=('SIP-Benutzername.',),
            ),
            Option(
                key='pass', label='SIP-Passwort', type='string', required=True, secret=True, restart=True,
                comment=('SIP-Passwort.',),
            ),
            Option(
                key='dial_timeout', label='Wählvorgang Timeout (s)', type='int', default=60,
                minimum=0, maximum=3600,
                comment=('Wie lange darf ein Wählvorgang dauern, bis er automatisch abgebrochen wird (Sekunden)',),
            ),
            Option(
                key='dnd_from', label='Klingelsperre ab (Stunde)', type='int', default=0,
                minimum=0, maximum=HOUR_MAX,
                comment=('Klingelsperre ab welcher Stunde am Abend (0 = deaktiviert).',),
            ),
            Option(
                key='dnd_to', label='Klingelsperre bis (Stunde)', type='int', default=0,
                minimum=0, maximum=HOUR_MAX,
                comment=('Klingelsperre bis zu welcher Stunde am Morgen (0 = deaktiviert).',),
            ),
            Option(
                key='whitelist_active', label='Whitelist aktiv', type='bool', default=False,
                comment=('Weist automatisch alle Anrufer ab, die nicht in [numbers] hinterlegt sind.',),
            ),
            Option(
                key='max_call_duration', label='Max. Gesprächsdauer (min)', type='int', default=0,
                minimum=0, maximum=1440,
                comment=('Beendet ausgehende Anrufe automatisch nach X Minuten (0 = deaktiviert).',),
            ),
        ),
    ),
    Section(
        name='pins',
        title='GPIO-Pins',
        options=(
            Option(
                key='nsi', label='Nummernschalter NSI', type='int', required=True, restart=True,
                minimum=0, maximum=GPIO_PIN_MAX,
                comment=('Nummern-Schalter-Impuls-Kontakt.',),
            ),
            Option(
                key='nsa', label='Nummernschalter NSA', type='int', required=True, restart=True,
                minimum=0, maximum=GPIO_PIN_MAX,
                comment=('Nummern-Schalter-Arbeits- (oder Abschalte-)Kontakt.',),
            ),
            Option(
                key='gabel', label='Gabelkontakt', type='int', required=True, restart=True,
                minimum=0, maximum=GPIO_PIN_MAX,
                comment=('Gabelkontakt.',),
            ),
        ),
    ),
    Section(
        name='numbers',
        title='Kurzwahlen und Kurzbefehle',
        entries=Entries(
            key_label='Kurzwahl',
            value_label='Rufnummer oder Kurzbefehl',
            comment=(
                'Gültige Rufnummern (Kurzwahlen) oder Kurzbefehle.',
                'Kurzbefehle: ' + ', '.join(COMMANDS),
            ),
            key_pattern=DIAL_CODE_PATTERN,
            key_message=f'Kurzwahl muss aus {MAX_DIAL_CODE} Ziffern bestehen.',
            value_pattern=PHONE_PATTERN,
            value_message='Rufnummer angeben oder einen der Kurzbefehle wählen.',
            choices=COMMANDS,
        ),
    ),
    Section(
        name='ringtones',
        title='Klingeltöne',
        entries=Entries(
            key_label='Rufnummer',
            value_label='Klingelton-Datei',
            comment=(
                'Rufnummerspezifische Klingeltöne. Fehlt eine Rufnummer,',
                'wird der generische Klingelton aus [sounds] verwendet.',
            ),
            value_pattern=r'\S.*\S|\S',
            value_message='Pfad zur Klangdatei angeben.',
        ),
    ),
    Section(
        name='sounds',
        title='Klänge',
        options=(
            Option(key='boot', label='Start', type='string', default='',
                   comment=('Klang beim Start des Telefons.',)),
            Option(key='reboot', label='Neustart', type='string', default='',
                   comment=('Klang vor einem Neustart.',)),
            Option(key='shutdown', label='Herunterfahren', type='string', default='',
                   comment=('Klang vor dem Herunterfahren.',)),
            Option(key='ring', label='Klingeln', type='string', default='',
                   comment=('Generischer Klingelton.',)),
            Option(key='test_earpiece', label='Test Hörer', type='string', default='',
                   comment=('Testton über den Hörer.',)),
            Option(key='test_loud', label='Test Lautsprecher', type='string', default='',
                   comment=('Testton über den Lautsprecher.',)),
            Option(key='waehlen_frei', label='Freizeichen', type='string', default='',
                   comment=('Freizeichen beim Abheben des Hörers.',)),
            Option(key='waehlen_besetzt', label='Besetzt', type='string', default='',
                   comment=('Besetztton, auch bei Timeout und beendeten Gesprächen.',)),
            Option(key='waehlen_ungueltig', label='Ungültige Kurzwahl', type='string', default='',
                   comment=('Klang bei einer zu langen Ziffernfolge.',)),
            Option(key='waehlen_nicht_verbunden', label='Nicht verbunden', type='string', default='',
                   comment=('Besetztton, wenn beim Abheben kein SIP-Client bereitsteht.',)),
            Option(key='action_confirmed', label='Bestätigung', type='string', default='',
                   comment=('Klang zur Bestätigung eines Kurzbefehls.',)),
            Option(
                key='sleep_music', label='Einschlafmusik', type='list', default=(),
                item_hint='Ein Pfad je Zeile',
                comment=(
                    'Einschlafmusik: mehrere Dateien werden in zufälliger Reihenfolge abgespielt.',
                    'Beispieldatei aus urheberrechtlichen Gründen nicht im Repository.',
                ),
            ),
        ),
    ),
    Section(
        name='misc',
        title='Nacht- und Aufwachlicht',
        options=(
            Option(key='night_light_pin', label='Nachtlicht: GPIO-Pin', type='int', default=0,
                   minimum=0, maximum=GPIO_PIN_MAX, restart=True,
                   comment=('GPIO-Pin für Nachtlicht (0 = deaktiviert).',)),
            Option(key='night_light_duty', label='Nachtlicht: Helligkeit (%)', type='float', default=50,
                   minimum=0, maximum=DUTY_MAX, restart=True,
                   comment=('Nachtlicht: Helligkeit in Prozent (100 = PWM deaktiviert, volle Leistung des GPIO)',)),
            Option(key='wake_light_pin', label='Aufwachlicht: GPIO-Pin', type='int', default=0,
                   minimum=0, maximum=GPIO_PIN_MAX, restart=True,
                   comment=('GPIO-Pin für Aufwach-Licht (0 = deaktiviert).',)),
            Option(key='wake_light_duty', label='Aufwachlicht: Helligkeit (%)', type='float', default=100,
                   minimum=0, maximum=DUTY_MAX, restart=True,
                   comment=('Aufwach-Licht: Helligkeit in Prozent (100 = PWM deaktiviert, volle Leistung des GPIO)',)),
            Option(
                key='wake_up_times', label='Aufstehzeiten', type='list', default=(),
                item_pattern=TIME_PATTERN, item_count=7, item_hint='Uhrzeit HH:MM',
                comment=(
                    'Uhrzeiten zum Aufstehen: Mo, Di, Mi, Do, Fr, Sa, So (Lokalzeit, ggf. inkl. Sommerzeit).',
                    'Es werden genau 7 Uhrzeiten benötigt, sonst bleibt der Nachtmodus wirkungslos.',
                ),
            ),
        ),
    ),
    Section(
        name='web',
        title='Webserver',
        options=(
            Option(key='port', label='Port', type='int', default=0,
                   minimum=0, maximum=PORT_MAX, restart=True,
                   comment=('Port des Webservers, 0 = deaktiviert.',)),
            Option(key='user', label='Benutzer', type='string', default='', restart=True,
                   comment=(
                       'Optionaler Zugangsschutz (HTTP Basic Auth).',
                       'Achtung: Ohne Zugangsschutz kann jeder im WLAN das Telefon herunterfahren',
                       'und die Konfiguration verändern!',
                       'Leere Felder = kein Zugangsschutz',
                   )),
            Option(key='pass', label='Passwort', type='string', default='', secret=True, restart=True,
                   comment=('Zum Benutzerfeld gehörendes Passwort.',)),
        ),
    ),
)

SECTION_BY_NAME = {section.name: section for section in SECTIONS}


# --------------------------------------------------------------------------------------------
# TOML-Schreiben
# --------------------------------------------------------------------------------------------

BARE_KEY = re.compile(r'[A-Za-z_][A-Za-z0-9_-]*')


def toml_key(key: str) -> str:
    """TOML-Schlüssel: In Anführungszeichen, sofern kein einfacher Schlüssel möglich ist"""
    if BARE_KEY.fullmatch(key):
        return key
    return toml_string(key)


def toml_string(value: str) -> str:
    """Zeichenkette in TOML-Schreibweise"""
    escaped = value.replace('\\', '\\\\').replace('"', '\\"').replace('\n', '\\n').replace('\t', '\\t')
    return f'"{escaped}"'


def toml_value(value: object) -> str:
    """Beliebigen Konfigurationswert in TOML-Schreibweise"""
    if value is None:
        # Kann nur bei unvollständigen Eingaben auftreten, die nicht gespeichert werden
        return '""'
    if isinstance(value, bool):
        return 'true' if value else 'false'
    if isinstance(value, int):
        return str(value)
    if isinstance(value, float):
        return repr(value)
    if isinstance(value, str):
        return toml_string(value)
    if isinstance(value, (list, tuple)):
        return '[' + ', '.join(toml_value(item) for item in value) + ']'
    raise TypeError(f"Unbekannter Wertetyp: {type(value)}")


HEADER = (
    '# PiPhone-Konfiguration',
    '#',
    '# Diese Datei kann auch im Webinterface des Telefons bearbeitet werden.',
    '# Kommentare werden beim Speichern aus dem Schema neu erzeugt,',
    '# selbst geschriebene Kommentare werden dabei nicht beibehalten.',
    '# Vorlage mit allen Optionen: support/config-example.toml',
)


def dump(data: dict) -> str:
    """Konfiguration mit Kommentaren als TOML-Text erzeugen"""

    lines = list(HEADER)
    written = set()

    for section in SECTIONS:
        values = data.get(section.name) or {}
        lines += ['', f'[{section.name}]']

        if section.entries:
            if section.entries.comment:
                lines += [f'# {line}' for line in section.entries.comment]
            for key in sorted(values, key=str):
                lines.append(f'{toml_key(str(key))} = {toml_value(values[key])}')

        else:
            known = set()
            for option in section.options:
                known.add(option.key)
                if option.comment:
                    lines += [f'# {line}' for line in option.comment]
                lines.append(f'{option.key} = {toml_value(values.get(option.key, option.default))}')

            # Unbekannte Optionen unverändert übernehmen
            for key in sorted(values, key=str):
                if key not in known:
                    lines.append(f'{toml_key(str(key))} = {toml_value(values[key])}')

        written.add(section.name)

    # Unbekannte Abschnitte ebenfalls nicht verlieren
    for name in sorted(data, key=str):
        if name not in written:
            lines += ['', f'[{toml_key(str(name))}]']
            for key in sorted(data[name], key=str):
                lines.append(f'{toml_key(str(key))} = {toml_value(data[name][key])}')

    return '\n'.join(lines) + '\n'


# --------------------------------------------------------------------------------------------
# Prüfen
# --------------------------------------------------------------------------------------------

def read(path: Path) -> dict:
    """Konfigurationsdatei einlesen"""
    with Path(path).open('rb') as config_file:
        return tomllib.load(config_file)


def _as_int(text: str) -> int:
    return int(text.strip())


def coerce(option: Option, raw: object) -> object:
    """
    Rohwert aus der Oberfläche in den konfigurierten Typ umwandeln.
    Wirft bei ungültigen Werten einen ValueError mit Klartextmeldung.
    """

    # Leere Eingaben: Standardwert verwenden, sonst ablehnen
    if raw is None or (isinstance(raw, str) and not raw.strip()):
        if option.default is not None:
            return list(option.default) if option.type == 'list' else option.default
        if option.required:
            raise ValueError('Pflichtangabe')
        raise ValueError('Wert fehlt')

    if option.type == 'bool':
        if isinstance(raw, bool):
            return raw
        text = str(raw).strip().lower()
        if text in ('true', '1', 'ja', 'yes', 'on', 'an', 'wahr'):
            return True
        if text in ('false', '0', 'nein', 'no', 'off', 'aus', 'falsch'):
            return False
        raise ValueError('muss an oder aus sein')

    if option.type == 'int':
        if isinstance(raw, bool):
            raise ValueError('muss eine ganze Zahl sein')
        try:
            value = _as_int(str(raw))
        except ValueError:
            raise ValueError('muss eine ganze Zahl sein')

    elif option.type == 'float':
        text = str(raw).strip()
        try:
            number = float(text)
        except ValueError:
            raise ValueError('muss eine Zahl sein')
        # Ganzzahlige Eingaben auch als Ganzzahl speichern, sonst wird 50 zu 50.0
        value = number if re.search(r'[.eE]', text) else int(number)

    elif option.type == 'string':
        value = str(raw)

    elif option.type == 'list':
        if isinstance(raw, str):
            raw = raw.split('\n')
        if not isinstance(raw, (list, tuple)):
            raise ValueError('muss eine Liste sein')
        items = [str(item).strip() for item in raw if str(item).strip()]

        if option.item_count is not None and len(items) != option.item_count:
            raise ValueError(f"muss genau {option.item_count} Einträge enthalten")

        if option.item_pattern is not None:
            for item in items:
                if not re.fullmatch(option.item_pattern, item):
                    raise ValueError('enthält einen ungültigen Eintrag')

        value = items

    else:
        raise ValueError('unbekannter Typ')

    if option.type in ('int', 'float'):
        if option.minimum is not None and value < option.minimum:
            raise ValueError(f"darf nicht kleiner als {option.minimum:g} sein")
        if option.maximum is not None and value > option.maximum:
            raise ValueError(f"darf nicht größer als {option.maximum:g} sein")

    if option.required and value == '':
        raise ValueError('Pflichtangabe')

    return value


def validate(data: dict, keep: dict = None) -> tuple[dict, dict]:
    """
    Konfiguration prüfen und in eine vollständige, speicherbare Form bringen.

    Fehlende Optionen erhalten ihren Standardwert, unbekannte Optionen bleiben erhalten.
    `keep` hält die bisherige Konfiguration fest: unbekannte Optionen und Abschnitte,
    die die Oberfläche nicht kennt, werden von dort übernommen und nicht verloren.
    Liefert (bereinigte Konfiguration, Fehler je Schlüssel `abschnitt.option`).
    """

    keep = keep or {}
    cleaned = {}
    errors = {}

    for section in SECTIONS:
        source = data.get(section.name)
        if source is None:
            source = {}
        if not isinstance(source, dict):
            errors[section.name] = 'Abschnitt ist keine Tabelle.'
            source = {}

        kept = keep.get(section.name) if isinstance(keep.get(section.name), dict) else {}

        values = {}

        if section.entries:
            for raw_key, raw_value in source.items():
                key = str(raw_key).strip()
                value = str(raw_value).strip()

                if not re.fullmatch(section.entries.key_pattern, key):
                    errors[f'{section.name}.{key}'] = section.entries.key_message
                    continue

                is_command = value in section.entries.choices
                if section.entries.value_pattern and not is_command and \
                        not re.fullmatch(section.entries.value_pattern, value):
                    errors[f'{section.name}.{key}'] = section.entries.value_message
                    continue

                if key in values:
                    errors[f'{section.name}.{key}'] = 'Doppelt belegt.'
                    continue

                values[key] = value

        else:
            known = set()
            for option in section.options:
                known.add(option.key)
                raw = source.get(option.key)
                try:
                    values[option.key] = coerce(option, raw)
                except ValueError as e:
                    message = str(e)
                    if message == 'Pflichtangabe':
                        message = 'Pflichtangabe'
                    errors[f'{section.name}.{option.key}'] = message
                    values[option.key] = option.default if option.default is not None else (
                        '' if option.type == 'string' else None)

            # Unbekannte Optionen aus der Oberfläche oder der bisherigen Datei übernehmen.
            # Bei Eintragstabellen wie [numbers] gibt es keine bekannten Schlüssel -
            # dort ist der komplette Inhalt aus der Oberfläche maßgeblich, damit
            # entfernte Einträge auch wirklich verschwinden.
            if not section.entries:
                for key in {**kept, **source}:
                    if key not in known and key not in values:
                        values[key] = source.get(key, kept.get(key))

        cleaned[section.name] = values

    # Unbekannte Abschnitte ebenfalls nicht verlieren
    for name in {**keep, **data}:
        if name not in cleaned:
            cleaned[name] = data.get(name, keep.get(name))

    return cleaned, errors


# --------------------------------------------------------------------------------------------
# Beschreibung für die Weboberfläche
# --------------------------------------------------------------------------------------------

def describe(data: dict) -> list:
    """Schema und aktuelle Werte als JSON-serialisierbare Struktur für die Weboberfläche"""

    description = []

    for section in SECTIONS:
        values = data.get(section.name) or {}

        if section.entries:
            description.append({
                'name': section.name,
                'title': section.title,
                'kind': 'entries',
                'help': list(section.entries.comment),
                'key_label': section.entries.key_label,
                'value_label': section.entries.value_label,
                'choices': list(section.entries.choices),
                'entries': [{'key': str(key), 'value': str(values[key])} for key in sorted(values, key=str)],
            })
            continue

        fields = []
        for option in section.options:
            fields.append({
                'key': option.key,
                'label': option.label,
                'type': option.type,
                'value': values.get(option.key, option.default),
                'help': list(option.comment),
                'secret': option.secret,
                'required': option.required,
                'minimum': option.minimum,
                'maximum': option.maximum,
                'item_hint': option.item_hint,
                'restart': option.restart,
            })

        description.append({
            'name': section.name,
            'title': section.title,
            'kind': 'options',
            'fields': fields,
        })

    return description