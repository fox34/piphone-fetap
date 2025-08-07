#!/usr/bin/python3

from RPi import GPIO
from time import time_ns, sleep
from threading import Timer

# Aufbauend auf
# https://github.com/antonmeyer/WaehlscheibeHID/blob/master/WaehlscheibeHID.ino
class RotaryDial:
    pinNSI = 23  # Nummern-Schalter-Impuls-Kontakt
    pinNSA = 24  # Nummern-Schalter-Arbeits- (oder Abschalte-)Kontakt
    
    sampleRate = 5  # ms
    lowPulseLimit = 20 / 5  # detection limit impulse duration low (20 / sampleRate)
    highPulseLimit = 40 / 5  # detection limit impluse duration high (40 / sampleRate)
    
    impulses = 0  # counts impulse
    counterIsRunning = False
    
    def __init__(self):
        GPIO.setmode(GPIO.BCM)
        GPIO.setup(self.pinNSI, GPIO.IN, pull_up_down=GPIO.PUD_UP)
        GPIO.setup(self.pinNSA, GPIO.IN, pull_up_down=GPIO.PUD_UP)
        print(f"Starte. NSI = {GPIO.input(self.pinNSI)}, NSA = {GPIO.input(self.pinNSA)}")
    
    
    # Wählvorgang starten
    def start(self):
        
        nsaLowCount = 0;
        nsaHighCount = 0;
        
        while True:
            
            # NSA = 0 -> Wählvorgang läuft
            if not GPIO.input(self.pinNSA):
            
                nsaHighCount = 0
                
                if nsaLowCount > 10:
                    # we have long enough a low signal
                    if not self.counterIsRunning:
                        self.counterIsRunning = True
                        Timer(self.sampleRate / 1000, self.loop).start()
                else:
                    nsaLowCount += 1
            
            else:
                # NSA = 1 -> Reset
                nsaLowCount = 0
                
                # debounce
                if nsaHighCount > 10:
                    # disc rotated to end
                    if self.counterIsRunning:
                        self.counterIsRunning = False
                        # ------- Hier Hook / Callback integrieren -------
                        print(f"Ziffer gewählt: {self.impulses} Impulse = Ziffer {self.impulses % 10}")
                        # ------- Hier Hook / Callback integrieren -------
                        self.impulses = 0
                else:
                    nsaHighCount += 1
    
    
    # Impulse zählen
    def loop(self):    
        lowPulse = 0  # count nsi period low
        highPulse = 0  # count nsi period high
        
        # Schleife alle 1ms ausführen - loop darf keine langsamen Operationen enthalten!
        lastStart = time_ns()
        while True:
            
            # Wählvorgang beendet
            if not self.counterIsRunning:
                return
            
            # Doppel-Check: Wählvorgang beendet (NSA = 1)
            #if GPIO.input(self.pinNSA):
            #    return
            
            # NSI = 0
            if not GPIO.input(self.pinNSI):
                lowPulse += 1
                if lowPulse > self.lowPulseLimit:
                    highPulse = 0 # reset the last high pulse
            
            else:
                # NSI = 1
                highPulse += 1
                if highPulse > self.highPulseLimit:
                    if lowPulse > self.lowPulseLimit:
                        self.impulses += 1
                    lowPulse = 0  # state changed to high, waiting for the next falling slope
            
            # Debugging
            #duration = (time_ns() - lastStart) / 1e6
            #print(f"took {duration}ms, waiting {(1 - duration) / 1000}")
            
            timeUntilNextIteration = (1 - (time_ns() - lastStart) / 1e6) / 1000
            if timeUntilNextIteration > 0:
                sleep(timeUntilNextIteration)
            lastStart = time_ns()
            

if __name__ == '__main__':    
    dial = RotaryDial()
    try:
        dial.start()
    except KeyboardInterrupt: # does not work if it runs in background.
        print ("\nQuit")
    GPIO.cleanup()