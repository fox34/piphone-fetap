from RPi import GPIO

class Led:

    verbose: bool

    # Nachtlicht
    night_light_pin: int | None = None
    night_light_duty: int
    night_light_pwm: GPIO.PWM | None = None

    # Aufwachlicht
    wake_light_pin: int | None = None
    wake_light_duty: int
    wake_light_pwm: GPIO.PWM | None = None

    def __init__(
            self,
            night_light_pin: int,
            night_light_duty: int,
            wake_light_pin: int,
            wake_light_duty: int,
            verbose: bool
    ):
        self.verbose = verbose

        # Nachtlicht einrichten
        if night_light_pin > 0:
            if self.verbose:
                print(f"Initialisiere Nachtlicht mit Duty {night_light_duty}% an Pin {night_light_pin}.")

            self.night_light_pin = night_light_pin
            self.night_light_duty = night_light_duty
            GPIO.setup(night_light_pin, GPIO.OUT)
            GPIO.output(night_light_pin, False)

        # Aufwachlicht einrichten
        if wake_light_pin > 0:
            if self.verbose:
                print(f"Initialisiere Aufwachlicht mit Duty {wake_light_duty}% an Pin {wake_light_pin}.")

            self.wake_light_pin = wake_light_pin
            self.wake_light_duty = wake_light_duty
            GPIO.setup(wake_light_pin, GPIO.OUT)
            GPIO.output(wake_light_pin, False)

    def night_light_on(self, duty_cycle: int | None = None):
        if self.night_light_pin is None:
            return

        if self.night_light_pwm is not None:
            self.night_light_pwm.stop()
            self.night_light_pwm = None

        print(self.night_light_pin, self.night_light_pwm, self.verbose)
        if self.verbose:
            print(f"Schalte Nachtlicht mit Duty {duty_cycle or self.night_light_duty}% ein.")

        if duty_cycle is not None or self.night_light_duty < 100:
            self.night_light_pwm = GPIO.PWM(self.night_light_pin, frequency=8000)
            self.night_light_pwm.start(duty_cycle or self.night_light_duty)
        else:
            GPIO.output(self.night_light_pin, True)

    def night_light_off(self):
        if self.night_light_pin is None:
            return

        if self.verbose:
            print("Schalte Nachtlicht ab.")

        if self.night_light_pwm is not None:
            self.night_light_pwm.stop()
            self.night_light_pwm = None

        GPIO.output(self.night_light_pin, False)

    def wake_light_on(self, duty_cycle: int | None = None):
        if self.wake_light_pin is None:
            return

        if self.wake_light_pwm is not None:
            self.wake_light_pwm.stop()
            self.wake_light_pwm = None

        if self.verbose:
            print(f"Schalte Aufwachlicht mit Duty {duty_cycle or self.night_light_duty}% ein.")

        if duty_cycle is not None or self.wake_light_duty < 100:
            self.wake_light_pwm = GPIO.PWM(self.wake_light_pin, frequency=8000)
            self.wake_light_pwm.start(duty_cycle or self.wake_light_duty)
        else:
            GPIO.output(self.wake_light_pin, True)

    def wake_light_blink(self):
        """Aufwachlicht Zeitweise als Signallicht einschalten"""
        if self.wake_light_pin is None:
            return

        if self.wake_light_pwm is not None:
            self.wake_light_pwm.stop()
            self.wake_light_pwm = None

        if self.verbose:
            print(f"Schalte Aufwachlicht als Signalleuchte ein.")

        self.wake_light_pwm = GPIO.PWM(self.wake_light_pin, frequency=1)
        self.wake_light_pwm.start(50)

    def wake_light_off(self):
        if self.wake_light_pin is None:
            return

        if self.verbose:
            print("Schalte Aufwachlicht ab.")

        if self.wake_light_pwm is not None:
            self.wake_light_pwm.stop()
            self.wake_light_pwm = None

        GPIO.output(self.wake_light_pin, False)
