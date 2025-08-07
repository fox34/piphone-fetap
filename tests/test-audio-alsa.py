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

import alsaaudio
import wave
from time import sleep

file = "StartupTwentiethAnniversaryMac.wav"
wav = wave.open(file)

audioUSB = alsaaudio.PCM(device="usb")
#audioUSB_mix = alsaaudio.Mixer(control='Speaker',cardindex=0)
#audioUSB_mix.setvolume(50)
audioUSB.setchannels(wav.getnchannels())
audioUSB.setrate(wav.getframerate())
audioUSB.setperiodsize(320)

print("Teste USB-Soundkarte (Hörer)...")
data = wav.readframes(320)
while data:
    audioUSB.write(data)
    data = wav.readframes(320)

wav.rewind()

print("Warte 2s...")
sleep(2)
print("Teste Lautsprecher...")

audioMAX98357 = alsaaudio.PCM(device="i2s")
#audioMAX98357_mix = alsaaudio.Mixer(control='PCM',cardindex=1)
#audioMAX98357_mix.setvolume(25)
#audioMAX98357.setchannels(wav.getnchannels())
#audioMAX98357.setrate(wav.getframerate())
#audioMAX98357.setperiodsize(320)

data = wav.readframes(320)
while data:
    audioMAX98357.write(data)
    data = wav.readframes(320)
wav.rewind()
wav.close()
