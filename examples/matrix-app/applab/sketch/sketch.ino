#include <Arduino.h>
#include "Arduino_RouterBridge.h"
#include <ArduinoGraphics.h>
#include <Arduino_LED_Matrix.h>

Arduino_LED_Matrix matrix;

volatile bool g_looping = false;
String g_loop_text = "";

int scroll(String text) {
    g_loop_text = text;
    g_looping = true;
    return text.length();
}

int show_char(String c) {
    g_looping = false;
    if (c.length() == 0) {
        matrix.clear();
        return 0;
    }
    matrix.clear();
    matrix.textFont(Font_5x7);
    matrix.beginText(4, 1, 127, 0, 0);
    matrix.print(c[0]);
    matrix.endText(NO_SCROLL);
    return 1;
}

int clear_matrix() {
    g_looping = false;
    g_loop_text = "";
    matrix.clear();
    return 1;
}

void setup() {
    matrix.begin();
    g_loop_text = "na8ve-os";
    g_looping = true;

    Bridge.begin();
    Bridge.provide("scroll", scroll);
    Bridge.provide("show_char", show_char);
    Bridge.provide("clear", clear_matrix);
}

void loop() {
    if (g_looping && g_loop_text.length() > 0) {
        String current = g_loop_text;
        String padded = String("   ") + current + String("   ");
        matrix.textFont(Font_5x7);
        matrix.textScrollSpeed(60);
        matrix.beginText(0, 0, 127, 0, 0);
        matrix.print(padded.c_str());
        matrix.endText(SCROLL_LEFT);
        if (g_looping) {
            delay(400);
        }
    } else {
        delay(50);
    }
}


