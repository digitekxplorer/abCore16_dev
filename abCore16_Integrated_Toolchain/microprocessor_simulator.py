# microprocessor_simulator.py
# June 27, 2025
# Generate base_filename.txt, .coe, and .hex files

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
        self.data_memory = [0] * self.data_memory_size
        self.stack_base = data_memory_size
        self.stack_limit = data_memory_size - stack_size if stack_size <= data_memory_size else 0
        self.sp = self.stack_base
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
        self.mmio_output_lines = []  # To store MMIO output for file writing

    def _reset_state(self):
        self.registers = {reg_name: 0 for reg_name in REG_NAMES.values()}
        self.data_memory = [0] * self.data_memory_size
        self.sp = self.stack_base
        self.program_counter = 0;
        self.program_bytes = []
        self.ZF, self.SF, self.CF, self.OF = False, False, False, False
        self.halted, self.clean_halt = False, False
        self.sim_input_buffer, self.sim_last_output_value = None, None
        self.mmio_output_lines = []  # Clear MMIO output for the new run
        self.output_log = [
            f"--- Sim Start (DataMemWords:{self.data_memory_size}, StackBase:{self.stack_base:04X}h, StackLimit:{self.stack_limit:04X}h) ---",
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

        if operation_str_for_log in ["LOAD", "LOADM", "MOV", "POP", "INP", "INM", "LOADFR", "MOVFRSP", "LOADI"] and \
                carry_occurred is None and overflow_occurred is None and \
                not clear_carry_overflow_for_logical and not is_compare_op:
            log_arith_flags = False

        if is_compare_op: log_arith_flags = True

        if log_arith_flags:
            self.output_log.append(
                f"    Flags set: ZF={int(self.ZF)} SF={int(self.SF)} CF={int(self.CF)} OF={int(self.OF)} (for val 0x{val_for_flags:04X})")

    def _is_valid_data_memory_word_address(self, address):
        return 0 <= address < self.data_memory_size

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

    def _handle_mmio_read(self, address):
        eff_addr = self._apply_16bit_limits(address)
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
        if self._is_valid_data_memory_word_address(eff_addr): return self.data_memory[eff_addr]
        self.output_log.append(f"Sim WARN: MMIO Read unmapped addr 0x{eff_addr:04X}h. Ret 0.");
        return 0

    def _handle_mmio_write(self, address, value):
        eff_addr = self._apply_16bit_limits(address);
        val16 = self._apply_16bit_limits(value)
        if eff_addr == DEFAULT_MMIO_OUTPUT_ADDR:
            self.sim_last_output_value = val16
            output_line = f"SIM MMIO OUTPUT (0x{eff_addr:04X}h): {val16}"
            print(output_line)  # Keep printing to console for live feedback
            self.mmio_output_lines.append(output_line)  # Capture for file output
            self.output_log.append(f"  MMIO Write OUTPUT(0x{eff_addr:04X}h): Val=0x{val16:04X}")
        elif self._is_valid_data_memory_word_address(eff_addr):
            self.data_memory[eff_addr] = val16
        else:
            self.output_log.append(f"Sim WARN: MMIO Write unmapped addr 0x{eff_addr:04X}h. Ignored.")

    def execute_cycle(self):
        # This function does not need changes.
        # ... (rest of the file is unchanged) ...
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
                self.halted, self.clean_halt = True, True
                self.output_log.append("  HALT: CPU Halted by instruction.")

            elif opcode_str == "LOAD":
                rd_code = self._fetch_byte_from_program()
                imm16 = self._fetch_word_le_from_program()
                if rd_code is None or imm16 is None: raise ValueError("LOAD operands missing or EOF.")
                rd_name = self._get_reg_name(rd_code)
                self.registers[rd_name] = self._apply_16bit_limits(imm16)
                self._update_flags(self.registers[rd_name], "LOAD")
                self.output_log.append(f"  LOAD: {rd_name} = #0x{imm16:04X} (Stored 0x{self.registers[rd_name]:04X})")

            elif opcode_str == "STORE":
                rs_code = self._fetch_byte_from_program()
                addr16 = self._fetch_word_le_from_program()
                if rs_code is None or addr16 is None: raise ValueError("STORE operands missing or EOF.")
                rs_name = self._get_reg_name(rs_code)
                val_to_store = self.registers[rs_name]
                self._handle_mmio_write(addr16, val_to_store)
                self.output_log.append(f"  STORE: Mem[0x{addr16:04X}h] = {rs_name}(0x{val_to_store:04X})")

            elif opcode_str == "LOADM":
                rd_code = self._fetch_byte_from_program()
                addr16 = self._fetch_word_le_from_program()
                if rd_code is None or addr16 is None: raise ValueError("LOADM operands missing or EOF.")
                rd_name = self._get_reg_name(rd_code)
                val_from_mem = self._handle_mmio_read(addr16)
                self.registers[rd_name] = self._apply_16bit_limits(val_from_mem)
                self._update_flags(self.registers[rd_name], "LOADM")
                self.output_log.append(
                    f"  LOADM: {rd_name} = Mem[0x{addr16:04X}h] (Value=0x{self.registers[rd_name]:04X})")

            elif opcode_str == "LOADFR":
                rd_code = self._fetch_byte_from_program()
                rbase_code = self._fetch_byte_from_program()
                s_offset16 = self._fetch_signed_word_le_from_program()
                if rd_code is None or rbase_code is None or s_offset16 is None: raise ValueError(
                    "LOADFR operands missing or EOF.")
                rd_name = self._get_reg_name(rd_code)
                rbase_name = self._get_reg_name(rbase_code)
                base_addr_val = self.registers[rbase_name]
                effective_addr = self._apply_16bit_limits(base_addr_val + s_offset16)
                if not self._is_valid_data_memory_word_address(effective_addr):
                    raise ValueError(
                        f"LOADFR: Invalid memory access at 0x{effective_addr:04X} (Base=0x{base_addr_val:04X}, Offset={s_offset16})")
                value_loaded = self.data_memory[effective_addr]
                self.registers[rd_name] = self._apply_16bit_limits(value_loaded)
                self._update_flags(self.registers[rd_name], "LOADFR")
                self.output_log.append(
                    f"  LOADFR: {rd_name} = Mem[{rbase_name}(0x{base_addr_val:04X}) + #{s_offset16} => 0x{effective_addr:04X}] (Value=0x{self.registers[rd_name]:04X})")

            elif opcode_str == "STORFR":
                rt_code = self._fetch_byte_from_program()
                rbase_code = self._fetch_byte_from_program()
                s_offset16 = self._fetch_signed_word_le_from_program()
                if rt_code is None or rbase_code is None or s_offset16 is None: raise ValueError(
                    "STORFR operands missing or EOF.")
                rt_name = self._get_reg_name(rt_code)
                rbase_name = self._get_reg_name(rbase_code)
                val_to_store = self.registers[rt_name]
                base_addr_val = self.registers[rbase_name]
                effective_addr = self._apply_16bit_limits(base_addr_val + s_offset16)
                if not self._is_valid_data_memory_word_address(effective_addr):
                    raise ValueError(
                        f"STORFR: Invalid memory access at 0x{effective_addr:04X} (Base=0x{base_addr_val:04X}, Offset={s_offset16})")
                self.data_memory[effective_addr] = self._apply_16bit_limits(val_to_store)
                self.output_log.append(
                    f"  STORFR: Mem[{rbase_name}(0x{base_addr_val:04X}) + #{s_offset16} => 0x{effective_addr:04X}] = {rt_name}(0x{val_to_store:04X})")

            elif opcode_str == "LOADI":
                rd_code = self._fetch_byte_from_program()
                rs_addr_code = self._fetch_byte_from_program()
                if rd_code is None or rs_addr_code is None: raise ValueError("LOADI operands missing or EOF.")
                rd_name = self._get_reg_name(rd_code)
                rs_addr_name = self._get_reg_name(rs_addr_code)

                address = self.registers[rs_addr_name]
                val_from_mem = self._handle_mmio_read(address)

                self.registers[rd_name] = self._apply_16bit_limits(val_from_mem)
                self._update_flags(self.registers[rd_name], "LOADI")
                self.output_log.append(
                    f"  LOADI: {rd_name} = Mem[{rs_addr_name}(0x{address:04X})] (Value=0x{self.registers[rd_name]:04X})")

            elif opcode_str == "STORI":
                rt_val_code = self._fetch_byte_from_program()
                rs_addr_code = self._fetch_byte_from_program()
                if rt_val_code is None or rs_addr_code is None: raise ValueError("STORI operands missing or EOF.")
                rt_val_name = self._get_reg_name(rt_val_code)
                rs_addr_name = self._get_reg_name(rs_addr_code)

                address = self.registers[rs_addr_name]
                val_to_store = self.registers[rt_val_name]

                self._handle_mmio_write(address, val_to_store)
                self.output_log.append(
                    f"  STORI: Mem[{rs_addr_name}(0x{address:04X})] = {rt_val_name}(0x{val_to_store:04X})")

            elif opcode_str == "MOVFRSP":
                rd_code = self._fetch_byte_from_program()
                if rd_code is None: raise ValueError("MOVFRSP operand missing or EOF.")
                rd_name = self._get_reg_name(rd_code)
                self.registers[rd_name] = self._apply_16bit_limits(self.sp)
                self._update_flags(self.registers[rd_name], "MOVFRSP")
                self.output_log.append(f"  MOVFRSP: {rd_name} = SP(0x{self.sp:04X})")

            elif opcode_str == "MOVTOSP":
                rs_code = self._fetch_byte_from_program()
                if rs_code is None: raise ValueError("MOVTOSP operand missing or EOF.")
                rs_name = self._get_reg_name(rs_code)
                new_sp_val = self.registers[rs_name]
                self.sp = self._apply_16bit_limits(new_sp_val)
                self.output_log.append(f"  MOVTOSP: SP = {rs_name}(0x{new_sp_val:04X}). New SP=0x{self.sp:04X}h")

            elif opcode_str == "INP":
                rd_code = self._fetch_byte_from_program()
                if rd_code is None: raise ValueError("INP operand missing or EOF.")
                rd_name = self._get_reg_name(rd_code)
                val = self._handle_mmio_read(DEFAULT_MMIO_INPUT_ADDR)
                self.registers[rd_name] = self._apply_16bit_limits(val)
                self._update_flags(self.registers[rd_name], "INP")
                self.output_log.append(f"  INP: {rd_name} = 0x{self.registers[rd_name]:04X}")

            elif opcode_str == "OUT":
                rs_code = self._fetch_byte_from_program()
                if rs_code is None: raise ValueError("OUT operand missing or EOF.")
                rs_name = self._get_reg_name(rs_code)
                self._handle_mmio_write(DEFAULT_MMIO_OUTPUT_ADDR, self.registers[rs_name])
                self.output_log.append(f"  OUT: Value from {rs_name}(0x{self.registers[rs_name]:04X})")

            elif opcode_str == "INM":
                rd_code = self._fetch_byte_from_program()
                addr16 = self._fetch_word_le_from_program()
                if rd_code is None or addr16 is None: raise ValueError("INM operands missing or EOF.")
                rd_name = self._get_reg_name(rd_code)
                val = self._handle_mmio_read(addr16)
                self.registers[rd_name] = self._apply_16bit_limits(val)
                self._update_flags(self.registers[rd_name], "INM")
                self.output_log.append(
                    f"  INM: {rd_name} = Mem[0x{addr16:04X}] (Value=0x{self.registers[rd_name]:04X})")

            elif opcode_str == "OUTM":
                rs_code = self._fetch_byte_from_program()
                addr16 = self._fetch_word_le_from_program()
                if rs_code is None or addr16 is None: raise ValueError("OUTM operands missing or EOF.")
                rs_name = self._get_reg_name(rs_code)
                self._handle_mmio_write(addr16, self.registers[rs_name])
                self.output_log.append(f"  OUTM: Mem[0x{addr16:04X}h] = {rs_name}(0x{self.registers[rs_name]:04X})")

            elif opcode_str == "ADD":
                r1_code = self._fetch_byte_from_program();
                r2_code = self._fetch_byte_from_program()
                if r1_code is None or r2_code is None: raise ValueError("ADD operands missing or EOF.")
                r1_name, r2_name = self._get_reg_name(r1_code), self._get_reg_name(r2_code)
                v1, v2 = self.registers[r1_name], self.registers[r2_name]
                res_raw = v1 + v2;
                res16 = self._apply_16bit_limits(res_raw)
                carry = res_raw > MAX_IMMEDIATE_16BIT
                s1, s2, sr = (v1 & 0x8000), (v2 & 0x8000), (res16 & 0x8000)
                overflow = (s1 == s2) and (sr != s1)
                self.registers[r1_name] = res16
                self._update_flags(res16, "ADD", carry_occurred=carry, overflow_occurred=overflow)
                self.output_log.append(f"  ADD: {r1_name}(0x{v1:04X}) + {r2_name}(0x{v2:04X}) = 0x{res16:04X}")

            elif opcode_str == "SUB":
                r1_code = self._fetch_byte_from_program();
                r2_code = self._fetch_byte_from_program()
                if r1_code is None or r2_code is None: raise ValueError("SUB operands missing or EOF.")
                r1_name, r2_name = self._get_reg_name(r1_code), self._get_reg_name(r2_code)
                v1, v2 = self.registers[r1_name], self.registers[r2_name]
                res_raw = v1 - v2;
                res16 = self._apply_16bit_limits(res_raw)
                borrow = v1 < v2
                s1, s2, sr = (v1 & 0x8000), (v2 & 0x8000), (res16 & 0x8000)
                overflow = (s1 != s2) and (sr != s1)
                self.registers[r1_name] = res16
                self._update_flags(res16, "SUB", carry_occurred=borrow, overflow_occurred=overflow)
                self.output_log.append(f"  SUB: {r1_name}(0x{v1:04X}) - {r2_name}(0x{v2:04X}) = 0x{res16:04X}")

            elif opcode_str == "MUL":
                r1_code = self._fetch_byte_from_program();
                r2_code = self._fetch_byte_from_program()
                if r1_code is None or r2_code is None: raise ValueError("MUL operands missing or EOF.")
                r1_name, r2_name = self._get_reg_name(r1_code), self._get_reg_name(r2_code)
                v1, v2 = self.registers[r1_name], self.registers[r2_name]
                res_raw = v1 * v2;
                res16 = self._apply_16bit_limits(res_raw)
                carry = res_raw > MAX_IMMEDIATE_16BIT
                self.registers[r1_name] = res16
                self._update_flags(res16, "MUL", carry_occurred=carry, overflow_occurred=carry)
                self.output_log.append(f"  MUL: {r1_name}(0x{v1:04X}) * {r2_name}(0x{v2:04X}) = 0x{res16:04X}")

            elif opcode_str == "INC":
                rd_code = self._fetch_byte_from_program()
                if rd_code is None: raise ValueError("INC operand missing or EOF.")
                rd_name = self._get_reg_name(rd_code)
                v1 = self.registers[rd_name];
                res_raw = v1 + 1;
                res16 = self._apply_16bit_limits(res_raw)
                carry = res_raw > MAX_IMMEDIATE_16BIT
                overflow = (v1 == 0x7FFF)
                self.registers[rd_name] = res16
                self._update_flags(res16, "INC", carry_occurred=carry, overflow_occurred=overflow)
                self.output_log.append(f"  INC: {rd_name} from 0x{v1:04X} to 0x{res16:04X}")

            elif opcode_str == "DEC":
                rd_code = self._fetch_byte_from_program()
                if rd_code is None: raise ValueError("DEC operand missing or EOF.")
                rd_name = self._get_reg_name(rd_code)
                v1 = self.registers[rd_name];
                res_raw = v1 - 1;
                res16 = self._apply_16bit_limits(res_raw)
                borrow = (v1 == 0)
                overflow = (v1 == 0x8000)
                self.registers[rd_name] = res16
                self._update_flags(res16, "DEC", carry_occurred=borrow, overflow_occurred=overflow)
                self.output_log.append(f"  DEC: {rd_name} from 0x{v1:04X} to 0x{res16:04X}")

            elif opcode_str in ["AND", "OR", "XOR"]:
                r1_code = self._fetch_byte_from_program();
                r2_code = self._fetch_byte_from_program()
                if r1_code is None or r2_code is None: raise ValueError(f"{opcode_str} operands missing or EOF.")
                r1_name, r2_name = self._get_reg_name(r1_code), self._get_reg_name(r2_code)
                v1, v2 = self.registers[r1_name], self.registers[r2_name]
                res16 = (v1 & v2) if opcode_str == "AND" else (v1 | v2) if opcode_str == "OR" else (v1 ^ v2)
                self.registers[r1_name] = self._apply_16bit_limits(res16)
                self._update_flags(self.registers[r1_name], opcode_str, clear_carry_overflow_for_logical=True)
                self.output_log.append(
                    f"  {opcode_str}: {r1_name}(0x{v1:04X}) op {r2_name}(0x{v2:04X}) = 0x{self.registers[r1_name]:04X}")

            elif opcode_str == "NOT":
                rd_code = self._fetch_byte_from_program()
                if rd_code is None: raise ValueError("NOT operand missing or EOF.")
                rd_name = self._get_reg_name(rd_code)
                self.registers[rd_name] = self._apply_16bit_limits(~self.registers[rd_name])
                self._update_flags(self.registers[rd_name], "NOT", clear_carry_overflow_for_logical=True)
                self.output_log.append(f"  NOT: {rd_name} = 0x{self.registers[rd_name]:04X}")

            elif opcode_str == "SHL":
                rd_code = self._fetch_byte_from_program();
                sa_byte = self._fetch_byte_from_program()
                if rd_code is None or sa_byte is None: raise ValueError("SHL operands missing or EOF.")
                rd_name, shift_amount = self._get_reg_name(rd_code), sa_byte
                v1 = self.registers[rd_name]
                carry_out = (v1 >> (16 - shift_amount)) & 1 if 0 < shift_amount <= 16 else 0
                res16 = self._apply_16bit_limits(v1 << shift_amount)
                self.registers[rd_name] = res16
                self._update_flags(res16, "SHL", carry_occurred=(carry_out if shift_amount > 0 else self.CF),
                                   overflow_occurred=False)
                self.output_log.append(f"  SHL: {rd_name}(0x{v1:04X}) << {shift_amount} = 0x{res16:04X}")

            elif opcode_str == "SHR":
                rd_code = self._fetch_byte_from_program();
                sa_byte = self._fetch_byte_from_program()
                if rd_code is None or sa_byte is None: raise ValueError("SHR operands missing or EOF.")
                rd_name, shift_amount = self._get_reg_name(rd_code), sa_byte
                v1 = self.registers[rd_name]
                carry_out = (v1 >> (shift_amount - 1)) & 1 if 0 < shift_amount <= 16 else 0
                res16 = self._apply_16bit_limits(v1 >> shift_amount)
                self.registers[rd_name] = res16
                self._update_flags(res16, "SHR", carry_occurred=(carry_out if shift_amount > 0 else self.CF),
                                   overflow_occurred=False)
                self.output_log.append(f"  SHR: {rd_name}(0x{v1:04X}) >> {shift_amount} = 0x{res16:04X}")

            elif opcode_str in ["L_AND", "L_OR"]:
                rd_c, rs1_c, rs2_c = self._fetch_byte_from_program(), self._fetch_byte_from_program(), self._fetch_byte_from_program()
                if rd_c is None or rs1_c is None or rs2_c is None: raise ValueError(f"{opcode_str} operands missing")
                rd_n, rs1_n, rs2_n = self._get_reg_name(rd_c), self._get_reg_name(rs1_c), self._get_reg_name(rs2_c)
                v1_bool, v2_bool = (self.registers[rs1_n] != 0), (self.registers[rs2_n] != 0)
                res_bool = (v1_bool and v2_bool) if opcode_str == "L_AND" else (v1_bool or v2_bool)
                self.registers[rd_n] = 1 if res_bool else 0
                self._update_flags(self.registers[rd_n], opcode_str, clear_carry_overflow_for_logical=True)
                self.output_log.append(f"  {opcode_str}: {rd_n} = ({rs1_n} op {rs2_n}) -> {self.registers[rd_n]}")

            elif opcode_str == "L_NOT":
                rd_c, rs_c = self._fetch_byte_from_program(), self._fetch_byte_from_program()
                if rd_c is None or rs_c is None: raise ValueError("L_NOT operands missing")
                rd_n, rs_n = self._get_reg_name(rd_c), self._get_reg_name(rs_c)
                self.registers[rd_n] = 1 if self.registers[rs_n] == 0 else 0
                self._update_flags(self.registers[rd_n], "L_NOT", clear_carry_overflow_for_logical=True)
                self.output_log.append(f"  L_NOT: {rd_n} = !{rs_n} -> {self.registers[rd_n]}")

            elif opcode_str == "CMP":
                r1_code = self._fetch_byte_from_program();
                r2_code = self._fetch_byte_from_program()
                if r1_code is None or r2_code is None: raise ValueError("CMP operands missing or EOF.")
                r1_name, r2_name = self._get_reg_name(r1_code), self._get_reg_name(r2_code)
                v1, v2 = self.registers[r1_name], self.registers[r2_name]
                res_raw = v1 - v2;
                res16_for_flags = self._apply_16bit_limits(res_raw)
                borrow = v1 < v2
                s1, s2, sr = (v1 & 0x8000), (v2 & 0x8000), (res16_for_flags & 0x8000)
                overflow = (s1 != s2) and (sr != s1)
                self._update_flags(res16_for_flags, "CMP", carry_occurred=borrow, overflow_occurred=overflow,
                                   is_compare_op=True)
                self.output_log.append(f"  CMP: {r1_name}(0x{v1:04X}) vs {r2_name}(0x{v2:04X}). Flags set.")

            elif opcode_str == "MOV":
                rd_code = self._fetch_byte_from_program();
                rs_code = self._fetch_byte_from_program()
                if rd_code is None or rs_code is None: raise ValueError("MOV operands missing or EOF.")
                rd_name, rs_name = self._get_reg_name(rd_code), self._get_reg_name(rs_code)
                self.registers[rd_name] = self.registers[rs_name]
                self._update_flags(self.registers[rd_name], "MOV")
                self.output_log.append(f"  MOV: {rd_name} = {rs_name}(0x{self.registers[rd_name]:04X})")

            elif opcode_str == "PUSH":
                rs_code = self._fetch_byte_from_program()
                if rs_code is None: raise ValueError("PUSH operand missing or EOF.")
                rs_name = self._get_reg_name(rs_code)
                if self.sp <= self.stack_limit: raise ValueError(
                    f"Stack Overflow on PUSH. SP(0x{self.sp:04X}h) at/below Limit(0x{self.stack_limit:04X}h).")
                self.sp = (self.sp - 1) & MAX_ADDRESS_16BIT
                if not self._is_valid_data_memory_word_address(self.sp): raise ValueError(
                    f"PUSH: Invalid SP 0x{self.sp:04X}h after decrement.")
                val_to_push = self.registers[rs_name]
                self.data_memory[self.sp] = self._apply_16bit_limits(val_to_push)
                self.output_log.append(f"  PUSH: {rs_name}(0x{val_to_push:04X}) to Mem[SP=0x{self.sp:04X}h].")

            elif opcode_str == "POP":
                rd_code = self._fetch_byte_from_program()
                if rd_code is None: raise ValueError("POP operand missing or EOF.")
                rd_name = self._get_reg_name(rd_code)
                if self.sp >= self.stack_base: raise ValueError(
                    f"Stack Underflow on POP. SP(0x{self.sp:04X}h) at/above Base(0x{self.stack_base:04X}h).")
                if not self._is_valid_data_memory_word_address(self.sp): raise ValueError(
                    f"POP: Invalid SP 0x{self.sp:04X}h before increment.")
                val_popped = self.data_memory[self.sp]
                self.sp = (self.sp + 1) & MAX_ADDRESS_16BIT
                self.registers[rd_name] = self._apply_16bit_limits(val_popped)
                self._update_flags(self.registers[rd_name], "POP")
                self.output_log.append(
                    f"  POP: {rd_name} = Mem[SP(old)=0x{(self.sp - 1) & MAX_ADDRESS_16BIT:04X}h] (Val=0x{val_popped:04X}). New SP=0x{self.sp:04X}h.")

            elif opcode_str == "CALL":
                target_addr16 = self._fetch_word_le_from_program()
                if target_addr16 is None: raise ValueError("CALL target address missing or EOF.")
                ret_addr = self.program_counter
                if self.sp <= self.stack_limit: raise ValueError("Stack Overflow on CALL for return address.")
                self.sp = (self.sp - 1) & MAX_ADDRESS_16BIT
                if not self._is_valid_data_memory_word_address(self.sp): raise ValueError(
                    "CALL: Invalid SP for ret_addr push.")
                self.data_memory[self.sp] = self._apply_16bit_limits(ret_addr)
                self.program_counter = self._apply_16bit_limits(target_addr16)
                self.output_log.append(
                    f"  CALL: Pushed RetAddr(0x{ret_addr:04X}h) to Stack[SP=0x{self.sp:04X}h]. JMP to 0x{self.program_counter:04X}h.")

            elif opcode_str == "RET":
                if self.sp >= self.stack_base: raise ValueError("Stack Underflow on RET.")
                if not self._is_valid_data_memory_word_address(self.sp): raise ValueError(
                    "RET: Invalid SP for ret_addr pop.")
                ret_addr_from_stack = self.data_memory[self.sp]
                self.sp = (self.sp + 1) & MAX_ADDRESS_16BIT
                self.program_counter = self._apply_16bit_limits(ret_addr_from_stack)
                self.output_log.append(
                    f"  RET: Popped RetAddr(0x{self.program_counter:04X}h) from Stack[SP(old)=0x{(self.sp - 1) & MAX_ADDRESS_16BIT:04X}h]. JMP.")

            elif opcode_str.startswith("J"):
                is_reg_cond_jmp = opcode_str in ["JMPZ", "JMPN"];
                reg_c = None
                if is_reg_cond_jmp: reg_c = self._fetch_byte_from_program()
                target_addr16 = self._fetch_word_le_from_program()
                if target_addr16 is None or (is_reg_cond_jmp and reg_c is None): raise ValueError(
                    f"{opcode_str} operands missing or EOF.")
                condition_met = False;
                log_cond_detail = ""
                if opcode_str == "JMP":
                    condition_met = True
                elif opcode_str == "JMPZ":
                    rn = self._get_reg_name(reg_c); condition_met = (
                                self.registers[rn] == 0); log_cond_detail = f"({rn}==0)"
                elif opcode_str == "JMPN":
                    rn = self._get_reg_name(reg_c); condition_met = (
                                (self.registers[rn] & 0x8000) != 0); log_cond_detail = f"({rn}<0)"
                elif opcode_str == "JE":
                    condition_met = self.ZF;  log_cond_detail = "(ZF=1)"
                elif opcode_str == "JNE":
                    condition_met = not self.ZF;log_cond_detail = "(ZF=0)"
                elif opcode_str == "JS":
                    condition_met = self.SF;  log_cond_detail = "(SF=1)"
                elif opcode_str == "JNS":
                    condition_met = not self.SF;log_cond_detail = "(SF=0)"
                elif opcode_str == "JC":
                    condition_met = self.CF;  log_cond_detail = "(CF=1)"
                elif opcode_str == "JNC":
                    condition_met = not self.CF;log_cond_detail = "(CF=0)"
                elif opcode_str == "JO":
                    condition_met = self.OF;  log_cond_detail = "(OF=1)"
                elif opcode_str == "JNO":
                    condition_met = not self.OF;log_cond_detail = "(OF=0)"
                if condition_met:
                    self.program_counter = self._apply_16bit_limits(target_addr16)
                    self.output_log.append(
                        f"  {opcode_str}{log_cond_detail}: Condition TRUE. JMP to 0x{target_addr16:04X}h")
                else:
                    self.output_log.append(f"  {opcode_str}{log_cond_detail}: Condition FALSE. No JMP.")

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
            self.output_log.append(traceback.format_exc())
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
        regs_s = ", ".join([f"{REG_NAMES[i]}:0x{self.registers[REG_NAMES[i]]:04X}" for i in sorted(REG_NAMES.keys())])
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
        print(f"Data Mem Sample (size {self.data_memory_size}):")
        printed_mem_count = 0
        for i in range(min(32, self.data_memory_size)):
            if self.data_memory[i] != 0: print(
                f"  Mem[0x{i:04X}h]: 0x{self.data_memory[i]:04X}"); printed_mem_count += 1
            if printed_mem_count >= 5 and i < self.stack_limit - 10: break
        if self.sp < self.stack_base:
            print("  Stack Area (near SP):")
            for i in range(max(self.stack_limit, self.sp - 4), min(self.stack_base, self.sp + 5)):
                mark = ""
                if i == self.sp:
                    mark = " <-- SP (next PUSH here if stack not full)"
                elif i == self.sp - 1 and self.sp != self.stack_base:
                    mark = " <-- SP (topmost valid item if POP occurs)"
                print(f"  Mem[0x{i:04X}h]: 0x{self.data_memory[i]:04X}{mark}");
                printed_mem_count += 1
                if printed_mem_count >= 15 and printed_mem_count > 5: break
        if printed_mem_count == 0: print("  (All sampled mem is zero or stack empty at base)")
        print("-------------------------------------------")


if __name__ == "__main__":
    from simple_assembler import SimpleAssembler

    # Test case now includes LOADI and STORI
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
