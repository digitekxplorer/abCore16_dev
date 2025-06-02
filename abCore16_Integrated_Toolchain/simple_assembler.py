# simple_assembler.py
import re
import os
# Import from the new definitions file
from abcore16_defs import (
    OPCODES, REG_CODES, VALID_REGISTERS, INSTRUCTION_FORMATS,
    MAX_IMMEDIATE_16BIT, MAX_ADDRESS_16BIT, MAX_IMMEDIATE_8BIT
)


class SimpleAssembler:
    def __init__(self):
        self.symbol_table = {}
        self.machine_code = []
        self.current_byte_offset = 0
        self.errors = []
        self.sal_listing_data = []

    def _get_instruction_byte_length(self, opcode_str):
        if opcode_str not in OPCODES: return 0
        if opcode_str in INSTRUCTION_FORMATS:
            length, _ = INSTRUCTION_FORMATS[opcode_str]
            return length
        self.errors.append(f"Internal Error: Opcode '{opcode_str}' not in INSTRUCTION_FORMATS for length.")
        return 0

    def _preprocess_line(self, line_text_raw):
        # Handles both // and ; style comments for SAL input
        line_text = line_text_raw.split('//', 1)[0]
        line_text = line_text.split(';', 1)[0]
        return line_text.strip()

    # Refactored _parse_operand to strictly enforce '#' for immediates
    def _parse_operand(self, operand_str_raw, current_opcode_str,  # current_opcode_str still useful for error messages
                       expect_register=False,
                       expect_immediate_8bit=False, expect_immediate_16bit=False,
                       expect_address_16bit=False, expect_label=False):

        operand_str_for_parsing = operand_str_raw.strip()
        operand_str_upper = operand_str_for_parsing.upper()
        max_val = 0
        is_hash_prefixed = operand_str_for_parsing.startswith('#')

        num_cand_str = operand_str_for_parsing
        base_parse = 10

        if expect_register:
            if is_hash_prefixed:  # Registers should not have #
                self.errors.append(
                    f"Register operand '{operand_str_raw}' for {current_opcode_str} should not start with '#'.")
                return None
            if operand_str_upper in REG_CODES:
                return REG_CODES[operand_str_upper]
            self.errors.append(f"Invalid register: '{operand_str_raw}'. Valid: {sorted(list(VALID_REGISTERS))}")
            return None

        is_numeric_expected = expect_immediate_8bit or expect_immediate_16bit or expect_address_16bit
        type_err_str = "operand"

        if expect_immediate_8bit or expect_immediate_16bit:
            type_err_str = "immediate value"
            if not is_hash_prefixed:
                self.errors.append(
                    f"Immediate operand '{operand_str_raw}' for {current_opcode_str} MUST start with '#'.")
                return None
            num_cand_str = operand_str_for_parsing[1:]  # Remove '#' for parsing
            if expect_immediate_8bit:
                max_val = MAX_IMMEDIATE_8BIT
            else:
                max_val = MAX_IMMEDIATE_16BIT

        elif expect_address_16bit:
            type_err_str = "address value"
            if is_hash_prefixed:  # Addresses should NOT have #
                self.errors.append(
                    f"Address operand '{operand_str_raw}' for {current_opcode_str} should NOT start with '#'.")
                return None
            max_val = MAX_ADDRESS_16BIT
            # num_cand_str is already operand_str_for_parsing

        elif expect_label:
            if is_hash_prefixed:  # Labels should not have #
                self.errors.append(
                    f"Label operand '{operand_str_raw}' for {current_opcode_str} should not start with '#'.")
                return None
            if re.fullmatch(r"[A-Z_0-9]+", operand_str_upper, re.IGNORECASE):
                return operand_str_upper  # Return label name as string
            self.errors.append(f"Invalid label format: '{operand_str_raw}' for {current_opcode_str}")
            return None

        # Common parsing logic for numbers (immediates and addresses)
        if is_numeric_expected:
            # Determine base for parsing (hex or decimal)
            # num_cand_str already has '#' removed if it was an immediate
            if num_cand_str.upper().startswith("0X"):
                base_parse = 16
                num_cand_str_for_int = num_cand_str[2:]
            else:
                base_parse = 10
                num_cand_str_for_int = num_cand_str

            try:
                val_parsed = int(num_cand_str_for_int, base_parse)
                if not (0 <= val_parsed <= max_val):
                    self.errors.append(
                        f"{type_err_str.capitalize()} '{val_parsed}' (from '{operand_str_raw}') out of range (0-{max_val}) for {current_opcode_str}.")
                    return None
                return val_parsed
            except ValueError:
                self.errors.append(
                    f"Invalid numeric format for {type_err_str}: '{operand_str_raw}' (tried parsing '{num_cand_str_for_int}' as base {base_parse}) for {current_opcode_str}.")
                return None

        # Fallback if no expectation matched (should not happen if called correctly)
        self.errors.append(
            f"Internal parse error: Could not classify operand '{operand_str_raw}' for opcode {current_opcode_str}")
        return None

    def first_pass(self, sal_code_lines):
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
                elif lbl_n in OPCODES:
                    self.errors.append(f"L{idx + 1}: Label '{lbl_n}' conflicts with opcode.")
                else:
                    self.symbol_table[lbl_n] = self.current_byte_offset
                self.sal_listing_data.append((addr_lst, orig_ln, proc_ln))
            else:
                instr_m = re.match(
                    r"^\s*([A-Z_]+)\s*(?:([^,\s]+)\s*(?:[,]?\s*([^,\s]+))?\s*(?:[,]?\s*([^,\s]+))?)?\s*$", proc_ln,
                    re.IGNORECASE)
                if instr_m:
                    op_s = instr_m.group(1).upper() if instr_m.group(1) else ""
                    if op_s not in OPCODES:
                        self.errors.append(f"L{idx + 1}: Unknown opcode '{op_s}' in SAL: '{proc_ln}'");
                        instr_len = 0
                    else:
                        instr_len = self._get_instruction_byte_length(op_s)
                    if instr_len == 0 and op_s in OPCODES:
                        self.errors.append(
                            f"L{idx + 1}: Failed to get length for known opcode '{op_s}'. Check INSTRUCTION_FORMATS.")
                    self.sal_listing_data.append((addr_lst, orig_ln, proc_ln))
                    if instr_len > 0: self.current_byte_offset += instr_len
                else:
                    self.errors.append(f"L{idx + 1}: Unrecognized SAL syntax: '{proc_ln}'");
                    self.sal_listing_data.append((-1, orig_ln, proc_ln))
        return not self.errors

    def second_pass(self, sal_code_lines_ignored):
        self.machine_code = []
        for addr_pass1, original_line, processed_line in self.sal_listing_data:
            if not processed_line or re.fullmatch(r"([A-Z_0-9]+):", processed_line, re.IGNORECASE):
                continue

            error_line_context = f"SAL (offset {addr_pass1:04X}h, original: \"{original_line}\")"
            match = re.match(r"^\s*([A-Z_]+)\s*(?:([^,\s]+)\s*(?:[,]?\s*([^,\s]+))?\s*(?:[,]?\s*([^,\s]+))?)?\s*$",
                             processed_line, re.IGNORECASE)

            if not match:
                if not processed_line.strip().startswith((";", "//")):  # Ensure it's not just a comment line
                    self.errors.append(
                        f"Error at {error_line_context}: Second pass re-parse failed for: '{processed_line}'")
                continue

            opcode_str = match.group(1).upper() if match.group(1) else ""
            op1_str, op2_str, op3_str = match.group(2), match.group(3), match.group(4)

            if opcode_str not in OPCODES:  # Should have been caught in pass 1
                self.errors.append(f"Error at {error_line_context}: Unknown opcode '{opcode_str}' during second pass");
                continue

            instr_bytes = [OPCODES[opcode_str]]
            _, operand_sig_types = INSTRUCTION_FORMATS.get(opcode_str, (0, []))
            raw_operand_strs = [s for s in [op1_str, op2_str, op3_str] if s is not None]

            if len(raw_operand_strs) != len(operand_sig_types):
                self.errors.append(
                    f"{error_line_context}: Mismatch between expected ({len(operand_sig_types)}) and found ({len(raw_operand_strs)}) operands for {opcode_str}");
                continue

            parsed_operands_values = []
            parse_error_occurred = False
            for i, op_type_expected in enumerate(operand_sig_types):
                current_op_raw_str = raw_operand_strs[i]
                parsed_value = None

                if op_type_expected == 'R':
                    parsed_value = self._parse_operand(current_op_raw_str, opcode_str, expect_register=True)
                elif op_type_expected == 'I16':
                    parsed_value = self._parse_operand(current_op_raw_str, opcode_str, expect_immediate_16bit=True)
                elif op_type_expected == 'I8':
                    parsed_value = self._parse_operand(current_op_raw_str, opcode_str, expect_immediate_8bit=True)
                elif op_type_expected == 'A16':
                    is_jump_or_call = opcode_str.startswith("J") or opcode_str == "CALL"
                    if is_jump_or_call and not (
                            current_op_raw_str.startswith("#") or current_op_raw_str.upper().startswith(
                            "0X") or current_op_raw_str.isdigit()):
                        # For jumps/calls, if it doesn't look like a number, assume it's a label
                        label_name = self._parse_operand(current_op_raw_str, opcode_str, expect_label=True)
                        if label_name is not None:
                            if label_name not in self.symbol_table:
                                self.errors.append(
                                    f"{error_line_context}: Undefined label '{label_name}' for {opcode_str}");
                                parse_error_occurred = True;
                                break
                            parsed_value = self.symbol_table[label_name]
                        else:  # _parse_operand already logged an error for invalid label format
                            parse_error_occurred = True;
                            break
                    else:  # For other A16 (like STORE) or if it looks numeric for jumps
                        parsed_value = self._parse_operand(current_op_raw_str, opcode_str, expect_address_16bit=True)

                if parsed_value is None:
                    parse_error_occurred = True;
                    break
                parsed_operands_values.append(parsed_value)

            if parse_error_occurred: continue

            for i, op_type_encoded in enumerate(operand_sig_types):
                value_to_encode = parsed_operands_values[i]
                if op_type_encoded == 'R' or op_type_encoded == 'I8':
                    instr_bytes.append(value_to_encode & 0xFF)
                elif op_type_encoded == 'I16' or op_type_encoded == 'A16':
                    instr_bytes.extend([value_to_encode & 0xFF, (value_to_encode >> 8) & 0xFF])

            self.machine_code.extend(instr_bytes)
        return True

    def _write_listing_file(self, listing_filename="program.asm"):
        try:
            with open(listing_filename, 'w') as f_list:
                f_list.write(f"// Assembly Listing for {os.path.basename(listing_filename).replace('.asm', '.bin')}\n")
                f_list.write(f"// Symbol Table (Label -> Byte Offset):\n")
                for label, addr in sorted(self.symbol_table.items()):
                    f_list.write(f"//   {label:<20}: {addr:04X}h ({addr})\n")
                f_list.write("//\n// ByteOffs | Original SAL Line\n")
                f_list.write("//----------|----------------------------------\n")
                for addr_pass1, original_line, processed_line in self.sal_listing_data:
                    addr_str = "        "
                    line_to_print = original_line
                    if processed_line:
                        label_match_result = re.fullmatch(r"([A-Z_0-9]+):", processed_line, re.IGNORECASE)
                        if label_match_result:
                            label_name = label_match_result.group(1).upper()
                            addr_str = f"{self.symbol_table.get(label_name, addr_pass1):04X}h:    "
                            line_to_print = processed_line
                        elif addr_pass1 != -1:
                            addr_str = f"{addr_pass1:04X}h     "
                    f_list.write(f"{addr_str}| {line_to_print}\n")
            print(f"Assembler: Assembly listing written to '{listing_filename}'")
        except IOError as e:
            print(f"Assembler: Error writing listing file '{listing_filename}': {e}")

    def assemble_to_file(self, sal_code_string, output_binary_filename="program.bin",
                         output_listing_filename="program.asm"):
        sal_lines = sal_code_string.strip().split('\n')
        self.errors = [];
        self.machine_code = [];
        self.sal_listing_data = [];
        self.symbol_table = {}
        print("--- Assembler: Starting First Pass ---")
        if not self.first_pass(sal_lines):
            print("Assembler: Assembly aborted due to errors in the first pass.")
            self._write_listing_file(output_listing_filename);
            return False
        print("--- Assembler: First Pass Complete ---");
        self._write_listing_file(output_listing_filename)
        print("\n--- Assembler: Starting Second Pass ---")
        self.second_pass(sal_code_lines_ignored=None)
        if self.errors:
            print("\nAssembler: Assembly failed. Accumulated errors:")
            unique_errors = sorted(list(set(self.errors)))
            for err in unique_errors: print(f"  - {err}")
            return False
        try:
            with open(output_binary_filename, 'wb') as f_out:
                f_out.write(bytes(self.machine_code))
            print(f"\nAssembler: Machine code successfully written to '{output_binary_filename}'")
            return True
        except IOError as e:
            print(f"Assembler: Error writing machine code to file: {e}"); return False


# Standalone test
if __name__ == "__main__":
    assembler = SimpleAssembler()
    # Test case that SHOULD work
    test_sal_correct_hash = """
    LOAD R0 #100      ; Immediate requires #
    STORE R0 0x0200   ; Address does not use #
    SHL R1 #5         ; Shift immediate requires #
    HALT
    """
    bin_f_ok = "test_hash_ok.bin";
    asm_f_ok = "test_hash_ok.asm"
    print(f"--- Assembling SAL with correct '#' usage: {bin_f_ok} ---")
    if assembler.assemble_to_file(test_sal_correct_hash, bin_f_ok, asm_f_ok):
        print(f"Assembly of {bin_f_ok} successful.")
    else:
        print(f"Assembly of {bin_f_ok} FAILED (should have succeeded).")

    # Test case that should FAIL due to missing # for LOAD's immediate
    test_sal_fail_immediate = "LOAD R1 50 ; Missing # for immediate"
    bin_f_fail1 = "temp_fail_imm.bin";
    asm_f_fail1 = "temp_fail_imm.asm"
    print(f"\n--- Assembling SAL that should fail (missing # for LOAD): {bin_f_fail1} ---")
    if not assembler.assemble_to_file(test_sal_fail_immediate, bin_f_fail1, asm_f_fail1):
        print("Assembly correctly failed as expected for missing # on immediate.")
    else:
        print(f"Assembly of {bin_f_fail1} INCORRECTLY succeeded.")

    # Test case that should FAIL due to having # for STORE's address
    test_sal_fail_address = "STORE R2 #0x0300 ; Address should not have #"
    bin_f_fail2 = "temp_fail_addr.bin";
    asm_f_fail2 = "temp_fail_addr.asm"
    print(f"\n--- Assembling SAL that should fail (has # for address): {bin_f_fail2} ---")
    if not assembler.assemble_to_file(test_sal_fail_address, bin_f_fail2, asm_f_fail2):
        print("Assembly correctly failed as expected for # on address.")
    else:
        print(f"Assembly of {bin_f_fail2} INCORRECTLY succeeded.")
