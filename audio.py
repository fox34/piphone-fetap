from subprocess import Popen, DEVNULL

class Audio:
    """
    Tonwiedergabe: Boot-Sound, Klingeln, usw.
    - aplay braucht eine .wav Datei und zwingend im korrekten Format (Frequenz, Kanäle, ...)
    - ffplay ist super langsam
    - mpg123 funktioniert grundsätzlich gut mit leichtem Overhead, aber nur mit .mp3
    - sox (`play`) kann alle Formate und außerdem repeat (für Klingelton)
    """

    @staticmethod
    def play(path: str, device: str, repeat: bool = False) -> Popen:
        # Simple, schnelle Variante mit aplay
        if not repeat and path.endswith(".wav"):
            return Popen(['aplay', '-q', '-D', device, path])
        else:
            cmd = ['/usr/bin/play', '-q', path, '-t', 'alsa']
            if repeat:
                # Datei um eine Sekunde verlängern (=1s Pause zwischen den Wiederholungen) und 99x wiederholen (das sollte reichen...)
                cmd = [*cmd, *['pad', '0', '1', 'repeat', '99']]

            return Popen(cmd, env={'AUDIODEV': device}, stderr=DEVNULL)



    @staticmethod
    def play_loud(path: str, repeat: bool = False) -> Popen:
        return Audio.play(path, device="i2s", repeat=repeat)

    @staticmethod
    def play_earpiece(path: str, repeat: bool = False) -> Popen:
        return Audio.play(path, device="usb", repeat=repeat)
