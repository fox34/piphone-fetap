# Project overview

This is a headless python 7.13 application that runs on a Raspberry Pi Zero 2W inside a historical rotary dial phone.

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
- Night mode (immediately enables amber LED)
- Wake up mode (enables green LED in the morning)
- Sleep music (plays music for a set amount of time)
- Loudspeaker and earpiece tests
- Shutdown
- Reboot

Calling and other features are performed/toggled via short codes, entered with the rotary dial.
A sample feature-complete configuration file is provided in support/config-example.toml.

# Web interface

An optional, dependency-free web server (`lib/webserver.py`) shows the phone status (uptime, connectivity,
call state) and the state of the features (night light, wake up mode, sleep music, dnd, next wake up time).
It is configured in the `[web]` section of the TOML config file (port 0 = disabled) and can also be disabled
with `--no-web`. The same actions as the rotary dial short codes can be triggered via
`POST /api/action/<name>`, the state is available as JSON under `/api/state`.

# Configuration

`lib/config.py` is the single source of truth for the TOML config file. It holds the schema of every
option (type, default value, description, limits) and provides reading, validation and writing.
`support/config-example.toml` is a documented sample.

The config file can also be edited in the browser at `/config`, which covers every option. Numbers
(dial codes and their targets in `[numbers]`) and ringtones are addable and removable tables. The
schema is rendered dynamically into forms by the JS in `lib/webserver.py`, so adding an option to
`lib/config.py` makes it appear in the UI automatically.

Changes are never applied to the running process and never trigger a restart; the UI points out
that a restart is required. Writing the file regenerates all comments from the schema, so comments
written by hand in the file are not preserved. Values the schema does not know are kept as-is.
