/*
 * Neural Bridge haptics firmware
 * --------------------------------
 * Reference controller for the serial driver in hardware/nb_haptics.
 *
 * Protocol (115200 baud, newline terminated):
 *   PULSE <intensity 0.00-1.00> <duration_ms 10-2000>  -> OK
 *   STOP                                               -> OK
 *   PING                                               -> PONG
 *
 * WIRING / SAFETY
 * ---------------
 * Never drive a vibration motor directly from a microcontroller pin.
 * Use a MOSFET or a motor driver module, a flyback diode across the motor,
 * a separate motor supply, and a common ground with the microcontroller.
 * Check the motor's rated voltage/current before connecting it.
 *
 * This sketch is for a DC eccentric-rotating-mass (ERM) motor driven by PWM.
 * A linear resonant actuator (LRA) needs an AC/LRA driver, not a simple
 * analogWrite; adapt the output stage accordingly.
 *
 * Pin 9 is a PWM pin on an Arduino Uno/Nano. On an ESP32/ESP8266, choose a
 * safe PWM-capable pin for your board and update MOTOR_PIN.
 */

#include <Arduino.h>
#include <math.h>

const uint8_t MOTOR_PIN = 9;
const unsigned long MIN_PULSE_MS = 10;
const unsigned long MAX_PULSE_MS = 2000;

char lineBuffer[96];
size_t lineLength = 0;

bool pulseActive = false;
unsigned long pulseEndsAt = 0;

void stopMotor() {
  analogWrite(MOTOR_PIN, 0);
  pulseActive = false;
  pulseEndsAt = 0;
}

void handleLine(char *line) {
  if (strcmp(line, "PING") == 0) {
    Serial.println("PONG");
    return;
  }

  if (strcmp(line, "STOP") == 0) {
    stopMotor();
    Serial.println("OK");
    return;
  }

  float intensity = 0.0;
  int durationMs = 0;
  if (sscanf(line, "PULSE %f %d", &intensity, &durationMs) != 2) {
    Serial.println("ERR");
    return;
  }
  if (!isfinite(intensity) || durationMs <= 0) {
    Serial.println("ERR");
    return;
  }

  // Clamp defensively. The Python bridge and backend already validate, but a
  // serial line can be corrupted or sent by another tool.
  if (intensity < 0.0) intensity = 0.0;
  if (intensity > 1.0) intensity = 1.0;
  if ((unsigned long)durationMs < MIN_PULSE_MS) durationMs = MIN_PULSE_MS;
  if ((unsigned long)durationMs > MAX_PULSE_MS) durationMs = MAX_PULSE_MS;

  int pwm = (int)(intensity * 255.0 + 0.5);
  analogWrite(MOTOR_PIN, pwm);
  pulseEndsAt = millis() + (unsigned long)durationMs;
  pulseActive = true;
  Serial.println("OK");
}

void setup() {
  pinMode(MOTOR_PIN, OUTPUT);
  digitalWrite(MOTOR_PIN, LOW);
  Serial.begin(115200);
  Serial.println("READY");
}

void loop() {
  // Drain serial input even while a pulse is active so a stop command is not
  // stuck behind a long pulse.
  while (Serial.available() > 0) {
    char incoming = (char)Serial.read();
    if (incoming == '\n') {
      lineBuffer[lineLength] = '\0';
      if (lineLength > 0) handleLine(lineBuffer);
      lineLength = 0;
    } else if (incoming != '\r' && lineLength < sizeof(lineBuffer) - 1) {
      lineBuffer[lineLength++] = incoming;
    }
  }

  if (pulseActive && (long)(millis() - pulseEndsAt) >= 0) {
    stopMotor();
  }
}
