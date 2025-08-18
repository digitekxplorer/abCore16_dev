// abcore16_defs.h
// Hardware definitions for the C-like preprocessor.
// This file MUST use #define syntax.

// --- Core Architectural Constants ---
#define IVT_START_ADDR 0x0002 // Start address of the Interrupt Vector Table

// NOTE: Do NOT place comment at the end of a #define line, it causes errors
// --- Programmable Interrupt Controller (PIC) Registers ---
// (R) Interrupt Request Register
#define ADDRESS_PIC_IRQ        0x1800
// (R/W) Interrupt Mask Register
#define ADDRESS_PIC_IMR        0x1802
// (R/W) In-Service Register
#define ADDRESS_PIC_ISR        0x1804
// (W) End of Interrupt Register
#define ADDRESS_PIC_EOI        0x1806

// --- Timer Peripheral Registers (Re-mapped) ---
#define ADDRESS_TIMER_CTRL     0x1808
#define ADDRESS_TIMER_PRESCALE 0x180A
#define ADDRESS_TIMER_RELOAD_L 0x180C
#define ADDRESS_TIMER_RELOAD_H 0x180E
#define ADDRESS_TIMER_COUNT_L  0x1810
#define ADDRESS_TIMER_COUNT_H  0x1812
#define ADDRESS_TIMER_STATUS   0x1814

// --- UART Peripheral Registers (Re-mapped) ---
#define ADDRESS_UART_CTRL      0x1818
#define ADDRESS_UART_STATUS    0x181A
#define ADDRESS_UART_TX_DATA   0x181C
#define ADDRESS_UART_RX_DATA   0x181E

// --- General Purpose I/O (Re-mapped) ---
#define ADDRESS_LED_CTRL       0x1820

// --- System Control (NEW) ---
#define ADDRESS_SYSTEM_CTRL    0x1822

// --- Default MMIO addresses ---
#define MMIO_OUTPUT_ADDR 0x17FF
#define MMIO_INPUT_ADDR  0x17FE
