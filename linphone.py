from re import compile, Pattern
from subprocess import Popen, PIPE, DEVNULL
from threading import Thread

class Linphone(Thread):

    # Prozesse
    linphone: Popen

    # Konfiguration
    hostname: str
    on_incoming_call: callable
    on_hang_up: callable

    # Zustand
    call_active: bool = False

    # Regex
    re_call_connected: Pattern = compile(r'Call \d+.* connected')
    re_call_terminated: Pattern = compile(r'Call \d+.* ended')

    def __init__(self, hostname: str, username: str, password: str, on_incoming_call: callable, on_hang_up: callable):
        Thread.__init__(self)

        # Konfiguration
        self.hostname = hostname
        self.on_incoming_call = on_incoming_call
        self.on_hang_up = on_hang_up

        # Starte linphonec
        #print("Starte linphonec")
        self.linphone = Popen("/usr/bin/linphonec", stdin=PIPE, stdout=PIPE, stderr=DEVNULL)
        self._send_cmd(f"register sip:{username}@{hostname} {hostname} {password}")

    def is_running(self):
        try:
            return True if self.linphone.poll() is None else False
        except AttributeError:
            return False

    def run(self):
        while self.is_running():
            line = self.linphone.stdout.readline().decode('utf-8').removeprefix('linphonec>').strip()

            # Leere Zeilen oder sinnlose, nicht deaktivierbare Warnungen
            if (
                    line == '' or
                    line.startswith("Warning: video is disabled")
            ):
                continue

            #print(f"--- linphone: '{line}'")

            # Eingehender Anruf
            if line.startswith('Receiving new incoming call'):
                self.on_incoming_call()
                continue

            if self.re_call_connected.match(line):
                self.call_active = True
                continue

            # Laufendes Gespräch beendet
            if self.re_call_terminated.match(line):
                self.call_active = False
                self.on_hang_up()
                continue

            #print(f"--- linphone: Ignoriere '{line}'")

    def stop_linphone(self):
        if self.is_running():
            self.linphone.kill()

    def _send_cmd(self, cmd):
        if not self.is_running():
            print(f"Kann Befehl '{cmd}' nicht an linphonec senden: Client läuft nicht")
            return

        #print(f"Sende Befehl an linphone: '{cmd}'")
        self.linphone.stdin.write(f"{cmd}\n".encode('utf8'))
        self.linphone.stdin.flush()

    def call(self, number):
        self._send_cmd(f"call sip:{number}@{self.hostname}")

    def hangup(self):
        if self.call_active:
            self._send_cmd("terminate")

    def answer(self):
        self._send_cmd("answer")
