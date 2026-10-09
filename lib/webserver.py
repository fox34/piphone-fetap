from asyncio import get_running_loop, start_server, StreamReader, StreamWriter
from base64 import b64decode
from json import dumps
from secrets import compare_digest


class WebServer:
    """
    Minimalistischer HTTP-Server zur Anzeige und Steuerung des Telefons.
    - Status wird per `/api/state` als JSON geliefert
    - Aktionen werden per `POST /api/action/<name>` ausgelöst
    - Benötigt keine externen Abhängigkeiten und läuft in der vorhandenen Event-Loop
    """

    # Konfiguration
    port: int
    credentials: str | None
    verbose: bool

    # Aufrufe in PiPhone
    get_state: callable
    actions: dict[str, callable]

    _server = None

    def __init__(
            self, port: int, get_state: callable, actions: dict,
            credentials: str | None = None, verbose: bool = False
    ):
        self.port = port
        self.get_state = get_state
        self.actions = actions
        self.credentials = credentials
        self.verbose = verbose

    async def start(self) -> None:
        """Server starten (Coroutine)"""
        self._server = await start_server(self._handle_client, host='0.0.0.0', port=self.port)
        print(f"Webserver läuft auf Port {self.port}.")

    async def stop(self) -> None:
        """Server beenden (Coroutine)"""
        if self._server is not None:
            self._server.close()
            await self._server.wait_closed()
            self._server = None

    async def _handle_client(self, reader: StreamReader, writer: StreamWriter) -> None:
        """HTTP-Anfrage auswerten und Antwort senden"""

        try:
            request_line = await reader.readline()
            if not request_line:
                return

            method, target, *_ = request_line.decode('utf-8', 'replace').split()
            path = target.split('?')[0]

            headers = {}
            while header_line := await reader.readline():
                if header_line in (b'\r\n', b'\n'):
                    break
                key, _, value = header_line.decode('utf-8', 'replace').partition(':')
                headers[key.strip().lower()] = value.strip()

            if self.verbose:
                print(f"<-- web: {method} {path}")

            # Zugangsschutz (optional)
            if not self._is_authorized(headers):
                self._send(writer, 401, 'text/plain', 'Unauthorized', {'WWW-Authenticate': 'Basic realm="PiPhone"'})
                return

            # Statusseite
            if method == 'GET' and path in ('/', '/index.html'):
                self._send(writer, 200, 'text/html; charset=utf-8', PAGE)
                return

            # Status als JSON
            if method == 'GET' and path == '/api/state':
                self._send_json(writer, self.get_state())
                return

            # Aktion auslösen
            if method == 'POST' and path.startswith('/api/action/'):
                action = path.removeprefix('/api/action/')

                if action not in self.actions:
                    self._send_json(writer, {'error': f"Unbekannte Aktion: {action}"}, status=404)
                    return

                if self.verbose:
                    print(f"--> web: Aktion {action}")

                # Antwort sofort senden und Aktion im Hintergrund ausführen,
                # da diese z.B. auf Klänge warten oder das System herunterfahren
                self._send_json(writer, {'ok': True, 'action': action})
                await writer.drain()
                await self._run(self.actions[action])
                return

            if path == '/favicon.ico':
                self._send(writer, 204, 'image/x-icon', '')
                return

            self._send(writer, 404, 'text/plain', 'Not Found')

        except (ConnectionResetError, BrokenPipeError):
            pass

        finally:
            writer.close()

    def _is_authorized(self, headers: dict) -> bool:
        """Optionale HTTP-Basic-Authentifizierung prüfen"""
        if self.credentials is None:
            return True

        authorization = headers.get('authorization', '')
        if not authorization.startswith('Basic '):
            return False

        try:
            provided = b64decode(authorization[6:]).decode('utf-8')
        except (ValueError, UnicodeDecodeError):
            return False

        return compare_digest(provided, self.credentials)

    async def _run(self, action: callable) -> None:
        """Aktion in einem Thread ausführen, um die Event-Loop nicht zu blockieren"""
        await get_running_loop().run_in_executor(None, action)

    def _send_json(self, writer: StreamWriter, data: dict, status: int = 200) -> None:
        self._send(writer, status, 'application/json', dumps(data))

    @staticmethod
    def _send(writer: StreamWriter, status: int, content_type: str, body: str, headers: dict | None = None) -> None:
        response = f"HTTP/1.1 {status} {HTTP_STATUS.get(status, 'OK')}\r\n"
        response += f"Content-Type: {content_type}\r\n"
        response += f"Content-Length: {len(body.encode('utf-8'))}\r\n"
        response += "Cache-Control: no-store\r\n"
        response += "Connection: close\r\n"
        for key, value in (headers or {}).items():
            response += f"{key}: {value}\r\n"
        response += "\r\n"

        writer.write(response.encode('utf-8') + body.encode('utf-8'))


HTTP_STATUS = {
    200: 'OK',
    204: 'No Content',
    401: 'Unauthorized',
    404: 'Not Found',
    500: 'Internal Server Error',
}


PAGE = """<!DOCTYPE html>
<html lang="de">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>PiPhone</title>
<style>
  :root { color-scheme: dark; }
  body {
    margin: 0 auto; padding: 1.5rem; max-width: 26rem;
    background: #111; color: #ddd;
    font: 1rem/1.5 system-ui, -apple-system, sans-serif;
  }
  h1 { font-size: 1.1rem; font-weight: 600; letter-spacing: .2em; text-transform: uppercase; color: #888; }
  section { border-top: 1px solid #2a2a2a; }
  .row { display: flex; justify-content: space-between; padding: .5rem 0; border-bottom: 1px solid #2a2a2a; }
  .row span:last-child { color: #fff; text-align: right; }
  .row span.on { color: #7ddc7d; }
  .row span.off { color: #777; }
  .buttons { display: grid; grid-template-columns: 1fr 1fr; gap: .5rem; margin-top: 1.5rem; }
  button {
    padding: .8rem .5rem; border: 1px solid #333; border-radius: .4rem;
    background: #1c1c1c; color: #ddd; font: inherit; cursor: pointer;
  }
  button:hover { background: #262626; }
  button:active { background: #333; }
  button:disabled { opacity: .5; cursor: default; }
  button.on { background: #16281a; border-color: #3d6b45; color: #7ddc7d; }
  button.danger { grid-column: span 2; color: #e88; }
  button .key { display: block; font-size: .7rem; color: #666; }
  button.on .key { color: #4c7d55; }
</style>
</head>
<body>
<h1>PiPhone</h1>

<section>
  <div class="row"><span>Laufzeit</span><span id="uptime">–</span></div>
  <div class="row"><span>WLAN</span><span id="connected">–</span></div>
  <div class="row"><span>Telefonie</span><span id="sip">–</span></div>
  <div class="row"><span>Nachtlicht</span><span id="night_light">–</span></div>
  <div class="row"><span>Aufwachmodus</span><span id="wake_up_mode">–</span></div>
  <div class="row"><span>Einschlafmusik</span><span id="sleep_music">–</span></div>
  <div class="row"><span>Nicht stören</span><span id="dnd">–</span></div>
  <div class="row"><span>Nächstes Aufstehen</span><span id="next_wake_up">–</span></div>
</section>

<div class="buttons">
  <button data-action="night-mode" id="night-mode-button"><span class="key">Nachtmodus</span>Nachtlicht</button>
  <button data-action="sleep-music" id="sleep-music-button"><span class="key">Einschlafmusik</span>Musik</button>
  <button data-action="test-loudspeaker"><span class="key">Test</span>Lautsprecher</button>
  <button data-action="test-earpiece"><span class="key">Test</span>Hörer</button>
  <button data-action="reboot" class="danger"><span class="key">Achtung</span>Neustart</button>
  <button data-action="shutdown" class="danger"><span class="key">Achtung</span>Herunterfahren</button>
</div>

<script>
const formatUptime = s => s == null ? '–'
  : [Math.floor(s / 86400), Math.floor(s / 3600) % 24, Math.floor(s / 60) % 60, s % 60]
      .map((v, i) => i === 0 ? `${v} Tage` : i === 1 ? `${v} Std` : i === 2 ? `${v} Min` : `${v} Sek`).join(' ');

const formatDate = s => s ? new Date(s).toLocaleString('de-DE', {weekday: 'short', hour: '2-digit', minute: '2-digit'}) : '–';
const bool = v => v ? 'Ja' : 'Nein';
const classFor = v => v ? 'on' : 'off';

async function refresh() {
  try {
    const state = await (await fetch('/api/state')).json();

    document.getElementById('uptime').textContent = formatUptime(state.uptime);
    for (const key of ['connected', 'night_light', 'wake_up_mode', 'sleep_music', 'dnd']) {
      const el = document.getElementById(key);
      el.textContent = bool(state[key]);
      el.className = classFor(state[key]);
    }
    document.getElementById('sip').textContent = state.call_active ? 'Gespräch aktiv' : state.sip_registered ? 'Bereit' : 'Nicht verfügbar';
    document.getElementById('next_wake_up').textContent = formatDate(state.next_wake_up);

    document.getElementById('night-mode-button').classList.toggle('on', state.night_light);
    document.getElementById('sleep-music-button').classList.toggle('on', state.sleep_music);
  } catch (e) {
    console.error(e);
  }
}

document.querySelectorAll('button').forEach(button => button.addEventListener('click', async () => {
  const action = button.dataset.action;
  if (action === 'reboot' && !confirm('Telefon wirklich neu starten?')) return;
  if (action === 'shutdown' && !confirm('Telefon wirklich herunterfahren?')) return;

  button.disabled = true;
  try {
    await fetch(`/api/action/${action}`, {method: 'POST'});
  } finally {
    setTimeout(() => button.disabled = false, 1000);
  }
  refresh();
}));

refresh();
setInterval(refresh, 2000);
</script>
</body>
</html>
"""