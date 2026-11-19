/*
 * sketch/sketch.ino - na8ve-os Developer SDK STM32U585 Reference Coprocessor Sketch
 *
 * Receives policy-approved actuation commands over Arduino_RouterBridge
 * and updates GPIO outputs and the LED Matrix.
 */

#include <Arduino_RouterBridge.h>
#include <Arduino_LED_Matrix.h>

Arduino_LED_Matrix matrix;

static const uint32_t GLYPH_SDK_READY[4] = {
    0x00182442,
    0x42241800,
    0x00000000,
    0x00000000
};

void on_fan(String state) {
    (void)state;
    matrix.loadFrame(GLYPH_SDK_READY);
}

void on_light(String state) {
    (void)state;
    digitalWrite(LED_BUILTIN, HIGH);
}

void on_matrix_glyph(String glyph_name) {
    (void)glyph_name;
    matrix.loadFrame(GLYPH_SDK_READY);
}

void setup() {
    pinMode(LED_BUILTIN, OUTPUT);
    matrix.begin();
    Bridge.begin();
    Bridge.provide("fan", on_fan);
    Bridge.provide("light", on_light);
    Bridge.provide("matrix.glyph", on_matrix_glyph);
}

void loop() {
    delay(50);
}

