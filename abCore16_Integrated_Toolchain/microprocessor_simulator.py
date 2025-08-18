# microprocessor_simulator.py
# FINAL CORRECTED VERSION with bytearray memory and char opcodes.
# This version implements the hardware-accurate word-addressing scheme (address >> 1),
# the hardware-accurate little-endian data format, and a simulated
# Programmable Interrupt Controller (PIC) for interrupt support.

import sys
from abcore16_defs import (
    REVERSE_OPCODES, REG_NAMES, INSTRUCTION_FORMATS,
    DEFAULT_MMIO_INPUT_ADDR, DEFAULT_MMIO_OUTPUT_ADDR,
    MAX_ADDRESS_16BIT, MAX_IMMEDIATE_16BIT, IVT_START_ADDR,
    HARDWARE_DATA_MEM_SIZE_BYTES
)

# --- NEW INTERRUPT SUPPORT: Manually define PIC and re-mapped peripheral addresses ---
# This mirrors abcore16_defs.h and avoids circular dependencies or complex parsing.
# --- NEW INTERRUPT SUPPORT: PIC addresses as WORD addresses ---
ADDRESS_PIC_IRQ = 0x0C00    # 0x1800 >> 1
ADDRESS_PIC_IMR = 0x0C01    # 0x1802 >> 1
ADDRESS_PIC_ISR = 0x0C02    # 0x1804 >> 1
ADDRESS_PIC_EOI = 0x0C03    # 0x1806 >> 1
ADDRESS_TIMER_STATUS = 0x0C0A  # 0x1814 >> 1
ADDRESS_UART_STATUS = 0x0C0D   # 0x181A >> 1
ADDRESS_UART_RX_DATA = 0x0C0F  # 0x181E >> 1
ADDRESS_LED_CTRL = 0x0C10      # 0x1820 >> 1


class MicroprocessorSimulator:
    def __init__(self, data_memory_size=HARDWARE_DATA_MEM_SIZE_BYTES, stack_size=256, program_memory_capacity=65536):
        # Registers & memory
        self.registers = {reg_name: 0 for reg_name in REG_NAMES.values()}
        self.data_memory_size = data_memory_size
        self.data_memory = bytearray(self.data_memory_size)

        # --- STACK SETUP ---
        # Stack starts at the highest valid word's low-byte index (descending stack)
        self.stack_base = self.data_memory_size - 2

        # Ensure at least 2 words (4 bytes) for interrupt context (PC + FLAGS)
        min_words_for_interrupt = 2
        effective_stack_words = max(stack_size, min_words_for_interrupt)

        # stack_limit = lowest usable byte index (stack grows down toward this)
        self.stack_limit = self.stack_base - (effective_stack_words * 2)

        # Initialize SP to top of stack
        self.sp = self.stack_base

        # --- CPU STATE ---
        self.program_counter = 0
        self.program_bytes = []
        self.program_memory_capacity = program_memory_capacity
        self.ZF = self.SF = self.CF = self.OF = False
        self.halted = False
        self.clean_halt = False
        self.sim_input_buffer = None
        self.sim_last_output_value = None
        self.mmio_output_lines = []

        # --- INTERRUPT STATE ---
        self.IE = False            # Interrupt Master Enable flag
        self.pic_irq = 0           # Interrupt Request Register (pending IRQs)
        self.pic_imr = 0           # Interrupt Mask Register (enabled IRQs)
        self.pic_isr = 0           # In-Service Register (currently servicing IRQs)
        self.sim_peripheral_irq_pending = {}  # Pending IRQs from peripherals

        # --- LOG STARTUP STATE ---
        self.output_log = [
            f"--- Sim Start (DataMemBytes:{len(self.data_memory)}, "
            f"StackBase:0x{self.stack_base:04X}h, StackLimit:0x{self.stack_limit:04X}h, "
            f"SP init:0x{self.sp:04X}h) ---",
            f"    MMIO In: {DEFAULT_MMIO_INPUT_ADDR:04X}h, MMIO Out: {DEFAULT_MMIO_OUTPUT_ADDR:04X}h"
        ]


    def _reset_state(self):
        self.registers = {reg_name: 0 for reg_name in REG_NAMES.values()}
        self.data_memory = bytearray(self.data_memory_size)
        #self.sp = self.stack_base - 2

        self.sp = self.stack_base  # <-- CHANGED: Start at top of stack

        self.program_counter = 0
        self.program_bytes = []
        self.ZF, self.SF, self.CF, self.OF = False, False, False, False
        self.halted, self.clean_halt = False, False
        self.sim_input_buffer, self.sim_last_output_value = None, None
        self.mmio_output_lines = []

        # --- NEW INTERRUPT SUPPORT: Reset interrupt state ---
        self.IE = False
        self.pic_irq = 0
        self.pic_imr = 0
        self.pic_isr = 0
        self.sim_peripheral_irq_pending = {}

    # --- NEW INTERRUPT SUPPORT: Helper to pack flags into a 16-bit word ---
    def _pack_flags(self):
        return (int(self.ZF) << 0) | (int(self.SF) << 1) | (int(self.CF) << 2) | (int(self.OF) << 3)

    # --- NEW INTERRUPT SUPPORT: Helper to unpack a 16-bit word into flags ---
    def _unpack_flags(self, flags_word):
        self.ZF = (flags_word & 0b0001) != 0
        self.SF = (flags_word & 0b0010) != 0
        self.CF = (flags_word & 0b0100) != 0
        self.OF = (flags_word & 0b1000) != 0

    def _apply_16bit_limits(self, value):
        return value & MAX_IMMEDIATE_16BIT

    def _update_flags(self, value_16bit_result, operation_str_for_log,
                      carry_occurred=None, overflow_occurred=None,
                      is_compare_op=False, clear_carry_overflow_for_logical=False):
        val_for_flags = self._apply_16bit_limits(value_16bit_result)
        self.ZF = (val_for_flags == 0)
        self.SF = (val_for_flags & 0x8000) != 0
        log_arith_flags = True
        if clear_carry_overflow_for_logical:
            self.CF, self.OF = False, False
        else:
            if carry_occurred is not None: self.CF = bool(carry_occurred)
            if overflow_occurred is not None: self.OF = bool(overflow_occurred)

        if operation_str_for_log in ["LOAD", "LOADM", "MOV", "POP", "INP", "INM", "LOADFR", "MOVFRSP", "LOADI", "LOADB",
                                     "LOADIB", "LOADBFR"] and \
                carry_occurred is None and overflow_occurred is None and not clear_carry_overflow_for_logical and not is_compare_op:
            log_arith_flags = False
        if is_compare_op: log_arith_flags = True
        if log_arith_flags:
            self.output_log.append(
                f"    Flags set: ZF={int(self.ZF)} SF={int(self.SF)} CF={int(self.CF)} OF={int(self.OF)} (for val 0x{val_for_flags:04X})")

    def _is_valid_data_memory_byte_address(self, address):
        return 0 <= address < len(self.data_memory)

    def _get_reg_name(self, reg_code):
        if reg_code is None: raise ValueError("Sim Error: Register code is None.")
        if reg_code not in REG_NAMES: raise ValueError(f"Sim Error: Invalid reg code {reg_code}.")
        return REG_NAMES[reg_code]

    def _fetch_byte_from_program(self):
        if self.program_counter >= len(self.program_bytes):
            self.output_log.append(f"ERR @PC={self.program_counter:04X}h: Fetch byte beyond program memory.");
            self.halted = True;
            return None
        byte = self.program_bytes[self.program_counter]
        self.program_counter = (self.program_counter + 1) & MAX_ADDRESS_16BIT
        return byte

    def _fetch_word_le_from_program(self):
        low = self._fetch_byte_from_program()
        if low is None: return None
        high = self._fetch_byte_from_program()
        if high is None: return None
        return (high << 8) | low

    def _fetch_signed_word_le_from_program(self):
        val_unsigned = self._fetch_word_le_from_program()
        if val_unsigned is None: return None
        return val_unsigned - 0x10000 if val_unsigned & 0x8000 else val_unsigned

    def load_binary_program(self, filepath):
        try:
            with open(filepath, 'rb') as f:
                self.program_bytes = list(f.read(self.program_memory_capacity))
            self.output_log.append(f"Sim: Binary '{filepath}' loaded ({len(self.program_bytes)}B).")
            if not self.program_bytes: self.output_log.append("Sim: WARN: Loaded program empty.")
            return True
        except Exception as e:
            self.output_log.append(f"Sim: ERR loading '{filepath}': {e}");
            return False

    def _handle_mmio_read(self, word_address):
        eff_addr = self._apply_16bit_limits(word_address)

        # --- NEW INTERRUPT SUPPORT: Handle PIC register reads ---
        if eff_addr == ADDRESS_PIC_IRQ:
            # Reading the IRQ register also simulates peripheral events asserting their lines
            if self.sim_peripheral_irq_pending.get(0, False):
                self.pic_irq |= (1 << 0)  # Timer IRQ
                self.output_log.append(f"  ** SIM: Timer IRQ 0 Asserted to PIC **")
                self.sim_peripheral_irq_pending[0] = False
            if self.sim_peripheral_irq_pending.get(1, False):
                self.pic_irq |= (1 << 1)  # UART IRQ
                self.output_log.append(f"  ** SIM: UART IRQ 1 Asserted to PIC **")
                self.sim_peripheral_irq_pending[1] = False
            self.output_log.append(f"  MMIO Read PIC_IRQ(0x{eff_addr:04X}h): Val=0x{self.pic_irq:04X}")
            return self.pic_irq
        elif eff_addr == ADDRESS_PIC_IMR:
            self.output_log.append(f"  MMIO Read PIC_IMR(0x{eff_addr:04X}h): Val=0x{self.pic_imr:04X}")
            return self.pic_imr
        elif eff_addr == ADDRESS_PIC_ISR:
            self.output_log.append(f"  MMIO Read PIC_ISR(0x{eff_addr:04X}h): Val=0x{self.pic_isr:04X}")
            return self.pic_isr

        if eff_addr == DEFAULT_MMIO_INPUT_ADDR:
            if self.sim_input_buffer is None:
                while True:
                    try:
                        val_str = input(f"MMIO Input (addr 0x{eff_addr:04X}, 16-bit int): ");
                        val_int = int(val_str)
                        if not (0 <= val_int <= MAX_IMMEDIATE_16BIT): print(f"Value out of 16-bit range."); continue
                        self.sim_input_buffer = val_int;
                        break
                    except ValueError:
                        print("Invalid integer. Try again.")
            val = self.sim_input_buffer;
            self.sim_input_buffer = None
            self.output_log.append(f"  MMIO Read INPUT(0x{eff_addr:04X}h): Val=0x{val:04X}");
            return val

        # --- MODIFIED FOR INTERRUPT SUPPORT: Use re-mapped addresses ---
        elif eff_addr == ADDRESS_UART_STATUS:
            uart_status = 0x0001
            if self.sim_peripheral_irq_pending.get(1, False):
                uart_status |= 0x0002  # Set RX data available bit
            self.output_log.append(f"  MMIO Read UART_STATUS(0x{eff_addr:04X}h): Val=0x{uart_status:04X}")
            return uart_status
        elif eff_addr == ADDRESS_TIMER_STATUS:
            timer_status = 0x0000
            if self.sim_peripheral_irq_pending.get(0, False):
                timer_status |= 0x0001  # Set timeout bit
            self.output_log.append(f"  MMIO Read TIMER_STATUS(0x{eff_addr:04X}h): Val=0x{timer_status:04X}")
            return timer_status
        elif eff_addr == ADDRESS_LED_CTRL:
            if not hasattr(self, '_sim_led_state'): self._sim_led_state = 0x0000
            self._sim_led_state ^= 0x0008
            self.output_log.append(f"  MMIO Read LED_CTRL(0x{eff_addr:04X}h): Val=0x{self._sim_led_state:04X}")
            return self._sim_led_state
        elif eff_addr == ADDRESS_UART_RX_DATA:
            self.output_log.append(f"  MMIO Read UART_RX_DATA(0x{eff_addr:04X}h): Val=0x0000 (no data)")
            if self.sim_peripheral_irq_pending.get(1, False):
                self.pic_irq |= (1 << 1)  # Reading data asserts IRQ
                self.output_log.append(f"  ** SIM: UART IRQ 1 Asserted to PIC **")
                self.sim_peripheral_irq_pending[1] = False
            return 0x0000

        byte_address = eff_addr * 2
        if self._is_valid_data_memory_byte_address(byte_address + 1):
            low = self.data_memory[byte_address]
            high = self.data_memory[byte_address + 1]
            return (high << 8) | low
        self.output_log.append(f"Sim WARN: MMIO Read unmapped addr 0x{eff_addr:04X}h. Ret 0.");
        return 0

    def _handle_mmio_write(self, word_address, value):
        eff_addr = self._apply_16bit_limits(word_address)
        val16 = self._apply_16bit_limits(value)

        # DEBUG: Log all MMIO writes
        self.output_log.append(f"  DEBUG MMIO Write: word_addr=0x{eff_addr:04X} (byte=0x{eff_addr * 2:04X}) val=0x{val16:04X}")

        # --- NEW INTERRUPT SUPPORT: Handle PIC register writes ---
        if eff_addr == ADDRESS_PIC_IMR:
            self.output_log.append(f"  MMIO Write PIC_IMR(0x{eff_addr:04X}h): Val=0x{val16:04X}")
            self.pic_imr = val16
            return
        elif eff_addr == ADDRESS_PIC_ISR:
            self.output_log.append(f"  MMIO Write PIC_ISR(0x{eff_addr:04X}h): Val=0x{val16:04X} (Ack)")
            self.pic_isr |= val16  # Software sets bit to acknowledge service
            self.pic_irq &= ~val16  # Acknowledging service clears the request bit
            return
        elif eff_addr == ADDRESS_PIC_EOI:
            self.output_log.append(f"  MMIO Write PIC_EOI(0x{eff_addr:04X}h): Val=0x{val16:04X}")
            self.pic_isr &= ~(1 << val16)  # EOI clears the in-service bit by number
            return

        elif eff_addr == ADDRESS_PIC_IRQ:
            self.output_log.append(f"  MMIO Write PIC_IRQ(0x{eff_addr:04X}h): Val=0x{val16:04X}")
            self.pic_irq = val16  # Allow manual setting of IRQ bits
            return



        if eff_addr == DEFAULT_MMIO_OUTPUT_ADDR:
            self.sim_last_output_value = val16
            output_line = f"SIM MMIO OUTPUT (0x{eff_addr:04X}h): {val16}"
            print(output_line)
            self.mmio_output_lines.append(output_line)
            if 32 <= val16 <= 126:
                print(f"CHAR OUTPUT: '{chr(val16)}'")
            elif val16 == 10:
                print("CHAR OUTPUT: '\\n' (newline)"); print()
            elif val16 == 13:
                print("CHAR OUTPUT: '\\r' (carriage return)")
            elif val16 == 9:
                print("CHAR OUTPUT: '\\t' (tab)")
            elif val16 == 0:
                print("CHAR OUTPUT: '\\0' (null terminator)")
            else:
                print(f"CHAR OUTPUT: [non-printable ASCII {val16}]")
            self.output_log.append(f"  MMIO Write OUTPUT(0x{eff_addr:04X}h): Val=0x{val16:04X}")
            return

        # --- MODIFIED FOR INTERRUPT SUPPORT: Use re-mapped addresses ---
        if eff_addr == ADDRESS_TIMER_STATUS:
            self.output_log.append(f"  MMIO Write TIMER_STATUS(0x{eff_addr:04X}h): Val=0x{val16:04X} (clear timeout)")
            if val16 & 0x0001:  # If software clears the timeout flag, arm the interrupt
                self.sim_peripheral_irq_pending[0] = True  # IRQ 0 for Timer
                self.output_log.append(f"  ** SIM: Timer peripheral interrupt is now PENDING **")
            return
        elif eff_addr == ADDRESS_LED_CTRL:
            self.output_log.append(f"  MMIO Write LED_CTRL(0x{eff_addr:04X}h): Val=0x{val16:04X}")
            self._sim_led_state = val16
            return

        # Fallback to general memory write if no specific MMIO address matched
        byte_address = eff_addr * 2
        if self._is_valid_data_memory_byte_address(byte_address + 1):
            self.data_memory[byte_address] = val16 & 0xFF
            self.data_memory[byte_address + 1] = (val16 >> 8) & 0xFF
        else:
            self.output_log.append(f"Sim WARN: MMIO Write unmapped addr 0x{eff_addr:04X}h. Ignored.")

    def execute_cycle(self):
        if self.halted: return False

        # --- NEW INTERRUPT SUPPORT: The Interrupt Checkpoint ---
        # This check happens *before* the next instruction is fetched, representing the
        # moment between the last instruction's completion and the new fetch cycle.
        self._check_for_interrupts()
        if self.halted: return False  # An interrupt might have changed the state

        initial_pc = self.program_counter
        if initial_pc >= len(self.program_bytes):
            if not self.clean_halt: self.output_log.append(f"Sim: PC (0x{initial_pc:04X}h) > prog len. Halting.")
            self.halted = True;
            return False

        opcode_byte = self._fetch_byte_from_program()
        if opcode_byte is None: self.halted = True; return False
        opcode_str = REVERSE_OPCODES.get(opcode_byte, f"UNK_OP_0x{opcode_byte:02X}")

        # --- NEW INTERRUPT SUPPORT: Add IE flag to status string ---
        flags_s = f"ZF={int(self.ZF)} SF={int(self.SF)} CF={int(self.CF)} OF={int(self.OF)} IE={int(self.IE)}"
        regs_s = ", ".join([f"{REG_NAMES[i]}:{self.registers[REG_NAMES[i]]:04X}" for i in sorted(REG_NAMES.keys())])
        self.output_log.append(
            f"PC={initial_pc:04X}h SP={self.sp:04X}h Flags:[{flags_s}] | Op:0x{opcode_byte:02X}({opcode_str}) | Regs:[{regs_s}]")

        try:
            if opcode_str == "NOP":
                self.output_log.append("  NOP executed.")
            elif opcode_str == "HALT":
                self.halted, self.clean_halt = True, True;
                self.output_log.append("  HALT: CPU Halted by instruction.")
            elif opcode_str == "LOAD":
                rd_code, imm16 = self._fetch_byte_from_program(), self._fetch_word_le_from_program();
                rd_name = self._get_reg_name(rd_code)
                self.registers[rd_name] = self._apply_16bit_limits(imm16);
                self._update_flags(self.registers[rd_name], "LOAD")
                self.output_log.append(f"  LOAD: {rd_name} = #0x{imm16:04X}")

            # --- NEW INTERRUPT SUPPORT: Implement EI, DI, RETI ---
            elif opcode_str == "EI":
                self.IE = True
                self.output_log.append("  EI: Interrupts Enabled")
            elif opcode_str == "DI":
                self.IE = False
                self.output_log.append("  DI: Interrupts Disabled")
            elif opcode_str == "RETI":
                self.output_log.append("  RETI: Return from Interrupt")
                # 1. Pop Flags
                new_sp = (self.sp + 2) & MAX_ADDRESS_16BIT
                if new_sp > self.stack_base: raise ValueError("Stack Underflow on RETI for Flags.")
                self.sp = new_sp
                low = self.data_memory[self.sp]
                high = self.data_memory[self.sp + 1]
                flags_val = (high << 8) | low
                self._unpack_flags(flags_val)
                # 2. Pop PC
                new_sp = (self.sp + 2) & MAX_ADDRESS_16BIT
                if new_sp > self.stack_base: raise ValueError("Stack Underflow on RETI for PC.")
                self.sp = new_sp
                low = self.data_memory[self.sp]
                high = self.data_memory[self.sp + 1]
                return_pc = (high << 8) | low
                # 3. Set PC and atomically enable interrupts
                self.program_counter = self._apply_16bit_limits(return_pc)
                self.IE = True
                self.output_log.append(f"    Popped Flags=0x{flags_val:04X}, PC=0x{return_pc:04X}h. IE set to 1.")

            elif opcode_str == "STORE":
                rs_code, immediate_addr = self._fetch_byte_from_program(), self._fetch_word_le_from_program()
                rs_name = self._get_reg_name(rs_code)
                word_addr = immediate_addr >> 1
                byte_index = word_addr * 2
                if not self._is_valid_data_memory_byte_address(byte_index + 1):
                    self._handle_mmio_write(word_addr, self.registers[rs_name])
                    # Note: The log for MMIO writes is inside _handle_mmio_write
                else:
                    val16 = self._apply_16bit_limits(self.registers[rs_name])
                    self.data_memory[byte_index] = val16 & 0xFF
                    self.data_memory[byte_index + 1] = (val16 >> 8) & 0xFF
                    self.output_log.append(
                        f"  STORE: Mem[WORD:0x{word_addr:04X}h] = {rs_name}(0x{self.registers[rs_name]:04X})")

            elif opcode_str == "LOADB":
                rd_code, immediate_addr = self._fetch_byte_from_program(), self._fetch_word_le_from_program()
                rd_name = self._get_reg_name(rd_code)
                word_addr = immediate_addr >> 1
                byte_select = immediate_addr & 1
                byte_index = (word_addr * 2) + byte_select
                if not self._is_valid_data_memory_byte_address(byte_index):
                    raise ValueError(f"LOADB: Invalid memory byte address 0x{immediate_addr:04X}")
                val = self.data_memory[byte_index]
                self.registers[rd_name] = self._apply_16bit_limits(val)
                self._update_flags(self.registers[rd_name], "LOADB")
                self.output_log.append(f"  LOADB: {rd_name} = Mem[BYTE:0x{immediate_addr:04X}] = 0x{val:02X}")

            elif opcode_str == "STORB":
                rs_code, immediate_addr = self._fetch_byte_from_program(), self._fetch_word_le_from_program()
                rs_name = self._get_reg_name(rs_code)
                word_addr = immediate_addr >> 1
                byte_select = immediate_addr & 1
                byte_index = (word_addr * 2) + byte_select
                if not self._is_valid_data_memory_byte_address(byte_index):
                    raise ValueError(f"STORB: Invalid memory byte address 0x{immediate_addr:04X}")
                self.data_memory[byte_index] = self.registers[rs_name] & 0xFF
                self.output_log.append(
                    f"  STORB: Mem[BYTE:0x{immediate_addr:04X}] = {rs_name}(0x{self.registers[rs_name] & 0xFF:02X})")

            elif opcode_str == "LOADM":
                rd_code, immediate_addr = self._fetch_byte_from_program(), self._fetch_word_le_from_program()
                rd_name = self._get_reg_name(rd_code)
                word_addr = immediate_addr >> 1
                byte_index = word_addr * 2
                val = 0
                if not self._is_valid_data_memory_byte_address(byte_index + 1):
                    val = self._handle_mmio_read(word_addr)
                    # Note: The log for MMIO reads is inside _handle_mmio_read
                else:
                    low = self.data_memory[byte_index]
                    high = self.data_memory[byte_index + 1]
                    val = (high << 8) | low
                    self.output_log.append(f"  LOADM: {rd_name} = Mem[WORD:0x{word_addr:04X}h]")
                self.registers[rd_name] = self._apply_16bit_limits(val)
                self._update_flags(self.registers[rd_name], "LOADM")

            elif opcode_str == "LOADIB":
                rd_code, ra_code = self._fetch_byte_from_program(), self._fetch_byte_from_program()
                rd_name, ra_name = self._get_reg_name(rd_code), self._get_reg_name(ra_code)
                address_from_reg = self.registers[ra_name]
                word_addr = address_from_reg >> 1
                byte_select = address_from_reg & 1
                byte_index = (word_addr * 2) + byte_select
                if not self._is_valid_data_memory_byte_address(byte_index):
                    raise ValueError(f"LOADIB: Invalid address 0x{address_from_reg:04X}")
                val = self.data_memory[byte_index]
                self.registers[rd_name] = self._apply_16bit_limits(val)
                self._update_flags(self.registers[rd_name], "LOADIB")
                self.output_log.append(f"  LOADIB: {rd_name} = Mem[{ra_name}(BYTE:0x{address_from_reg:04X})]")

            elif opcode_str == "STORIB":
                rt_code, ra_code = self._fetch_byte_from_program(), self._fetch_byte_from_program()
                rt_name, ra_name = self._get_reg_name(rt_code), self._get_reg_name(ra_code)
                address_from_reg = self.registers[ra_name]
                word_addr = address_from_reg >> 1
                byte_select = address_from_reg & 1
                byte_index = (word_addr * 2) + byte_select
                if not self._is_valid_data_memory_byte_address(byte_index):
                    raise ValueError(f"STORIB: Invalid address 0x{address_from_reg:04X}")
                self.data_memory[byte_index] = self.registers[rt_name] & 0xFF
                self.output_log.append(f"  STORIB: Mem[{ra_name}(BYTE:0x{address_from_reg:04X})] = {rt_name}")

            elif opcode_str == "LOADFR":
                rd_code, rbase_code, s_offset16 = self._fetch_byte_from_program(), self._fetch_byte_from_program(), self._fetch_signed_word_le_from_program()
                rd_name, rbase_name = self._get_reg_name(rd_code), self._get_reg_name(rbase_code)
                base_addr_val = self.registers[rbase_name]
                eff_addr = self._apply_16bit_limits(base_addr_val + s_offset16)
                word_addr = eff_addr >> 1
                byte_index = word_addr * 2
                if not self._is_valid_data_memory_byte_address(byte_index + 1):
                    raise ValueError(f"LOADFR: Invalid memory access at effective address 0x{eff_addr:04X}")
                low = self.data_memory[byte_index]
                high = self.data_memory[byte_index + 1]
                val = (high << 8) | low
                self.registers[rd_name] = self._apply_16bit_limits(val)
                self._update_flags(self.registers[rd_name], "LOADFR")
                self.output_log.append(
                    f"  LOADFR: {rd_name} = Mem[{rbase_name}(0x{base_addr_val:04X}) + #{s_offset16} => WORD:0x{word_addr:04X}]")

            elif opcode_str == "STORFR":
                rt_code, rbase_code, s_offset16 = self._fetch_byte_from_program(), self._fetch_byte_from_program(), self._fetch_signed_word_le_from_program()
                rt_name, rbase_name = self._get_reg_name(rt_code), self._get_reg_name(rbase_code)
                val_to_store = self.registers[rt_name]
                base_addr_val = self.registers[rbase_name]
                eff_addr = self._apply_16bit_limits(base_addr_val + s_offset16)
                word_addr = eff_addr >> 1
                byte_index = word_addr * 2
                if not self._is_valid_data_memory_byte_address(byte_index + 1):
                    raise ValueError(f"STORFR: Invalid memory access at effective address 0x{eff_addr:04X}")
                val16 = self._apply_16bit_limits(val_to_store)
                self.data_memory[byte_index] = val16 & 0xFF
                self.data_memory[byte_index + 1] = (val16 >> 8) & 0xFF
                self.output_log.append(
                    f"  STORFR: Mem[{rbase_name}(0x{base_addr_val:04X}) + #{s_offset16} => WORD:0x{word_addr:04X}] = {rt_name}")

            elif opcode_str == "LOADBFR":
                rd_code, rbase_code, s_offset16 = self._fetch_byte_from_program(), self._fetch_byte_from_program(), self._fetch_signed_word_le_from_program()
                rd_name, rbase_name = self._get_reg_name(rd_code), self._get_reg_name(rbase_code)
                base_addr_val = self.registers[rbase_name]
                eff_addr = self._apply_16bit_limits(base_addr_val + s_offset16)
                word_addr = eff_addr >> 1
                byte_select = eff_addr & 1
                byte_index = (word_addr * 2) + byte_select
                if not self._is_valid_data_memory_byte_address(byte_index):
                    raise ValueError(f"LOADBFR: Invalid effective byte address 0x{eff_addr:04X}")
                val = self.data_memory[byte_index]
                self.registers[rd_name] = self._apply_16bit_limits(val)
                self._update_flags(self.registers[rd_name], "LOADBFR")
                self.output_log.append(
                    f"  LOADBFR: {rd_name} = Mem[{rbase_name}(0x{base_addr_val:04X}) + #{s_offset16} => BYTE:0x{eff_addr:04X}] = 0x{val:02X}")

            elif opcode_str == "STORBFR":
                rt_code, rbase_code, s_offset16 = self._fetch_byte_from_program(), self._fetch_byte_from_program(), self._fetch_signed_word_le_from_program()
                rt_name, rbase_name = self._get_reg_name(rt_code), self._get_reg_name(rbase_code)
                val_to_store = self.registers[rt_name]
                base_addr_val = self.registers[rbase_name]
                eff_addr = self._apply_16bit_limits(base_addr_val + s_offset16)
                word_addr = eff_addr >> 1
                byte_select = eff_addr & 1
                byte_index = (word_addr * 2) + byte_select
                if not self._is_valid_data_memory_byte_address(byte_index):
                    raise ValueError(f"STORBFR: Invalid effective byte address 0x{eff_addr:04X}")
                self.data_memory[byte_index] = val_to_store & 0xFF
                self.output_log.append(
                    f"  STORBFR: Mem[{rbase_name}(0x{base_addr_val:04X}) + #{s_offset16} => BYTE:0x{eff_addr:04X}] = {rt_name}(0x{val_to_store & 0xFF:02X})")



            elif opcode_str == "LOADI":
                rd_code, rs_addr_code = self._fetch_byte_from_program(), self._fetch_byte_from_program()
                rd_name, rs_addr_name = self._get_reg_name(rd_code), self._get_reg_name(rs_addr_code)
                address_from_reg = self.registers[rs_addr_name]
                word_addr = address_from_reg >> 1

                # Check for MMIO addresses FIRST
                if self._is_mmio_address(word_addr):
                    val = self._handle_mmio_read(word_addr)
                else:
                    # Regular memory read
                    byte_index = word_addr * 2
                    if self._is_valid_data_memory_byte_address(byte_index + 1):
                        low = self.data_memory[byte_index]
                        high = self.data_memory[byte_index + 1]
                        val = (high << 8) | low
                        self.output_log.append(
                            f"  LOADI: {rd_name} = Mem[{rs_addr_name}(WORD:0x{word_addr:04X})] = 0x{val:04X}")
                    else:
                        val = 0  # Invalid address returns 0
                        self.output_log.append(f"  LOADI: Invalid address 0x{address_from_reg:04X}, returning 0")

                self.registers[rd_name] = self._apply_16bit_limits(val)
                self._update_flags(self.registers[rd_name], "LOADI")



            elif opcode_str == "STORI":
                rt_val_code, rs_addr_code = self._fetch_byte_from_program(), self._fetch_byte_from_program()
                rt_val_name, rs_addr_name = self._get_reg_name(rt_val_code), self._get_reg_name(rs_addr_code)
                address_from_reg = self.registers[rs_addr_name]
                val_to_store = self.registers[rt_val_name]
                word_addr = address_from_reg >> 1

                # Check for MMIO addresses FIRST
                if self._is_mmio_address(word_addr):
                    self._handle_mmio_write(word_addr, val_to_store)
                else:
                    # Regular memory write
                    byte_index = word_addr * 2
                    if self._is_valid_data_memory_byte_address(byte_index + 1):
                        val16 = self._apply_16bit_limits(val_to_store)
                        self.data_memory[byte_index] = val16 & 0xFF
                        self.data_memory[byte_index + 1] = (val16 >> 8) & 0xFF
                        self.output_log.append(
                            f"  STORI: Mem[{rs_addr_name}(WORD:0x{word_addr:04X})] = {rt_val_name}(0x{val_to_store:04X})")
                    else:
                        # Invalid address - could log an error
                        self.output_log.append(f"  STORI: Invalid address 0x{address_from_reg:04X}")


            elif opcode_str == "MOVFRSP":
                rd_code = self._fetch_byte_from_program();
                rd_name = self._get_reg_name(rd_code);
                self.registers[rd_name] = self._apply_16bit_limits(self.sp);
                self._update_flags(self.registers[rd_name], "MOVFRSP")
                self.output_log.append(f"  MOVFRSP: {rd_name} = SP(0x{self.sp:04X})")
            elif opcode_str == "MOVTOSP":
                rs_code = self._fetch_byte_from_program();
                rs_name = self._get_reg_name(rs_code);
                self.sp = self._apply_16bit_limits(self.registers[rs_name])
                self.output_log.append(
                    f"  MOVTOSP: SP = {rs_name}(0x{self.registers[rs_name]:04X}). New SP=0x{self.sp:04X}h")

            elif opcode_str == "INP":
                rd_code = self._fetch_byte_from_program();
                rd_name = self._get_reg_name(rd_code);
                val = self._handle_mmio_read(DEFAULT_MMIO_INPUT_ADDR)
                self.registers[rd_name] = self._apply_16bit_limits(val);
                self._update_flags(self.registers[rd_name], "INP")
                self.output_log.append(f"  INP: {rd_name} = 0x{self.registers[rd_name]:04X}")
            elif opcode_str == "OUT":
                rs_code = self._fetch_byte_from_program();
                rs_name = self._get_reg_name(rs_code)
                self._handle_mmio_write(DEFAULT_MMIO_OUTPUT_ADDR, self.registers[rs_name])
                self.output_log.append(f"  OUT: Value from {rs_name}(0x{self.registers[rs_name]:04X})")

            elif opcode_str == "INM":
                rd_code, immediate_addr = self._fetch_byte_from_program(), self._fetch_word_le_from_program()
                rd_name = self._get_reg_name(rd_code)
                word_addr = immediate_addr >> 1
                if immediate_addr % 2 != 0:
                    self.output_log.append(
                        f"Sim WARN: INM from unaligned address 0x{immediate_addr:04X}. Using word addr 0x{word_addr:04X}.")
                val = self._handle_mmio_read(word_addr)
                self.registers[rd_name] = self._apply_16bit_limits(val)
                self._update_flags(self.registers[rd_name], "INM")
                self.output_log.append(
                    f"  INM: {rd_name} = Mem[0x{immediate_addr:04X}] (Value=0x{self.registers[rd_name]:04X})")

            elif opcode_str == "OUTM":
                rs_code, immediate_addr = self._fetch_byte_from_program(), self._fetch_word_le_from_program()
                rs_name = self._get_reg_name(rs_code)
                word_addr = immediate_addr >> 1
                if immediate_addr % 2 != 0:
                    self.output_log.append(
                        f"Sim WARN: OUTM to unaligned address 0x{immediate_addr:04X}. Using word addr 0x{word_addr:04X}.")
                self._handle_mmio_write(word_addr, self.registers[rs_name])
                self.output_log.append(
                    f"  OUTM: Mem[0x{immediate_addr:04X}h] = {rs_name}(0x{self.registers[rs_name]:04X})")

            elif opcode_str == "ADD":
                r1, r2 = self._fetch_byte_from_program(), self._fetch_byte_from_program();
                n1, n2 = self._get_reg_name(r1), self._get_reg_name(r2)
                v1, v2 = self.registers[n1], self.registers[n2];
                res = v1 + v2;
                res16 = self._apply_16bit_limits(res)
                s1, s2, sr = (v1 & 0x8000), (v2 & 0x8000), (res16 & 0x8000)
                self.registers[n1] = res16;
                self._update_flags(res16, "ADD", res > 0xFFFF, (s1 == s2) and (sr != s1));
                self.output_log.append(f"  ADD: {n1}(0x{v1:04X})+{n2}(0x{v2:04X})=0x{res16:04X}")
            elif opcode_str == "SUB":
                r1, r2 = self._fetch_byte_from_program(), self._fetch_byte_from_program();
                n1, n2 = self._get_reg_name(r1), self._get_reg_name(r2)
                v1, v2 = self.registers[n1], self.registers[n2];
                res = v1 - v2;
                res16 = self._apply_16bit_limits(res)
                s1, s2, sr = (v1 & 0x8000), (v2 & 0x8000), (res16 & 0x8000)
                self.registers[n1] = res16;
                self._update_flags(res16, "SUB", v1 < v2, (s1 != s2) and (sr != s1));
                self.output_log.append(f"  SUB: {n1}(0x{v1:04X})-{n2}(0x{v2:04X})=0x{res16:04X}")
            elif opcode_str == "MUL":
                r1, r2 = self._fetch_byte_from_program(), self._fetch_byte_from_program();
                n1, n2 = self._get_reg_name(r1), self._get_reg_name(r2)
                v1, v2 = self.registers[n1], self.registers[n2];
                res = v1 * v2;
                res16 = self._apply_16bit_limits(res)
                self.registers[n1] = res16;
                self._update_flags(res16, "MUL", res > 0xFFFF, res > 0xFFFF);
                self.output_log.append(f"  MUL: {n1}(0x{v1:04X})*{n2}(0x{v2:04X})=0x{res16:04X}")
            elif opcode_str == "INC":
                rd = self._fetch_byte_from_program();
                n = self._get_reg_name(rd);
                v1 = self.registers[n];
                res = v1 + 1
                res16 = self._apply_16bit_limits(res);
                self.registers[n] = res16;
                self._update_flags(res16, "INC", res > 0xFFFF, v1 == 0x7FFF);
                self.output_log.append(f"  INC: {n} from 0x{v1:04X} to 0x{res16:04X}")
            elif opcode_str == "DEC":
                rd = self._fetch_byte_from_program();
                n = self._get_reg_name(rd);
                v1 = self.registers[n];
                res = v1 - 1
                res16 = self._apply_16bit_limits(res);
                self.registers[n] = res16;
                self._update_flags(res16, "DEC", v1 == 0, v1 == 0x8000);
                self.output_log.append(f"  DEC: {n} from 0x{v1:04X} to 0x{res16:04X}")
            elif opcode_str in ["AND", "OR", "XOR"]:
                r1, r2 = self._fetch_byte_from_program(), self._fetch_byte_from_program();
                n1, n2 = self._get_reg_name(r1), self._get_reg_name(r2)
                v1, v2 = self.registers[n1], self.registers[n2]
                res16 = (v1 & v2) if opcode_str == "AND" else (v1 | v2) if opcode_str == "OR" else (v1 ^ v2);
                self.registers[n1] = self._apply_16bit_limits(res16);
                self._update_flags(res16, opcode_str, clear_carry_overflow_for_logical=True);
                self.output_log.append(
                    f"  {opcode_str}: {n1}(0x{v1:04X}) op {n2}(0x{v2:04X})=0x{self.registers[n1]:04X}")
            elif opcode_str == "NOT":
                rd = self._fetch_byte_from_program();
                n = self._get_reg_name(rd);
                self.registers[n] = self._apply_16bit_limits(~self.registers[n]);
                self._update_flags(self.registers[n], "NOT", clear_carry_overflow_for_logical=True);
                self.output_log.append(f"  NOT: {n}=0x{self.registers[n]:04X}")
            elif opcode_str in ["SHL", "SHR"]:
                rd, sa = self._fetch_byte_from_program(), self._fetch_byte_from_program();
                n, amt = self._get_reg_name(rd), sa;
                v1 = self.registers[n];
                c_out = (v1 >> (16 - amt)) & 1 if 0 < amt <= 16 else 0;
                res16 = self._apply_16bit_limits(v1 << amt) if opcode_str == "SHL" else self._apply_16bit_limits(
                    v1 >> amt)
                self.registers[n] = res16;
                self._update_flags(res16, opcode_str, c_out if amt > 0 else self.CF, False);
                self.output_log.append(f"  {opcode_str}: {n}(0x{v1:04X}) by {amt}=0x{res16:04X}")
            elif opcode_str in ["L_AND", "L_OR"]:
                rd, rs1, rs2 = self._fetch_byte_from_program(), self._fetch_byte_from_program(), self._fetch_byte_from_program();
                n, n1, n2 = self._get_reg_name(rd), self._get_reg_name(rs1), self._get_reg_name(rs2)
                v1, v2 = (self.registers[n1] != 0), (self.registers[n2] != 0);
                res = (v1 and v2) if opcode_str == "L_AND" else (v1 or v2)
                self.registers[n] = 1 if res else 0;
                self._update_flags(self.registers[n], opcode_str, clear_carry_overflow_for_logical=True);
                self.output_log.append(f"  {opcode_str}:{n}=({n1} op {n2})->{self.registers[n]}")
            elif opcode_str == "L_NOT":
                rd, rs = self._fetch_byte_from_program(), self._fetch_byte_from_program();
                n, n1 = self._get_reg_name(rd), self._get_reg_name(rs)
                self.registers[n] = 1 if self.registers[n1] == 0 else 0;
                self._update_flags(self.registers[n], "L_NOT", clear_carry_overflow_for_logical=True);
                self.output_log.append(f"  L_NOT:{n}=!{n1}->{self.registers[n]}")
            elif opcode_str == "CMP":
                r1, r2 = self._fetch_byte_from_program(), self._fetch_byte_from_program();
                n1, n2 = self._get_reg_name(r1), self._get_reg_name(r2);
                v1, v2 = self.registers[n1], self.registers[n2];
                res = v1 - v2;
                res16 = self._apply_16bit_limits(res);
                s1, s2, sr = (v1 & 0x8000), (v2 & 0x8000), (res16 & 0x8000)
                self._update_flags(res16, "CMP", v1 < v2, (s1 != s2) and (sr != s1), is_compare_op=True);
                self.output_log.append(f"  CMP:{n1}(0x{v1:04X}) vs {n2}(0x{v2:04X})")
            elif opcode_str == "MOV":
                rd, rs = self._fetch_byte_from_program(), self._fetch_byte_from_program();
                n1, n2 = self._get_reg_name(rd), self._get_reg_name(rs)
                self.registers[n1] = self.registers[n2];
                self._update_flags(self.registers[n1], "MOV");
                self.output_log.append(f"  MOV:{n1}={n2}(0x{self.registers[n1]:04X})")

            elif opcode_str == "PUSH":
                rs_code = self._fetch_byte_from_program()
                rs_name = self._get_reg_name(rs_code)
                if self.sp < self.stack_limit:
                    raise ValueError(
                        f"Stack Overflow on PUSH. SP(0x{self.sp:04X}h) at/below Limit(0x{self.stack_limit:04X}h).")
                if not self._is_valid_data_memory_byte_address(self.sp + 1):
                    raise ValueError(f"PUSH: Invalid SP 0x{self.sp:04X}h before store.")
                val_to_push = self.registers[rs_name]
                val16 = self._apply_16bit_limits(val_to_push)
                self.data_memory[self.sp] = val16 & 0xFF
                self.data_memory[self.sp + 1] = (val16 >> 8) & 0xFF
                self.output_log.append(f"  PUSH: {rs_name}(0x{val_to_push:04X}) to Mem[SP=0x{self.sp:04X}h].")
                self.sp = (self.sp - 2) & MAX_ADDRESS_16BIT

            elif opcode_str == "POP":
                rd_code = self._fetch_byte_from_program()
                rd_name = self._get_reg_name(rd_code)
                new_sp = (self.sp + 2) & MAX_ADDRESS_16BIT
                if new_sp > self.stack_base:
                    raise ValueError("Stack Underflow on POP. SP would be > base.")
                self.sp = new_sp
                if not self._is_valid_data_memory_byte_address(self.sp + 1):
                    raise ValueError(f"POP: Invalid SP 0x{self.sp:04X}h after increment.")
                low = self.data_memory[self.sp]
                high = self.data_memory[self.sp + 1]
                val_popped = (high << 8) | low
                self.registers[rd_name] = self._apply_16bit_limits(val_popped)
                self._update_flags(self.registers[rd_name], "POP")
                self.output_log.append(f"  POP: {rd_name} = Mem[SP=0x{self.sp:04X}h] (Val=0x{val_popped:04X}).")

            elif opcode_str == "CALL":
                target_addr16 = self._fetch_word_le_from_program()
                ret_addr = self.program_counter
                if self.sp < self.stack_limit:
                    raise ValueError("Stack Overflow on CALL for return address.")
                if not self._is_valid_data_memory_byte_address(self.sp + 1):
                    raise ValueError("CALL: Invalid SP for ret_addr push.")
                ret16 = self._apply_16bit_limits(ret_addr)
                self.data_memory[self.sp] = ret16 & 0xFF
                self.data_memory[self.sp + 1] = (ret16 >> 8) & 0xFF
                self.output_log.append(
                    f"  CALL: Pushed RetAddr(0x{ret_addr:04X}h) to Stack[SP=0x{self.sp:04X}h]. JMP to 0x{target_addr16:04X}h.")
                self.sp = (self.sp - 2) & MAX_ADDRESS_16BIT
                self.program_counter = self._apply_16bit_limits(target_addr16)

            elif opcode_str == "RET":
                new_sp = (self.sp + 2) & MAX_ADDRESS_16BIT
                if new_sp > self.stack_base:
                    raise ValueError("Stack Underflow on RET.")
                self.sp = new_sp
                if not self._is_valid_data_memory_byte_address(self.sp + 1):
                    raise ValueError("RET: Invalid SP for ret_addr pop.")
                low = self.data_memory[self.sp]
                high = self.data_memory[self.sp + 1]
                ret_addr_from_stack = (high << 8) | low
                self.program_counter = self._apply_16bit_limits(ret_addr_from_stack)
                self.output_log.append(
                    f"  RET: Popped RetAddr(0x{self.program_counter:04X}h) from Stack[SP=0x{self.sp:04X}h]. JMP.")

            elif opcode_str.startswith("J"):
                is_reg_cond_jmp = opcode_str in ["JMPZ", "JMPN"]
                reg_c = self._fetch_byte_from_program() if is_reg_cond_jmp else None
                target_addr16 = self._fetch_word_le_from_program()
                condition_met = False
                if opcode_str == "JMP":
                    condition_met = True
                elif opcode_str == "JMPZ":
                    condition_met = (self.registers[self._get_reg_name(reg_c)] == 0)
                elif opcode_str == "JMPN":
                    condition_met = ((self.registers[self._get_reg_name(reg_c)] & 0x8000) != 0)
                elif opcode_str == "JE":
                    condition_met = self.ZF
                elif opcode_str == "JNE":
                    condition_met = not self.ZF
                elif opcode_str == "JS":
                    condition_met = self.SF
                elif opcode_str == "JNS":
                    condition_met = not self.SF
                elif opcode_str == "JC":
                    condition_met = self.CF
                elif opcode_str == "JNC":
                    condition_met = not self.CF
                elif opcode_str == "JO":
                    condition_met = self.OF
                elif opcode_str == "JNO":
                    condition_met = not self.OF
                if condition_met:
                    self.program_counter = self._apply_16bit_limits(target_addr16);
                    self.output_log.append(
                        f"  {opcode_str}: Condition TRUE. JMP to 0x{target_addr16:04X}h")
                else:
                    self.output_log.append(f"  {opcode_str}: Condition FALSE. No JMP.")
            else:
                self.output_log.append(
                    f"  SIMULATOR ERROR: Opcode '{opcode_str}' (0x{opcode_byte:02X}) defined but not implemented.")
                self.halted = True;
                return False
        except ValueError as ve:
            self.output_log.append(
                f"  RUNTIME ERROR @PC=0x{initial_pc:04X}h Op='{opcode_str}' (0x{opcode_byte:02X}): {ve}")
            self.halted = True;
            return False
        except Exception as e_unhandled:
            self.output_log.append(
                f"  UNEXPECTED SIM PYTHON ERROR @PC=0x{initial_pc:04X}h ({opcode_str}): {e_unhandled} ({type(e_unhandled).__name__})")
            import traceback;
            self.output_log.append(traceback.format_exc());
            self.halted = True;
            return False
        return True

    # check if an address is MMIO
    #def _is_mmio_address(self, word_addr):
    #    return word_addr in [
    #        ADDRESS_PIC_IRQ, ADDRESS_PIC_IMR, ADDRESS_PIC_ISR, ADDRESS_PIC_EOI,
    #        ADDRESS_TIMER_STATUS, ADDRESS_UART_STATUS, ADDRESS_UART_RX_DATA,
    #        ADDRESS_LED_CTRL, DEFAULT_MMIO_OUTPUT_ADDR, DEFAULT_MMIO_INPUT_ADDR
    #    ]

    # check if an address is MMIO
    def _is_mmio_address(self, word_addr):
        # MMIO_BASE_ADDR in abcore16_defs.py is a byte address (e.g. 0x1800).
        # This function receives a word address (Address >> 1), so convert the
        # MMIO byte-range into the equivalent word-range before testing.
        from abcore16_defs import MMIO_BASE_ADDR

        # Convert byte base/end into word addresses (floor division by 2)
        mmio_base_word = MMIO_BASE_ADDR >> 1
        mmio_end_word = (MMIO_BASE_ADDR + 0x0100) >> 1  # exclusive upper bound

        return mmio_base_word <= word_addr < mmio_end_word

    # --- NEW INTERRUPT SUPPORT: Logic to check for and service an interrupt ---
    def _check_for_interrupts(self):
        # Determine which interrupts are active and enabled, but not currently being serviced
        active_and_enabled = self.pic_irq & self.pic_imr
        pending_interrupts = active_and_enabled & ~self.pic_isr

        # DEBUG: Add these lines
        if self.pic_irq != 0 or self.pic_imr != 0:
            self.output_log.append(
                f"  DEBUG INT CHECK: IE={self.IE} IRQ=0x{self.pic_irq:04X} IMR=0x{self.pic_imr:04X} ISR=0x{self.pic_isr:04X} pending=0x{pending_interrupts:04X}")

        # Only proceed if there's a pending interrupt and the master IE flag is on
        if not self.IE or pending_interrupts == 0:
            return

        # Priority Encoder: Find the highest priority interrupt (lowest number for simplicity)
        highest_priority_irq_num = -1
        for i in range(16):
            if (pending_interrupts >> i) & 1:
                highest_priority_irq_num = i
                break

        if highest_priority_irq_num == -1: return

        self.output_log.append(f"--- INTERRUPT DETECTED (IRQ #{highest_priority_irq_num}) ---")

        # === Begin Interrupt Acknowledge Sequence (Simulated) ===
        # 1. Atomically disable further interrupts
        self.IE = False
        self.output_log.append(f"    IE flag cleared to 0")


        # 2/3 PRE-FLIGHT: Need room for PC and FLAGS (2 words total) on the stack.
        # Because we do write-then-decrement semantics, check that SP >= (stack_limit + 4)
        # Equivalent: self.sp - 3 >= self.stack_limit  (but do without underflow)
        needed_bytes_for_context = 2 * 2  # 2 words = 4 bytes
        if (self.sp - (needed_bytes_for_context - 1)) < self.stack_limit:
            # Make the message explicit to help debugging.
            raise ValueError("Stack Overflow on interrupt: need 2 words for PC+FLAGS.")

        # 2. Push PC onto the stack FIRST (hardware pushes return address first)
        pc_val = self.program_counter
        self.data_memory[self.sp] = pc_val & 0xFF
        self.data_memory[self.sp + 1] = (pc_val >> 8) & 0xFF
        self.output_log.append(f"    PUSH PC (0x{pc_val:04X}) to Stack[SP=0x{self.sp:04X}h].")
        self.sp = (self.sp - 2) & MAX_ADDRESS_16BIT

        # 3. Push Flags onto the stack SECOND
        flags_val = self._pack_flags()
        self.data_memory[self.sp] = flags_val & 0xFF
        self.data_memory[self.sp + 1] = (flags_val >> 8) & 0xFF
        self.output_log.append(f"    PUSH Flags (0x{flags_val:04X}) to Stack[SP=0x{self.sp:04X}h].")
        self.sp = (self.sp - 2) & MAX_ADDRESS_16BIT


        # 4. Get ISR address from Interrupt Vector Table (IVT)
        ivt_byte_addr = IVT_START_ADDR + (highest_priority_irq_num * 2)
        if not self._is_valid_data_memory_byte_address(ivt_byte_addr + 1):
            raise ValueError(f"IVT address 0x{ivt_byte_addr:04X} for IRQ #{highest_priority_irq_num} is out of bounds.")

        low = self.data_memory[ivt_byte_addr]
        high = self.data_memory[ivt_byte_addr + 1]
        isr_addr = (high << 8) | low
        self.output_log.append(f"    Read IVT[0x{ivt_byte_addr:04X}h], got ISR address 0x{isr_addr:04X}h")

        # 5. Jump to ISR
        self.program_counter = isr_addr
        self.output_log.append(f"    Jumping to ISR.")
        self.output_log.append(f"--- END INTERRUPT SEQUENCE ---")

    def run_program(self, binary_source_file):
        self._reset_state()
        if not self.load_binary_program(binary_source_file):
            self.output_log.append(f"--- Sim Aborted: Load fail '{binary_source_file}' ---")
            return "\n".join(self.output_log)
        if not self.program_bytes:
            self.output_log.append("Sim: Program empty. Halted.")
            self.halted, self.clean_halt = True, True
        max_cycles = (len(self.program_bytes) * 50) + 5000;
        cycles = 0
        while not self.halted and cycles < max_cycles:
            if not self.execute_cycle(): break
            cycles += 1
        if cycles >= max_cycles and not self.halted:
            self.output_log.append(f"Sim: MAX CYCLES ({max_cycles}) REACHED! Halting.")
            self.halted = True
        status = "CPU " + ("HALTED cleanly" if self.clean_halt else "STOPPED")
        self.output_log.append(f"--- Sim Finished ({status}) ({cycles} cycles) ---")
        self.output_log.append(f"Final PC: 0x{self.program_counter:04X}h")
        regs_s = ", ".join([f"{REG_NAMES[i]}:{self.registers[REG_NAMES[i]]:04X}" for i in sorted(REG_NAMES.keys())])
        self.output_log.append(f"Final Regs: [{regs_s}]")
        self.output_log.append(f"Final SP: 0x{self.sp:04X}h")
        self.output_log.append(
            f"Final Flags: ZF={int(self.ZF)} SF={int(self.SF)} CF={int(self.CF)} OF={int(self.OF)} IE={int(self.IE)}")
        return "\n".join(self.output_log)

    def print_final_state(self):
        print("\n--- Final Simulator State (print_final_state) ---")
        for i in sorted(REG_NAMES.keys()):
            print(
                f"Reg {REG_NAMES[i]:<3}: {self.registers[REG_NAMES[i]]:<5} (0x{self.registers[REG_NAMES[i]]:04X}) ({self.registers[REG_NAMES[i]]:016b}b)")
        print(
            f"SP: 0x{self.sp:04X}h ({self.sp}) PC:0x{self.program_counter:04X}h ({self.program_counter}) Flags: Z{int(self.ZF)}S{int(self.SF)}C{int(self.CF)}O{int(self.OF)} IE={int(self.IE)}")
        print(f"Halted: {self.halted}, Clean Halt: {self.clean_halt}")
        print(f"Data Mem Sample (size {len(self.data_memory)} bytes):")
        printed_mem_count = 0
        for i in range(0, min(64, len(self.data_memory)), 2):
            if i + 1 < len(self.data_memory) and (self.data_memory[i] != 0 or self.data_memory[i + 1] != 0):
                low, high = self.data_memory[i], self.data_memory[i + 1]
                word_val = (high << 8) | low
                print(f"  Mem[WORD:0x{i // 2:04X}h | BYTE:0x{i:04X}h]: 0x{word_val:04X}");
                printed_mem_count += 1
            if printed_mem_count >= 8: break

        if self.sp < self.stack_base:
            print("  Stack Area (near SP):")
            start_addr = max(self.stack_limit, self.sp - 8) & 0xFFFE
            end_addr = min(self.stack_base, self.sp + 8)
            for i in range(start_addr, end_addr, 2):
                low, high = self.data_memory[i], self.data_memory[i + 1]
                word_val = (high << 8) | low
                mark = ""
                if i == self.sp:
                    mark = " <-- Current SP (next PUSH writes here)"
                elif i == self.sp + 2:
                    mark = " <-- Last item pushed"
                print(f"  Mem[WORD:0x{i // 2:04X}h | BYTE:0x{i:04X}h]: 0x{word_val:04X} {mark}");
        if printed_mem_count == 0: print("  (All sampled mem is zero or stack empty at base)")
        print("-------------------------------------------")


if __name__ == "__main__":
    from simple_assembler import SimpleAssembler

    test_sal_all_new_isa = """
    // Test new indirect instructions
    LOAD R0, #0x1100      // R0 will hold an address
    LOAD R1, #999         // R1 holds the value to store
    STORI R1, R0          // Mem[0x1100] = 999
    LOADI R2, R0          // R2 = Mem[0x1100]
    OUT R2                // Expected: 999
    HALT
    """
    asm_test = SimpleAssembler()
    bin_f = "test_full_isa_sim.bin"
    asm_f = "test_full_isa_sim.asm"
    print(f"--- Assembling SAL for full ISA simulator test: {bin_f} ---")
    if asm_test.assemble_to_file(test_sal_all_new_isa, bin_f, asm_f):
        print(f"\n--- Testing Simulator with full ISA extensions '{bin_f}' ---")
        sim = MicroprocessorSimulator()
        log = sim.run_program(bin_f)
        print("\nSimulation Log:")
        print(log)
        sim.print_final_state()
    else:
        print(f"Failed to assemble {bin_f}. Errors:")
        if asm_test.errors:
            for error_message in asm_test.errors:
                print(f"  - {error_message}")
        else:
            print("  (No specific errors reported by assembler object)")
