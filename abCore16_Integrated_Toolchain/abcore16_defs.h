// abcore16_defs.h
// Hardware definitions for the C-like preprocessor.
// This file MUST use #define syntax.

#define ADDRESS_TIMER_CTRL     0x1800
#define ADDRESS_TIMER_PRESCALE 0x1802
#define ADDRESS_TIMER_RELOAD_L 0x1804
#define ADDRESS_TIMER_RELOAD_H 0x1806
#define ADDRESS_TIMER_COUNT_L  0x1808
#define ADDRESS_TIMER_COUNT_H  0x180A
#define ADDRESS_TIMER_STATUS   0x180C
#define ADDRESS_UART_CTRL      0x1810
#define ADDRESS_UART_STATUS    0x1812
#define ADDRESS_UART_TX_DATA   0x1814
#define ADDRESS_UART_RX_DATA   0x1816
#define ADDRESS_LED_CTRL       0x1818

// You can also include core architectural constants here
// to have a single header for everything.
#define MMIO_OUTPUT_ADDR 0x17FF
#define MMIO_INPUT_ADDR  0x17FE
