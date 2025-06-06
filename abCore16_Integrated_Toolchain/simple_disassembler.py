# simple_disassembler.py
# Import from the new definitions file
from abcore16_defs import REVERSE_OPCODES, REG_NAMES, INSTRUCTION_FORMATS


class SimpleDisassembler:
    def __init__(self):
        self.program_bytes = []
        self.pc = 0
        self.output_lines = []
        self.errors = []
        self.potential_labels = {}
        self.processed_addresses = set()

    def _fetch_byte(self):
        if self.pc >= len(self.program_bytes):
            self.errors.append(f"Disasm Error: Unexpected EOF while fetching byte at PC=0x{self.pc:04X}.")
            return None
        byte = self.program_bytes[self.pc]
        self.pc += 1
        return byte

    def _fetch_word_le(self):  # For unsigned 16-bit (I16, A16)
        low = self._fetch_byte()
        if low is None: return None
        high = self._fetch_byte()
        if high is None: return None
        return (high << 8) | low

    def _fetch_signed_word_le(self):  # For signed 16-bit (S16)
        val_unsigned = self._fetch_word_le()
        if val_unsigned is None: return None
        if val_unsigned & 0x8000:
            return val_unsigned - 0x10000
        return val_unsigned

    def _format_operand(self, operand_val, op_type_str, current_instr_addr_for_log):
        if op_type_str == 'R':
            if operand_val in REG_NAMES:
                return REG_NAMES[operand_val]
            self.errors.append(
                f"Disasm Error @0x{current_instr_addr_for_log:04X}h: Invalid register code {operand_val}")
            return f"R_ERR({operand_val})"
        elif op_type_str == 'I16':
            return f"#0x{operand_val:04X}"
        elif op_type_str == 'I8':
            return f"#{operand_val}"
        elif op_type_str == 'A16':
            return self.potential_labels.get(operand_val, f"0x{operand_val:04X}")
        elif op_type_str == 'S16':
            return f"#{operand_val}"

        self.errors.append(
            f"Disasm Error @0x{current_instr_addr_for_log:04X}h: Unknown operand type '{op_type_str}' for value {operand_val}")
        return f"UNK_OP_TYPE({operand_val})"

    def _pre_scan_for_labels(self):
        self.potential_labels = {}
        scan_pc = 0;
        program_len = len(self.program_bytes)
        while scan_pc < program_len:
            instr_start_addr = scan_pc
            if instr_start_addr >= program_len: break
            opcode_byte = self.program_bytes[instr_start_addr]
            opcode_str = REVERSE_OPCODES.get(opcode_byte)
            current_instr_len = 1
            if opcode_str and opcode_str in INSTRUCTION_FORMATS:
                instr_total_bytes, op_types_fmt = INSTRUCTION_FORMATS[opcode_str]
                current_instr_len = instr_total_bytes
                is_jump_or_call_type = opcode_str.startswith("J") or opcode_str == "CALL"
                if is_jump_or_call_type:
                    a16_operand_offset = 1;
                    found_a16_for_jump = False
                    for op_type_in_fmt in op_types_fmt:
                        if op_type_in_fmt == 'A16':
                            found_a16_for_jump = True; break
                        elif op_type_in_fmt == 'R' or op_type_in_fmt == 'I8':
                            a16_operand_offset += 1
                        elif op_type_in_fmt == 'I16' or op_type_in_fmt == 'S16':
                            a16_operand_offset += 2
                    if found_a16_for_jump:
                        addr_low_byte_pos = instr_start_addr + a16_operand_offset
                        addr_high_byte_pos = addr_low_byte_pos + 1
                        if addr_high_byte_pos < program_len:
                            target_a16_val = (self.program_bytes[addr_high_byte_pos] << 8) | self.program_bytes[
                                addr_low_byte_pos]
                            if target_a16_val not in self.potential_labels:
                                self.potential_labels[target_a16_val] = f"L_{target_a16_val:04X}"
            scan_pc += current_instr_len
            if current_instr_len == 0: scan_pc += 1  # Ensure progress

    def disassemble(self, machine_code_bytes):
        self.program_bytes = list(machine_code_bytes)
        self.pc = 0;
        self.output_lines = [];
        self.errors = [];
        self.processed_addresses = set()
        if not self.program_bytes: self.output_lines.append("; Empty binary file."); return "\n".join(self.output_lines)

        self._pre_scan_for_labels()

        while self.pc < len(self.program_bytes):
            current_instr_addr = self.pc
            if current_instr_addr in self.potential_labels and current_instr_addr not in self.processed_addresses:
                self.output_lines.append(f"{self.potential_labels[current_instr_addr]}:")
                self.processed_addresses.add(current_instr_addr)

            opcode_byte = self._fetch_byte()
            if opcode_byte is None: break
            opcode_str = REVERSE_OPCODES.get(opcode_byte)

            if not opcode_str:
                self.output_lines.append(f"{current_instr_addr:04X}h:  DB 0x{opcode_byte:02X}    ; Unknown Opcode")
                self.errors.append(f"Unknown opcode 0x{opcode_byte:02X} at 0x{current_instr_addr:04X}h")
                continue

            instr_total_bytes, operand_type_list_fmt = INSTRUCTION_FORMATS.get(opcode_str, (1, []))
            fetched_operands_values = [];
            operand_fetch_error = False

            for op_fmt_type in operand_type_list_fmt:
                val = None
                if op_fmt_type == 'R':
                    val = self._fetch_byte()
                elif op_fmt_type == 'I8':
                    val = self._fetch_byte()
                elif op_fmt_type == 'I16':
                    val = self._fetch_word_le()
                elif op_fmt_type == 'A16':
                    val = self._fetch_word_le()
                elif op_fmt_type == 'S16':
                    val = self._fetch_signed_word_le()
                else:
                    self.errors.append(
                        f"Disasm Error @0x{current_instr_addr:04X}h: Opcode {opcode_str} has unknown operand type '{op_fmt_type}'.")
                    operand_fetch_error = True;
                    break
                if val is None: operand_fetch_error = True; break
                fetched_operands_values.append(val)

            if operand_fetch_error:
                partial_op_str = " ".join([f"0x{opv:02X}" for opv in fetched_operands_values if opv is not None])
                self.output_lines.append(
                    f"{current_instr_addr:04X}h:  {opcode_str} {partial_op_str}... ; Incomplete instruction")
                break

            operands_str_display_list = []
            for i, op_val_fetched in enumerate(fetched_operands_values):
                operands_str_display_list.append(
                    self._format_operand(op_val_fetched, operand_type_list_fmt[i], current_instr_addr)
                )

            sal_instruction_str = opcode_str
            if operands_str_display_list:
                sal_instruction_str += " " + ", ".join(operands_str_display_list)

            # Get all bytes for this instruction for hex display
            instr_bytes_for_hex = self.program_bytes[current_instr_addr: self.pc]  # self.pc is already advanced
            hex_bytes_str = " ".join([f"{b:02X}" for b in instr_bytes_for_hex]).ljust(14)  # Pad to align comments

            self.output_lines.append(f"{current_instr_addr:04X}h: {hex_bytes_str} {sal_instruction_str}")

        if self.errors:
            self.output_lines.append("\n; --- Disassembly Errors/Warnings ---")
            for err_msg in self.errors: self.output_lines.append(f"; {err_msg}")
        return "\n".join(self.output_lines)


# Standalone test block
if __name__ == "__main__":
    disassembler = SimpleDisassembler()

    # Test case including MOVFRSP, MOVTOSP, LOADFR, STORFR
    # MOVFRSP R1             (Op=81, R1=01)
    # MOVTOSP R0             (Op=82, R0=00)
    # LOADFR R1, R5, #-4     (Op=04, R1=01, R5=05, Offset=-4 = 0xFFFC -> FC FF)
    # STORFR R2, R5, #10     (Op=05, R2=02, R5=05, Offset=10 = 0x000A -> 0A 00)
    # HALT (FF)
    test_machine_code_all_new = bytes([
        0x81, 0x01,  # MOVFRSP R1
        0x01, 0x00, 0x34, 0x12,  # LOAD R0, #0x1234
        0x82, 0x00,  # MOVTOSP R0
        0x01, 0x05, 0x00, 0x01,  # LOAD R5, #0x0100
        0x04, 0x01, 0x05, 0xFC, 0xFF,  # LOADFR R1, R5, #-4
        0x05, 0x02, 0x05, 0x0A, 0x00,  # STORFR R2, R5, #10
        0xFF  # HALT
    ])

    print("--- Disassembling test code with all new opcodes ---")
    disassembled_sal = disassembler.disassemble(test_machine_code_all_new)
    print(disassembled_sal)

    if disassembler.errors:
        print("\nDisassembly encountered errors:")
        for err in disassembler.errors: print(f"  - {err}")
            
