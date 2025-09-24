from re import compile, Pattern
from subprocess import Popen, PIPE, DEVNULL
from time import sleep
from threading import Thread


class Linphone(Thread):

    # Prozesse
    linphone: Popen

    # Konfiguration
    _username: str
    _password: str
    hostname: str
    on_boot: callable
    on_incoming_call: callable
    on_hang_up: callable
    verbose: bool

    # Zustand
    call_active: bool = False
    line_received: bool = False

    # Regex
    re_call_incoming: Pattern = compile(r'Receiving new incoming call from .*sip:([*+\d]+)@.*, assigned id \d+')
    re_call_connected: Pattern = compile(r'Call \d+.* connected')
    re_call_terminated: Pattern = compile(r'Call \d+.* ended')

    def __init__(
            self,
            hostname: str, username: str, password: str,
            on_boot: callable, on_incoming_call: callable, on_hang_up: callable,
            verbose: bool
    ):
        Thread.__init__(self)

        # Konfiguration
        self._username = username
        self._password = password
        self.hostname = hostname
        self.on_boot = on_boot
        self.on_incoming_call = on_incoming_call
        self.on_hang_up = on_hang_up
        self.verbose = verbose

    def is_running(self):
        try:
            return True if self.linphone.poll() is None else False
        except AttributeError:
            return False

    def run(self):
        """Ausgabe (Aktivität) von linphonec parsen"""

        while self.is_running():
            line = (self.linphone.stdout.readline().decode('utf-8')
                    .removeprefix('linphonec>').strip()
                    .removeprefix('linphonec>').strip())  # Präfix ist in seltenen Fällen doppelt vorhanden

            if line != "":
                self.line_received = True

            # Leere Zeilen oder sinnlose, nicht deaktivierbare Warnungen
            if line == '' or line.startswith("Warning: video is disabled"):
                continue

            if self.verbose:
                print(f"<-- linphone: {line}")

            # Eingehender Anruf
            caller = self.re_call_incoming.match(line)
            if caller:
                self.call_active = True
                self.on_incoming_call(caller[1])
                continue

            # Verbindungsaufbau oder Verbindung hergestellt
            if line.startswith('Establishing call id to') or self.re_call_connected.match(line):
                self.call_active = True
                continue

            # Laufendes Gespräch beendet
            if self.re_call_terminated.match(line):
                self.call_active = False
                self.on_hang_up()
                continue

            if self.verbose:
                print(f"--- linphone: Unbekannte Ausgabe, ignoriere: {line}")

    def start_linphone(self):
        """Starte linphonec und Thread"""

        if self.is_running():
            print("linphonec läuft bereits.")
            return

        print("Starte linphonec.")
        self.linphone = Popen("/usr/bin/linphonec", stdin=PIPE, stdout=PIPE, stderr=DEVNULL)
        self.start()

        counter = 0
        while self.is_running() and not self.line_received:
            counter += 1
            if self.verbose:
                print(f"Warte auf linphonec... ({counter}00ms)", end='\r')
            sleep(0.1)

        if self.verbose:
            print("linphonec gestartet, registriere Account.")
        self._send_cmd(f"register sip:{self._username}@{self.hostname} {self.hostname} {self._password}")
        self.on_boot()

    def stop_linphone(self):
        if self.is_running():
            self.linphone.kill()
        self.line_received = False

    def _send_cmd(self, cmd):
        if not self.is_running():
            print(f"Kann Befehl '{cmd}' nicht an linphonec senden: Client läuft nicht")
            return

        if self.verbose:
            print(f"--> linphone: {cmd}")

        self.linphone.stdin.write(f"{cmd}\n".encode('utf8'))
        self.linphone.stdin.flush()

    def call(self, number):
        """Angegebene Nummer anrufen"""
        self.call_active = True
        self._send_cmd(f"call sip:{number}@{self.hostname}")

    def hangup(self):
        """Aktuelles Gespräch beenden"""
        if self.call_active:
            self._send_cmd("terminate")

    def answer(self):
        """Eingehenden Anruf annehmen"""
        self._send_cmd("answer")
