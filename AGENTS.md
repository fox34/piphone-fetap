# Project overview

This is a headless python application that runs on a Raspberry Pi Zero 2W inside a historical rotary dial phone.

# Hardware

- MAX98357A amplifier + speaker for ringtones and music
- A generic USB Soundcard connected to the earpiece and microphone for phone calls
- One amber-colored LED in the back, used as night-light
- One green status LED on the front

# Software

- This project runs on Raspberry Pi OS
- Outgoing/Incoming calls (SIP) are performed via `linphonec`

# Features

- Outgoing calls
- Incoming calls
- Outgoing call duration limit
- Incoming number whitelist
- Do not disturb
- Night mode (enable night light)
- Sleep music (plays music for a set amount of time)
- Loudspeaker and earpiece tests
- Shutdown
- Reboot

Calling and other features are performed/toggled via short codes, entered with the rotary dial.
A sample feature-complete configuration file is provided in support/config-example.ini.
