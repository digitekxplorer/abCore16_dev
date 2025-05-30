# simple_compiler.py
import re


class SimpleCompilerLLM:
    def __init__(self):
        # SSL Regex, SAL Template, [Operand Types: R=Reg, V16=16b Val, V8=8b Val, A16=16b Addr, L=Label, N=None for no ops]
        # Regex for registers changed from (R[0-5]) to (R[0-7])
        self.compilation_rules = [
            (re.compile(r"SET\s+(R[0-7])\s+(0x[0-9A-Fa-f]+|\d+)", re.IGNORECASE), "LOAD {0}, #{1}", ['R', 'V16']),
            (re.compile(r"MOV\s+(R[0-7])\s+(R[0-7])", re.IGNORECASE), "MOV {0}, {1}", ['R', 'R']),
            (re.compile(r"STORE\s+(R[0-7])\s+(0x[0-9A-Fa-f]+|\d+)", re.IGNORECASE), "STORE {0}, {1}", ['R', 'A16']),
            (re.compile(r"FETCH\s+(R[0-7])\s+(0x[0-9A-Fa-f]+|\d+)", re.IGNORECASE), "LOADM {0}, {1}", ['R', 'A16']),
            (re.compile(r"ADD\s+(R[0-7])\s+(R[0-7])", re.IGNORECASE), "ADD {0}, {1}", ['R', 'R']),
            (re.compile(r"SUB\s+(R[0-7])\s+(R[0-7])", re.IGNORECASE), "SUB {0}, {1}", ['R', 'R']),
            (re.compile(r"MUL\s+(R[0-7])\s+(R[0-7])", re.IGNORECASE), "MUL {0}, {1}", ['R', 'R']),
            (re.compile(r"INC\s+(R[0-7])", re.IGNORECASE), "INC {0}", ['R']),
            (re.compile(r"DEC\s+(R[0-7])", re.IGNORECASE), "DEC {0}", ['R']),
            (re.compile(r"AND\s+(R[0-7])\s+(R[0-7])", re.IGNORECASE), "AND {0}, {1}", ['R', 'R']),
            (re.compile(r"OR\s+(R[0-7])\s+(R[0-7])", re.IGNORECASE), "OR {0}, {1}", ['R', 'R']),
            (re.compile(r"XOR\s+(R[0-7])\s+(R[0-7])", re.IGNORECASE), "XOR {0}, {1}", ['R', 'R']),
            (re.compile(r"NOT\s+(R[0-7])", re.IGNORECASE), "NOT {0}", ['R']),
            (re.compile(r"SHL\s+(R[0-7])\s+(0x[0-9A-Fa-f]+|\d+)", re.IGNORECASE), "SHL {0}, #{1}", ['R', 'V8']),
            (re.compile(r"SHR\s+(R[0-7])\s+(0x[0-9A-Fa-f]+|\d+)", re.IGNORECASE), "SHR {0}, #{1}", ['R', 'V8']),
            (re.compile(r"INP\s+(R[0-7])", re.IGNORECASE), "INP {0}", ['R']),
            (re.compile(r"PRINT\s+(R[0-7])", re.IGNORECASE), "OUT {0}", ['R']),
            (re.compile(r"INM\s+(R[0-7])\s+(0x[0-9A-Fa-f]+|\d+)", re.IGNORECASE), "INM {0}, {1}", ['R', 'A16']),
            (re.compile(r"OUTM\s+(R[0-7])\s+(0x[0-9A-Fa-f]+|\d+)", re.IGNORECASE), "OUTM {0}, {1}", ['R', 'A16']),
            (re.compile(r"CMP\s+(R[0-7])\s+(R[0-7])", re.IGNORECASE), "CMP {0}, {1}", ['R', 'R']),
            (re.compile(r"JMP\s+([A-Z_0-9]+)", re.IGNORECASE), "JMP {0}", ['L']),
            (re.compile(r"JMPZ\s+(R[0-7])\s+([A-Z_0-9]+)", re.IGNORECASE), "JMPZ {0}, {1}", ['R', 'L']),
            (re.compile(r"JMPN\s+(R[0-7])\s+([A-Z_0-9]+)", re.IGNORECASE), "JMPN {0}, {1}", ['R', 'L']),
            (re.compile(r"JE\s+([A-Z_0-9]+)", re.IGNORECASE), "JE {0}", ['L']),
            (re.compile(r"JNE\s+([A-Z_0-9]+)", re.IGNORECASE), "JNE {0}", ['L']),
            (re.compile(r"JS\s+([A-Z_0-9]+)", re.IGNORECASE), "JS {0}", ['L']),
            (re.compile(r"JNS\s+([A-Z_0-9]+)", re.IGNORECASE), "JNS {0}", ['L']),
            (re.compile(r"JC\s+([A-Z_0-9]+)", re.IGNORECASE), "JC {0}", ['L']),
            (re.compile(r"JNC\s+([A-Z_0-9]+)", re.IGNORECASE), "JNC {0}", ['L']),
            (re.compile(r"JO\s+([A-Z_0-9]+)", re.IGNORECASE), "JO {0}", ['L']),
            (re.compile(r"JNO\s+([A-Z_0-9]+)", re.IGNORECASE), "JNO {0}", ['L']),
            (re.compile(r"PUSH\s+(R[0-7])", re.IGNORECASE), "PUSH {0}", ['R']),
            (re.compile(r"POP\s+(R[0-7])", re.IGNORECASE), "POP {0}", ['R']),
            (re.compile(r"CALL\s+([A-Z_0-9]+)", re.IGNORECASE), "CALL {0}", ['L']),
            (re.compile(r"RET", re.IGNORECASE), "RET", ['N']),
            (re.compile(r"NOP", re.IGNORECASE), "NOP", ['N']),
            (re.compile(r"HALT", re.IGNORECASE), "HALT", ['N']),
            (re.compile(r"([A-Z_0-9]+):", re.IGNORECASE), "{0}:", ['L_DEF']),
        ]
        self.valid_registers = {'R0', 'R1', 'R2', 'R3', 'R4', 'R5', 'R6', 'R7'}  # Updated
        self.max_immediate_16bit = 65535
        self.max_immediate_8bit = 255
        self.max_address_16bit = 65535

    def _preprocess_line(self, line_text):  # No change
        line_text = line_text.split('//', 1)[0]
        return line_text.strip()

    def compile_line(self, ssl_line_processed):  # Validation uses self.valid_registers, so it adapts
        # ... (The rest of this method remains the same as the previous version)
        # The existing logic for validating 'R' type operands against self.valid_registers
        # will automatically work with the new set of R0-R7.
        # The error message will also correctly list R0-R7 if an invalid one is used.
        label_def_pattern, _, label_def_op_type = self.compilation_rules[-1]
        if label_def_op_type == ['L_DEF'] and label_def_pattern.fullmatch(ssl_line_processed):
            label_name = label_def_pattern.fullmatch(ssl_line_processed).group(1).upper()
            return f"{label_name}:", "SUCCESS"

        for p_idx, (pattern, template, operand_types) in enumerate(self.compilation_rules):
            if operand_types == ['N']:
                if pattern.fullmatch(ssl_line_processed):
                    return template, "SUCCESS"

        for pattern, template, operand_types in self.compilation_rules:
            if operand_types == ['L_DEF'] or operand_types == ['N']:
                continue
            match = pattern.fullmatch(ssl_line_processed)
            if match:
                operands_captured = match.groups()
                operands_for_template = []
                instruction_name_match = re.match(r"([A-Z]+)", template)
                instruction_name = instruction_name_match.group(1).upper() if instruction_name_match else "SSL_OP"

                for i, op_type in enumerate(operand_types):
                    current_operand_str_raw = operands_captured[i]
                    current_operand_str_upper = current_operand_str_raw.upper()

                    if op_type == 'R':
                        if current_operand_str_upper not in self.valid_registers:
                            return f"Invalid register '{current_operand_str_raw}' in {instruction_name}. Valid: {', '.join(sorted(list(self.valid_registers)))}.", "ERROR"
                        operands_for_template.append(current_operand_str_upper)
                    elif op_type in ['V16', 'V8', 'A16']:
                        val = 0;
                        max_val = 0;
                        type_str_for_error = ""
                        base = 10;
                        parse_str = current_operand_str_raw
                        if current_operand_str_raw.upper().startswith("0X"):
                            base = 16;
                            parse_str = current_operand_str_raw[2:]
                        try:
                            val = int(parse_str, base)
                        except ValueError:
                            return f"Invalid numeric format for {op_type} '{current_operand_str_raw}' in {instruction_name}.", "ERROR"
                        if op_type == 'V16':
                            max_val = self.max_immediate_16bit; type_str_for_error = "16-bit immediate value"
                        elif op_type == 'V8':
                            max_val = self.max_immediate_8bit; type_str_for_error = "8-bit immediate value"
                        elif op_type == 'A16':
                            max_val = self.max_address_16bit; type_str_for_error = "16-bit address"
                        if not (
                                0 <= val <= max_val): return f"{type_str_for_error.capitalize()} '{current_operand_str_raw}' ({val}) out of range (0-{max_val}) for {instruction_name}.", "ERROR"
                        if op_type == 'A16':
                            operands_for_template.append(f"0x{val:04X}")
                        else:
                            operands_for_template.append(str(val))
                    elif op_type == 'L':
                        if not re.fullmatch(r"[A-Z_0-9]+", current_operand_str_upper,
                                            re.IGNORECASE): return f"Invalid label name format '{current_operand_str_raw}' in {instruction_name}.", "ERROR"
                        operands_for_template.append(current_operand_str_upper)
                sal_instruction = template.format(*operands_for_template)
                return sal_instruction, "SUCCESS"
        return f"Unknown command or invalid syntax: '{ssl_line_processed}'", "ERROR"

    def compile_program(self, ssl_program_string):  # No change
        print("--- Starting Compilation ---");
        lines = ssl_program_string.strip().split('\n')
        compiled_assembly_lines = [];
        has_errors = False
        for i, line_text_orig in enumerate(lines):
            ssl_line_number = i + 1
            print(f"\nProcessing Original SSL Line {ssl_line_number}: \"{line_text_orig.strip()}\"")
            processed_line = self._preprocess_line(line_text_orig)
            if not processed_line:
                if line_text_orig.strip().startswith("//"):
                    print(f"  Full-line SSL Comment: \"{line_text_orig.strip()}\""); compiled_assembly_lines.append(
                        f"; {line_text_orig.strip()}")
                else:
                    print("  Skipping empty or whitespace-only line after preprocessing.")
                continue
            print(f"  Command part for compilation: \"{processed_line}\"")
            assembly_code_or_error_msg, status = self.compile_line(processed_line)
            if status == "ERROR":
                has_errors = True
                full_error_message = f"SSL Line {ssl_line_number}: {assembly_code_or_error_msg} (Original: \"{line_text_orig.strip()}\")"
                print(f"  Compilation Status: ERROR");
                print(f"  Message: {full_error_message}")
                compiled_assembly_lines.append(
                    f"; ERROR at SSL Line {ssl_line_number}: {assembly_code_or_error_msg} (Source: {line_text_orig.strip()})")
            elif status == "SUCCESS":
                sal_instruction_part = assembly_code_or_error_msg;
                comment_to_append = ""
                if '//' in line_text_orig:
                    original_ssl_comment = line_text_orig.split('//', 1)[1].strip()
                    if original_ssl_comment: comment_to_append = f" ; // {original_ssl_comment}"
                current_sal_line_to_add = ""
                if sal_instruction_part.endswith(":") or sal_instruction_part in ["RET", "NOP", "HALT"]:
                    current_sal_line_to_add = sal_instruction_part
                    compiled_assembly_lines.append(current_sal_line_to_add)
                    if comment_to_append: compiled_assembly_lines.append(
                        f"; // {comment_to_append.replace('; //', '').strip()}")
                else:
                    current_sal_line_to_add = f"{sal_instruction_part}{comment_to_append}"
                    compiled_assembly_lines.append(current_sal_line_to_add)
                print(f"  Compilation Status: SUCCESS");
                print(f"  Generated SAL: \"{current_sal_line_to_add}\"")
        print("\n--- Compilation Finished ---")
        if has_errors:
            print("Compilation finished with errors.")
        else:
            print("Compilation successful.")
        final_sal_lines = [line for line in compiled_assembly_lines if line.strip()]
        return "\n".join(final_sal_lines), has_errors


# Standalone test
if __name__ == "__main__":
    compiler = SimpleCompilerLLM()
    test_ssl_r0_r7 = """
    SET R0 10
    SET R7 20
    ADD R0 R7
    PRINT R0 
    MOV R5 R0
    PRINT R5 
    // SET R8 100 // This would be an error
    HALT
    """
    print(f"Compiling SSL with R0-R7 registers:\n{test_ssl_r0_r7}")
    compiled_sal, had_errors = compiler.compile_program(test_ssl_r0_r7)
    print("\nCompiled SAL:")
    print(compiled_sal)
    if had_errors: print("\nCompiler reported errors.")
