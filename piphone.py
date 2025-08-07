#!/usr/bin/python3

from audio import Audio
from linphone import Linphone
from rotarydial import RotaryDial

import asyncio
from configparser import ConfigParser
from RPi import GPIO
from signal import signal, SIGTERM, SIGINT
from os import system
import socket
from subprocess import Popen
from sys import exit
from time import sleep

config = ConfigParser()
config.read("/boot/piphone/config.ini")

class PiPhone:
    
    # Instanzen
    loop: asyncio.AbstractEventLoop
    dial: RotaryDial

    # Tasks und Prozesse
    wifi_test_task: asyncio.Task
    earpiece_tone_subprocess: Popen|None = None
    speaker_tone_subprocess: Popen|None = None
    linphone: Linphone

    # Zustandsvariablen
    is_connected: bool = False
    call_incoming: bool = False
    terminate_requested: bool = False
    
    def __init__(self, loop: asyncio.AbstractEventLoop):
        """Haupt-Programm starten"""

        # Event-Loop speichern
        self.loop = loop

        # WLAN-Verbindung überwachen
        asyncio.create_task(self.check_wifi())

        # Systemsignale
        signal(SIGTERM, self.handle_sigterm)
        signal(SIGINT, self.handle_sigterm)

        # GPIO einrichten
        GPIO.setmode(GPIO.BCM)

        # Nummernschalter
        self.dial = RotaryDial(
            pin_nsi = config['Pins'].getint('nsi'),
            pin_nsa = config['Pins'].getint('nsa'),
            receive_number_callback = self.receive_number
        )

        # Gabelkontakt
        GPIO.setup(config['Pins'].getint('gabel'), GPIO.IN, pull_up_down=GPIO.PUD_UP)
        GPIO.add_event_detect(config['Pins'].getint('gabel'), GPIO.BOTH, callback = self.watch_hook, bouncetime=100)

        # Linphone
        self.linphone = Linphone(
            hostname = config['SIP']['host'],
            username = config['SIP']['user'],
            password = config['SIP']['pass'],
            on_incoming_call=self.incoming_call,
            on_hang_up=self.hung_up
        )
        self.linphone.start()

    @staticmethod
    def handle_sigterm(_, __):
        """SIGTERM/SIGINT empfangen und Programm sauber beenden"""
        print("\nSIGTERM/SIGINT empfangen, beende.")
        raise SystemExit()

    async def check_wifi(self):
        """WLAN-Verbindung periodisch prüfen"""

        await asyncio.sleep(5)
        socket.setdefaulttimeout(1)
        while True:
            try:
                with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
                    sock.connect((config['Network']['wifi_test_host'], 80))
                #print("WLAN-Verbindung verfügbar.")
                self.is_connected = True
                await asyncio.sleep(60)

            except TimeoutError:
                print("WLAN-Verbindung verloren!")
                Audio.play_loud(config['Sounds']['wlan_nicht_verbunden'])
                self.is_connected = False
                await asyncio.sleep(10)

    @staticmethod
    def is_hungup() -> bool:
        """Prüfe, ob Hörer auf Gabel liegt (aufgelegt ist)"""
        return GPIO.input(config['Pins'].getint('gabel'))

    def watch_hook(self, _):
        """Gabelkontakt überwachen"""

        if self.is_hungup():
            # Hörer wurde soeben aufgelegt
            print("Hörer aufgelegt")

            # Wählvorgang beenden, falls aktiv
            self.dial.end_dialing()

            # Wiedergabe (Freizeichen, Besetzt, usw.) im Hörer stoppen
            if self.earpiece_tone_subprocess is not None:
                self.earpiece_tone_subprocess.kill()

            # Auflegen
            if self.linphone is not None:
                self.linphone.hangup()

        else:
            # Hörer wurde soeben abgehoben
            print("Hörer abgehoben")

            # WLAN nicht verbunden - keine weitere Aktion
            if not self.is_connected:
                self.earpiece_tone_subprocess = Audio.play_earpiece(config['Sounds']['waehlen_nicht_verbunden'])
                return

            # Eingehender Anruf
            if self.call_incoming:
                # Wiedergabe im Hörer stoppen (nur zur Sicherheit; hier sollte nichts laufen)
                if self.earpiece_tone_subprocess is not None:
                    self.earpiece_tone_subprocess.kill()

                # Klingeln stoppen
                if self.speaker_tone_subprocess is not None:
                    self.speaker_tone_subprocess.kill()

                # Anruf annehmen
                self.linphone.answer()

            else:
                # Freizeichen im Hörer abspielen
                self.earpiece_tone_subprocess = Audio.play_earpiece(config['Sounds']['waehlen_frei'])

                # Nummernschalter überwachen
                asyncio.run_coroutine_threadsafe(self.dial.start_dialing(), self.loop)

                # TODO Timeout (1 Minute o.ä.)

    def receive_number(self, number: str):
        """
        Ziffernfolge von rotarydial empfangen und mit gespeicherten Kurzwahlen/Befehlen abgleichen
        Nummer muss zwingend `str` sein, da sie mit einer 0 beginnen kann.
        """

        #print(f"Gewählte Ziffernfolge: {number}")
        try:
            action = config['Numbers'][number]
        except KeyError:
            # Ziffernfolge nicht hinterlegt

            # Bereits zu viele Ziffern gewählt
            if len(number) > 5:
                print("Ziffernfolge zu lang, beende Wahlvorgang.")
                self.dial.end_dialing()
                self.earpiece_tone_subprocess.kill()
                self.earpiece_tone_subprocess = Audio.play_earpiece(config['Sounds']['waehlen_ungueltig'])

            return

        print(f"Gewählt: {number} -> {action}")
        self.dial.end_dialing()
        self.earpiece_tone_subprocess.kill()

        match action:
            case "test-loudspeaker":
                Audio.play_loud(config['Sounds']['test_loud']).wait()
                sleep(1)
                if not GPIO.input(config['Pins'].getint('gabel')):
                    # Hörer noch nicht aufgelegt
                    self.earpiece_tone_subprocess = Audio.play_earpiece(config['Sounds']['waehlen_besetzt'])

            case "test-earpiece":
                Audio.play_earpiece(config['Sounds']['test_earpiece']).wait()
                sleep(1)
                if not GPIO.input(config['Pins'].getint('gabel')):
                    # Hörer noch nicht aufgelegt
                    self.earpiece_tone_subprocess = Audio.play_earpiece(config['Sounds']['waehlen_besetzt'])

            case "reboot":
                Audio.play_loud(config['Sounds']['reboot']).wait()
                system("systemctl reboot -i")
                raise SystemExit()

            case "shutdown":
                Audio.play_loud(config['Sounds']['shutdown']).wait()
                system("systemctl poweroff -i")
                raise SystemExit()

            case _:
                print(f"Rufe Nummer an: {action}")
                self.linphone.call(action)

    def incoming_call(self):
        """Eingehender Anruf"""
        print("Eingehender Anruf")

        # TODO Klingelsperre zu bestimmten Uhrzeiten

        # Hörer abgehoben -> Anruf abweisen
        if not self.is_hungup():
            self.linphone.hangup()
            return

        self.call_incoming = True

        # Klingelton spielen
        self.speaker_tone_subprocess = Audio.play_loud(config['Sounds']['ring'], repeat=True)

    def hung_up(self):
        """Gespräch wurde (durch uns oder Gegenseite) beendet"""
        print("Anruf beendet")
        self.call_incoming = False

        # Klingeln beenden
        if self.speaker_tone_subprocess is not None:
            self.speaker_tone_subprocess.kill()

        # Falls Hörer abgehoben: Besetztton spielen
        if not self.is_hungup():
            self.earpiece_tone_subprocess = Audio.play_earpiece(config['Sounds']['waehlen_besetzt'])


async def main():
    print("Starte piphone...")
    Audio.play_loud(config['Sounds']['boot'])

    piphone = PiPhone(loop=asyncio.get_running_loop())
    print("Bereit.")

    try:
        while True:
            await asyncio.sleep(1)

    except (KeyboardInterrupt, SystemExit):
        GPIO.cleanup()
        piphone.linphone.stop_linphone()
        Audio.play_loud(config['Sounds']['shutdown']).wait()
        print("piphone beendet.")
        exit(0)

    except Exception as e:
        print(e)
        GPIO.cleanup()
        piphone.linphone.stop_linphone()
        exit(1)


if __name__ == "__main__":
    asyncio.run(main())
