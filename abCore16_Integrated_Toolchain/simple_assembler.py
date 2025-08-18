# simple_assembler.py
# FINAL CORRECTED VERSION: The second pass is now capable of resolving
# labels as immediate values for instructions like LOAD.

import re
import os
from abcore16_defs import (
    OPCODES, REG_CODES, VALID_REGISTERS, INSTRUCTION_FORMATS,
    MAX_IMMEDIATE_16BIT, MAX_ADDRESS_16BIT, MAX_IMMEDIATE_8BIT,
    MIN_SIGNED_IMMEDIATE_16BIT, MAX_SIGNED_IMMEDIATE_16BIT
)


class SimpleAssembler:
    def __init__(self):
        self.symbol_table = {}
        self.machine_code = []
        self.current_byte_offset = 0
        self.errors = []
        self.sal_listing_data = []

    def _get_instruction_byte_length(self, opcode_str):
        opcode_str_upper = opcode_str.upper()
        if opcode_str_upper not in OPCODES: return 0
        if opcode_str_upper in INSTRUCTION_FORMATS:
            length, _ = INSTRUCTION_FORMATS[opcode_str_upper]
            return length
        self.errors.append(f"Internal Error: Opcode '{opcode_str_upper}' not in INSTRUCTION_FORMATS for length.")
        return 0

    def _preprocess_line(self, line_text_raw):
        line_text = line_text_raw.split('//', 1)[0]
        line_text = line_text.split(';', 1)[0]
        return line_text.strip()

    def _parse_operand(self, operand_str_raw, current_opcode_str,
                       expect_register=False,
                       expect_immediate_8bit=False, expect_immediate_16bit=False,
                       expect_address_16bit=False, expect_label=False,
                       expect_signed_immediate_16bit=False):
        operand_str_for_parsing = operand_str_raw.strip()
        operand_str_upper = operand_str_for_parsing.upper()
        is_hash_prefixed = operand_str_for_parsing.startswith('#')
        num_cand_str = operand_str_for_parsing

        if expect_register:
            if is_hash_prefixed:
                self.errors.append(
                    f"Register operand '{operand_str_raw}' for {current_opcode_str} should not start with '#'.")
                return None
            if operand_str_upper in REG_CODES:
                return REG_CODES[operand_str_upper]
            self.errors.append(f"Invalid register: '{operand_str_raw}'. Valid: {sorted(list(VALID_REGISTERS))}")
            return None

        if expect_label:
            if is_hash_prefixed:
                self.errors.append(
                    f"Label operand '{operand_str_raw}' for {current_opcode_str} should not start with '#'.")
                return None
            if re.fullmatch(r"[A-Z_0-9]+", operand_str_upper, re.IGNORECASE):
                return operand_str_upper
            self.errors.append(f"Invalid label format: '{operand_str_raw}' for {current_opcode_str}")
            return None

        type_err_str = "operand";
        min_val, max_val = 0, 0
        if expect_signed_immediate_16bit:
            type_err_str = "16-bit signed immediate offset";
            min_val, max_val = MIN_SIGNED_IMMEDIATE_16BIT, MAX_SIGNED_IMMEDIATE_16BIT
            if not is_hash_prefixed: self.errors.append(
                f"{type_err_str.capitalize()} '{operand_str_raw}' for {current_opcode_str} MUST start with '#'."); return None
            num_cand_str = operand_str_for_parsing[1:]
        elif expect_immediate_16bit:
            type_err_str = "16-bit unsigned immediate";
            min_val, max_val = 0, MAX_IMMEDIATE_16BIT
            if not is_hash_prefixed: self.errors.append(
                f"{type_err_str.capitalize()} '{operand_str_raw}' for {current_opcode_str} MUST start with '#'."); return None
            num_cand_str = operand_str_for_parsing[1:]
        elif expect_immediate_8bit:
            type_err_str = "8-bit unsigned immediate";
            min_val, max_val = 0, MAX_IMMEDIATE_8BIT
            if not is_hash_prefixed: self.errors.append(
                f"{type_err_str.capitalize()} '{operand_str_raw}' for {current_opcode_str} MUST start with '#'."); return None
            num_cand_str = operand_str_for_parsing[1:]
        elif expect_address_16bit:
            type_err_str = "16-bit address value";
            min_val, max_val = 0, MAX_ADDRESS_16BIT
            if is_hash_prefixed: self.errors.append(
                f"{type_err_str.capitalize()} '{operand_str_raw}' for {current_opcode_str} should NOT start with '#'."); return None
        else:
            self.errors.append(
                f"Internal parse error: No specific numeric expectation for '{operand_str_raw}'.");
            return None

        base_parse = 10;
        num_str_to_parse = num_cand_str
        if num_cand_str.upper().startswith("0X"):
            base_parse = 16;
            num_str_to_parse = num_cand_str[2:]
        elif num_cand_str.upper().startswith("-0X"):
            if expect_signed_immediate_16bit: self.errors.append(
                f"Negative hex for {type_err_str} ('{operand_str_raw}') not supported; use decimal."); return None
            base_parse = 16
        try:
            val_parsed = int(num_str_to_parse, base_parse)
            if not (min_val <= val_parsed <= max_val):
                self.errors.append(
                    f"{type_err_str.capitalize()} '{val_parsed}' (from '{operand_str_raw}') out of range ({min_val} to {max_val}).");
                return None
            return val_parsed
        except ValueError:
            self.errors.append(f"Invalid numeric format for {type_err_str}: '{operand_str_raw}'.");
            return None

    def first_pass(self, sal_code_lines):
        self.symbol_table = {};
        self.current_byte_offset = 0;
        self.errors = [];
        self.sal_listing_data = []
        for idx, raw_ln in enumerate(sal_code_lines):
            proc_ln = self._preprocess_line(raw_ln);
            orig_ln = raw_ln.strip();
            addr_lst = self.current_byte_offset
            if not proc_ln: self.sal_listing_data.append((-1, orig_ln, proc_ln)); continue
            lbl_m = re.fullmatch(r"([a-zA-Z_][a-zA-Z_0-9]*):", proc_ln, re.IGNORECASE)
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
                    r"^\s*([a-zA-Z_]+)\s*(?:([^,\s]+)\s*(?:[,]?\s*([^,\s]+))?\s*(?:[,]?\s*([^,\s]+))?)?\s*$", proc_ln,
                    re.IGNORECASE)
                if instr_m:
                    op_s = instr_m.group(1).upper()
                    if op_s not in OPCODES:
                        self.errors.append(f"L{idx + 1}: Unknown opcode '{op_s}'");
                        instr_len = 0
                    else:
                        instr_len = self._get_instruction_byte_length(op_s)
                    if instr_len == 0 and op_s in OPCODES: self.errors.append(
                        f"L{idx + 1}: Failed to get length for '{op_s}'.")
                    self.sal_listing_data.append((addr_lst, orig_ln, proc_ln))
                    if instr_len > 0: self.current_byte_offset += instr_len
                else:
                    self.errors.append(f"L{idx + 1}: Unrecognized syntax: '{proc_ln}'");
                    self.sal_listing_data.append(
                        (-1, orig_ln, proc_ln))
        return not self.errors

    # --- MODIFIED FOR INTERRUPT SUPPORT: This method is now smarter about labels ---
    def second_pass(self, sal_code_lines_ignored=None):
        self.machine_code = []
        for addr_pass1, original_line, processed_line in self.sal_listing_data:
            if addr_pass1 == -1 or not processed_line or re.fullmatch(r"([a-zA-Z_0-9]+):", processed_line,
                                                                      re.IGNORECASE): continue
            error_context_msg = f"SAL (offset ~{addr_pass1:04X}h, \"{original_line}\")"
            instr_match = re.match(r"^\s*([a-zA-Z_]+)\s*(?:([^,\s]+)\s*(?:,\s*([^,\s]+)\s*(?:,\s*([^,\s]+))?)?)?\s*$",
                                   processed_line, re.IGNORECASE)
            if not instr_match: continue
            opcode_str = instr_match.group(1).upper()
            raw_ops = [s for s in instr_match.groups()[1:] if s is not None]
            if opcode_str not in OPCODES: continue

            current_instr_bytes = [OPCODES[opcode_str]]
            _, operand_sig_types = INSTRUCTION_FORMATS.get(opcode_str, (0, []))
            if len(raw_ops) != len(operand_sig_types): self.errors.append(
                f"{error_context_msg}: Operand count mismatch for {opcode_str}."); continue

            parsed_vals = [];
            line_err = False
            for i, op_type_exp in enumerate(operand_sig_types):
                raw_op_str = raw_ops[i];
                val = None

                # Check if the operand is a label that needs to be resolved.
                op_body = raw_op_str.lstrip('#')
                is_potential_label = False
                try:
                    int(op_body, 16 if op_body.upper().startswith('0X') else 10)
                except ValueError:
                    is_potential_label = True

                if op_type_exp == 'R':
                    val = self._parse_operand(raw_op_str, opcode_str, expect_register=True)

                elif op_type_exp in ['I16', 'S16', 'I8'] and is_potential_label:
                    if not raw_op_str.startswith('#'):
                        self.errors.append(
                            f"{error_context_msg}: Immediate value '{raw_op_str}' for {opcode_str} must start with '#'.")
                        line_err = True;
                        break

                    label_name = op_body.upper()
                    if label_name in self.symbol_table:
                        val = self.symbol_table[label_name]
                    else:
                        self.errors.append(f"{error_context_msg}: Undefined label '{label_name}' used as immediate.")
                        line_err = True;
                        break

                elif op_type_exp == 'A16' and is_potential_label:
                    is_jmp_call = opcode_str.startswith("J") or opcode_str == "CALL"
                    if is_jmp_call:
                        val = self.symbol_table.get(raw_op_str.upper())
                        if val is None:
                            self.errors.append(f"{error_context_msg}: Undefined label '{raw_op_str}' for jump/call.")
                            line_err = True;
                            break
                    else:
                        val = self._parse_operand(raw_op_str, opcode_str, expect_address_16bit=True)

                else:  # It's a numeric literal, not a label.
                    if op_type_exp == 'I16':
                        val = self._parse_operand(raw_op_str, opcode_str, expect_immediate_16bit=True)
                    elif op_type_exp == 'S16':
                        val = self._parse_operand(raw_op_str, opcode_str, expect_signed_immediate_16bit=True)
                    elif op_type_exp == 'I8':
                        val = self._parse_operand(raw_op_str, opcode_str, expect_immediate_8bit=True)
                    elif op_type_exp == 'A16':
                        val = self._parse_operand(raw_op_str, opcode_str, expect_address_16bit=True)

                if val is None: line_err = True; break
                parsed_vals.append(val)
            if line_err: continue

            for i, op_type_enc in enumerate(operand_sig_types):
                val_enc = parsed_vals[i]
                if op_type_enc == 'R' or op_type_enc == 'I8':
                    current_instr_bytes.append(val_enc & 0xFF)
                elif op_type_enc in ['I16', 'A16', 'S16']:
                    current_instr_bytes.extend([val_enc & 0xFF, (val_enc >> 8) & 0xFF])
            self.machine_code.extend(current_instr_bytes)
        return not self.errors

    def _write_listing_file(self, listing_filename="program.asm"):
        try:
            with open(listing_filename, 'w') as f_list:
                f_list.write(f"// Assembly Listing for {os.path.basename(listing_filename).replace('.asm', '.bin')}\n")
                f_list.write(f"// Symbol Table (Label -> Byte Offset):\n")
                if self.symbol_table:
                    for label, addr in sorted(self.symbol_table.items()): f_list.write(
                        f"//   {label:<20}: {addr:04X}h ({addr})\n")
                else:
                    f_list.write(f"//   (No symbols defined)\n")
                f_list.write("//\n// ByteOffs HexBytes   | Original SAL Line\n")
                f_list.write("//---------- ------------|----------------------------------\n")
                mc_ptr = 0
                for addr_p1, orig_ln, proc_ln in self.sal_listing_data:
                    addr_s = "        ";
                    mc_bytes_s = "            "
                    if addr_p1 != -1:
                        addr_s = f"{addr_p1:04X}h"
                        if proc_ln.endswith(":"):
                            addr_s += ":  "
                        else:
                            addr_s += "    "
                            op_match = re.match(r"^\s*([a-zA-Z_]+)", proc_ln)
                            if op_match:
                                op_for_len = op_match.group(1).upper()
                                if op_for_len in OPCODES:
                                    instr_len = self._get_instruction_byte_length(op_for_len)
                                    if mc_ptr + instr_len <= len(
                                            self.machine_code):
                                        mc_slice = self.machine_code[mc_ptr: mc_ptr + instr_len]
                                        mc_bytes_s = " ".join([f"{b:02X}" for b in mc_slice]).ljust(12)
                                        mc_ptr += instr_len
                    f_list.write(f"{addr_s} {mc_bytes_s}| {orig_ln}\n")
            print(f"Assembler: Assembly listing written to '{listing_filename}'")
        except IOError as e:
            self.errors.append(f"Error writing listing file '{listing_filename}': {e}");
            print(
                f"Assembler: Error writing listing file: {e}")

    def assemble_to_file(self, sal_code_string, output_binary_filename="program.bin",
                         output_listing_filename="program.asm"):
        sal_lines = sal_code_string.strip().split('\n');
        self.errors = [];
        self.machine_code = [];
        self.sal_listing_data = [];
        self.symbol_table = {}
        print("--- Assembler: Starting First Pass ---")
        if not self.first_pass(sal_lines):
            print("Assembler: First pass completed with errors.")
            self._write_listing_file(output_listing_filename)
            if self.errors: print("\nAssembler: Assembly aborted. Errors:"); [print(f"  - {e}") for e in
                                                                              sorted(list(set(self.errors)))]
            return False
        print("--- Assembler: First Pass Complete ---")
        self._write_listing_file(output_listing_filename)
        print("\n--- Assembler: Starting Second Pass ---")
        self.second_pass()
        if self.errors:
            print("\nAssembler: Assembly failed. Errors:");
            [print(f"  - {e}") for e in sorted(list(set(self.errors)))]
            self._write_listing_file(output_listing_filename)
            return False
        try:
            with open(output_binary_filename, 'wb') as f_out:
                f_out.write(bytes(self.machine_code))
            print(
                f"\nAssembler: Machine code successfully written to '{output_binary_filename}' ({len(self.machine_code)} bytes)")
            self._write_listing_file(output_listing_filename)
            return True
        except IOError as e:
            self.errors.append(f"Error writing binary: {e}");
            print(
                f"Assembler: Error writing binary: {e}");
            return False


if __name__ == "__main__":
    assembler = SimpleAssembler()
    test_sal_sp_ops = """
    // Test new SP-related MOV instructions
    LOAD R0, #1234
    MOVTOSP R0   // SP = R0 (1234)
    MOVFRSP R1   // R1 = SP (should be 1234)
    OUT R1       // Expected: 1234
    HALT
    """
    bin_f = "test_sp_mov.bin";
    asm_f = "test_sp_mov.asm"
    print(f"--- Assembling SAL with MOVFRSP/MOVTOSP: {bin_f} ---")
    if assembler.assemble_to_file(test_sal_sp_ops, bin_f, asm_f):
        print(f"Assembly of {bin_f} successful.")
    else:
        print(f"Assembly of {bin_f} FAILED.")
        if assembler.errors: [print(f"  - {e}") for e in assembler.errors]

    test_sal_new_ops = """
    START:
        LOAD R5, #0x0100  ; R5 = Frame Pointer (base)
        LOAD R0, #77
        STORFR R0, R5, #2   ; Mem[0x0100 + 2] = R0 (77)
        LOADFR R1, R5, #2   ; R1 = Mem[0x0100 + 2]
        OUT R1              ; Expected: 77

        STORFR R0, R5, #-4  ; Mem[0x0100 - 4] = R0 (77) -> Addr 0x00FC
        LOADFR R2, R5, #-4
        OUT R2              ; Expected: 77
        HALT
    """
    bin_f2 = "test_isa_ext_asm.bin";
    asm_f2 = "test_isa_ext_asm.asm"
    print(f"\n--- Assembling SAL with LOADFR/STORFR: {bin_f2} ---")
    if assembler.assemble_to_file(test_sal_new_ops, bin_f2, asm_f2):
        print(f"Assembly of {bin_f2} successful.")
    else:
        print(f"Assembly of {bin_f2} FAILED.")
        if assembler.errors: [print(f"  - {e}") for e in assembler.errors]
