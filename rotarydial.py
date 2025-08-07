#!/usr/bin/python3

from audio import Audio

from RPi import GPIO
from time import time_ns, sleep
from threading import Timer
from typing import Final


# Aufbauend auf https://github.com/antonmeyer/WaehlscheibeHID/blob/master/WaehlscheibeHID.ino
class RotaryDial:

    # Konstanten
    SAMPLE_RATE: Final[int] = 5  # ms
    LOW_PULSE_DURATION: Final[int] = 20 / 5  # detection limit impulse duration low (20 / sampleRate)
    HIGH_PULSE_DURATION: Final[int] = 40 / 5  # detection limit impluse duration high (40 / sampleRate)

    # Konfiguration
    pin_nsi: int  # Nummern-Schalter-Impuls-Kontakt
    pin_nsa: int  # Nummern-Schalter-Arbeits- (oder Abschalte-)Kontakt
    receive_number_callback: callable

    # Zustand
    dialing: bool = False
    current_number: str
    impulses: int
    impulse_counter_is_running: bool = False

    def __init__(self, pin_nsi: int, pin_nsa: int, receive_number_callback: callable):
        self.pin_nsi = pin_nsi
        self.pin_nsa = pin_nsa
        self.receive_number_callback = receive_number_callback

        # GPIO.setmode(GPIO.BCM)  # Voraussetzung - Bereits in piphone.py erledigt
        GPIO.setup(self.pin_nsi, GPIO.IN, pull_up_down=GPIO.PUD_UP)
        GPIO.setup(self.pin_nsa, GPIO.IN, pull_up_down=GPIO.PUD_UP)

    async def start_dialing(self):
        """Wählvorgang starten"""

        #print("Starte Wählvorgang")
        self.dialing = True
        self.current_number = ""
        nsa_low_count = 0
        nsa_high_count = 0
        self.impulses = 0
        
        while self.dialing:

            # NSA = 0 -> Wählvorgang läuft
            if not GPIO.input(self.pin_nsa):
            
                nsa_high_count = 0
                
                if nsa_low_count > 10:
                    # we have long enough a low signal
                    if not self.impulse_counter_is_running:
                        self.impulse_counter_is_running = True
                        Timer(self.SAMPLE_RATE / 1000, self.count_impulses).start()
                else:
                    nsa_low_count += 1
            
            else:
                # NSA = 1 -> Reset
                nsa_low_count = 0
                
                # debounce
                if nsa_high_count > 10:
                    # disc rotated to end
                    if self.impulse_counter_is_running:
                        self.impulse_counter_is_running = False
                        #print(f"Ziffer gewählt: {self.impulses} Impulse = Ziffer {self.impulses % 10}")
                        self.current_number += str(self.impulses % 10)
                        self.receive_number_callback(self.current_number)
                        self.impulses = 0
                else:
                    nsa_high_count += 1

        #print("Wählvorgang beendet")

    def end_dialing(self):
        """Wählvorgang sanft beenden"""
        if self.dialing:
            #print("Beende Wählvorgang...")
            self.dialing = False

    def count_impulses(self):
        """Impulse zählen"""

        low_pulse = 0  # count nsi period low
        high_pulse = 0  # count nsi period high
        
        # Schleife alle 1ms ausführen - loop darf keine langsamen Operationen enthalten!
        last_start = time_ns()
        while True:
            
            # Wählvorgang beendet
            if not self.impulse_counter_is_running:
                return
            
            # Doppel-Check: Wählvorgang beendet (NSA = 1)
            #if GPIO.input(self.pinNSA):
            #    return
            
            # NSI = 0
            if not GPIO.input(self.pin_nsi):
                low_pulse += 1
                if low_pulse > self.LOW_PULSE_DURATION:
                    high_pulse = 0 # reset the last high pulse
            
            else:
                # NSI = 1
                high_pulse += 1
                if high_pulse > self.HIGH_PULSE_DURATION:
                    if low_pulse > self.LOW_PULSE_DURATION:
                        self.impulses += 1
                    low_pulse = 0  # state changed to high, waiting for the next falling slope
            
            # Debugging
            #duration = (time_ns() - last_start) / 1e6
            #print(f"took {duration}ms, waiting {(1 - duration) / 1000}")
            
            time_until_next_iteration = (1 - (time_ns() - last_start) / 1e6) / 1000
            if time_until_next_iteration > 0:
                sleep(time_until_next_iteration)

            last_start = time_ns()

    def gather_number(self, number: int):
        """Gewählte Nummer merken"""
        self.current_number += str(number)
