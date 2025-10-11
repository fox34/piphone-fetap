#!/usr/bin/python3

from lib.audio import Audio
from lib.linphone import Linphone
from lib.rotarydial import RotaryDial

import argparse
import asyncio
from configparser import ConfigParser
from datetime import datetime
from getpass import getuser
from pathlib import Path
from RPi import GPIO
from signal import signal, SIGTERM, SIGINT
from os import system
import socket
from sys import exit
from threading import Timer
from time import sleep


# CLI-Argumente lesen
argparser = argparse.ArgumentParser(
    prog='PiPhone',
    description='Steuerung für Raspberry Pi-basiertes Headless-Telefon im Gehäuse alter Telefone (bspw. FeTAp). '
                'Koordiniert Hörer, Lautsprecher, Gabelkontakt, Nummernschalter und SIP-Client (linphonec).'
)
argparser.add_argument('-c', '--config', type=Path, default=Path("/boot/piphone/config.ini"),
                       help='Pfad zur Konfigurationsdatei (Standard: %(default)s)')
argparser.add_argument('--ignore-dnd', action='store_true', help='Nicht stören für Testzwecke deaktivieren')
argparser.add_argument('-v', '--verbose', action='store_true', help='Ausführliches Logging aktivieren')
args = argparser.parse_args()

if not args.config.exists():
    raise Exception(f"Konfigurationsdatei {args.config} nicht gefunden.")

# Konfiguration lesen
config = ConfigParser()
config.read(args.config)

if args.ignore_dnd:
    config.set('SIP', 'dnd_from', "0")
    config.set('SIP', 'dnd_to', "0")


class PiPhone:
    
    # Instanzen
    loop: asyncio.AbstractEventLoop
    dial: RotaryDial
    linphone: Linphone | None = None

    # Tasks, Timer und Prozesse
    wifi_test_task: asyncio.Task
    dialing_timeout: Timer | None = None

    # Zustandsvariablen
    first_boot: bool = True  # Erster Startvorgang: Bootsound abspielen, sobald linphonec gestartet wurde
    is_connected: bool = False
    call_incoming: bool = False
    declined_incoming_call: bool = False
    terminate_requested: bool = False
    
    def __init__(self, loop: asyncio.AbstractEventLoop):
        """Haupt-Programm starten"""
        print(f"Starte PiPhone als {getuser()}...")

        # Event-Loop speichern
        self.loop = loop

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
            if args.verbose:
                print("Gabel ist während des Startvorgangs abgehoben, spiele Besetztton.")
            self.cancel_dialing()

        # WLAN-Verbindung und linphonec überwachen
        asyncio.create_task(self.watchdog())

        # Registrierte Rufnummern loggen
        print("Registrierte Zielrufnummern:")
        for (number, action) in config['Numbers'].items():
            print(f" - {number} -> {action}")

        print("Bereit.")

    def handle_sigterm(self, _, __) -> None:
        """SIGTERM/SIGINT empfangen und Programm sauber beenden"""
        print("\nSIGTERM/SIGINT empfangen, beende.")
        if self.dialing_timeout is not None:
            self.dialing_timeout.cancel()
        raise SystemExit()

    def start_linphonec(self) -> None:
        self.linphone = Linphone(
            hostname=config['SIP']['host'],
            username=config['SIP']['user'],
            password=config['SIP']['pass'],
            on_boot=self.linphone_booted,
            on_incoming_call=self.incoming_call,
            on_hang_up=self.hung_up,
            verbose=args.verbose
        )

    async def watchdog(self) -> None:
        """WLAN-Verbindung (und linphonec) periodisch prüfen"""
        await asyncio.sleep(1)
        socket.setdefaulttimeout(1)
        while True:

            # linphonec-Prozess überwachen
            if self.linphone is not None and not self.linphone.is_running():
                self.linphone = None

            # WLAN prüfen
            try:
                with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
                    sock.connect((config['Network']['wifi_test_host'], 80))

                # Verbindung ist verfügbar (sonst: TimeoutError/OSError)

                # Verbindung war zuvor nicht verfügbar (oder es handelt sich um den ersten Startvorgang)
                if not self.is_connected:
                    print("WLAN-Verbindung verfügbar.")
                    self.is_connected = True

                # linphonec (neu) starten
                if self.linphone is None:
                    self.start_linphonec()

                # Alle 60s prüfen
                await asyncio.sleep(60)

            except (TimeoutError, OSError):
                # Verbindung war zuvor verfügbar
                if self.is_connected:
                    self.is_connected = False
                    print("WLAN-Verbindung wurde getrennt.")

                    # linphonec beenden
                    if self.linphone is not None:
                        self.linphone.terminate()
                        self.linphone = None

                await asyncio.sleep(1)

    @staticmethod
    def is_hungup() -> bool:
        """Prüfe, ob Hörer auf Gabel liegt (aufgelegt ist)"""
        return GPIO.input(config['Pins'].getint('gabel'))

    def watch_hook(self, _) -> None:
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
            if not self.is_connected or self.linphone is None or not self.linphone.is_running():
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

    def cancel_dialing(self) -> None:
        """Timer: Wählvorgang nach einer Minute automatisch abbrechen"""
        print("Wählvorgang nach Timeout automatisch abgebrochen.")
        self.dial.end_dialing()
        Audio.play_earpiece(config['Sounds']['waehlen_besetzt'], repeat=True)

    def receive_number(self, number: str) -> None:
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
                sleep(0.5)
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

    def linphone_booted(self) -> None:
        """Callback: linphonec gestartet"""
        if self.first_boot:
            self.first_boot = False
            Audio.play_speaker(config['Sounds']['boot'])

    def incoming_call(self, caller: str) -> None:
        """Callback: Eingehender Anruf"""
        print(f"Eingehender Anruf von {caller}")

        # Hörer ist abgehoben / Klingelsperre
        now = datetime.now()
        if (
                not self.is_hungup() or                                 # Hörer ist abgehoben
                (0 < now.hour <= config['SIP'].getint("dnd_to")) or     # Nicht stören: Morgens
                (0 < config['SIP'].getint("dnd_from") <= now.hour)      # Nicht stören: Abends
        ):
            print("Hörer ist abgehoben oder Klingelsperre ist aktiv: weise Anruf ab")
            self.declined_incoming_call = True  # Nötig für hung_up()
            self.linphone.hangup()
            return

        # Whitelist ist aktiv
        if (
            config['SIP'].getboolean("whitelist_active") == True
        ):
            print("Whitelsit aktiv, prüfe Anrufer.")
            if self._caller_in_numbers(caller) is False:
                print("Anrufer nicht in hinterlegten Nummbern: weise Anruf ab")
                self.declined_incoming_call = True  # Nötig für hung_up()
                self.linphone.hangup()
                return
        

        self.call_incoming = True

        # Klingelton spielen
        try:
            Audio.play_speaker(config['Ringtones'][caller], repeat=True)
        except KeyError:
            Audio.play_speaker(config['Sounds']['ring'], repeat=True)

    def _caller_in_numbers(self, caller: str) -> bool:
        number_keys = config['Numbers']
        numbers = []
        for key in number_keys:
            numbers.append(number_keys[key])

        if caller in numbers:
            return True
        
        return False

    def hung_up(self) -> None:
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


async def main() -> None:
    piphone = PiPhone(loop=asyncio.get_running_loop())
    try:
        while True:
            await asyncio.sleep(0.1)

    except (KeyboardInterrupt, SystemExit):
        GPIO.cleanup()
        piphone.linphone.terminate()
        Audio.play_speaker(config['Sounds']['shutdown']).wait()
        print("PiPhone beendet.")
        exit(0)

    except Exception as e:
        print(e)
        GPIO.cleanup()
        piphone.linphone.terminate()
        exit(1)


if __name__ == "__main__":
    asyncio.run(main())
