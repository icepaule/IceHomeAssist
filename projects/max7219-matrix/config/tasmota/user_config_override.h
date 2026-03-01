/*
  Custom Tasmota Build for MAX7219 LED Matrix Display
  =====================================================
  Build for: Matrix3 (ESP8266 + 8x MAX7219 8x8 LED Dot Matrix)
  Created: 2026-02-25

  IMPORTANT: The standard tasmota-display build only includes
  USE_DISPLAY_MAX7219 (7-segment) which does NOT work with
  8x8 dot matrix modules! We need USE_DISPLAY_MAX7219_MATRIX.
*/

#ifndef _USER_CONFIG_OVERRIDE_H_
#define _USER_CONFIG_OVERRIDE_H_

// -- Force MAX7219 MATRIX driver (disables 7-segment and TM1637) --
#undef USE_DISPLAY_MAX7219
#undef USE_DISPLAY_TM1637
#define USE_DISPLAY_MAX7219_MATRIX

// -- UTF8 Latin1 charset support --
#define USE_UTF8_LATIN1

#endif  // _USER_CONFIG_OVERRIDE_H_
