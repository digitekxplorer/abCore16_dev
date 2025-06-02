# simple_disassembler.py
# import re
# import os
# Import from the new definitions file
from abcore16_defs import REVERSE_OPCODES, REG_NAMES, INSTRUCTION_FORMATS


class SimpleDisassembler:
    # Class-level constants are now directly from abcore16_defs.
    def __init__(self):
        self.program_bytes = []
        self.pc = 0
        self.output_lines = []
        self.errors = []
        self.potential_labels = {}

    def _fetch_byte(self):  # No change
        if self.pc >= len(self.program_bytes): return None
        byte = self.program_bytes[self.pc]
        self.pc += 1
        return byte

    def _fetch_word_le(self):  # No change
        low = self._fetch_byte()
        high = self._fetch_byte()
        if low is None or high is None: return None
        return (high << 8) | low

    def _format_operand(self, operand_val, op_type_str, current_addr_for_error_log):  # Uses imported REG_NAMES
        if op_type_str == 'R':
            if operand_val in REG_NAMES: return REG_NAMES[operand_val]
            self.errors.append(f"Disasm Error @{current_addr_for_error_log:04X}h: Invalid reg code {operand_val}")
            return f"R_ERR({operand_val})"
        elif op_type_str == 'I16':
            return f"#0x{operand_val:04X}"
        elif op_type_str == 'I8':
            return f"#{operand_val}"
        elif op_type_str == 'A16':
            return self.potential_labels.get(operand_val, f"0x{operand_val:04X}")  # Use label if found
        self.errors.append(f"Disasm Error @{current_addr_for_error_log:04X}h: Unknown op type '{op_type_str}'")
        return f"UNK_OP({operand_val})"

    def _pre_scan_for_labels(self):  # Uses imported REVERSE_OPCODES, INSTRUCTION_FORMATS
        self.potential_labels = {}
        scan_pc = 0
        while scan_pc < len(self.program_bytes):
            #instr_start_addr = scan_pc
            if scan_pc >= len(self.program_bytes): break
            opcode_byte = self.program_bytes[scan_pc]
            opcode_str = REVERSE_OPCODES.get(opcode_byte)
            current_instr_len = 1  # Default advance if unknown

            if opcode_str and opcode_str in INSTRUCTION_FORMATS:
                instr_total_bytes, op_types_fmt = INSTRUCTION_FORMATS[opcode_str]
                current_instr_len = instr_total_bytes

                # Check for A16 operand in jump/call instructions
                if 'A16' in op_types_fmt and (opcode_str.startswith("J") or opcode_str == "CALL"):
                    #bytes_before_a16 = 1  # Opcode byte
                    target_a16_val = -1

                    temp_pc_for_operand_fetch = scan_pc + 1  # Start after opcode
                    found_a16_for_label = False

                    for op_idx, op_type_in_fmt in enumerate(op_types_fmt):
                        if temp_pc_for_operand_fetch >= len(self.program_bytes): break  # EOF

                        if op_type_in_fmt == 'A16':
                            if temp_pc_for_operand_fetch + 1 < len(self.program_bytes):  # Enough for L, H bytes
                                addr_l = self.program_bytes[temp_pc_for_operand_fetch]
                                addr_h = self.program_bytes[temp_pc_for_operand_fetch + 1]
                                target_a16_val = (addr_h << 8) | addr_l
                                found_a16_for_label = True
                                break  # Found the A16 for this jump/call
                            else:
                                break  # EOF for A16
                        elif op_type_in_fmt == 'R' or op_type_in_fmt == 'I8':
                            temp_pc_for_operand_fetch += 1
                        elif op_type_in_fmt == 'I16':  # Should not precede A16 in jump/call formats usually
                            temp_pc_for_operand_fetch += 2

                    if found_a16_for_label and target_a16_val not in self.potential_labels:
                        self.potential_labels[target_a16_val] = f"L_{target_a16_val:04X}"
            scan_pc += current_instr_len
            if current_instr_len == 0: scan_pc += 1  # Ensure progress if error

    def disassemble(self, machine_code_bytes):  # Uses imported REVERSE_OPCODES, INSTRUCTION_FORMATS
        self.program_bytes = list(machine_code_bytes)
        self.pc = 0
        self.output_lines = []
        self.errors = []
        processed_addresses = set()
        self._pre_scan_for_labels()

        while self.pc < len(self.program_bytes):
            current_addr = self.pc
            if current_addr in self.potential_labels and current_addr not in processed_addresses:
                self.output_lines.append(f"{self.potential_labels[current_addr]}:")
                processed_addresses.add(current_addr)

            opcode_byte = self._fetch_byte()
            if opcode_byte is None: break
            opcode_str = REVERSE_OPCODES.get(opcode_byte)

            if not opcode_str:
                self.output_lines.append(f"{current_addr:04X}h:  DB 0x{opcode_byte:02X} ; Unknown Opcode")
                self.errors.append(f"Unknown opcode 0x{opcode_byte:02X} at {current_addr:04X}h")
                continue

            operands_str_list = []
            fetch_error = False
            _, operand_types_fmt = INSTRUCTION_FORMATS.get(opcode_str, (0, []))

            fetched_operand_values = []
            for op_type in operand_types_fmt:
                val = None
                if op_type == 'R' or op_type == 'I8':
                    val = self._fetch_byte()
                elif op_type == 'I16' or op_type == 'A16':
                    val = self._fetch_word_le()
                if val is None: fetch_error = True; break
                fetched_operand_values.append(val)

            if fetch_error:
                self.errors.append(f"Disasm Error: EOF fetching operands for {opcode_str} at {current_addr:04X}h.")
                # Try to log partial info
                partial_op_str = " ".join([f"0x{opv:02X}" for opv in fetched_operand_values])
                self.output_lines.append(f"{current_addr:04X}h:  {opcode_str} {partial_op_str} ; ... (EOF)")
                break

            for i, op_val in enumerate(fetched_operand_values):
                operands_str_list.append(self._format_operand(op_val, operand_types_fmt[i], current_addr))

            sal_instruction = f"{opcode_str} {', '.join(operands_str_list)}" if operands_str_list else opcode_str
            self.output_lines.append(f"{current_addr:04X}h:  {sal_instruction}")

        if self.errors:
            self.output_lines.append("\n; --- Disassembly Errors/Warnings ---")
            for err in self.errors: self.output_lines.append(f"; {err}")
        return "\n".join(self.output_lines)


# Standalone test - no change
if __name__ == "__main__":
    machine_code_logical = bytes(
        [0x01, 0x00, 0x05, 0x00, 0x26, 0x03, 0x00, 0x02, 0xFF])  # LOAD R0,#5; L_AND R3,R0,R2; HALT
    disassembler = SimpleDisassembler()
    disassembled_sal = disassembler.disassemble(machine_code_logical)
    print("\n--- Disassembled SAL (using abcore16_defs) ---")
    print(disassembled_sal)
