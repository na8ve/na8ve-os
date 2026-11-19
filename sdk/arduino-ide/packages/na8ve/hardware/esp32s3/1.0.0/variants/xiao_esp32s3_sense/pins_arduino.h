/* pins_arduino.h - Seeed XIAO ESP32-S3 Sense (na8ve-os)
 *
 * Reserved system pins (microSD CS/SPI on GPIO 21, 7, 8, 9 and PDM mic on GPIO 41, 42)
 * are protected at compile time and in the board's actuator safety policy table.
 */
#ifndef Pins_Arduino_h
#define Pins_Arduino_h

#include <stdint.h>

#define NA8VE_PIN_D0  1
#define NA8VE_PIN_D1  2
#define NA8VE_PIN_D2  3
#define NA8VE_PIN_D3  4
#define NA8VE_PIN_D4  5
#define NA8VE_PIN_D5  6
#define NA8VE_PIN_D6  43
#define NA8VE_PIN_D7  44

/* Reserved system pins: microSD SPI (7, 8, 9, 21) and PDM Microphone (41, 42) */
#define NA8VE_PIN_RESERVED_MASK(pin) \
    ((pin) == 7 || (pin) == 8 || (pin) == 9 || (pin) == 21 || (pin) == 41 || (pin) == 42)

#ifdef __cplusplus
template <int Pin>
struct Na8vePinCheck {
    static_assert(!NA8VE_PIN_RESERVED_MASK(Pin),
                  "GPIO pin is reserved by na8ve-os (microSD / LED / PDM Mic) and cannot be used by a sketch.");
    static constexpr int value = Pin;
};
#define NA8VE_CHECK_PIN(pin) (Na8vePinCheck<(pin)>::value)
#endif

#endif /* Pins_Arduino_h */

