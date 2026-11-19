/*
 * sketch/sketch.ino - the greenhouse's STM32U585 coprocessor sketch.
 *
 * The LED matrix shows what the greenhouse's dashboard shows: the Linux side reads the dashboard's
 * own stream and sends a line here ("show") whenever it changes, which scrolls until the next one.
 * The actuator handlers are the board's policy-approved actuations: they set the outputs and leave
 * the matrix to the stream, so nothing on it is a fixed pattern.
 */

#include <Arduino.h>
#include <Arduino_RouterBridge.h>
#include <ArduinoGraphics.h>
#include <Arduino_LED_Matrix.h>

Arduino_LED_Matrix matrix;

String g_line = "greenhouse";

int show(String line) {
    g_line = line.length() ? line : String("greenhouse");
    return g_line.length();
}

void on_light(String state) {
    digitalWrite(LED_BUILTIN, state == "on" ? HIGH : LOW);
}

void on_actuator(String state) {
    (void)state;
}

void setup() {
    pinMode(LED_BUILTIN, OUTPUT);
    matrix.begin();
    Bridge.begin();
    Bridge.provide("show", show);
    Bridge.provide("light", on_light);
    Bridge.provide("fan", on_actuator);
    Bridge.provide("mister", on_actuator);
    Bridge.provide("buzzer", on_actuator);
    Bridge.provide("matrix.glyph", on_actuator);
}

void loop() {
    matrix.textFont(Font_5x7);
    matrix.textScrollSpeed(60);
    matrix.beginText(0, 1, 127, 0, 0);
    matrix.print("  " + g_line + "  ");
    matrix.endText(SCROLL_LEFT);
}
