# microprocessor_simulator.py
import re

OPCODES_SIM = {
    0x00: "NOP", 0x01: "LOAD", 0x02: "STORE", 0x03: "LOADM",
    0x10: "ADD", 0x11: "SUB", 0x12: "MUL",
    0x13: "INC", 0x14: "DEC",
    0x20: "AND", 0x21: "OR", 0x22: "XOR", 0x23: "NOT",
    0x24: "SHL", 0x25: "SHR",
    0x30: "INP", 0x31: "OUT",
    0x32: "INM", 0x33: "OUTM",
    0x40: "CMP",
    0x50: "JMP", 0x51: "JMPZ", 0x52: "JMPN",
    0x53: "JE", 0x54: "JNE", 0x55: "JS", 0x56: "JNS",
    0x57: "JC", 0x58: "JNC", 0x59: "JO", 0x5A: "JNO",
    0x60: "PUSH", 0x61: "POP",
    0x70: "CALL", 0x71: "RET",
    0x80: "MOV",
    0xFF: "HALT"
}
REG_NAMES_SIM = {0: 'R0', 1: 'R1', 2: 'R2', 3: 'R3', 4: 'R4', 5: 'R5', 6: 'R6', 7: 'R7'}

DEFAULT_MMIO_INPUT_ADDR = 0x00FE
DEFAULT_MMIO_OUTPUT_ADDR = 0x00FF


class MicroprocessorSimulator:
    def __init__(self, data_memory_size=65536, stack_size=256, program_memory_capacity=65536):
        self.registers = {'R0': 0, 'R1': 0, 'R2': 0, 'R3': 0, 'R4': 0, 'R5': 0, 'R6': 0, 'R7': 0}
        self.data_memory = [0] * data_memory_size
        self.data_memory_size = data_memory_size
        self.sp = data_memory_size
        self.stack_base = data_memory_size
        self.stack_limit = data_memory_size - stack_size if stack_size <= data_memory_size else 0
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

    def _reset_state(self):
        self.registers = {'R0': 0, 'R1': 0, 'R2': 0, 'R3': 0, 'R4': 0, 'R5': 0, 'R6': 0, 'R7': 0}
        self.sp = self.stack_base
        self.data_memory = [0] * self.data_memory_size
        self.program_counter = 0;
        self.program_bytes = []
        self.ZF = False;
        self.SF = False;
        self.CF = False;
        self.OF = False
        self.halted = False;
        self.clean_halt = False
        self.sim_input_buffer = None;
        self.sim_last_output_value = None
        self.output_log = [
            f"--- Sim Start (16b-Data/PC/SP/DataAddrs; DataMemWords:{self.data_memory_size}, StackLmt:{self.stack_limit}) ---"]
        self.output_log.append(
            f"    Default MMIO In: {DEFAULT_MMIO_INPUT_ADDR:04X}h, Default MMIO Out: {DEFAULT_MMIO_OUTPUT_ADDR:04X}h")

    def _apply_16bit_limits(self, value):
        return value & 0xFFFF

    def _update_flags(self, value_16bit, op_str_for_log_check, carry_occurred=None, overflow_occurred=None,
                      is_cmp=False, clear_carry_for_logical=False):
        value_16bit = self._apply_16bit_limits(value_16bit)  # Ensure value is 16-bit
        self.ZF = (value_16bit == 0)
        self.SF = (value_16bit & 0x8000) != 0

        # Initialize log_flags_now to its default (True)
        log_flags_now = True  # <<<<<<<<<<<<<<<< ADD THIS LINE

        if clear_carry_for_logical:
            self.CF = False
            self.OF = False  # Logical ops typically clear OF as well
        else:
            if carry_occurred is not None:
                self.CF = carry_occurred
            # Else CF remains unchanged by default for ops not explicitly setting it

            if overflow_occurred is not None:
                self.OF = overflow_occurred
            # Else OF remains unchanged for ops not explicitly setting it (unless cleared above)

        # Conditional logging refinement
        if is_cmp:  # CMP logs its own comprehensive flag summary
            log_flags_now = False
        elif op_str_for_log_check in ["LOAD", "LOADM", "MOV", "POP", "INP", "INM", "NOT"]:
            # For these, only ZF/SF are inherently tied to the value.
            # OF is explicitly set to False (or unchanged for NOT).
            # CF is often unchanged (or cleared for logical NOT).
            # Don't log if only ZF/SF changed based on value and CF/OF are not explicitly part of this op's standard flag effects.
            if carry_occurred is None and (
                    overflow_occurred is False or overflow_occurred is None) and not clear_carry_for_logical:
                log_flags_now = False
        elif op_str_for_log_check in ["SHL", "SHR"]:
            # SHL/SHR explicitly set CF and clear OF. Log if CF changed.
            # The generic 'log_flags_now = True' will cover this unless further refined.
            pass

        if log_flags_now:
            self.output_log.append(
                f"    Flags updated: ZF{int(self.ZF)}SF{int(self.SF)}CF{int(self.CF)}OF{int(self.OF)} (val {value_16bit})")

    def _is_valid_data_memory_word_address(self, address_16bit):
        return 0 <= address_16bit < self.data_memory_size

    def _get_reg_name(self, reg_code):
        if reg_code is None: raise ValueError("Register code is None.")
        if reg_code not in REG_NAMES_SIM: raise ValueError(f"Invalid reg code: {reg_code}")
        return REG_NAMES_SIM[reg_code]

    def _fetch_byte_from_program(self):
        if self.program_counter >= len(self.program_bytes):
            self.output_log.append(
                f"ERR: PC({self.program_counter:04X}h of {len(self.program_bytes)}B) OOB. Fetch byte failed.")
            return None
        byte = self.program_bytes[self.program_counter]
        self.program_counter = (self.program_counter + 1) & 0xFFFF
        return byte

    def _fetch_word_le_from_program(self):
        low_byte = self._fetch_byte_from_program()
        if low_byte is None: return None
        high_byte = self._fetch_byte_from_program()
        if high_byte is None: self.output_log.append("ERR: EOF fetching high byte of 16-bit operand."); return None
        return (high_byte << 8) | low_byte

    def load_binary_program(self, filepath):
        try:
            with open(filepath, 'rb') as f:
                self.program_bytes = list(f.read())
            self.output_log.append(f"Binary '{filepath}' loaded. Size:{len(self.program_bytes)}B.")
            if not self.program_bytes: self.output_log.append("WARN: Loaded program empty.")
            return True
        except FileNotFoundError:
            self.output_log.append(f"ERROR: Binary file not found: {filepath}"); return False
        except Exception as e:
            self.output_log.append(f"ERR loading '{filepath}':{e}"); return False

    def _handle_mmio_read(self, address_16bit):
        if not (0 <= address_16bit <= 0xFFFF): raise ValueError(f"MMIO address {address_16bit} out of 16-bit range.")
        if address_16bit == DEFAULT_MMIO_INPUT_ADDR:
            if self.sim_input_buffer is None:
                while True:
                    try:
                        uv_s = input(f"MMIO Input (Addr {address_16bit:04X}h): Enter int: ")
                        uv = int(uv_s)
                        self.sim_input_buffer = self._apply_16bit_limits(uv);
                        break
                    except ValueError:
                        print("Invalid int for MMIO.")
            val = self.sim_input_buffer;
            self.sim_input_buffer = None
            self.output_log.append(f"  MMIO Read from INPUT({address_16bit:04X}h): Val={val}")
            return val
        elif self._is_valid_data_memory_word_address(address_16bit):
            return self.data_memory[address_16bit]
        else:
            raise ValueError(
                f"Data memory word addr {address_16bit:04X}h OOB for read (not default MMIO). Valid 0-{self.data_memory_size - 1}")

    def _handle_mmio_write(self, address_16bit, value_16bit):
        if not (0 <= address_16bit <= 0xFFFF): raise ValueError(f"MMIO address {address_16bit} out of 16-bit range.")
        val16 = self._apply_16bit_limits(value_16bit)
        if address_16bit == DEFAULT_MMIO_OUTPUT_ADDR:
            self.sim_last_output_value = val16
            print(f"SIMULATOR MMIO OUTPUT (Addr {address_16bit:04X}h): {val16}")
            self.output_log.append(f"  MMIO Write to OUTPUT({address_16bit:04X}h): Val={val16}")
        elif self._is_valid_data_memory_word_address(address_16bit):
            self.data_memory[address_16bit] = val16
        else:
            raise ValueError(
                f"Data memory word addr {address_16bit:04X}h OOB for write (not default MMIO). Valid 0-{self.data_memory_size - 1}")

    def execute_cycle(self):
        initial_pc_for_log = 0;
        opcode_byte = 0;
        opcode_str = "START_CYCLE"
        if self.halted: return False
        if self.program_counter >= len(self.program_bytes): self.output_log.append(
            "End of prog (no HALT)."); self.halted = True; return False

        initial_pc_for_log = self.program_counter
        opcode_byte = self._fetch_byte_from_program()
        if opcode_byte is None: self.halted = True; return False
        opcode_str = OPCODES_SIM.get(opcode_byte, f"UNK_OP_{opcode_byte:02X}")

        regs_s_list = []
        for i in range(8):  # R0 to R7
            reg_key = f"R{i}"
            if reg_key in self.registers:
                regs_s_list.append(f"{reg_key}:{self.registers[reg_key]}")
            else:
                regs_s_list.append(f"{reg_key}:ERR")
        regs_s = " ".join(regs_s_list)

        flgs_s = f"ZF{int(self.ZF)}SF{int(self.SF)}CF{int(self.CF)}OF{int(self.OF)}"
        self.output_log.append(
            f"PC={initial_pc_for_log:04X}h (of {len(self.program_bytes)}B) SP={self.sp:04X}h Flags:[{flgs_s}] | Op:{opcode_byte:02X}({opcode_str}) | Regs:[{regs_s}]")
        jumped = False

        try:
            if opcode_str == "NOP":
                self.output_log.append("  NOP")
            elif opcode_str == "HALT":
                self.halted = True;
                self.clean_halt = True;
                self.output_log.append("  HALT: CPU Halted.")

            elif opcode_str == "LOAD":
                reg_c = self._fetch_byte_from_program()
                imm16 = self._fetch_word_le_from_program()
                if reg_c is None or imm16 is None: raise ValueError("LOAD ops missing")
                rn = self._get_reg_name(reg_c)
                self.registers[rn] = self._apply_16bit_limits(imm16)
                self._update_flags(self.registers[rn], opcode_str, overflow_occurred=False)
                self.output_log.append(f"  LOAD: {rn} = #{imm16} (Stored {self.registers[rn]})")

            elif opcode_str == "STORE":
                reg_c = self._fetch_byte_from_program()
                addr16 = self._fetch_word_le_from_program()
                if reg_c is None or addr16 is None: raise ValueError("STORE ops missing")
                rn = self._get_reg_name(reg_c);
                vts = self.registers[rn]
                self._handle_mmio_write(addr16, vts)
                self.output_log.append(f"  STORE: Reg {rn}({vts}) to Addr[{addr16:04X}h]")

            elif opcode_str == "LOADM":
                reg_c = self._fetch_byte_from_program()
                addr16 = self._fetch_word_le_from_program()
                if reg_c is None or addr16 is None: raise ValueError("LOADM ops missing")
                rn = self._get_reg_name(reg_c)
                vfm = self._handle_mmio_read(addr16)
                self.registers[rn] = self._apply_16bit_limits(vfm)
                self._update_flags(self.registers[rn], opcode_str, overflow_occurred=False)
                self.output_log.append(f"  LOADM: Reg {rn} = Val from Addr[{addr16:04X}h] ({self.registers[rn]})")

            elif opcode_str == "INP":
                reg_c = self._fetch_byte_from_program()
                if reg_c is None: raise ValueError("INP op missing")
                rn = self._get_reg_name(reg_c)
                vfid = self._handle_mmio_read(DEFAULT_MMIO_INPUT_ADDR)
                self.registers[rn] = self._apply_16bit_limits(vfid)
                self._update_flags(self.registers[rn], opcode_str, overflow_occurred=False)
                self.output_log.append(
                    f"  INP (via MMIO {DEFAULT_MMIO_INPUT_ADDR:04X}h): Reg {rn} = {self.registers[rn]}")

            elif opcode_str == "OUT":
                reg_c = self._fetch_byte_from_program()
                if reg_c is None: raise ValueError("OUT op missing")
                rn = self._get_reg_name(reg_c)
                vto = self.registers[rn]
                self._handle_mmio_write(DEFAULT_MMIO_OUTPUT_ADDR, vto)
                self.output_log.append(f"  OUT (via MMIO {DEFAULT_MMIO_OUTPUT_ADDR:04X}h): Reg {rn} ({vto})")

            elif opcode_str == "INM":
                reg_c = self._fetch_byte_from_program()
                addr16 = self._fetch_word_le_from_program()
                if reg_c is None or addr16 is None: raise ValueError("INM ops missing")
                rn = self._get_reg_name(reg_c)
                vfd = self._handle_mmio_read(addr16)
                self.registers[rn] = self._apply_16bit_limits(vfd)
                self._update_flags(self.registers[rn], opcode_str, overflow_occurred=False)
                self.output_log.append(f"  INM: Reg {rn} = Val from MMIO Addr {addr16:04X}h ({self.registers[rn]})")

            elif opcode_str == "OUTM":
                reg_c = self._fetch_byte_from_program()
                addr16 = self._fetch_word_le_from_program()
                if reg_c is None or addr16 is None: raise ValueError("OUTM ops missing")
                rn = self._get_reg_name(reg_c)
                vto = self.registers[rn]
                self._handle_mmio_write(addr16, vto)
                self.output_log.append(f"  OUTM: Reg {rn} ({vto}) to MMIO Addr {addr16:04X}h")

            elif opcode_str == "ADD":
                r1_c = self._fetch_byte_from_program();
                r2_c = self._fetch_byte_from_program()
                if r1_c is None or r2_c is None: raise ValueError("ADD ops missing")
                r1n, r2n = self._get_reg_name(r1_c), self._get_reg_name(r2_c)
                v1, v2 = self.registers[r1n], self.registers[r2n]
                raw_sum = v1 + v2;
                result_16bit = self._apply_16bit_limits(raw_sum);
                carry = raw_sum > 0xFFFF
                s1, s2, sr = (v1 & 0x8000), (v2 & 0x8000), (result_16bit & 0x8000);
                overflow = (s1 == s2) and (sr != s1)
                self.registers[r1n] = result_16bit;
                self._update_flags(result_16bit, opcode_str, carry, overflow)
                self.output_log.append(f"  ADD: {r1n}({v1})+{r2n}({v2})={result_16bit}")
            elif opcode_str == "SUB":
                r1_c = self._fetch_byte_from_program();
                r2_c = self._fetch_byte_from_program()
                if r1_c is None or r2_c is None: raise ValueError("SUB ops missing")
                r1n, r2n = self._get_reg_name(r1_c), self._get_reg_name(r2_c)
                v1, v2 = self.registers[r1n], self.registers[r2n]
                raw_diff = v1 - v2;
                result_16bit = self._apply_16bit_limits(raw_diff);
                borrow = v1 < v2
                s1, s2, sr = (v1 & 0x8000), (v2 & 0x8000), (result_16bit & 0x8000);
                overflow = (s1 != s2) and (sr != s1)
                self.registers[r1n] = result_16bit;
                self._update_flags(result_16bit, opcode_str, borrow, overflow)
                self.output_log.append(f"  SUB: {r1n}({v1})-{r2n}({v2})={result_16bit}")
            elif opcode_str == "MUL":
                r1_c = self._fetch_byte_from_program();
                r2_c = self._fetch_byte_from_program()
                if r1_c is None or r2_c is None: raise ValueError("MUL ops missing")
                r1n, r2n = self._get_reg_name(r1_c), self._get_reg_name(r2_c)
                v1, v2 = self.registers[r1n], self.registers[r2n]
                raw_product = v1 * v2;
                result_16bit = self._apply_16bit_limits(raw_product);
                carry = raw_product > 0xFFFF
                self.registers[r1n] = result_16bit;
                self._update_flags(result_16bit, opcode_str, carry, carry)
                self.output_log.append(f"  MUL: {r1n}({v1})*{r2n}({v2})={result_16bit}")
            elif opcode_str == "INC":
                reg_c = self._fetch_byte_from_program()
                if reg_c is None: raise ValueError("INC op missing")
                rn = self._get_reg_name(reg_c);
                v1 = self.registers[rn]
                raw_sum = v1 + 1;
                result_16bit = self._apply_16bit_limits(raw_sum);
                ca = raw_sum > 0xFFFF
                s1, s_inc, sr = (v1 & 0x8000), (1 & 0x8000), (result_16bit & 0x8000);
                of = (s1 == s_inc) and (sr != s1)
                self.registers[rn] = result_16bit;
                self._update_flags(result_16bit, opcode_str, ca, of)
                self.output_log.append(f"  INC: {rn} from {v1} to {result_16bit}")
            elif opcode_str == "DEC":
                reg_c = self._fetch_byte_from_program()
                if reg_c is None: raise ValueError("DEC op missing")
                rn = self._get_reg_name(reg_c);
                v1 = self.registers[rn]
                raw_diff = v1 - 1;
                result_16bit = self._apply_16bit_limits(raw_diff);
                bo = v1 < 1
                s1, s_dec, sr = (v1 & 0x8000), (1 & 0x8000), (result_16bit & 0x8000);
                of = (s1 != s_dec) and (sr != s1)
                self.registers[rn] = result_16bit;
                self._update_flags(result_16bit, opcode_str, bo, of)
                self.output_log.append(f"  DEC: {rn} from {v1} to {result_16bit}")
            elif opcode_str == "AND":
                r1_c, r2_c = self._fetch_byte_from_program(), self._fetch_byte_from_program()
                if r1_c is None or r2_c is None: raise ValueError("AND ops missing")
                r1n, r2n = self._get_reg_name(r1_c), self._get_reg_name(r2_c)
                v1, v2 = self.registers[r1n], self.registers[r2n];
                res = v1 & v2;
                self.registers[r1n] = self._apply_16bit_limits(res)
                self._update_flags(self.registers[r1n], opcode_str, clear_carry_for_logical=True)
                self.output_log.append(
                    f"  AND: {r1n}({v1:016b})&{r2n}({v2:016b})={self.registers[r1n]:016b}b ({self.registers[r1n]})")
            elif opcode_str == "OR":
                r1_c, r2_c = self._fetch_byte_from_program(), self._fetch_byte_from_program()
                if r1_c is None or r2_c is None: raise ValueError("OR ops missing")
                r1n, r2n = self._get_reg_name(r1_c), self._get_reg_name(r2_c)
                v1, v2 = self.registers[r1n], self.registers[r2n];
                res = v1 | v2;
                self.registers[r1n] = self._apply_16bit_limits(res)
                self._update_flags(self.registers[r1n], opcode_str, clear_carry_for_logical=True)
                self.output_log.append(
                    f"  OR: {r1n}({v1:016b})|{r2n}({v2:016b})={self.registers[r1n]:016b}b ({self.registers[r1n]})")
            elif opcode_str == "XOR":
                r1_c, r2_c = self._fetch_byte_from_program(), self._fetch_byte_from_program()
                if r1_c is None or r2_c is None: raise ValueError("XOR ops missing")
                r1n, r2n = self._get_reg_name(r1_c), self._get_reg_name(r2_c)
                v1, v2 = self.registers[r1n], self.registers[r2n];
                res = v1 ^ v2;
                self.registers[r1n] = self._apply_16bit_limits(res)
                self._update_flags(self.registers[r1n], opcode_str, clear_carry_for_logical=True)
                self.output_log.append(
                    f"  XOR: {r1n}({v1:016b})^{r2n}({v2:016b})={self.registers[r1n]:016b}b ({self.registers[r1n]})")
            elif opcode_str == "NOT":
                reg_c = self._fetch_byte_from_program()
                if reg_c is None: raise ValueError("NOT op missing")
                rn = self._get_reg_name(reg_c)
                res = ~self.registers[rn];
                self.registers[rn] = self._apply_16bit_limits(res)
                self._update_flags(self.registers[rn], opcode_str, overflow_occurred=False)
                self.output_log.append(f"  NOT: {rn}={self.registers[rn]:016b}b ({self.registers[rn]})")
            elif opcode_str == "SHL":
                reg_c, sv_b = self._fetch_byte_from_program(), self._fetch_byte_from_program()
                if reg_c is None or sv_b is None: raise ValueError("SHL ops missing")
                rn, sa = self._get_reg_name(reg_c), sv_b
                ov = self.registers[rn];
                co = False;
                pcf = self.CF
                if sa > 0: pcf = (ov >> (15 - (sa - 1))) & 1 if sa <= 16 and (15 - (sa - 1)) >= 0 else False
                res = ov << sa;
                self.registers[rn] = self._apply_16bit_limits(res)
                self._update_flags(self.registers[rn], opcode_str, carry_occurred=(pcf if sa > 0 else self.CF),
                                   overflow_occurred=False)
                self.output_log.append(f"  SHL: {rn}={self.registers[rn]:016b}b from {ov}<<{sa}")
            elif opcode_str == "SHR":
                reg_c, sv_b = self._fetch_byte_from_program(), self._fetch_byte_from_program()
                if reg_c is None or sv_b is None: raise ValueError("SHR ops missing")
                rn, sa = self._get_reg_name(reg_c), sv_b
                ov = self.registers[rn];
                co = False;
                pcf = self.CF
                if sa > 0: pcf = (ov >> (sa - 1)) & 1 if sa <= 16 else False
                res = ov >> sa;
                self.registers[rn] = self._apply_16bit_limits(res)
                self._update_flags(self.registers[rn], opcode_str, carry_occurred=(pcf if sa > 0 else self.CF),
                                   overflow_occurred=False)
                self.output_log.append(f"  SHR: {rn}={self.registers[rn]:016b}b from {ov}>>{sa}")
            elif opcode_str == "CMP":
                r1_c, r2_c = self._fetch_byte_from_program(), self._fetch_byte_from_program()
                if r1_c is None or r2_c is None: raise ValueError("CMP ops missing")
                r1n, r2n = self._get_reg_name(r1_c), self._get_reg_name(r2_c)
                v1, v2 = self.registers[r1n], self.registers[r2n]
                rd = v1 - v2;
                r16f = self._apply_16bit_limits(rd);
                bo = v1 < v2
                s1, s2, sr = (v1 & 0x8000), (v2 & 0x8000), (r16f & 0x8000);
                of = (s1 != s2) and (sr != s1)
                self._update_flags(r16f, opcode_str, bo, of, is_cmp=True)
                self.output_log.append(
                    f"  CMP: {r1n}({v1}) vs {r2n}({v2}). Flags: ZF{int(self.ZF)}SF{int(self.SF)}CF{int(self.CF)}OF{int(self.OF)}")
            elif opcode_str == "MOV":
                dr_c, sr_c = self._fetch_byte_from_program(), self._fetch_byte_from_program()
                if dr_c is None or sr_c is None: raise ValueError("MOV ops missing")
                drn, srn = self._get_reg_name(dr_c), self._get_reg_name(sr_c)
                vm = self.registers[srn];
                self.registers[drn] = vm;
                self._update_flags(vm, opcode_str, overflow_occurred=False)
                self.output_log.append(f"  MOV: {drn}={vm} from {srn}({vm})")
            elif opcode_str == "PUSH":
                reg_c = self._fetch_byte_from_program()
                if reg_c is None: raise ValueError("PUSH op missing")
                rn = self._get_reg_name(reg_c);
                self.sp = (self.sp - 1) & 0xFFFF
                if self.sp < self.stack_limit: self.sp = (self.sp + 1) & 0xFFFF; raise ValueError(
                    f"Stack Overflow PUSH (SP={self.sp + 1}, limit={self.stack_limit})")
                if not self._is_valid_data_memory_word_address(self.sp): raise ValueError(
                    f"Invalid SP {self.sp:04X}h for PUSH (datamem size {self.data_memory_size})")
                vtp = self.registers[rn];
                self.data_memory[self.sp] = self._apply_16bit_limits(vtp)
                self.output_log.append(f"  PUSH: Reg {rn}({vtp}) to DataMemWord[{self.sp:04X}h]. SP:{self.sp:04X}h")
            elif opcode_str == "POP":
                reg_c = self._fetch_byte_from_program()
                if reg_c is None: raise ValueError("POP op missing")
                rn = self._get_reg_name(reg_c)
                if self.sp >= self.stack_base: raise ValueError(
                    f"Stack Underflow POP (SP={self.sp}, base={self.stack_base})")
                if not self._is_valid_data_memory_word_address(self.sp): raise ValueError(
                    f"Invalid SP {self.sp:04X}h for POP")
                vp = self.data_memory[self.sp];
                self.registers[rn] = self._apply_16bit_limits(vp)
                self.sp = (self.sp + 1) & 0xFFFF
                self._update_flags(self.registers[rn], opcode_str, overflow_occurred=False)
                self.output_log.append(
                    f"  POP: {vp} from DataMemWord[{(self.sp - 1) & 0xFFFF :04X}h] to Reg {rn}. SP:{self.sp:04X}h")
            elif opcode_str == "CALL":
                target_addr16 = self._fetch_word_le_from_program()
                if target_addr16 is None: raise ValueError("CALL op missing")
                return_address16 = self.program_counter;
                self.sp = (self.sp - 1) & 0xFFFF
                if self.sp < self.stack_limit: self.sp = (self.sp + 1) & 0xFFFF; raise ValueError("Stack Overflow CALL")
                if not self._is_valid_data_memory_word_address(self.sp): raise ValueError(
                    f"Invalid SP {self.sp:04X}h for CALL")
                self.data_memory[self.sp] = self._apply_16bit_limits(return_address16)
                self.program_counter = target_addr16;
                jumped = True
                self.output_log.append(
                    f"  CALL: Pushed ret({return_address16:04X}h) to DataMemWord[{self.sp:04X}h]. JMP to {self.program_counter:04X}h. SP:{self.sp:04X}h")
            elif opcode_str == "RET":
                if self.sp >= self.stack_base: raise ValueError("Stack Underflow RET")
                if not self._is_valid_data_memory_word_address(self.sp): raise ValueError(
                    f"Invalid SP {self.sp:04X}h for RET")
                ra16fs = self.data_memory[self.sp];
                self.sp = (self.sp + 1) & 0xFFFF
                self.program_counter = self._apply_16bit_limits(ra16fs);
                jumped = True
                self.output_log.append(
                    f"  RET: Popped ret({self.program_counter:04X}h) from DataMemWord[{(self.sp - 1) & 0xFFFF :04X}h]. JMP to {self.program_counter:04X}h. SP:{self.sp:04X}h")

            elif opcode_str == "JMP":
                target_addr16 = self._fetch_word_le_from_program()
                if target_addr16 is None: raise ValueError("JMP op missing")
                self.program_counter = target_addr16;
                jumped = True
                self.output_log.append(f"  JMP: to {target_addr16:04X}h")
            elif opcode_str == "JMPZ":
                reg_code = self._fetch_byte_from_program();
                target_addr16 = self._fetch_word_le_from_program()
                if reg_code is None or target_addr16 is None: raise ValueError("JMPZ ops missing")
                rn = self._get_reg_name(reg_code)
                if self.registers[rn] == 0:
                    self.program_counter = target_addr16;jumped = True;self.output_log.append(
                        f"  JMPZ: Reg {rn} zero. JMP to {target_addr16:04X}h")
                else:
                    self.output_log.append(f"  JMPZ: Reg {rn}({self.registers[rn]}) not zero. No JMP.")
            elif opcode_str == "JMPN":
                reg_code = self._fetch_byte_from_program();
                target_addr16 = self._fetch_word_le_from_program()
                if reg_code is None or target_addr16 is None: raise ValueError("JMPN ops missing")
                rn = self._get_reg_name(reg_code)
                if (self.registers[rn] & 0x8000) != 0:
                    self.program_counter = target_addr16;jumped = True;self.output_log.append(
                        f"  JMPN: Reg {rn}({self.registers[rn]}) neg. JMP to {target_addr16:04X}h")
                else:
                    self.output_log.append(f"  JMPN: Reg {rn}({self.registers[rn]}) not neg. No JMP.")
            elif opcode_str == "JE":
                target_addr16 = self._fetch_word_le_from_program()
                if target_addr16 is None: raise ValueError("JE op missing")
                if self.ZF:
                    self.program_counter = target_addr16;jumped = True;self.output_log.append(
                        f"  JE: ZF True. JMP to {target_addr16:04X}h")
                else:
                    self.output_log.append(f"  JE: ZF False. No JMP.")
            elif opcode_str == "JNE":
                target_addr16 = self._fetch_word_le_from_program()
                if target_addr16 is None: raise ValueError("JNE op missing")
                if not self.ZF:
                    self.program_counter = target_addr16;jumped = True;self.output_log.append(
                        f"  JNE: ZF False. JMP to {target_addr16:04X}h")
                else:
                    self.output_log.append(f"  JNE: ZF True. No JMP.")
            elif opcode_str == "JS":
                target_addr16 = self._fetch_word_le_from_program()
                if target_addr16 is None: raise ValueError("JS op missing")
                if self.SF:
                    self.program_counter = target_addr16;jumped = True;self.output_log.append(
                        f"  JS: SF True. JMP to {target_addr16:04X}h")
                else:
                    self.output_log.append(f"  JS: SF False. No JMP.")
            elif opcode_str == "JNS":
                target_addr16 = self._fetch_word_le_from_program()
                if target_addr16 is None: raise ValueError("JNS op missing")
                if not self.SF:
                    self.program_counter = target_addr16;jumped = True;self.output_log.append(
                        f"  JNS: SF False. JMP to {target_addr16:04X}h")
                else:
                    self.output_log.append(f"  JNS: SF True. No JMP.")
            elif opcode_str == "JC":
                target_addr16 = self._fetch_word_le_from_program()
                if target_addr16 is None: raise ValueError("JC op missing")
                if self.CF:
                    self.program_counter = target_addr16;jumped = True;self.output_log.append(
                        f"  JC: CF True. JMP to {target_addr16:04X}h")
                else:
                    self.output_log.append(f"  JC: CF False. No JMP.")
            elif opcode_str == "JNC":
                target_addr16 = self._fetch_word_le_from_program()
                if target_addr16 is None: raise ValueError("JNC op missing")
                if not self.CF:
                    self.program_counter = target_addr16;jumped = True;self.output_log.append(
                        f"  JNC: CF False. JMP to {target_addr16:04X}h")
                else:
                    self.output_log.append(f"  JNC: CF True. No JMP.")
            elif opcode_str == "JO":
                target_addr16 = self._fetch_word_le_from_program()
                if target_addr16 is None: raise ValueError("JO op missing")
                if self.OF:
                    self.program_counter = target_addr16;jumped = True;self.output_log.append(
                        f"  JO: OF True. JMP to {target_addr16:04X}h")
                else:
                    self.output_log.append(f"  JO: OF False. No JMP.")
            elif opcode_str == "JNO":
                target_addr16 = self._fetch_word_le_from_program()
                if target_addr16 is None: raise ValueError("JNO op missing")
                if not self.OF:
                    self.program_counter = target_addr16;jumped = True;self.output_log.append(
                        f"  JNO: OF False. JMP to {target_addr16:04X}h")
                else:
                    self.output_log.append(f"  JNO: OF True. No JMP.")
            else:
                self.output_log.append(
                    f"  FATAL: Opcode {opcode_str}({opcode_byte:02X}) UNKNOWN or no exec logic."); self.halted = True; return False
        except ValueError as e:
            self.output_log.append(
                f"  RUNTIME ERROR @PC {initial_pc_for_log:04X}h for {opcode_str}({opcode_byte:02X}): {e}"); self.halted = True; return False
        except TypeError as e:
            self.output_log.append(
                f"  RUNTIME TYPE ERROR @PC {initial_pc_for_log:04X}h for {opcode_str}({opcode_byte:02X}): {e}"); self.halted = True; return False
        return True

    def run_program(self, binary_filepath):
        self._reset_state()
        if not self.load_binary_program(binary_filepath): self.output_log.append(
            f"--- Sim Aborted: load fail ---"); return "\n".join(self.output_log)
        max_cycles = (len(self.program_bytes) * 20) + 1000;
        cycles = 0
        while not self.halted and cycles < max_cycles:
            if not self.execute_cycle(): break
            cycles += 1
        if cycles >= max_cycles and not self.halted: self.output_log.append("MAX CYCLES REACHED!"); self.halted = True
        log_end_msg = "--- Sim Finished"
        if self.halted:
            log_end_msg += " (CPU HALTED" + (")" if self.clean_halt else " by error/max_cycles)")
        elif self.program_counter >= len(self.program_bytes):
            log_end_msg += " (End of program)"
        self.output_log.append(f"{log_end_msg} ({cycles} cycles) ---")
        self.output_log.append(f"Final PC: {self.program_counter:04X}h")
        self.output_log.append(f"Final Regs: {self.registers}")
        self.output_log.append(f"Final SP: {self.sp:04X}h")
        self.output_log.append(f"Final Flags: ZF{int(self.ZF)}SF{int(self.SF)}CF{int(self.CF)}OF{int(self.OF)}")
        return "\n".join(self.output_log)

    def get_register_value(self, reg_name):
        return self.registers.get(reg_name.upper())

    def print_final_state(self):
        print("\n--- Final Simulator State (16-bit PC/SP/Data/DataAddrs) ---")
        for reg, val in sorted(self.registers.items()): print(f"Register {reg}: {val} (0x{val:04X}) ({val:016b}b)")
        print(f"Stack Pointer (SP): {self.sp:04X}h ({self.sp})")
        print(f"Program Counter (PC): {self.program_counter:04X}h ({self.program_counter})")
        print(f"Flags: ZF={int(self.ZF)}, SF={int(self.SF)}, CF={int(self.CF)}, OF={int(self.OF)}")
        print(f"Data Memory (Words 0-{self.data_memory_size - 1}, Sample):")
        count = 0;
        printed_indices = set()
        for i in range(self.data_memory_size):
            if self.data_memory[i] != 0 and i not in printed_indices:
                print(f"  DataMemWord[{i:04X}h ({i:d})]: {self.data_memory[i]} (0x{self.data_memory[i]:04X})")
                printed_indices.add(i);
                count += 1
            if count >= 8 and i > self.stack_base and self.sp >= self.stack_base: break
            if i >= 15 and count == 0 and i > 0.01 * self.data_memory_size: break
        if self.sp < self.stack_base:
            print("  Stack Area (16-bit words in Data Memory):")
            stack_display_start = max(self.stack_limit, self.sp - 4)
            stack_display_end = min(self.stack_base, self.sp + 8)
            for i in range(stack_display_start, stack_display_end):
                if i not in printed_indices:
                    print(
                        f"  DataMemWord[{i:04X}h ({i:d})]: {self.data_memory[i]} (0x{self.data_memory[i]:04X}) {'<- SP points here' if i == self.sp else ''}")
                    printed_indices.add(i);
                    count += 1
        if count == 0: print("  (All relevant data memory word locations in sample are zero)")
        print("---------------------------")


# Standalone test
if __name__ == "__main__":
    from simple_assembler import SimpleAssembler

    sample_sal_16bit_all_addr_test = """
    LOAD R0, #30000
    STORE R0, 500
    LOADM R1, 500
    OUT R1      
    CALL SUB1   
    OUT R0      
    JMP ENDING_LABEL
    SUBROUTINE:
    INC R0
    RET
    ENDING_LABEL:
    HALT
    """
    assembler = SimpleAssembler()
    bin_file = "test_16bit_all_addr_sim_final.bin"
    asm_file = "test_16bit_all_addr_sim_final.asm"
    if assembler.assemble_to_file(sample_sal_16bit_all_addr_test, bin_file, asm_file):
        print(f"\n--- Testing Simulator (16-bit All Addr) with '{bin_file}' ---")
        simulator = MicroprocessorSimulator(data_memory_size=1024, stack_size=64, program_memory_capacity=65536)
        log = simulator.run_program(bin_file)
        print("\nSimulation Log (16-bit All Addr Test):")
        print(log)
        simulator.print_final_state()
    else:
        print(f"Failed to assemble {bin_file} for simulator test.")
