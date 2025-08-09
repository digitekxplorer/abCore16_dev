# microprocessor_simulator.py
# FINAL CORRECTED VERSION with bytearray memory and char opcodes.

import sys
from abcore16_defs import (
    REVERSE_OPCODES, REG_NAMES, INSTRUCTION_FORMATS,
    DEFAULT_MMIO_INPUT_ADDR, DEFAULT_MMIO_OUTPUT_ADDR,
    MAX_ADDRESS_16BIT, MAX_IMMEDIATE_16BIT
)


class MicroprocessorSimulator:
    def __init__(self, data_memory_size=8192, stack_size=256, program_memory_capacity=65536):
        self.registers = {reg_name: 0 for reg_name in REG_NAMES.values()}
        self.data_memory_size = data_memory_size

        # --- CORE CHANGE: Memory is now a bytearray ---
        self.data_memory = bytearray(self.data_memory_size)

        self.stack_base = self.data_memory_size
        self.stack_limit = self.data_memory_size - stack_size if stack_size <= data_memory_size else 0
        self.sp = self.stack_base  # This will be adjusted in _reset_state
        self.output_log = []
        self.program_counter = 0
        self.program_bytes = []
        self.program_memory_capacity = program_memory_capacity
        self.ZF = False;
        self.SF = False;
        self.CF = False;
        self.OF = False
        self.halted = False;
        self.clean_halt = False
        self.sim_input_buffer = None;
        self.sim_last_output_value = None
        self.mmio_output_lines = []

    def _reset_state(self):
        self.registers = {reg_name: 0 for reg_name in REG_NAMES.values()}
        # --- CORE CHANGE: Reset with a bytearray ---
        self.data_memory = bytearray(self.data_memory_size)

        # SP now points to the first USABLE slot in a byte-addressable space.
        self.sp = self.stack_base - 2

        self.program_counter = 0;
        self.program_bytes = []
        self.ZF, self.SF, self.CF, self.OF = False, False, False, False
        self.halted, self.clean_halt = False, False
        self.sim_input_buffer, self.sim_last_output_value = None, None
        self.mmio_output_lines = []
        self.output_log = [
            f"--- Sim Start (DataMemBytes:{len(self.data_memory)}, StackBase:{self.stack_base:04X}h, StackLimit:{self.stack_limit:04X}h) ---",
            f"    SP Initialized to: {self.sp:04X}h (Hardware Model)",
            f"    MMIO In: {DEFAULT_MMIO_INPUT_ADDR:04X}h, MMIO Out: {DEFAULT_MMIO_OUTPUT_ADDR:04X}h"]

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
        # DEBUG: Print every MMIO read attempt
        print(f"DEBUG MMIO READ: addr=0x{eff_addr:04X}")

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

        # === NEW MMIO PERIPHERAL SIMULATION ===
        elif eff_addr == 0x1812:  # ADDRESS_UART_STATUS
            # Simulate UART status: TX FIFO ready (bit 0 = 1), no RX data available (bit 1 = 0)
            uart_status = 0x0001  # TX FIFO ready
            self.output_log.append(f"  MMIO Read UART_STATUS(0x{eff_addr:04X}h): Val=0x{uart_status:04X} (TX ready)")
            return uart_status

        elif eff_addr == 0x180C:  # ADDRESS_TIMER_STATUS
            # Simulate timer status: timeout occurred (bit 0 = 1)
            timer_status = 0x0001  # Timeout bit set
            self.output_log.append(
                f"  MMIO Read TIMER_STATUS(0x{eff_addr:04X}h): Val=0x{timer_status:04X} (timeout ready)")
            return timer_status

        elif eff_addr == 0x1818:  # ADDRESS_LED_CTRL
            # Simulate LED control register - return current LED state
            # For simulation, we'll alternate the 4th LED bit to show blinking behavior
            if not hasattr(self, '_sim_led_state'):
                self._sim_led_state = 0x0000
            # Toggle the 4th LED bit (bit 3) each time it's read to simulate blinking
            self._sim_led_state ^= 0x0008
            self.output_log.append(f"  MMIO Read LED_CTRL(0x{eff_addr:04X}h): Val=0x{self._sim_led_state:04X}")
            return self._sim_led_state

        elif eff_addr == 0x1816:  # ADDRESS_UART_RX_DATA
            # Simulate UART RX data - return 0 (no data received)
            self.output_log.append(f"  MMIO Read UART_RX_DATA(0x{eff_addr:04X}h): Val=0x0000 (no data)")
            return 0x0000
        # === END NEW MMIO SIMULATION ===

        # Default case: try to read from data memory or return 0 for unmapped addresses
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

        if eff_addr == DEFAULT_MMIO_OUTPUT_ADDR:
            self.sim_last_output_value = val16

            # EXISTING: Original numeric output line (preserved for compatibility)
            output_line = f"SIM MMIO OUTPUT (0x{eff_addr:04X}h): {val16}"
            print(output_line)
            self.mmio_output_lines.append(output_line)

            # NEW: Additional character display for ASCII values
            if 32 <= val16 <= 126:  # Printable ASCII characters
                char_output = chr(val16)
                print(f"CHAR OUTPUT: '{char_output}'")
            elif val16 == 10:  # Newline character
                print("CHAR OUTPUT: '\\n' (newline)")
                print()  # Also print actual newline for visual effect
            elif val16 == 13:  # Carriage return
                print("CHAR OUTPUT: '\\r' (carriage return)")
            elif val16 == 9:  # Tab
                print("CHAR OUTPUT: '\\t' (tab)")
            elif val16 == 0:  # Null terminator
                print("CHAR OUTPUT: '\\0' (null terminator)")
            else:  # Other values
                print(f"CHAR OUTPUT: [non-printable ASCII {val16}]")

            # EXISTING: Original log entry (preserved)
            self.output_log.append(f"  MMIO Write OUTPUT(0x{eff_addr:04X}h): Val=0x{val16:04X}")

        # === NEW MMIO PERIPHERAL WRITE SIMULATION ===
        elif eff_addr == 0x1800:  # ADDRESS_TIMER_CTRL
            self.output_log.append(f"  MMIO Write TIMER_CTRL(0x{eff_addr:04X}h): Val=0x{val16:04X}")

        elif eff_addr == 0x1802:  # ADDRESS_TIMER_PRESCALE
            self.output_log.append(f"  MMIO Write TIMER_PRESCALE(0x{eff_addr:04X}h): Val=0x{val16:04X}")

        elif eff_addr == 0x1804:  # ADDRESS_TIMER_RELOAD_L
            self.output_log.append(f"  MMIO Write TIMER_RELOAD_L(0x{eff_addr:04X}h): Val=0x{val16:04X}")

        elif eff_addr == 0x1806:  # ADDRESS_TIMER_RELOAD_H
            self.output_log.append(f"  MMIO Write TIMER_RELOAD_H(0x{eff_addr:04X}h): Val=0x{val16:04X}")

        elif eff_addr == 0x180C:  # ADDRESS_TIMER_STATUS
            self.output_log.append(f"  MMIO Write TIMER_STATUS(0x{eff_addr:04X}h): Val=0x{val16:04X} (clear timeout)")

        elif eff_addr == 0x1810:  # ADDRESS_UART_CTRL
            self.output_log.append(f"  MMIO Write UART_CTRL(0x{eff_addr:04X}h): Val=0x{val16:04X}")

        elif eff_addr == 0x1814:  # ADDRESS_UART_TX_DATA
            # Simulate UART transmission - just log the data
            char_output = ""
            if 32 <= val16 <= 126:
                char_output = f" ('{chr(val16)}')"
            elif val16 == 10:
                char_output = " ('\\n')"
            elif val16 == 13:
                char_output = " ('\\r')"
            self.output_log.append(f"  MMIO Write UART_TX_DATA(0x{eff_addr:04X}h): Val=0x{val16:04X}{char_output}")

        elif eff_addr == 0x1818:  # ADDRESS_LED_CTRL
            self.output_log.append(f"  MMIO Write LED_CTRL(0x{eff_addr:04X}h): Val=0x{val16:04X}")
            # Store the LED state for reads
            self._sim_led_state = val16
        # === END NEW MMIO WRITE SIMULATION ===

        else:
            # EXISTING: All other MMIO handling (unchanged)
            byte_address = eff_addr * 2
            if self._is_valid_data_memory_byte_address(byte_address + 1):
                self.data_memory[byte_address] = val16 & 0xFF
                self.data_memory[byte_address + 1] = (val16 >> 8) & 0xFF
            else:
                self.output_log.append(f"Sim WARN: MMIO Write unmapped addr 0x{eff_addr:04X}h. Ignored.")


    def execute_cycle(self):
        if self.halted: return False
        initial_pc = self.program_counter
        if initial_pc >= len(self.program_bytes):
            if not self.clean_halt: self.output_log.append(f"Sim: PC (0x{initial_pc:04X}h) > prog len. Halting.")
            self.halted = True;
            return False
        opcode_byte = self._fetch_byte_from_program()
        if opcode_byte is None: self.halted = True; return False
        opcode_str = REVERSE_OPCODES.get(opcode_byte, f"UNK_OP_0x{opcode_byte:02X}")
        regs_s = ", ".join([f"{REG_NAMES[i]}:{self.registers[REG_NAMES[i]]:04X}" for i in sorted(REG_NAMES.keys())])
        flags_s = f"ZF={int(self.ZF)} SF={int(self.SF)} CF={int(self.CF)} OF={int(self.OF)}"
        self.output_log.append(
            f"PC={initial_pc:04X}h SP={self.sp:04X}h Flags:[{flags_s}] | Op:0x{opcode_byte:02X}({opcode_str}) | Regs:[{regs_s}]")
        try:
            if opcode_str == "NOP":
                self.output_log.append("  NOP executed.")
            elif opcode_str == "HALT":
                self.halted, self.clean_halt = True, True; self.output_log.append("  HALT: CPU Halted by instruction.")
            elif opcode_str == "LOAD":
                rd_code, imm16 = self._fetch_byte_from_program(), self._fetch_word_le_from_program();
                rd_name = self._get_reg_name(rd_code)
                self.registers[rd_name] = self._apply_16bit_limits(imm16);
                self._update_flags(self.registers[rd_name], "LOAD")
                self.output_log.append(f"  LOAD: {rd_name} = #0x{imm16:04X}")
            elif opcode_str == "STORE":
                rs_code, word_addr = self._fetch_byte_from_program(), self._fetch_word_le_from_program();
                rs_name = self._get_reg_name(rs_code)
                self._handle_mmio_write(word_addr, self.registers[rs_name])
                self.output_log.append(
                    f"  STORE: Mem[WORD:0x{word_addr:04X}h] = {rs_name}(0x{self.registers[rs_name]:04X})")
            elif opcode_str == "LOADM":
                rd_code, word_addr = self._fetch_byte_from_program(), self._fetch_word_le_from_program();
                rd_name = self._get_reg_name(rd_code)
                val = self._handle_mmio_read(word_addr);
                self.registers[rd_name] = self._apply_16bit_limits(val);
                self._update_flags(self.registers[rd_name], "LOADM")
                self.output_log.append(f"  LOADM: {rd_name} = Mem[WORD:0x{word_addr:04X}h]")
            elif opcode_str == "LOADB":
                rd_code, byte_addr = self._fetch_byte_from_program(), self._fetch_word_le_from_program();
                rd_name = self._get_reg_name(rd_code)
                if not self._is_valid_data_memory_byte_address(byte_addr): raise ValueError(
                    f"LOADB: Invalid byte address 0x{byte_addr:04X}")
                val = self.data_memory[byte_addr];
                self.registers[rd_name] = self._apply_16bit_limits(val)
                self._update_flags(self.registers[rd_name], "LOADB");
                self.output_log.append(f"  LOADB: {rd_name} = Mem[BYTE:0x{byte_addr:04X}]")
            elif opcode_str == "STORB":
                rs_code, byte_addr = self._fetch_byte_from_program(), self._fetch_word_le_from_program();
                rs_name = self._get_reg_name(rs_code)
                if not self._is_valid_data_memory_byte_address(byte_addr): raise ValueError(
                    f"STORB: Invalid byte address 0x{byte_addr:04X}")
                self.data_memory[byte_addr] = self.registers[rs_name] & 0xFF
                self.output_log.append(f"  STORB: Mem[BYTE:0x{byte_addr:04X}] = {rs_name}")
            elif opcode_str == "LOADIB":
                rd_code, ra_code = self._fetch_byte_from_program(), self._fetch_byte_from_program();
                rd_name, ra_name = self._get_reg_name(rd_code), self._get_reg_name(ra_code)
                byte_addr = self.registers[ra_name]
                if not self._is_valid_data_memory_byte_address(byte_addr): raise ValueError(
                    f"LOADIB: Invalid byte address 0x{byte_addr:04X}")
                val = self.data_memory[byte_addr];
                self.registers[rd_name] = self._apply_16bit_limits(val)
                self._update_flags(self.registers[rd_name], "LOADIB");
                self.output_log.append(f"  LOADIB: {rd_name} = Mem[{ra_name}(BYTE:0x{byte_addr:04X})]")
            elif opcode_str == "STORIB":
                rt_code, ra_code = self._fetch_byte_from_program(), self._fetch_byte_from_program();
                rt_name, ra_name = self._get_reg_name(rt_code), self._get_reg_name(ra_code)
                byte_addr = self.registers[ra_name]
                if not self._is_valid_data_memory_byte_address(byte_addr): raise ValueError(
                    f"STORIB: Invalid byte address 0x{byte_addr:04X}")
                self.data_memory[byte_addr] = self.registers[rt_name] & 0xFF
                self.output_log.append(f"  STORIB: Mem[{ra_name}(BYTE:0x{byte_addr:04X})] = {rt_name}")
            elif opcode_str == "LOADFR":
                rd_code, rbase_code, s_offset16 = self._fetch_byte_from_program(), self._fetch_byte_from_program(), self._fetch_signed_word_le_from_program()
                rd_name, rbase_name = self._get_reg_name(rd_code), self._get_reg_name(rbase_code);
                base_addr_val = self.registers[rbase_name]
                eff_addr = self._apply_16bit_limits(base_addr_val + s_offset16)
                if not self._is_valid_data_memory_byte_address(eff_addr + 1): raise ValueError(
                    f"LOADFR: Invalid memory access at byte addr 0x{eff_addr:04X}")
                low, high = self.data_memory[eff_addr], self.data_memory[eff_addr + 1];
                val = (high << 8) | low
                self.registers[rd_name] = self._apply_16bit_limits(val);
                self._update_flags(self.registers[rd_name], "LOADFR")
                self.output_log.append(
                    f"  LOADFR: {rd_name} = Mem[{rbase_name}(0x{base_addr_val:04X}) + #{s_offset16} => 0x{eff_addr:04X}]")
            elif opcode_str == "STORFR":
                rt_code, rbase_code, s_offset16 = self._fetch_byte_from_program(), self._fetch_byte_from_program(), self._fetch_signed_word_le_from_program()
                rt_name, rbase_name = self._get_reg_name(rt_code), self._get_reg_name(rbase_code);
                val_to_store = self.registers[rt_name]
                base_addr_val = self.registers[rbase_name];
                eff_addr = self._apply_16bit_limits(base_addr_val + s_offset16)
                if not self._is_valid_data_memory_byte_address(eff_addr + 1): raise ValueError(
                    f"STORFR: Invalid memory access at byte addr 0x{eff_addr:04X}")
                val16 = self._apply_16bit_limits(val_to_store)
                self.data_memory[eff_addr] = val16 & 0xFF;
                self.data_memory[eff_addr + 1] = (val16 >> 8) & 0xFF
                self.output_log.append(
                    f"  STORFR: Mem[{rbase_name}(0x{base_addr_val:04X}) + #{s_offset16} => 0x{eff_addr:04X}] = {rt_name}")


            elif opcode_str == "LOADBFR":
                rd_code, rbase_code, s_offset16 = self._fetch_byte_from_program(), self._fetch_byte_from_program(), self._fetch_signed_word_le_from_program()
                rd_name, rbase_name = self._get_reg_name(rd_code), self._get_reg_name(rbase_code)
                base_addr_val = self.registers[rbase_name]
                eff_addr = self._apply_16bit_limits(base_addr_val + s_offset16)
                if not self._is_valid_data_memory_byte_address(eff_addr):
                    raise ValueError(f"LOADBFR: Invalid byte address 0x{eff_addr:04X}")
                val = self.data_memory[eff_addr]
                self.registers[rd_name] = self._apply_16bit_limits(val)
                self._update_flags(self.registers[rd_name], "LOADBFR")
                self.output_log.append(f"  LOADBFR: {rd_name} = Mem[{rbase_name}(0x{base_addr_val:04X}) + #{s_offset16} => BYTE:0x{eff_addr:04X}] = 0x{val:02X}")

            elif opcode_str == "STORBFR":
                rt_code, rbase_code, s_offset16 = self._fetch_byte_from_program(), self._fetch_byte_from_program(), self._fetch_signed_word_le_from_program()
                rt_name, rbase_name = self._get_reg_name(rt_code), self._get_reg_name(rbase_code)
                val_to_store = self.registers[rt_name]
                base_addr_val = self.registers[rbase_name]
                eff_addr = self._apply_16bit_limits(base_addr_val + s_offset16)
                if not self._is_valid_data_memory_byte_address(eff_addr):
                    raise ValueError(f"STORBFR: Invalid byte address 0x{eff_addr:04X}")
                self.data_memory[eff_addr] = val_to_store & 0xFF
                self.output_log.append(f"  STORBFR: Mem[{rbase_name}(0x{base_addr_val:04X}) + #{s_offset16} => BYTE:0x{eff_addr:04X}] = {rt_name}(0x{val_to_store & 0xFF:02X})")


            # handles memory-mapped IO access
            elif opcode_str == "LOADI":
                print("DEBUG: NEW LOADI CODE IS RUNNING!")  # This should appear in output

                rd_code, rs_addr_code = self._fetch_byte_from_program(), self._fetch_byte_from_program()
                rd_name, rs_addr_name = self._get_reg_name(rd_code), self._get_reg_name(rs_addr_code)
                byte_address = self.registers[rs_addr_name]

                print(f"DEBUG: LOADI byte_address=0x{byte_address:04X}")  # Debug the address

                # CORRECTED: Check if the byte address itself is an MMIO address
                is_mmio_address = (
                        byte_address == DEFAULT_MMIO_INPUT_ADDR or
                        byte_address == DEFAULT_MMIO_OUTPUT_ADDR or
                        0x1800 <= byte_address <= 0x181F  # MMIO peripheral range (direct comparison)
                )

                print(f"DEBUG: is_mmio_address={is_mmio_address}")  # Debug MMIO check

                if is_mmio_address:
                    print("DEBUG: Calling MMIO handler with byte_address!")
                    # Handle as MMIO - pass the byte address directly to MMIO handler
                    val = self._handle_mmio_read(byte_address)
                    self.output_log.append(f"  LOADI: {rd_name} = MMIO[0x{byte_address:04X}h] = 0x{val:04X}")
                elif self._is_valid_data_memory_byte_address(byte_address) and \
                        self._is_valid_data_memory_byte_address(byte_address + 1):
                    print("DEBUG: Reading from data memory")
                    # Read directly from data memory as a word (little-endian)
                    low = self.data_memory[byte_address]
                    high = self.data_memory[byte_address + 1]
                    val = (high << 8) | low
                    self.output_log.append(
                        f"  LOADI: {rd_name} = Mem[{rs_addr_name}(ADDR:0x{byte_address:04X})] = 0x{val:04X}")
                else:
                    print("DEBUG: Invalid address")
                    # Invalid address
                    raise ValueError(f"LOADI: Invalid address 0x{byte_address:04X}")

                self.registers[rd_name] = self._apply_16bit_limits(val)
                self._update_flags(self.registers[rd_name], "LOADI")


            # handles memory-mapped IO access
            elif opcode_str == "STORI":
                rt_val_code, rs_addr_code = self._fetch_byte_from_program(), self._fetch_byte_from_program()
                rt_val_name, rs_addr_name = self._get_reg_name(rt_val_code), self._get_reg_name(rs_addr_code)
                byte_address = self.registers[rs_addr_name]
                val_to_store = self.registers[rt_val_name]

                # Check if this is an MMIO address first (same logic as LOADI)
                is_mmio_address = (
                        byte_address == DEFAULT_MMIO_INPUT_ADDR or
                        byte_address == DEFAULT_MMIO_OUTPUT_ADDR or
                        0x1800 <= byte_address <= 0x181F  # MMIO peripheral range
                )

                if is_mmio_address:
                    # Handle as MMIO
                    self._handle_mmio_write(byte_address, val_to_store)
                    self.output_log.append(
                        f"  STORI: MMIO[0x{byte_address:04X}h] = {rt_val_name}(0x{val_to_store:04X})")
                elif self._is_valid_data_memory_byte_address(byte_address) and \
                        self._is_valid_data_memory_byte_address(byte_address + 1):
                    # Write directly to data memory as a word (little-endian)
                    val16 = self._apply_16bit_limits(val_to_store)
                    self.data_memory[byte_address] = val16 & 0xFF
                    self.data_memory[byte_address + 1] = (val16 >> 8) & 0xFF
                    self.output_log.append(
                        f"  STORI: Mem[{rs_addr_name}(ADDR:0x{byte_address:04X})] = {rt_val_name}(0x{val_to_store:04X})")
                else:
                    # Invalid address
                    raise ValueError(f"STORI: Invalid address 0x{byte_address:04X}")



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
                rd_code, addr16 = self._fetch_byte_from_program(), self._fetch_word_le_from_program();
                rd_name = self._get_reg_name(rd_code)
                val = self._handle_mmio_read(addr16);
                self.registers[rd_name] = self._apply_16bit_limits(val);
                self._update_flags(self.registers[rd_name], "INM")
                self.output_log.append(
                    f"  INM: {rd_name} = Mem[0x{addr16:04X}] (Value=0x{self.registers[rd_name]:04X})")
            elif opcode_str == "OUTM":
                rs_code, addr16 = self._fetch_byte_from_program(), self._fetch_word_le_from_program();
                rs_name = self._get_reg_name(rs_code)
                self._handle_mmio_write(addr16, self.registers[rs_name]);
                self.output_log.append(f"  OUTM: Mem[0x{addr16:04X}h] = {rs_name}(0x{self.registers[rs_name]:04X})")
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
                rs_code = self._fetch_byte_from_program();
                rs_name = self._get_reg_name(rs_code)
                if self.sp < self.stack_limit: raise ValueError(
                    f"Stack Overflow on PUSH. SP(0x{self.sp:04X}h) at/below Limit(0x{self.stack_limit:04X}h).")
                if not self._is_valid_data_memory_byte_address(self.sp + 1): raise ValueError(
                    f"PUSH: Invalid SP 0x{self.sp:04X}h before store.")
                val_to_push = self.registers[rs_name];
                val16 = self._apply_16bit_limits(val_to_push)
                self.data_memory[self.sp] = val16 & 0xFF;
                self.data_memory[self.sp + 1] = (val16 >> 8) & 0xFF
                self.output_log.append(f"  PUSH: {rs_name}(0x{val_to_push:04X}) to Mem[SP=0x{self.sp:04X}h].")
                self.sp = (self.sp - 2) & MAX_ADDRESS_16BIT
            elif opcode_str == "POP":
                rd_code = self._fetch_byte_from_program();
                rd_name = self._get_reg_name(rd_code)
                new_sp = (self.sp + 2) & MAX_ADDRESS_16BIT
                if new_sp > self.stack_base: raise ValueError(f"Stack Underflow on POP. SP would be > base.")
                self.sp = new_sp
                if not self._is_valid_data_memory_byte_address(self.sp + 1): raise ValueError(
                    f"POP: Invalid SP 0x{self.sp:04X}h after increment.")
                low, high = self.data_memory[self.sp], self.data_memory[self.sp + 1];
                val_popped = (high << 8) | low
                self.registers[rd_name] = self._apply_16bit_limits(val_popped);
                self._update_flags(self.registers[rd_name], "POP")
                self.output_log.append(f"  POP: {rd_name} = Mem[SP=0x{self.sp:04X}h] (Val=0x{val_popped:04X}).")
            elif opcode_str == "CALL":
                target_addr16 = self._fetch_word_le_from_program();
                ret_addr = self.program_counter
                if self.sp < self.stack_limit: raise ValueError("Stack Overflow on CALL for return address.")
                if not self._is_valid_data_memory_byte_address(self.sp + 1): raise ValueError(
                    "CALL: Invalid SP for ret_addr push.")
                ret16 = self._apply_16bit_limits(ret_addr)
                self.data_memory[self.sp] = ret16 & 0xFF;
                self.data_memory[self.sp + 1] = (ret16 >> 8) & 0xFF
                self.output_log.append(
                    f"  CALL: Pushed RetAddr(0x{ret_addr:04X}h) to Stack[SP=0x{self.sp:04X}h]. JMP to 0x{target_addr16:04X}h.")
                self.sp = (self.sp - 2) & MAX_ADDRESS_16BIT;
                self.program_counter = self._apply_16bit_limits(target_addr16)
            elif opcode_str == "RET":
                new_sp = (self.sp + 2) & MAX_ADDRESS_16BIT
                if new_sp > self.stack_base: raise ValueError("Stack Underflow on RET.")
                self.sp = new_sp
                if not self._is_valid_data_memory_byte_address(self.sp + 1): raise ValueError(
                    "RET: Invalid SP for ret_addr pop.")
                low, high = self.data_memory[self.sp], self.data_memory[self.sp + 1];
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
        self.output_log.append(f"Final Flags: ZF={int(self.ZF)} SF={int(self.SF)} CF={int(self.CF)} OF={int(self.OF)}")
        return "\n".join(self.output_log)

    def print_final_state(self):
        print("\n--- Final Simulator State (print_final_state) ---")
        for i in sorted(REG_NAMES.keys()):
            print(
                f"Reg {REG_NAMES[i]:<3}: {self.registers[REG_NAMES[i]]:<5} (0x{self.registers[REG_NAMES[i]]:04X}) ({self.registers[REG_NAMES[i]]:016b}b)")
        print(
            f"SP: 0x{self.sp:04X}h ({self.sp}) PC:0x{self.program_counter:04X}h ({self.program_counter}) Flags: Z{int(self.ZF)}S{int(self.SF)}C{int(self.CF)}O{int(self.OF)}")
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
        sim = MicroprocessorSimulator(data_memory_size=8192, stack_size=256)
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
