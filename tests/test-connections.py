#!/usr/bin/python3

import RPi.GPIO as GPIO
from time import sleep

GPIO.setmode(GPIO.BCM)

pin_nsi         = 23 
pin_nsa         = 24
pin_gabel    = 15

GPIO.setup(pin_nsi, GPIO.IN, pull_up_down=GPIO.PUD_UP)
GPIO.setup(pin_nsa, GPIO.IN, pull_up_down=GPIO.PUD_UP)
GPIO.setup(pin_gabel, GPIO.IN, pull_up_down=GPIO.PUD_UP)

try:
    while True:
        dialing = not GPIO.input(pin_nsa)
        
        if dialing:
            print("  Wählvorgang, Impuls = ", end="")
            print(GPIO.input(pin_nsi), end="")
        else:
            print("         Kein Wählvorgang", end="")
        
        print(", Hörer: ", end="")
        if GPIO.input(pin_gabel):
            print("aufgelegt", end="\r")
        else:
            print("abgehoben", end="\r")
        
        if dialing:
            sleep(0.01)
        else:
            sleep(0.1)

# ctrl+c
except KeyboardInterrupt:
    print("\nStopped with keyboard interrupt!")
    GPIO.cleanup()
