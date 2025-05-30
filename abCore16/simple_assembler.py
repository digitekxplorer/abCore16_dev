# simple_assembler.py
import re
import os

# Global variable to help _parse_operand distinguish context for '#' requirement.
# This is still a bit of a hack for _parse_operand to know if a '#' is mandatory.
opcode_str_being_parsed_for_asm = ""


class SimpleAssembler:
    OPCODES_CLASS = {
        "NOP": 0x00, "LOAD": 0x01, "STORE": 0x02, "LOADM": 0x03,
        "ADD": 0x10, "SUB": 0x11, "MUL": 0x12,
        "INC": 0x13, "DEC": 0x14,
        "AND": 0x20, "OR": 0x21, "XOR": 0x22, "NOT": 0x23,
        "SHL": 0x24, "SHR": 0x25,
        "INP": 0x30, "OUT": 0x31,
        "INM": 0x32, "OUTM": 0x33,
        "CMP": 0x40,
        "JMP": 0x50, "JMPZ": 0x51, "JMPN": 0x52,
        "JE": 0x53, "JNE": 0x54, "JS": 0x55, "JNS": 0x56,
        "JC": 0x57, "JNC": 0x58, "JO": 0x59, "JNO": 0x5A,
        "PUSH": 0x60, "POP": 0x61,
        "CALL": 0x70, "RET": 0x71,
        "MOV": 0x80,
        "HALT": 0xFF
    }
    REG_CODES_CLASS = {'R0': 0, 'R1': 1, 'R2': 2, 'R3': 3, 'R4': 4, 'R5': 5, 'R6': 6, 'R7': 7}
    VALID_REGISTERS_ASSEMBLER_CLASS = set(REG_CODES_CLASS.keys())
    MAX_IMMEDIATE_16BIT_CLASS = 65535
    MAX_ADDRESS_16BIT_CLASS = 65535
    MAX_IMMEDIATE_8BIT_CLASS = 255

    def __init__(self):
        self.symbol_table = {}
        self.machine_code = []
        self.current_byte_offset = 0
        self.errors = []
        self.sal_listing_data = []

    def _get_instruction_byte_length(self, opcode_str, op1_str=None, op2_str=None):
        global opcode_str_being_parsed_for_asm
        opcode_str_being_parsed_for_asm = opcode_str
        if opcode_str not in SimpleAssembler.OPCODES_CLASS: return 0
        if opcode_str == "LOAD": return 4
        if opcode_str in ["STORE", "LOADM", "INM", "OUTM", "JMPZ", "JMPN"]: return 4
        if opcode_str in ["SHL", "SHR", "ADD", "SUB", "MUL", "AND", "OR", "XOR", "CMP", "MOV"]: return 3
        if opcode_str in ["JMP", "JE", "JNE", "JS", "JNS", "JC", "JNC", "JO", "JNO", "CALL"]: return 3
        if opcode_str in ["NOT", "INP", "OUT", "PUSH", "POP", "INC", "DEC"]: return 2
        if opcode_str in ["RET", "NOP", "HALT"]: return 1
        self.errors.append(f"Internal Error: Opcode '{opcode_str}' no defined length in _get_instruction_byte_length.")
        return 0

    def _preprocess_line(self, line_text_raw):
        return line_text_raw.split(';', 1)[0].strip()

    def _parse_operand(self, operand_str_raw, expect_register=False,
                       expect_immediate_8bit=False, expect_immediate_16bit=False,
                       expect_address_16bit=False, expect_label=False):
        global opcode_str_being_parsed_for_asm
        operand_str_for_parsing = operand_str_raw.strip()
        operand_str_upper = operand_str_for_parsing.upper()
        max_val = 0;
        is_hash = operand_str_for_parsing.startswith('#');
        is_hex = operand_str_upper.startswith('0X')
        num_cand = operand_str_for_parsing;
        base_parse = 10
        if is_hash:
            num_cand = num_cand[1:]
            if num_cand.upper().startswith("0X"): num_cand = num_cand[2:]; base_parse = 16
        elif is_hex and not expect_label:
            num_cand = num_cand[2:];
            base_parse = 16

        if expect_register:
            if operand_str_upper in SimpleAssembler.REG_CODES_CLASS: return SimpleAssembler.REG_CODES_CLASS[
                operand_str_upper]
            self.errors.append(
                f"Invalid register: '{operand_str_raw}'. Valid: {sorted(list(SimpleAssembler.VALID_REGISTERS_ASSEMBLER_CLASS))}");
            return None

        is_num = False;
        type_err = "value/address"
        if expect_immediate_8bit:
            max_val = SimpleAssembler.MAX_IMMEDIATE_8BIT_CLASS;is_num = True;type_err = "8-bit immediate"
        elif expect_immediate_16bit:
            max_val = SimpleAssembler.MAX_IMMEDIATE_16BIT_CLASS;is_num = True;type_err = "16-bit immediate"
        elif expect_address_16bit:
            max_val = SimpleAssembler.MAX_ADDRESS_16BIT_CLASS;is_num = True;type_err = "16-bit address"

        if is_num:
            if (expect_immediate_8bit or expect_immediate_16bit) and \
                    opcode_str_being_parsed_for_asm in ["LOAD", "SHL", "SHR"] and not is_hash:
                self.errors.append(
                    f"Immediate '{operand_str_raw}' for {opcode_str_being_parsed_for_asm} must start with '#'.");
                return None
            if expect_address_16bit and \
                    opcode_str_being_parsed_for_asm in ["STORE", "LOADM", "INM", "OUTM"] and is_hash:
                self.errors.append(
                    f"Address '{operand_str_raw}' for {opcode_str_being_parsed_for_asm} should not start with '#'.");
                return None
            try:
                val_parsed = int(num_cand, base_parse)
                if not (0 <= val_parsed <= max_val):
                    self.errors.append(
                        f"{type_err.capitalize()} '{val_parsed}' from '{operand_str_raw}' out of range (0-{max_val}).");
                    return None
                return val_parsed
            except ValueError:
                self.errors.append(
                    f"Invalid numeric format for {type_err}: '{operand_str_raw}' (parsed '{num_cand}' base {base_parse})");
                return None
        elif expect_label:
            if re.fullmatch(r"[A-Z_0-9]+", operand_str_upper): return operand_str_upper
            self.errors.append(f"Invalid label format: '{operand_str_raw}'");
            return None
        return None

    def first_pass(self, sal_code_lines):
        global opcode_str_being_parsed_for_asm
        self.symbol_table = {};
        self.current_byte_offset = 0;
        self.sal_listing_data = []
        for idx, raw_ln in enumerate(sal_code_lines):
            proc_ln = self._preprocess_line(raw_ln);
            orig_ln = raw_ln.strip();
            addr_lst = self.current_byte_offset
            if not proc_ln: self.sal_listing_data.append((-1, orig_ln, proc_ln)); continue
            lbl_m = re.fullmatch(r"([A-Z_0-9]+):", proc_ln, re.IGNORECASE)
            if lbl_m:
                lbl_n = lbl_m.group(1).upper()
                if lbl_n in self.symbol_table:
                    self.errors.append(f"L{idx + 1}: Duplicate label '{lbl_n}'")
                elif lbl_n in SimpleAssembler.OPCODES_CLASS:
                    self.errors.append(f"L{idx + 1}: Label '{lbl_n}' conflicts.")
                else:
                    self.symbol_table[lbl_n] = self.current_byte_offset
                self.sal_listing_data.append((addr_lst, orig_ln, proc_ln))
            else:
                instr_m = re.match(r"^\s*([A-Z]+)\s*(?:([^,\s]+)\s*(?:[,]?\s*([^,\s]+))?)?\s*$", proc_ln, re.IGNORECASE)
                if instr_m:
                    op_s = instr_m.group(1).upper() if instr_m.group(1) else "";
                    opcode_str_being_parsed_for_asm = op_s
                    op1_s, op2_s = instr_m.group(2), instr_m.group(3)
                    if op_s not in SimpleAssembler.OPCODES_CLASS:
                        self.errors.append(f"L{idx + 1}: Unknown opcode '{op_s}'"); instr_len = 0
                    else:
                        instr_len = self._get_instruction_byte_length(op_s, op1_s, op2_s)
                    if instr_len == 0 and op_s in SimpleAssembler.OPCODES_CLASS: self.errors.append(
                        f"L{idx + 1}: Failed len for '{op_s}'.")
                    self.sal_listing_data.append((addr_lst, orig_ln, proc_ln))
                    if instr_len > 0: self.current_byte_offset += instr_len
                else:
                    self.errors.append(f"L{idx + 1}: Unrecognized SAL: '{proc_ln}'"); self.sal_listing_data.append(
                        (-1, orig_ln, proc_ln))
        return not self.errors

    def second_pass(self, sal_code_lines_ignored):  # Uses self.sal_listing_data
        global opcode_str_being_parsed_for_asm
        self.machine_code = []

        for addr_pass1, original_line, processed_line in self.sal_listing_data:
            if not processed_line or re.fullmatch(r"([A-Z_0-9]+):", processed_line, re.IGNORECASE):
                continue

            error_line_context = f"SAL (offset {addr_pass1:04X}h, original: \"{original_line}\")"
            match = re.match(r"^\s*([A-Z]+)\s*(?:([^,\s]+)\s*(?:[,]?\s*([^,\s]+))?)?\s*$", processed_line,
                             re.IGNORECASE)

            if not match:
                # This should ideally be caught by first_pass's syntax check
                if not processed_line.strip().startswith(
                        ";"):  # Don't error on lines that became empty after comment removal
                    self.errors.append(f"Error at {error_line_context}: Re-parse failed: '{processed_line}'")
                continue

            opcode_str = match.group(1).upper() if match.group(1) else ""
            opcode_str_being_parsed_for_asm = opcode_str  # For _parse_operand context
            op1_str = match.group(2) if match.group(2) else None  # Ensure None if not present
            op2_str = match.group(3) if match.group(3) else None  # Ensure None if not present

            if opcode_str not in SimpleAssembler.OPCODES_CLASS:
                # This should ideally be caught by first_pass
                self.errors.append(f"Error at {error_line_context}: Unknown opcode '{opcode_str}' during second pass")
                continue

            instr_bytes = [SimpleAssembler.OPCODES_CLASS[opcode_str]]

            # Operand handling logic
            if opcode_str == "LOAD":
                if not op1_str or not op2_str: self.errors.append(
                    f"{error_line_context}: Missing operands for LOAD"); continue
                reg = self._parse_operand(op1_str, expect_register=True)
                val16 = self._parse_operand(op2_str, expect_immediate_16bit=True)
                if reg is None or val16 is None: continue  # Error already logged by _parse_operand
                instr_bytes.extend([reg, val16 & 0xFF, (val16 >> 8) & 0xFF])

            elif opcode_str in ["SHL", "SHR"]:
                if not op1_str or not op2_str: self.errors.append(
                    f"{error_line_context}: Missing operands for {opcode_str}"); continue
                reg = self._parse_operand(op1_str, expect_register=True)
                val8 = self._parse_operand(op2_str, expect_immediate_8bit=True)
                if reg is None or val8 is None: continue
                instr_bytes.extend([reg, val8])

            elif opcode_str in ["STORE", "LOADM", "INM", "OUTM"]:
                if not op1_str or not op2_str: self.errors.append(
                    f"{error_line_context}: Missing operands for {opcode_str}"); continue
                reg = self._parse_operand(op1_str, expect_register=True)
                addr16 = self._parse_operand(op2_str, expect_address_16bit=True)
                if reg is None or addr16 is None: continue
                instr_bytes.extend([reg, addr16 & 0xFF, (addr16 >> 8) & 0xFF])

            elif opcode_str in ["ADD", "SUB", "MUL", "AND", "OR", "XOR", "CMP", "MOV"]:
                if not op1_str or not op2_str: self.errors.append(
                    f"{error_line_context}: Missing operands for {opcode_str}"); continue
                reg1 = self._parse_operand(op1_str, expect_register=True)
                reg2 = self._parse_operand(op2_str, expect_register=True)
                if reg1 is None or reg2 is None: continue
                instr_bytes.extend([reg1, reg2])
            elif opcode_str in ["NOT", "INP", "OUT", "PUSH", "POP", "INC", "DEC"]:
                if not op1_str: self.errors.append(f"{error_line_context}: Missing operand for {opcode_str}"); continue
                reg = self._parse_operand(op1_str, expect_register=True)
                if reg is None: continue
                instr_bytes.append(reg)

            elif opcode_str in ["JMP", "JE", "JNE", "JS", "JNS", "JC", "JNC", "JO", "JNO", "CALL"]:
                if not op1_str: self.errors.append(f"{error_line_context}: Missing label for {opcode_str}"); continue
                label_name = self._parse_operand(op1_str, expect_label=True)
                if label_name is None: continue
                if label_name not in self.symbol_table: self.errors.append(
                    f"{error_line_context}: Undefined label '{label_name}' in {opcode_str}"); continue
                target_addr16 = self.symbol_table[label_name]
                if not (0 <= target_addr16 <= SimpleAssembler.MAX_ADDRESS_16BIT_CLASS):
                    self.errors.append(
                        f"{error_line_context}: Label '{label_name}' addr {target_addr16} out of range.");
                    continue
                instr_bytes.extend([target_addr16 & 0xFF, (target_addr16 >> 8) & 0xFF])

            elif opcode_str in ["JMPZ", "JMPN"]:
                if not op1_str or not op2_str: self.errors.append(
                    f"{error_line_context}: Missing operands for {opcode_str}"); continue
                reg = self._parse_operand(op1_str, expect_register=True)
                label_name = self._parse_operand(op2_str, expect_label=True)
                if reg is None or label_name is None: continue
                if label_name not in self.symbol_table: self.errors.append(
                    f"{error_line_context}: Undefined label '{label_name}' in {opcode_str}"); continue
                target_addr16 = self.symbol_table[label_name]
                if not (0 <= target_addr16 <= SimpleAssembler.MAX_ADDRESS_16BIT_CLASS):
                    self.errors.append(
                        f"{error_line_context}: Label '{label_name}' addr {target_addr16} out of range.");
                    continue
                instr_bytes.extend([reg, target_addr16 & 0xFF, (target_addr16 >> 8) & 0xFF])

            elif opcode_str in ["RET", "NOP", "HALT"]:
                pass  # No operands, just opcode byte
            else:
                # This case should ideally not be reached if OPCODES_CLASS is comprehensive
                # and _get_instruction_byte_length handles all known opcodes.
                self.errors.append(f"Logic error: Unhandled known opcode '{opcode_str}' at {error_line_context}")

            self.machine_code.extend(instr_bytes)
        return True  # Second pass itself doesn't "fail" here; errors are aggregated.

    def _write_listing_file(self, listing_filename="program.asm"):
        try:
            with open(listing_filename, 'w') as f_list:
                f_list.write(f"; Assembly Listing for {os.path.basename(listing_filename).replace('.asm', '.bin')}\n")
                f_list.write(f"; Symbol Table (Label -> Byte Offset):\n")
                for label, addr in sorted(self.symbol_table.items()):
                    f_list.write(f";   {label:<20}: {addr:04X}h ({addr})\n")
                f_list.write(";\n; ByteOffs | Original SAL Line\n")
                f_list.write(";----------|----------------------------------\n")

                for addr_pass1, original_line, processed_line in self.sal_listing_data:
                    addr_str = "        "
                    line_to_print = original_line

                    if processed_line:
                        label_match_result = re.fullmatch(r"([A-Z_0-9]+):", processed_line, re.IGNORECASE)
                        if label_match_result:
                            label_name = label_match_result.group(1).upper()
                            addr_str = f"{self.symbol_table.get(label_name, -1):04X}h:    "
                            line_to_print = processed_line
                        elif addr_pass1 != -1:
                            addr_str = f"{addr_pass1:04X}h     "

                    f_list.write(f"{addr_str}| {line_to_print}\n")
            print(f"Assembly listing written to '{listing_filename}'")
        except IOError as e:
            print(f"Error writing listing file '{listing_filename}': {e}")

    def assemble_to_file(self, sal_code_string, output_binary_filename="program.bin",
                         output_listing_filename="program.asm"):
        sal_lines = sal_code_string.strip().split('\n')
        # Reset state for each new assembly job
        self.errors = [];
        self.machine_code = [];
        self.sal_listing_data = [];
        self.symbol_table = {}

        print("--- Assembler: Starting First Pass ---")
        if not self.first_pass(sal_lines):  # first_pass populates self.errors
            print("Assembly aborted due to errors in the first pass.")
            self._write_listing_file(output_listing_filename)  # Still try to write listing for debug
            return False
        print("--- Assembler: First Pass Complete ---");
        print("Symbol Table (Label -> Byte Offset):", self.symbol_table)

        self._write_listing_file(output_listing_filename)  # Write listing after successful pass 1

        print("\n--- Assembler: Starting Second Pass ---")
        self.second_pass(sal_code_lines_ignored=None)  # Pass None or self.sal_listing_data

        if self.errors:  # Check accumulated errors from both passes
            print("\nAssembly failed. Accumulated errors:")
            unique_errors = sorted(list(set(self.errors)))  # Show unique errors only once
            for err in unique_errors: print(f"  - {err}")
            return False

        try:
            with open(output_binary_filename, 'wb') as f_out:
                f_out.write(bytes(self.machine_code))
            print(f"\nMachine code successfully written to '{output_binary_filename}'")
            print(f"Generated machine code (hex): {' '.join(f'{b:02X}' for b in self.machine_code)}")
            return True
        except IOError as e:
            print(f"Error writing machine code to file: {e}"); return False


# Global variable (still a hack, but defined at module level now)
opcode_str_being_parsed_for_asm = ""

# Standalone test
if __name__ == "__main__":
    assembler = SimpleAssembler()
    test_sal_16bit_all_addr = """
    LOAD R0, #30000
    STORE R0, 0x0200  ; Store R0 to 16-bit data memory address 512 (0x0200)
    LOADM R1, 0x0200  ; Loadm R1 from 16-bit data memory address 512
    OUT R1           ; Should print 30000
    CALL SUBROUTINE ; Target address can be 16-bit
    OUT R0           ; R0 should be 30001 after sub
    JMP ENDING_LABEL
    SUBROUTINE:
    INC R0
    RET
    ENDING_LABEL:
    HALT
    """
    bin_f = "test_16bit_all_addr_corrected.bin"
    asm_f = "test_16bit_all_addr_corrected.asm"
    if assembler.assemble_to_file(test_sal_16bit_all_addr, bin_f, asm_f):
        print(f"Assembly of {bin_f} successful for 16-bit all addressing test.")
    else:
        print(f"Assembly of {bin_f} test failed.")