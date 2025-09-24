from subprocess import Popen, DEVNULL
from threading import Lock


class Audio:
    """
    Tonwiedergabe: Boot-Sound, Klingeln, usw.
    - aplay braucht eine .wav Datei und zwingend im korrekten Format (Frequenz, Kanäle, ...)
    - ffplay ist super langsam
    - mpg123 funktioniert grundsätzlich gut mit leichtem Overhead, aber nur mit .mp3
    - sox (`play`) kann alle Formate und außerdem repeat (für Klingelton), ist aber ebenfalls etwas langsamer
    """

    # Locking nötig, da sich sonst zwei nahezu gleichzeitige Prozesse in den Weg kommen können
    _earpiece_lock: Lock
    _speaker_lock: Lock

    # Laufende Wiedergabeprozesse
    _earpiece_tone_subprocess: Popen | None = None
    _speaker_tone_subprocess: Popen | None = None

    @staticmethod
    def _play(path: str, device: str, repeat: bool = False) -> Popen:
        # Simple, etwas effizientere Variante mit aplay
        if not repeat and path.endswith(".wav"):
            return Popen(['aplay', '-q', '-D', device, path])
        else:
            cmd = ['/usr/bin/play', '-q', path, '-t', 'alsa']
            if repeat:
                # Datei um eine Sekunde verlängern (=1s Pause zwischen den Wiederholungen) und 99x wiederholen (das sollte reichen...)
                cmd = [*cmd, *['pad', '0', '1', 'repeat', '99']]

            return Popen(cmd, env={'AUDIODEV': device}, stderr=DEVNULL)

    @staticmethod
    def play_speaker(path: str, repeat: bool = False) -> Popen:
        Audio._speaker_lock.acquire()
        Audio.stop_speaker()
        Audio._speaker_tone_subprocess = Audio._play(path, device="i2s", repeat=repeat)
        Audio._speaker_lock.release()
        return Audio._speaker_tone_subprocess

    @staticmethod
    def stop_speaker() -> None:
        if Audio._speaker_tone_subprocess is not None:
            Audio._speaker_tone_subprocess.kill()
            Audio._speaker_tone_subprocess = None

    @staticmethod
    def play_earpiece(path: str, repeat: bool = False) -> Popen:
        Audio._earpiece_lock.acquire()
        Audio.stop_speaker()
        Audio._earpiece_tone_subprocess = Audio._play(path, device="usb", repeat=repeat)
        Audio._earpiece_lock.release()
        return Audio._earpiece_tone_subprocess

    @staticmethod
    def stop_earpiece() -> None:
        if Audio._earpiece_tone_subprocess is not None:
            Audio._earpiece_tone_subprocess.kill()
            Audio._earpiece_tone_subprocess = None

Audio._earpiece_lock = Lock()
Audio._speaker_lock = Lock()
