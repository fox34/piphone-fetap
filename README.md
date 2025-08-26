# FeTAp611-VoIP-Tischtelefon auf Basis eines Raspberry Pi Zero 2 W

Komponenten:

- FeTAp 611, nötige Originalkomponenten: Nummernschalter und Gabelkontakt
- Raspberry Pi Zero 2 W
- Netzteil: Hi-Link 5V, 3W (600mA)
- Verstärker für Lautsprecher: MAX98357A (auf fertiger Platine für I2S)
- Lautsprecher: Visaton FR7, 4 Ohm, 5W Nennleistung
- USB-OTG-Adapter (Mikro-USB auf USB-A)
- USB-Soundkarte (einfacher/günstiger zu finden als USB-OTG-Soundkarte)
  hier: Vention = ID 0d8c:0014 C-Media Electronics, Inc. Audio Adapter (Unitek Y-247A)
- Hörer-Lautsprecher aus altem Headset
- Hörer-Mikrofon aus altem Headset

# Verkabelung

| Gerät/Funktion | Pin | GPIO | Pi-Pin-Nr. |
| :--- | :--- | ---: | ---: |
| **Hörerkontakt** | 1 | 15 | 10 |
|  | 2 | GND | 9 |
| **MAX98357** | BCLK | 18 | 12 |
|  | LRCK | 19 | 35 |
|  | DIn | 21 | 40 |
|  | GND | GND | 39 |
|  | VIn | +5V | 4 |
| **Nummernschalter** | 1 (nsi1) | GND | 14 |
|  | 2 (nsi2) | 23 | 16 |
|  | 3 (nsa1) | GND | 20 |
|  | 4 (nsa2) | 24 | 18 |

# Linux konfigurieren

## Komponenten installieren

```
sudo apt update ; sudo apt upgrade
sudo apt install git sox libsox-fmt-mp3 --no-install-recommends
sudo apt autoremove
```

## MAX98357A aktivieren

Siehe
- https://learn.pimoroni.com/article/raspberry-pi-phat-dac-install
- https://learn.adafruit.com/adafruit-max98357-i2s-class-d-mono-amp/raspberry-pi-usage

Datei `/boot/firmware/config.txt` anpassen:

```
dtparam=i2s=on
#dtparam=audio=on
dtoverlay=max98357a
```

In `/etc/modprobe.d/raspi-blacklist.conf` folgende Einträge, falls vorhanden, entfernen:

- `i2c-bcm2708`
- `snd-soc-pcm512x`
- `snd-soc-wm8804`

In `/etc/modules` den Eintrag `snd_bcm2835`, falls vorhanden, entfernen.

## Reihenfolge der Soundkarten fixieren

Siehe https://wiki.archlinux.org/title/Advanced_Linux_Sound_Architecture#Card_index

Datei `/etc/modprobe.d/alsa-base.conf` anlegen:

```
options snd slots=snd_usb_audio
```

Damit bekommt die USB-Soundkarte (Hörer) immer Index 0.

## Soundkarten konfigurieren

Datei `/etc/asound.conf` anpassen bzw. anlegen:

```
# USB als Standardgerät (nützlich für linphonec)
pcm.!default {
    type hw
    card 0
}

ctl.!default {
    type hw
    card 0
}

# USB-Soundkarte
pcm.usb {
    type hw
    card 0
    device 0
}

# MAX98357 über dmix, um parallel Stille zu senden (Knacken verhindern)
pcm.i2s_dmix {
    type dmix
    ipc_key 1024
    ipc_perm 0666  # Zugriff für alle Nutzer zulassen, optional
    slave {
        pcm {
            type hw
            card 1
            device 0
        }
        rate 48000
        channels 2
        format S32_LE
        period_time 0
        period_size 1024
        buffer_size 8192
    }
}

ctl.i2s_dmix {
    type hw
    card 1
}

# MAX98357 zusätzlich mit Softvol, um Lautstärke steuern zu können
pcm.i2s {
    type softvol
    slave.pcm i2s_dmix
    control {
        name "Lautsprecher"
        card 1
    }
    min_dB -50.0
    # Maximale Lautstärke gleich hier konfigurieren
    max_dB -18.0
    resolution 100
}

ctl.i2s {
    type hw
    card 1
}
```

## Knacken am MAX98357 bei Start einer Wiedergabe verhindern

Siehe auch: https://github.com/volumio/Volumio2/issues/1973

Systemd-Dienst z.B. in `/etc/systemd/system/i2s-silence.service` anlegen:

```
[Unit]
Description=Play silence to I2S output using dmix to avoid pop/click noise
After=sound.target

[Service]
ExecStart=/usr/bin/aplay -D i2s -t raw -r 48000 -c 2 -f S32_LE /dev/zero
Restart=always
RestartSec=1
Nice=-20

[Install]
WantedBy=multi-user.target
```

Dann aktivieren mit 
```
systemctl daemon-reload
systemctl enable --now i2s-silence.service
```

## Lautstärke festlegen und für einen Neustart speichern

Hinweis: Funktionierte bei mir nur mit der USB-Soundkarte, nicht mit dem MAX98357.

```
alsamixer
sudo alsactl store
```

## linphone

Die Dokumentation ist leider äußerst spärlich: https://wiki.linphone.org/xwiki/wiki/public/view/Linphone/

### Vorkompilierte Version

```
sudo apt install linphone-cli --no-install-recommends
```

Funktioniert, ist jedoch veraltet und nicht optimal (bringt ständig Warnungen wegen irgendwelcher Video-Funktionen)

### Konfigurieren

```
sudo mkdir -p /root/.local/share/linphone
sudo linphonec
```

In der Konsole von linphonec:

```
soundcard list
soundcard use 1  # Nummer entsprechend anpassen, nur mit default funktionierte es bei mir nicht
```

Testanruf tätigen:

```
register sip:username@hostname hostname password
call 0123456789
# [...]
terminate  # Auflegen
terminate  # linphonec beenden
```

Datei `/root/.linphonerc` gemäß Vorlage in `support/` anpassen.

## Optional: SD-Karte read-only mounten

Hinweis: Hat bei mir nicht richtig funktioniert (RAM/Swap zu klein?).

`sudo raspi-config`

- 1 -> S10 (Logging) -> None
- 4 -> P2 (OverlayFS) -> Aktivieren (Boot-Partition beschreibbar lassen, um es wieder deaktivieren zu können)
