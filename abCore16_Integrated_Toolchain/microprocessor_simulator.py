# microprocessor_simulator.py
# import re
# Import from the new definitions file
from abcore16_defs import (
    REVERSE_OPCODES, REG_NAMES, INSTRUCTION_FORMATS,
    DEFAULT_MMIO_INPUT_ADDR, DEFAULT_MMIO_OUTPUT_ADDR,
    MAX_ADDRESS_16BIT, MAX_IMMEDIATE_16BIT
)


class MicroprocessorSimulator:
    def __init__(self, data_memory_size=65536, stack_size=256, program_memory_capacity=65536):
        self.registers = {reg_name: 0 for reg_name in REG_NAMES.values()}
        self.data_memory = [0] * data_memory_size
        self.data_memory_size = data_memory_size
        self.sp = data_memory_size
        self.stack_base = data_memory_size
        self.stack_limit = data_memory_size - stack_size if stack_size <= data_memory_size else 0
        self.output_log = []
        self.program_counter = 0
        self.program_bytes = []
        self.program_memory_capacity = program_memory_capacity
        self.ZF = False
        self.SF = False
        self.CF = False
        self.OF = False
        self.halted = False
        self.clean_halt = False
        self.sim_input_buffer = None
        self.sim_last_output_value = None

    def _reset_state(self):
        self.registers = {reg_name: 0 for reg_name in REG_NAMES.values()}
        self.sp = self.stack_base
        self.data_memory = [0] * self.data_memory_size
        self.program_counter = 0
        self.program_bytes = []
        self.ZF = False
        self.SF = False
        self.CF = False
        self.OF = False
        self.halted = False
        self.clean_halt = False
        self.sim_input_buffer = None
        self.sim_last_output_value = None
        self.output_log = [
            f"--- Sim Start (DataMemWords:{self.data_memory_size}, StackLmt:{self.stack_limit:04X}h) ---"]
        self.output_log.append(
            f"    MMIO In: {DEFAULT_MMIO_INPUT_ADDR:04X}h, MMIO Out: {DEFAULT_MMIO_OUTPUT_ADDR:04X}h")

    def _apply_16bit_limits(self, value):
        return value & MAX_IMMEDIATE_16BIT

    # _update_flags from the previous response (with clear_all_arith option)
    def _update_flags(self, value_16bit, op_str_for_log, carry_occurred=None, overflow_occurred=None,
                      is_cmp=False, clear_carry_for_logical=False, clear_all_arith_flags=False):
        value_16bit = self._apply_16bit_limits(value_16bit)
        self.ZF = (value_16bit == 0)
        self.SF = (value_16bit & 0x8000) != 0

        log_flags_now = True

        if clear_all_arith_flags:
            self.CF = False
            self.OF = False
        elif clear_carry_for_logical:
            self.CF = False
            self.OF = False
        else:
            if carry_occurred is not None: self.CF = carry_occurred
            if overflow_occurred is not None: self.OF = overflow_occurred

        if is_cmp:
            log_flags_now = False
        elif op_str_for_log in ["LOAD", "LOADM", "MOV", "POP", "INP", "INM", "NOT"] and \
                carry_occurred is None and \
                (overflow_occurred is False or overflow_occurred is None) and \
                not clear_carry_for_logical and not clear_all_arith_flags:
            log_flags_now = False

        if log_flags_now:
            self.output_log.append(
                f"    Flags updated: ZF{int(self.ZF)}SF{int(self.SF)}CF{int(self.CF)}OF{int(self.OF)} (val {value_16bit})")

    def _is_valid_data_memory_word_address(self, address):
        return 0 <= address < self.data_memory_size

    def _get_reg_name(self, reg_code):
        if reg_code not in REG_NAMES: raise ValueError(f"Invalid reg code: {reg_code}")
        return REG_NAMES[reg_code]

    def _fetch_byte_from_program(self):
        if self.program_counter >= len(self.program_bytes): self.output_log.append(
            f"ERR: PC OOB"); self.halted = True; return None
        byte = self.program_bytes[self.program_counter]
        self.program_counter = (self.program_counter + 1) & MAX_ADDRESS_16BIT
        return byte

    def _fetch_word_le_from_program(self):
        low = self._fetch_byte_from_program()
        high = self._fetch_byte_from_program()
        if low is None or high is None: self.output_log.append("ERR: EOF fetching word."); return None
        return (high << 8) | low

    def load_binary_program(self, filepath):
        try:
            with open(filepath, 'rb') as f:
                self.program_bytes = list(f.read())
            self.output_log.append(f"Sim: Binary '{filepath}' loaded ({len(self.program_bytes)}B).")
            if not self.program_bytes: self.output_log.append("Sim: WARN: Loaded program empty.")
            return True
        except Exception as e:
            self.output_log.append(f"Sim: ERR loading '{filepath}':{e}"); return False

    def _handle_mmio_read(self, address):
        address = self._apply_16bit_limits(address)  # Ensure address is 16-bit
        if address == DEFAULT_MMIO_INPUT_ADDR:
            if self.sim_input_buffer is None:
                while True:
                    try:
                        uv_s = input(f"MMIO Input ({address:04X}h, enter 16-bit int): ")
                        uv = int(uv_s)
                        if not (0 <= uv <= MAX_IMMEDIATE_16BIT):  # Check range
                            print(f"Value out of 16-bit range (0-{MAX_IMMEDIATE_16BIT}). Try again.")
                            continue
                        self.sim_input_buffer = self._apply_16bit_limits(uv)
                        break
                    except ValueError:
                        print("Invalid integer input. Try again.")
            val = self.sim_input_buffer
            self.sim_input_buffer = None
            self.output_log.append(f"  MMIO Read INPUT({address:04X}h): {val}")
            return val
        if self._is_valid_data_memory_word_address(address): return self.data_memory[address]
        self.output_log.append(f"Sim WARN: MMIO Read from unmapped/invalid address {address:04X}h. Returning 0.")
        return 0

    def _handle_mmio_write(self, address, value):
        address = self._apply_16bit_limits(address)  # Ensure address is 16-bit
        val16 = self._apply_16bit_limits(value)
        if address == DEFAULT_MMIO_OUTPUT_ADDR:
            self.sim_last_output_value = val16
            print(f"SIM MMIO OUTPUT ({address:04X}h): {val16}")
            self.output_log.append(f"  MMIO Write OUTPUT({address:04X}h): {val16}")
        elif self._is_valid_data_memory_word_address(address):
            self.data_memory[address] = val16
        else:
            self.output_log.append(f"Sim WARN: MMIO Write to unmapped/invalid address {address:04X}h. Ignored.")

    def execute_cycle(self):
        initial_pc_for_log = self.program_counter
        if self.halted or initial_pc_for_log >= len(self.program_bytes):
            self.halted = True
            if initial_pc_for_log >= len(self.program_bytes) and not self.clean_halt: self.output_log.append(
                "Sim: End of program reached without HALT.")
            return False

        opcode_byte = self._fetch_byte_from_program()
        if opcode_byte is None:  # Should be caught by PC check above, but safety
            self.halted = True
            return False

        opcode_str = REVERSE_OPCODES.get(opcode_byte, f"UNK_OP_{opcode_byte:02X}")

        regs_s_list = [f"{REG_NAMES[i]}:{self.registers[REG_NAMES[i]]}" for i in range(len(REG_NAMES))]
        regs_s = " ".join(regs_s_list)
        flgs_s = f"ZF{int(self.ZF)}SF{int(self.SF)}CF{int(self.CF)}OF{int(self.OF)}"
        self.output_log.append(
            f"PC={initial_pc_for_log:04X}h SP={self.sp:04X}h Flags:[{flgs_s}] | Op:{opcode_byte:02X}({opcode_str}) | Regs:[{regs_s}]")

        jumped = False  # Not currently used, but can be useful for debugging jumps

        try:
            if opcode_str == "NOP":
                self.output_log.append("  NOP")
            elif opcode_str == "HALT":
                self.halted = True
                self.clean_halt = True
                self.output_log.append("  HALT: CPU Halted.")

            elif opcode_str == "LOAD":
                reg_c = self._fetch_byte_from_program()
                imm16 = self._fetch_word_le_from_program()
                if reg_c is None or imm16 is None: raise ValueError(f"{opcode_str} operands missing")
                rn = self._get_reg_name(reg_c)
                self.registers[rn] = self._apply_16bit_limits(imm16)
                self._update_flags(self.registers[rn], opcode_str, overflow_occurred=False)
                self.output_log.append(f"  LOAD: {rn} = #{imm16} (Stored 0x{self.registers[rn]:04X})")

            elif opcode_str == "STORE":
                reg_c = self._fetch_byte_from_program()
                addr16 = self._fetch_word_le_from_program()
                if reg_c is None or addr16 is None: raise ValueError(f"{opcode_str} operands missing")
                rn = self._get_reg_name(reg_c)
                val_to_store = self.registers[rn]
                self._handle_mmio_write(addr16, val_to_store)
                self.output_log.append(f"  STORE: Reg {rn}(0x{val_to_store:04X}) to Addr[0x{addr16:04X}h]")

            elif opcode_str == "LOADM":
                reg_c = self._fetch_byte_from_program()
                addr16 = self._fetch_word_le_from_program()
                if reg_c is None or addr16 is None: raise ValueError(f"{opcode_str} operands missing")
                rn = self._get_reg_name(reg_c)
                val_from_mem = self._handle_mmio_read(addr16)
                self.registers[rn] = self._apply_16bit_limits(val_from_mem)
                self._update_flags(self.registers[rn], opcode_str, overflow_occurred=False)
                self.output_log.append(
                    f"  LOADM: Reg {rn} = Val from Addr[0x{addr16:04X}h] (0x{self.registers[rn]:04X})")

            elif opcode_str == "INP":
                reg_c = self._fetch_byte_from_program()
                if reg_c is None: raise ValueError(f"{opcode_str} operand missing")
                rn = self._get_reg_name(reg_c)
                val_from_input = self._handle_mmio_read(DEFAULT_MMIO_INPUT_ADDR)
                self.registers[rn] = self._apply_16bit_limits(val_from_input)
                self._update_flags(self.registers[rn], opcode_str, overflow_occurred=False)
                self.output_log.append(
                    f"  INP (via MMIO {DEFAULT_MMIO_INPUT_ADDR:04X}h): Reg {rn} = 0x{self.registers[rn]:04X}")

            elif opcode_str == "OUT":
                reg_c = self._fetch_byte_from_program()
                if reg_c is None: raise ValueError(f"{opcode_str} operand missing")
                rn = self._get_reg_name(reg_c)
                val_to_output = self.registers[rn]
                self._handle_mmio_write(DEFAULT_MMIO_OUTPUT_ADDR, val_to_output)
                self.output_log.append(
                    f"  OUT (via MMIO {DEFAULT_MMIO_OUTPUT_ADDR:04X}h): Reg {rn} (0x{val_to_output:04X})")

            elif opcode_str == "INM":
                reg_c = self._fetch_byte_from_program()
                addr16 = self._fetch_word_le_from_program()
                if reg_c is None or addr16 is None: raise ValueError(f"{opcode_str} operands missing")
                rn = self._get_reg_name(reg_c)
                val_from_mem = self._handle_mmio_read(addr16)
                self.registers[rn] = self._apply_16bit_limits(val_from_mem)
                self._update_flags(self.registers[rn], opcode_str, overflow_occurred=False)
                self.output_log.append(
                    f"  INM: Reg {rn} = Val from MMIO Addr 0x{addr16:04X}h (0x{self.registers[rn]:04X})")

            elif opcode_str == "OUTM":
                reg_c = self._fetch_byte_from_program()
                addr16 = self._fetch_word_le_from_program()
                if reg_c is None or addr16 is None: raise ValueError(f"{opcode_str} operands missing")
                rn = self._get_reg_name(reg_c)
                val_to_output = self.registers[rn]
                self._handle_mmio_write(addr16, val_to_output)
                self.output_log.append(f"  OUTM: Reg {rn} (0x{val_to_output:04X}) to MMIO Addr 0x{addr16:04X}h")

            elif opcode_str == "ADD":
                r1_c = self._fetch_byte_from_program()
                r2_c = self._fetch_byte_from_program()
                if r1_c is None or r2_c is None: raise ValueError(f"{opcode_str} operands missing")
                r1n, r2n = self._get_reg_name(r1_c), self._get_reg_name(r2_c)
                v1, v2 = self.registers[r1n], self.registers[r2n]
                raw_sum = v1 + v2
                result_16bit = self._apply_16bit_limits(raw_sum)
                carry = raw_sum > MAX_IMMEDIATE_16BIT
                s1, s2, sr = (v1 & 0x8000), (v2 & 0x8000), (result_16bit & 0x8000)
                overflow = (s1 == s2) and (sr != s1)
                self.registers[r1n] = result_16bit
                self._update_flags(result_16bit, opcode_str, carry_occurred=carry, overflow_occurred=overflow)
                self.output_log.append(f"  ADD: {r1n}(0x{v1:04X}) + {r2n}(0x{v2:04X}) = 0x{result_16bit:04X}")

            elif opcode_str == "SUB":
                r1_c = self._fetch_byte_from_program()
                r2_c = self._fetch_byte_from_program()
                if r1_c is None or r2_c is None: raise ValueError(f"{opcode_str} operands missing")
                r1n, r2n = self._get_reg_name(r1_c), self._get_reg_name(r2_c)
                v1, v2 = self.registers[r1n], self.registers[r2n]
                raw_diff = v1 - v2
                result_16bit = self._apply_16bit_limits(raw_diff)
                borrow = v1 < v2  # Or raw_diff < 0 if considering full range before wrap
                s1, s2, sr = (v1 & 0x8000), (v2 & 0x8000), (result_16bit & 0x8000)
                overflow = (s1 != s2) and (sr != s1)
                self.registers[r1n] = result_16bit
                self._update_flags(result_16bit, opcode_str, carry_occurred=borrow, overflow_occurred=overflow)
                self.output_log.append(f"  SUB: {r1n}(0x{v1:04X}) - {r2n}(0x{v2:04X}) = 0x{result_16bit:04X}")

            elif opcode_str == "MUL":
                r1_c = self._fetch_byte_from_program()
                r2_c = self._fetch_byte_from_program()
                if r1_c is None or r2_c is None: raise ValueError(f"{opcode_str} operands missing")
                r1n, r2n = self._get_reg_name(r1_c), self._get_reg_name(r2_c)
                v1, v2 = self.registers[r1n], self.registers[r2n]
                raw_product = v1 * v2
                result_16bit = self._apply_16bit_limits(raw_product)
                carry = raw_product > MAX_IMMEDIATE_16BIT  # If product exceeds 16 bits
                self.registers[r1n] = result_16bit
                self._update_flags(result_16bit, opcode_str, carry_occurred=carry,
                                   overflow_occurred=carry)  # OF=CF for simple MUL
                self.output_log.append(f"  MUL: {r1n}(0x{v1:04X}) * {r2n}(0x{v2:04X}) = 0x{result_16bit:04X}")

            elif opcode_str == "INC":
                reg_c = self._fetch_byte_from_program()
                if reg_c is None: raise ValueError(f"{opcode_str} operand missing")
                rn = self._get_reg_name(reg_c)
                v1 = self.registers[rn]
                raw_sum = v1 + 1
                result_16bit = self._apply_16bit_limits(raw_sum)
                carry = raw_sum > MAX_IMMEDIATE_16BIT
                s1, s_inc, sr = (v1 & 0x8000), (1 & 0x8000), (result_16bit & 0x8000)
                overflow = (s1 == s_inc) and (sr != s1)
                self.registers[rn] = result_16bit
                self._update_flags(result_16bit, opcode_str, carry_occurred=carry, overflow_occurred=overflow)
                self.output_log.append(f"  INC: {rn} from 0x{v1:04X} to 0x{result_16bit:04X}")

            elif opcode_str == "DEC":
                reg_c = self._fetch_byte_from_program()
                if reg_c is None: raise ValueError(f"{opcode_str} operand missing")
                rn = self._get_reg_name(reg_c)
                v1 = self.registers[rn]
                raw_diff = v1 - 1
                result_16bit = self._apply_16bit_limits(raw_diff)
                borrow = v1 < 1
                s1, s_dec, sr = (v1 & 0x8000), (1 & 0x8000), (result_16bit & 0x8000)
                overflow = (s1 != s_dec) and (sr != s1)
                self.registers[rn] = result_16bit
                self._update_flags(result_16bit, opcode_str, carry_occurred=borrow, overflow_occurred=overflow)
                self.output_log.append(f"  DEC: {rn} from 0x{v1:04X} to 0x{result_16bit:04X}")

            elif opcode_str == "AND":  # Bitwise
                r1_c = self._fetch_byte_from_program()
                r2_c = self._fetch_byte_from_program()
                if r1_c is None or r2_c is None: raise ValueError(f"{opcode_str} operands missing")
                r1n, r2n = self._get_reg_name(r1_c), self._get_reg_name(r2_c)
                v1, v2 = self.registers[r1n], self.registers[r2n]
                result = v1 & v2
                self.registers[r1n] = self._apply_16bit_limits(result)
                self._update_flags(self.registers[r1n], opcode_str, clear_carry_for_logical=True)
                self.output_log.append(f"  AND: {r1n}(0x{v1:04X}) & {r2n}(0x{v2:04X}) = 0x{self.registers[r1n]:04X}")

            elif opcode_str == "OR":  # Bitwise
                r1_c = self._fetch_byte_from_program()
                r2_c = self._fetch_byte_from_program()
                if r1_c is None or r2_c is None: raise ValueError(f"{opcode_str} operands missing")
                r1n, r2n = self._get_reg_name(r1_c), self._get_reg_name(r2_c)
                v1, v2 = self.registers[r1n], self.registers[r2n]
                result = v1 | v2
                self.registers[r1n] = self._apply_16bit_limits(result)
                self._update_flags(self.registers[r1n], opcode_str, clear_carry_for_logical=True)
                self.output_log.append(f"  OR: {r1n}(0x{v1:04X}) | {r2n}(0x{v2:04X}) = 0x{self.registers[r1n]:04X}")

            elif opcode_str == "XOR":  # Bitwise
                r1_c = self._fetch_byte_from_program()
                r2_c = self._fetch_byte_from_program()
                if r1_c is None or r2_c is None: raise ValueError(f"{opcode_str} operands missing")
                r1n, r2n = self._get_reg_name(r1_c), self._get_reg_name(r2_c)
                v1, v2 = self.registers[r1n], self.registers[r2n]
                result = v1 ^ v2
                self.registers[r1n] = self._apply_16bit_limits(result)
                self._update_flags(self.registers[r1n], opcode_str, clear_carry_for_logical=True)
                self.output_log.append(f"  XOR: {r1n}(0x{v1:04X}) ^ {r2n}(0x{v2:04X}) = 0x{self.registers[r1n]:04X}")

            elif opcode_str == "NOT":  # Bitwise
                reg_c = self._fetch_byte_from_program()
                if reg_c is None: raise ValueError(f"{opcode_str} operand missing")
                rn = self._get_reg_name(reg_c)
                result = ~self.registers[rn]
                self.registers[rn] = self._apply_16bit_limits(result)
                self._update_flags(self.registers[rn], opcode_str,
                                   overflow_occurred=False)  # CF conventionally unaffected by NOT
                self.output_log.append(f"  NOT: {rn} = 0x{self.registers[rn]:04X}")

            elif opcode_str == "SHL":
                reg_c = self._fetch_byte_from_program()
                shift_val_byte = self._fetch_byte_from_program()
                if reg_c is None or shift_val_byte is None: raise ValueError(f"{opcode_str} operands missing")
                rn, sa = self._get_reg_name(reg_c), shift_val_byte
                orig_val = self.registers[rn]
                carry_out = False
                if sa > 0: carry_out = (orig_val >> (16 - sa)) & 1 if sa <= 16 else False  # Bit shifted out of MSB
                result_val = orig_val << sa
                self.registers[rn] = self._apply_16bit_limits(result_val)
                self._update_flags(self.registers[rn], opcode_str, carry_occurred=(carry_out if sa > 0 else self.CF),
                                   overflow_occurred=False)
                self.output_log.append(f"  SHL: {rn}(0x{orig_val:04X}) << {sa} = 0x{self.registers[rn]:04X}")

            elif opcode_str == "SHR":
                reg_c = self._fetch_byte_from_program()
                shift_val_byte = self._fetch_byte_from_program()
                if reg_c is None or shift_val_byte is None: raise ValueError(f"{opcode_str} operands missing")
                rn, sa = self._get_reg_name(reg_c), shift_val_byte
                orig_val = self.registers[rn]
                carry_out = False
                if sa > 0: carry_out = (orig_val >> (sa - 1)) & 1 if sa <= 16 else False  # Bit shifted out of LSB
                result_val = orig_val >> sa
                self.registers[rn] = self._apply_16bit_limits(result_val)
                self._update_flags(self.registers[rn], opcode_str, carry_occurred=(carry_out if sa > 0 else self.CF),
                                   overflow_occurred=False)
                self.output_log.append(f"  SHR: {rn}(0x{orig_val:04X}) >> {sa} = 0x{self.registers[rn]:04X}")

            elif opcode_str == "L_AND":
                rd_c, rs1_c, rs2_c = self._fetch_byte_from_program(), self._fetch_byte_from_program(), self._fetch_byte_from_program()
                if rd_c is None or rs1_c is None or rs2_c is None: raise ValueError(f"{opcode_str} operands missing")
                rd_n, rs1_n, rs2_n = self._get_reg_name(rd_c), self._get_reg_name(rs1_c), self._get_reg_name(rs2_c)
                v1, v2 = self.registers[rs1_n], self.registers[rs2_n]
                result = 1 if (v1 != 0 and v2 != 0) else 0
                self.registers[rd_n] = result
                self._update_flags(result, opcode_str, clear_all_arith_flags=True)
                self.output_log.append(f"  L_AND: {rd_n} = ({rs1_n}({v1})!=0 && {rs2_n}({v2})!=0) -> {result}")

            elif opcode_str == "L_OR":
                rd_c, rs1_c, rs2_c = self._fetch_byte_from_program(), self._fetch_byte_from_program(), self._fetch_byte_from_program()
                if rd_c is None or rs1_c is None or rs2_c is None: raise ValueError(f"{opcode_str} operands missing")
                rd_n, rs1_n, rs2_n = self._get_reg_name(rd_c), self._get_reg_name(rs1_c), self._get_reg_name(rs2_c)
                v1, v2 = self.registers[rs1_n], self.registers[rs2_n]
                result = 1 if (v1 != 0 or v2 != 0) else 0
                self.registers[rd_n] = result
                self._update_flags(result, opcode_str, clear_all_arith_flags=True)
                self.output_log.append(f"  L_OR: {rd_n} = ({rs1_n}({v1})!=0 || {rs2_n}({v2})!=0) -> {result}")

            elif opcode_str == "L_NOT":
                rd_c = self._fetch_byte_from_program()
                rs_c = self._fetch_byte_from_program()
                if rd_c is None or rs_c is None: raise ValueError(f"{opcode_str} operands missing")
                rd_n, rs_n = self._get_reg_name(rd_c), self._get_reg_name(rs_c)
                val_s = self.registers[rs_n]
                result = 1 if val_s == 0 else 0
                self.registers[rd_n] = result
                self._update_flags(result, opcode_str, clear_all_arith_flags=True)
                self.output_log.append(f"  L_NOT: {rd_n} = !({rs_n}({val_s})!=0) -> {result}")

            elif opcode_str == "CMP":
                r1_c = self._fetch_byte_from_program()
                r2_c = self._fetch_byte_from_program()
                if r1_c is None or r2_c is None: raise ValueError(f"{opcode_str} operands missing")
                r1n, r2n = self._get_reg_name(r1_c), self._get_reg_name(r2_c)
                v1, v2 = self.registers[r1n], self.registers[r2n]
                raw_diff = v1 - v2
                result_16bit_for_flags = self._apply_16bit_limits(raw_diff)
                borrow = v1 < v2
                s1, s2, sr = (v1 & 0x8000), (v2 & 0x8000), (result_16bit_for_flags & 0x8000)
                overflow = (s1 != s2) and (sr != s1)
                self._update_flags(result_16bit_for_flags, opcode_str, carry_occurred=borrow,
                                   overflow_occurred=overflow, is_cmp=True)
                self.output_log.append(f"  CMP: {r1n}(0x{v1:04X}) vs {r2n}(0x{v2:04X}). Flags set.")

            elif opcode_str == "MOV":
                dest_reg_c = self._fetch_byte_from_program()
                src_reg_c = self._fetch_byte_from_program()
                if dest_reg_c is None or src_reg_c is None: raise ValueError(f"{opcode_str} operands missing")
                dest_rn, src_rn = self._get_reg_name(dest_reg_c), self._get_reg_name(src_reg_c)
                val_to_move = self.registers[src_rn]
                self.registers[dest_rn] = val_to_move
                self._update_flags(val_to_move, opcode_str,
                                   overflow_occurred=False)  # Only ZF, SF directly affected by value
                self.output_log.append(f"  MOV: {dest_rn} = {src_rn} (0x{val_to_move:04X})")

            elif opcode_str == "PUSH":
                reg_c = self._fetch_byte_from_program()
                if reg_c is None: raise ValueError(f"{opcode_str} operand missing")
                rn = self._get_reg_name(reg_c)
                self.sp = (self.sp - 1) & MAX_ADDRESS_16BIT
                if self.sp < self.stack_limit:
                    self.sp = (self.sp + 1) & MAX_ADDRESS_16BIT  # Revert SP change on error
                    raise ValueError(f"Stack Overflow PUSH (SP={self.sp + 1}, Limit={self.stack_limit})")
                if not self._is_valid_data_memory_word_address(self.sp):
                    raise ValueError(f"Invalid SP 0x{self.sp:04X}h for PUSH (DataMemSize {self.data_memory_size})")
                val_to_push = self.registers[rn]
                self.data_memory[self.sp] = self._apply_16bit_limits(val_to_push)
                self.output_log.append(
                    f"  PUSH: Reg {rn}(0x{val_to_push:04X}) to DataMemWord[0x{self.sp:04X}h]. New SP: 0x{self.sp:04X}h")

            elif opcode_str == "POP":
                reg_c = self._fetch_byte_from_program()
                if reg_c is None: raise ValueError(f"{opcode_str} operand missing")
                rn = self._get_reg_name(reg_c)
                if self.sp >= self.stack_base:
                    raise ValueError(f"Stack Underflow POP (SP=0x{self.sp:04X}h, Base=0x{self.stack_base:04X}h)")
                if not self._is_valid_data_memory_word_address(self.sp):
                    raise ValueError(f"Invalid SP 0x{self.sp:04X}h for POP before increment")
                val_popped = self.data_memory[self.sp]
                self.registers[rn] = self._apply_16bit_limits(val_popped)
                self.sp = (self.sp + 1) & MAX_ADDRESS_16BIT
                self._update_flags(self.registers[rn], opcode_str, overflow_occurred=False)
                self.output_log.append(
                    f"  POP: 0x{val_popped:04X} from DataMemWord[0x{(self.sp - 1) & MAX_ADDRESS_16BIT:04X}h] to Reg {rn}. New SP: 0x{self.sp:04X}h")

            elif opcode_str == "CALL":
                target_addr16 = self._fetch_word_le_from_program()
                if target_addr16 is None: raise ValueError(f"{opcode_str} operand missing")
                return_addr = self.program_counter  # PC is already past the CALL's operands
                self.sp = (self.sp - 1) & MAX_ADDRESS_16BIT
                if self.sp < self.stack_limit:
                    self.sp = (self.sp + 1) & MAX_ADDRESS_16BIT
                    raise ValueError("Stack Overflow CALL")
                if not self._is_valid_data_memory_word_address(self.sp):
                    raise ValueError(f"Invalid SP 0x{self.sp:04X}h for CALL stack push")
                self.data_memory[self.sp] = self._apply_16bit_limits(return_addr)
                self.program_counter = self._apply_16bit_limits(target_addr16)
                jumped = True
                self.output_log.append(
                    f"  CALL: Pushed RetAddr(0x{return_addr:04X}h) to Stack[0x{self.sp:04X}h]. JMP to 0x{self.program_counter:04X}h.")

            elif opcode_str == "RET":
                if self.sp >= self.stack_base: raise ValueError("Stack Underflow RET")
                if not self._is_valid_data_memory_word_address(self.sp):
                    raise ValueError(f"Invalid SP 0x{self.sp:04X}h for RET stack pop")
                ret_addr_from_stack = self.data_memory[self.sp]
                self.sp = (self.sp + 1) & MAX_ADDRESS_16BIT
                self.program_counter = self._apply_16bit_limits(ret_addr_from_stack)
                jumped = True
                self.output_log.append(
                    f"  RET: Popped RetAddr(0x{self.program_counter:04X}h) from Stack[0x{(self.sp - 1) & MAX_ADDRESS_16BIT:04X}h]. JMP.")

            elif opcode_str in ["JMP", "JE", "JNE", "JS", "JNS", "JC", "JNC", "JO", "JNO"]:
                target_addr16 = self._fetch_word_le_from_program()
                if target_addr16 is None: raise ValueError(f"{opcode_str} operand missing")
                condition_met = False
                if opcode_str == "JMP":
                    condition_met = True
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
                    self.program_counter = self._apply_16bit_limits(target_addr16)
                    jumped = True
                    self.output_log.append(f"  {opcode_str}: Condition TRUE. JMP to 0x{target_addr16:04X}h")
                else:
                    self.output_log.append(f"  {opcode_str}: Condition FALSE. No JMP.")

            elif opcode_str in ["JMPZ", "JMPN"]:
                reg_c = self._fetch_byte_from_program()
                target_addr16 = self._fetch_word_le_from_program()
                if reg_c is None or target_addr16 is None: raise ValueError(f"{opcode_str} operands missing")
                rn = self._get_reg_name(reg_c)
                reg_val = self.registers[rn]
                condition_met = False
                if opcode_str == "JMPZ":
                    condition_met = (reg_val == 0)
                elif opcode_str == "JMPN":
                    condition_met = ((reg_val & 0x8000) != 0)

                if condition_met:
                    self.program_counter = self._apply_16bit_limits(target_addr16)
                    jumped = True
                    self.output_log.append(
                        f"  {opcode_str}: Reg {rn}(0x{reg_val:04X}) cond TRUE. JMP to 0x{target_addr16:04X}h")
                else:
                    self.output_log.append(f"  {opcode_str}: Reg {rn}(0x{reg_val:04X}) cond FALSE. No JMP.")

            else:  # Opcode in REVERSE_OPCODES but no execution logic implemented above
                self.output_log.append(f"  FATAL: Opcode {opcode_str}({opcode_byte:02X}) KNOWN but NO EXEC LOGIC.")
                self.halted = True
                return False

        except ValueError as e:
            self.output_log.append(
                f"  RUNTIME ERROR @PC 0x{initial_pc_for_log:04X}h for Op {opcode_str}(0x{opcode_byte:02X}): {e}")
            self.halted = True
            return False
        except Exception as e_unhandled:  # Catch any other unexpected Python errors
            self.output_log.append(
                f"  UNEXPECTED SIMULATOR PYTHON ERROR @PC 0x{initial_pc_for_log:04X}h ({opcode_str}): {e_unhandled} ({type(e_unhandled).__name__})")
            import traceback
            self.output_log.append(traceback.format_exc())
            self.halted = True
            return False
        return True

    # run_program and print_final_state should be fine from the previous centralized version.
    # Just ensure they are using the correct REG_NAMES for iteration if needed.
    def run_program(self, binary_source_file):
        self._reset_state()
        if not self.load_binary_program(binary_source_file):
            self.output_log.append(f"--- Sim Aborted: load fail ---")
            return "\n".join(self.output_log)

        max_cycles = (len(self.program_bytes) * 30) + 2000  # Increased generosity
        if not self.program_bytes: max_cycles = 1  # Handle empty program

        cycles = 0
        while not self.halted and cycles < max_cycles:
            if not self.program_bytes and cycles == 0:  # First cycle for empty program
                self.output_log.append("Sim: No instructions to execute.")
                self.halted = True
                self.clean_halt = True
                break
            if not self.execute_cycle(): break  # execute_cycle handles halting on error or end
            cycles += 1

        if cycles >= max_cycles and not self.halted:
            self.output_log.append("Sim: MAX CYCLES REACHED! Halting simulation.")
            self.halted = True

        end_msg = "--- Sim Finished"
        if self.halted:
            end_msg += " (CPU " + ("HALTED cleanly" if self.clean_halt else "STOPPED/ERRORED") + ")"
        elif self.program_counter >= len(self.program_bytes) and len(
                self.program_bytes) > 0:  # Ended by falling off end
            end_msg += " (End of program without HALT)"

        self.output_log.append(f"{end_msg} ({cycles} cycles executed) ---")
        self.output_log.append(f"Final PC: 0x{self.program_counter:04X}h")
        final_regs_str = ", ".join(
            [f"{REG_NAMES[i]}:0x{self.registers[REG_NAMES[i]]:04X}" for i in range(len(REG_NAMES))])
        self.output_log.append(f"Final Regs: [{final_regs_str}]")
        self.output_log.append(f"Final SP: 0x{self.sp:04X}h")
        self.output_log.append(f"Final Flags: ZF{int(self.ZF)}SF{int(self.SF)}CF{int(self.CF)}OF{int(self.OF)}")
        return "\n".join(self.output_log)

    def print_final_state(self):
        print("\n--- Final Simulator State ---")
        for i in range(len(REG_NAMES)):  # Iterate using defined number of registers
            reg_name = REG_NAMES[i]
            val = self.registers[reg_name]
            print(f"Register {reg_name}: {val} (0x{val:04X}) ({val:016b}b)")
        print(f"Stack Pointer (SP): 0x{self.sp:04X}h ({self.sp})")
        print(f"Program Counter (PC): 0x{self.program_counter:04X}h ({self.program_counter})")
        print(f"Flags: ZF={int(self.ZF)}, SF={int(self.SF)}, CF={int(self.CF)}, OF={int(self.OF)}")
        print(f"Data Memory (Words 0-{self.data_memory_size - 1}, Sample of non-zero/stack):")

        printed_count = 0
        # Print first few non-zero values
        for i in range(min(256, self.data_memory_size)):  # Scan initial part of memory
            if self.data_memory[i] != 0:
                print(f"  DataMemWord[0x{i:04X}h ({i:3d})]: {self.data_memory[i]} (0x{self.data_memory[i]:04X})")
                printed_count += 1
                if printed_count >= 8: break

        # Print stack area if SP is active
        if self.sp < self.stack_base:
            print("  Stack Area (around SP):")
            start_sp_view = max(self.stack_limit, self.sp - 4)
            end_sp_view = min(self.stack_base, self.sp + 5)
            for i in range(start_sp_view, end_sp_view):
                sp_indicator = " <-- SP" if i == self.sp else ""
                print(
                    f"  DataMemWord[0x{i:04X}h ({i:3d})]: {self.data_memory[i]} (0x{self.data_memory[i]:04X}){sp_indicator}")
                printed_count += 1

        if printed_count == 0:
            print("  (All sampled data memory locations are zero or stack is at base)")
        print("---------------------------")


# Standalone test
if __name__ == "__main__":
    from simple_assembler import SimpleAssembler  # Make sure assembler is also using abcore16_defs

    sample_sal_for_sim_test = """
    LOAD R0, #10
    LOAD R1, #20
    MOV R2, R0  ; Test MOV
    ADD R2, R1  ; R2 = R0 + R1 = 10 + 20 = 30
    PRINT R2    ; Expected output: 30
    HALT
    """
    assembler = SimpleAssembler()  # Assumes SimpleAssembler is updated for abcore16_defs
    bin_file = "test_sim_full_exec.bin"
    asm_file = "test_sim_full_exec.asm"

    print(f"--- Assembling SAL for full simulator test: {bin_file} ---")
    if assembler.assemble_to_file(sample_sal_for_sim_test, bin_file, asm_file):
        print(f"\n--- Testing Simulator (Full Exec Logic) with '{bin_file}' ---")
        simulator = MicroprocessorSimulator(data_memory_size=1024, stack_size=64)
        log = simulator.run_program(bin_file)
        print("\nSimulation Log:")
        print(log)
        simulator.print_final_state()
    else:
        print(f"Failed to assemble {bin_file} for simulator test.")
