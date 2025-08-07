#!/usr/bin/python3

"""
> aplay -l
**** List of PLAYBACK Hardware Devices ****
card 0: Device [USB Audio Device], device 0: USB Audio [USB Audio]
  Subdevices: 1/1
  Subdevice #0: subdevice #0
card 1: MAX98357A [MAX98357A], device 0: bcm2835-i2s-HiFi HiFi-0 [bcm2835-i2s-HiFi HiFi-0]
  Subdevices: 1/1
  Subdevice #0: subdevice #0

> arecord -l
**** List of CAPTURE Hardware Devices ****
card 0: Device [USB Audio Device], device 0: USB Audio [USB Audio]
  Subdevices: 1/1
  Subdevice #0: subdevice #0
"""

import subprocess
from time import sleep

# - aplay braucht eine Datei zwingend im absolut korrekten Format...
# - ffplay ist super langsam
# - mpg123 funktioniert gut
# - sox/play ebenso, unterstützt auch WAV
def play(path, device):
    if path.endswith(".mp3")
    subprocess.Popen(['play', '-d', device, path]).wait()

def play_loud(path):
    play_on_device(path, device="alsa:device=i2s")

def play_earpiece(path):
    play_on_device(path, device="alsa:device=usb")


file = "StartupTwentiethAnniversaryMac.wav"

print("Teste Lautsprecher...")
play_loud(file)

print("Warte 1s...")
sleep(1)

print("Teste USB-Soundkarte (Hörer)...")
play_earpiece(file)
