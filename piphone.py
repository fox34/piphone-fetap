#!/usr/bin/python3

from audio import Audio
from linphone import Linphone
from rotarydial import RotaryDial

import asyncio
from configparser import ConfigParser
from datetime import datetime
from getpass import getuser
from RPi import GPIO
from signal import signal, SIGTERM, SIGINT
from os import system
import socket
from sys import exit
from threading import Timer
from time import sleep

config = ConfigParser()
config.read("/boot/piphone/config.ini")

class PiPhone:
    
    # Instanzen
    loop: asyncio.AbstractEventLoop
    dial: RotaryDial
    linphone: Linphone

    # Tasks, Timer und Prozesse
    wifi_test_task: asyncio.Task
    dialing_timeout: Timer | None = None

    # Zustandsvariablen
    is_connected: bool = False
    call_incoming: bool = False
    declined_incoming_call: bool = False
    terminate_requested: bool = False
    
    def __init__(self, loop: asyncio.AbstractEventLoop):
        """Haupt-Programm starten"""
        print(f"Starte piphone als {getuser()}...")
        Audio.play_speaker(config['Sounds']['boot'])

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

        # Falls beim booten direkt der Hörer abgehoben ist: Besetztton spielen
        if not self.is_hungup():
            self.cancel_dialing()

        # Linphone
        self.linphone = Linphone(
            hostname = config['SIP']['host'],
            username = config['SIP']['user'],
            password = config['SIP']['pass'],
            on_incoming_call=self.incoming_call,
            on_hang_up=self.hung_up
        )
        self.linphone.start()
        print("Bereit.")


    def handle_sigterm(self, _, __):
        """SIGTERM/SIGINT empfangen und Programm sauber beenden"""
        print("\nSIGTERM/SIGINT empfangen, beende.")
        if self.dialing_timeout is not None:
            self.dialing_timeout.cancel()
        Audio.play_speaker(config['Sounds']['shutdown']).wait()
        raise SystemExit()

    async def check_wifi(self):
        """WLAN-Verbindung periodisch prüfen"""
        await asyncio.sleep(2)
        socket.setdefaulttimeout(1)
        while True:
            try:
                with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
                    sock.connect((config['Network']['wifi_test_host'], 80))
                #print("WLAN-Verbindung verfügbar.")
                self.is_connected = True
                await asyncio.sleep(60)

            except (TimeoutError, OSError):
                print("WLAN-Verbindung nicht hergestellt")
                Audio.play_speaker(config['Sounds']['wlan_nicht_verbunden'])
                self.is_connected = False
                await asyncio.sleep(5)

    @staticmethod
    def is_hungup() -> bool:
        """Prüfe, ob Hörer auf Gabel liegt (aufgelegt ist)"""
        return GPIO.input(config['Pins'].getint('gabel'))

    def watch_hook(self, _):
        """Callback/Hook: Gabelkontakt hat ausgelöst"""

        if self.is_hungup():
            # Hörer wurde soeben aufgelegt
            print("Hörer aufgelegt")

            # Wählvorgang beenden, falls aktiv
            self.dial.end_dialing()
            if self.dialing_timeout is not None:
                self.dialing_timeout.cancel()

            # Wiedergabe (Freizeichen, Besetzt, usw.) im Hörer stoppen
            Audio.stop_earpiece()

            # Auflegen
            if self.linphone is not None:
                self.linphone.hangup()

            # Zustand zurücksetzen
            self.declined_incoming_call = False

        else:
            # Hörer wurde soeben abgehoben
            print("Hörer abgehoben")

            # WLAN nicht verbunden - keine weitere Aktion
            if not self.is_connected:
                Audio.play_earpiece(config['Sounds']['waehlen_nicht_verbunden'])
                return

            # Eingehender Anruf
            if self.call_incoming:
                # Wiedergabe im Hörer (nur zur Sicherheit; hier sollte nichts laufen) und Klingeln stoppen
                Audio.stop_earpiece()
                Audio.stop_speaker()

                # Anruf annehmen
                self.linphone.answer()

            else:
                # Freizeichen im Hörer abspielen
                Audio.play_earpiece(config['Sounds']['waehlen_frei'])

                # Nummernschalter überwachen
                asyncio.run_coroutine_threadsafe(self.dial.start_dialing(), self.loop)

                # Timeout
                self.dialing_timeout = Timer(config['SIP'].getint('dial_timeout'), self.cancel_dialing)
                self.dialing_timeout.start()

    def cancel_dialing(self):
        """Timer: Wählvorgang nach einer Minute automatisch abbrechen"""
        print("Wählvorgang nach Timeout automatisch abgebrochen.")
        self.dial.end_dialing()
        Audio.play_earpiece(config['Sounds']['waehlen_besetzt'], repeat=True)

    def receive_number(self, number: str):
        """
        Callback: Ziffernfolge von rotarydial empfangen -> mit gespeicherten Kurzwahlen/Befehlen abgleichen
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
                Audio.play_earpiece(config['Sounds']['waehlen_ungueltig'])

            return

        print(f"Gewählt: {number} -> {action}")
        self.dial.end_dialing()
        self.dialing_timeout.cancel()
        Audio.stop_earpiece()

        match action:
            case "test-loudspeaker":
                Audio.play_speaker(config['Sounds']['test_loud']).wait()
                sleep(1)
                if not self.is_hungup():
                    # Hörer noch nicht aufgelegt
                    Audio.play_earpiece(config['Sounds']['waehlen_besetzt'])

            case "test-earpiece":
                Audio.play_earpiece(config['Sounds']['test_earpiece']).wait()
                sleep(1)
                if not self.is_hungup():
                    # Hörer noch nicht aufgelegt
                    Audio.play_earpiece(config['Sounds']['waehlen_besetzt'])

            case "reboot":
                Audio.play_speaker(config['Sounds']['reboot']).wait()
                system("systemctl reboot -i")
                raise SystemExit()

            case "shutdown":
                Audio.play_speaker(config['Sounds']['shutdown']).wait()
                system("systemctl poweroff -i")
                raise SystemExit()

            case _:
                print(f"Rufe Nummer an: {action}")
                self.linphone.call(action)

    def incoming_call(self, caller: str):
        """Callback: Eingehender Anruf"""
        print(f"Eingehender Anruf von {caller}")

        # Hörer ist abgehoben / Klingelsperre
        now = datetime.now()
        if (
                not self.is_hungup() or                                 # Hörer ist abgehoben
                (now.hour <= config['SIP'].getint("dnd_to")) or         # Nicht stören: Morgens
                (0 < config['SIP'].getint("dnd_from") <= now.hour)      # Nicht stören: Abends
        ):
            print("Hörer ist abgehoben oder Klingelsperre ist aktiv: weise Anruf ab")
            self.declined_incoming_call = True  # Nötig für hung_up()
            self.linphone.hangup()
            return

        self.call_incoming = True

        # Klingelton spielen
        try:
            Audio.play_speaker(config['Ringtones'][caller], repeat=True)
        except KeyError:
            Audio.play_speaker(config['Sounds']['ring'], repeat=True)

    def hung_up(self):
        """Callback: Gespräch wurde (durch uns oder Gegenseite) beendet"""
        print("Anruf beendet")
        self.call_incoming = False

        # Anruf wurde durch uns abgewiesen, da Hörer bereits abgehoben war - hier nichts weiter tun
        if self.declined_incoming_call:
            self.declined_incoming_call = False
            return

        # Klingeln beenden
        Audio.stop_speaker()

        # Falls Hörer abgehoben: Besetztton spielen
        if not self.is_hungup():
            Audio.play_earpiece(config['Sounds']['waehlen_besetzt'])


async def main():
    piphone = PiPhone(loop=asyncio.get_running_loop())
    try:
        while True:
            await asyncio.sleep(0.1)

    except (KeyboardInterrupt, SystemExit):
        GPIO.cleanup()
        piphone.linphone.stop_linphone()
        Audio.play_speaker(config['Sounds']['shutdown']).wait()
        print("piphone beendet.")
        exit(0)

    except Exception as e:
        print(e)
        GPIO.cleanup()
        piphone.linphone.stop_linphone()
        exit(1)


if __name__ == "__main__":
    asyncio.run(main())
