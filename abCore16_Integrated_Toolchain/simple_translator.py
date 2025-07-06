# simple_translator.py
import re
# Import from the new definitions file
from abcore16_defs import (
    VALID_REGISTERS, MAX_IMMEDIATE_16BIT, MAX_IMMEDIATE_8BIT,
    MAX_ADDRESS_16BIT, OPCODES, MIN_SIGNED_IMMEDIATE_16BIT, MAX_SIGNED_IMMEDIATE_16BIT
)


class SimpleTranslator:
    def __init__(self):
        # SSL Regex, SAL Template, [Operand Types: R=Reg, V16=16b Val, V8=8b Val, A16=16b Addr, S16=16b Signed Val, L=Label, N=None for no ops]
        # ** FIX: Replaced separators with '\s*,?\s*' to flexibly handle both comma-separated and space-separated operands. **
        self.translation_rules = [
            (re.compile(r"SET\s+(R[0-7])\s*,?\s*(0x[0-9A-Fa-f]+|\d+)", re.IGNORECASE), "LOAD {0}, #{1}", ['R', 'V16']),
            (re.compile(r"MOV\s+(R[0-7])\s*,?\s*(R[0-7])", re.IGNORECASE), "MOV {0}, {1}", ['R', 'R']),
            (re.compile(r"STORE\s+(R[0-7])\s*,?\s*(0x[0-9A-Fa-f]+|\d+)", re.IGNORECASE), "STORE {0}, {1}",
             ['R', 'A16']),
            (re.compile(r"FETCH\s+(R[0-7])\s*,?\s*(0x[0-9A-Fa-f]+|\d+)", re.IGNORECASE), "LOADM {0}, {1}",
             ['R', 'A16']),
            (re.compile(r"LOADFR\s+(R[0-7])\s*,?\s*(R[0-7])\s*,?\s*([+-]?(?:0x[0-9a-fA-F]+|\d+))", re.IGNORECASE),
             "LOADFR {0}, {1}, #{2}", ['R', 'R', 'S16']),
            (re.compile(r"STORFR\s+(R[0-7])\s*,?\s*(R[0-7])\s*,?\s*([+-]?(?:0x[0-9a-fA-F]+|\d+))", re.IGNORECASE),
             "STORFR {0}, {1}, #{2}", ['R', 'R', 'S16']),
            (re.compile(r"LOADI\s+(R[0-7])\s*,?\s*(R[0-7])", re.IGNORECASE), "LOADI {0}, {1}", ['R', 'R']),
            (re.compile(r"STORI\s+(R[0-7])\s*,?\s*(R[0-7])", re.IGNORECASE), "STORI {0}, {1}", ['R', 'R']),
            (re.compile(r"MOVFRSP\s+(R[0-7])", re.IGNORECASE), "MOVFRSP {0}", ['R']),
            (re.compile(r"MOVTOSP\s+(R[0-7])", re.IGNORECASE), "MOVTOSP {0}", ['R']),
            (re.compile(r"ADD\s+(R[0-7])\s*,?\s*(R[0-7])", re.IGNORECASE), "ADD {0}, {1}", ['R', 'R']),
            (re.compile(r"SUB\s+(R[0-7])\s*,?\s*(R[0-7])", re.IGNORECASE), "SUB {0}, {1}", ['R', 'R']),
            (re.compile(r"MUL\s+(R[0-7])\s*,?\s*(R[0-7])", re.IGNORECASE), "MUL {0}, {1}", ['R', 'R']),
            (re.compile(r"INC\s+(R[0-7])", re.IGNORECASE), "INC {0}", ['R']),
            (re.compile(r"DEC\s+(R[0-7])", re.IGNORECASE), "DEC {0}", ['R']),
            (re.compile(r"AND\s+(R[0-7])\s*,?\s*(R[0-7])", re.IGNORECASE), "AND {0}, {1}", ['R', 'R']),
            (re.compile(r"OR\s+(R[0-7])\s*,?\s*(R[0-7])", re.IGNORECASE), "OR {0}, {1}", ['R', 'R']),
            (re.compile(r"XOR\s+(R[0-7])\s*,?\s*(R[0-7])", re.IGNORECASE), "XOR {0}, {1}", ['R', 'R']),
            (re.compile(r"NOT\s+(R[0-7])", re.IGNORECASE), "NOT {0}", ['R']),
            (re.compile(r"SHL\s+(R[0-7])\s*,?\s*(0x[0-9A-Fa-f]+|\d+)", re.IGNORECASE), "SHL {0}, #{1}", ['R', 'V8']),
            (re.compile(r"SHR\s+(R[0-7])\s*,?\s*(0x[0-9A-Fa-f]+|\d+)", re.IGNORECASE), "SHR {0}, #{1}", ['R', 'V8']),
            (re.compile(r"L_AND\s+(R[0-7])\s*,?\s*(R[0-7])\s*,?\s*(R[0-7])", re.IGNORECASE), "L_AND {0}, {1}, {2}",
             ['R', 'R', 'R']),
            (re.compile(r"L_OR\s+(R[0-7])\s*,?\s*(R[0-7])\s*,?\s*(R[0-7])", re.IGNORECASE), "L_OR {0}, {1}, {2}",
             ['R', 'R', 'R']),
            (re.compile(r"L_NOT\s+(R[0-7])\s*,?\s*(R[0-7])", re.IGNORECASE), "L_NOT {0}, {1}", ['R', 'R']),
            (re.compile(r"INP\s+(R[0-7])", re.IGNORECASE), "INP {0}", ['R']),
            (re.compile(r"PRINT\s+(R[0-7])", re.IGNORECASE), "OUT {0}", ['R']),
            (re.compile(r"INM\s+(R[0-7])\s*,?\s*(0x[0-9A-Fa-f]+|\d+)", re.IGNORECASE), "INM {0}, {1}", ['R', 'A16']),
            (re.compile(r"OUTM\s+(R[0-7])\s*,?\s*(0x[0-9A-Fa-f]+|\d+)", re.IGNORECASE), "OUTM {0}, {1}", ['R', 'A16']),
            (re.compile(r"CMP\s+(R[0-7])\s*,?\s*(R[0-7])", re.IGNORECASE), "CMP {0}, {1}", ['R', 'R']),
            (re.compile(r"JMP\s+([A-Z_0-9]+)", re.IGNORECASE), "JMP {0}", ['L']),
            (re.compile(r"JMPZ\s+(R[0-7])\s*,?\s*([A-Z_0-9]+)", re.IGNORECASE), "JMPZ {0}, {1}", ['R', 'L']),
            (re.compile(r"JMPN\s+(R[0-7])\s*,?\s*([A-Z_0-9]+)", re.IGNORECASE), "JMPN {0}, {1}", ['R', 'L']),
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
        # Use imported constants
        self.valid_registers = VALID_REGISTERS
        self.max_immediate_16bit = MAX_IMMEDIATE_16BIT
        self.max_immediate_8bit = MAX_IMMEDIATE_8BIT
        self.max_address_16bit = MAX_ADDRESS_16BIT
        self.min_signed_immediate_16bit = MIN_SIGNED_IMMEDIATE_16BIT
        self.max_signed_immediate_16bit = MAX_SIGNED_IMMEDIATE_16BIT

    def _preprocess_line(self, line_text):
        line_text = line_text.split('//', 1)[0]
        return line_text.strip()

    # The rest of the file (translate_line, translate_program, __main__)
    # does not need any changes, as the logic is correct. The fix is
    # entirely within the regular expressions in the __init__ method.
    def translate_line(self, ssl_line_processed):
        label_def_pattern, _, label_def_op_type = self.translation_rules[-1]
        if label_def_op_type == ['L_DEF'] and label_def_pattern.fullmatch(ssl_line_processed):
            label_name = label_def_pattern.fullmatch(ssl_line_processed).group(1).upper()
            return f"{label_name}:", "SUCCESS"

        for p_idx, (pattern, template, operand_types) in enumerate(self.translation_rules):
            if operand_types == ['N']:
                if pattern.fullmatch(ssl_line_processed):
                    return template, "SUCCESS"

        for pattern, template, operand_types in self.translation_rules:
            if operand_types == ['L_DEF'] or operand_types == ['N']:
                continue

            match = pattern.fullmatch(ssl_line_processed)
            if match:
                operands_captured = match.groups()
                operands_for_template = []
                instruction_name_match = re.match(r"([A-Z_]+)", template)
                instruction_name = instruction_name_match.group(1).upper() if instruction_name_match else "SSL_OP"

                for i, op_type in enumerate(operand_types):
                    current_operand_str_raw = operands_captured[i]
                    current_operand_str_upper = current_operand_str_raw.upper()

                    if op_type == 'R':
                        if current_operand_str_upper not in self.valid_registers:
                            return f"Invalid register '{current_operand_str_raw}' in {instruction_name}. Valid: {', '.join(sorted(list(self.valid_registers)))}.", "ERROR"
                        operands_for_template.append(current_operand_str_upper)

                    elif op_type in ['V16', 'V8', 'A16', 'S16']:
                        try:
                            val = int(current_operand_str_raw, 0)
                        except ValueError:
                            return f"Invalid numeric format for {op_type} '{current_operand_str_raw}' in {instruction_name}.", "ERROR"

                        min_val, max_val, type_str_for_error = 0, 0, ""

                        if op_type == 'V16':
                            min_val, max_val = 0, self.max_immediate_16bit
                            type_str_for_error = "16-bit immediate value"
                        elif op_type == 'V8':
                            min_val, max_val = 0, self.max_immediate_8bit
                            type_str_for_error = "8-bit immediate value"
                        elif op_type == 'A16':
                            min_val, max_val = 0, self.max_address_16bit
                            type_str_for_error = "16-bit address"
                        elif op_type == 'S16':
                            min_val, max_val = self.min_signed_immediate_16bit, self.max_signed_immediate_16bit
                            type_str_for_error = "16-bit signed offset"

                        if not (min_val <= val <= max_val):
                            return f"{type_str_for_error.capitalize()} '{current_operand_str_raw}' ({val}) out of range ({min_val} to {max_val}) for {instruction_name}.", "ERROR"

                        if op_type == 'A16':
                            operands_for_template.append(f"0x{val:04X}")
                        else:
                            operands_for_template.append(str(val))

                    elif op_type == 'L':
                        if not re.fullmatch(r"[A-Z_0-9]+", current_operand_str_upper, re.IGNORECASE):
                            return f"Invalid label name format '{current_operand_str_raw}' in {instruction_name}.", "ERROR"
                        operands_for_template.append(current_operand_str_upper)

                sal_instruction = template.format(*operands_for_template)
                return sal_instruction, "SUCCESS"

        return f"Unknown command or invalid syntax: '{ssl_line_processed}'", "ERROR"

    def translate_program(self, ssl_program_string):
        print("--- Starting Translation ---")
        lines = ssl_program_string.strip().split('\n')
        translated_assembly_lines = []
        has_errors = False
        for i, line_text_orig in enumerate(lines):
            ssl_line_number = i + 1
            processed_line = self._preprocess_line(line_text_orig)
            if not processed_line:
                if line_text_orig.strip().startswith("//"):
                    translated_assembly_lines.append(f"; {line_text_orig.strip()}")
                continue

            assembly_code_or_error_msg, status = self.translate_line(processed_line)
            if status == "ERROR":
                has_errors = True
                full_error_message = f"SSL Line {ssl_line_number}: {assembly_code_or_error_msg} (Original: \"{line_text_orig.strip()}\")"
                print(f"  Translator ERROR: {full_error_message}")
                translated_assembly_lines.append(
                    f"; ERROR at SSL Line {ssl_line_number}: {assembly_code_or_error_msg} (Source: {line_text_orig.strip()})")
            elif status == "SUCCESS":
                sal_instruction_part = assembly_code_or_error_msg
                comment_to_append = ""
                if '//' in line_text_orig:
                    original_ssl_comment = line_text_orig.split('//', 1)[1].strip()
                    if original_ssl_comment: comment_to_append = f" ; // {original_ssl_comment}"

                is_simple_no_op_or_label = sal_instruction_part.endswith(":") or sal_instruction_part in ["RET", "NOP",
                                                                                                          "HALT"]
                current_sal_line_to_add = f"{sal_instruction_part}{comment_to_append}" if not is_simple_no_op_or_label else sal_instruction_part

                translated_assembly_lines.append(current_sal_line_to_add)
                if is_simple_no_op_or_label and comment_to_append:
                    translated_assembly_lines.append(f"; // {comment_to_append.replace('; //', '').strip()}")
        if has_errors: print("TRANSLATOR: Translation finished with errors.")
        final_sal_lines = [line for line in translated_assembly_lines if line.strip()]
        return "\n".join(final_sal_lines), has_errors


# Standalone test
if __name__ == "__main__":
    translator = SimpleTranslator()
    # Test program with corrected typo and mixed comma/no-comma syntax
    test_ssl_new_ops = """
    // Test new instructions for abCore16 with flexible syntax
    SET R0, 0x1234          // Comma syntax
    SET R1 0x1000           // No-comma syntax
    SET R7, 0x2000          

    // Test indirect store/load
    STORI R0, R1           // Comma syntax
    LOADI R2 R1            // No-comma syntax

    // Test frame-relative store/load (with corrected typo)
    STOREFR R0 R7 -4    // No-comma, with negative offset
    LOADFR  R3, R7, -4  // Comma, with negative offset

    HALT
    """
    print(f"Translating SSL with new instructions and flexible syntax:\n{test_ssl_new_ops}")
    compiled_sal, had_errors = translator.translate_program(test_ssl_new_ops)
    print("\nTranslated SAL:")
    print(compiled_sal)
    if had_errors: print("\nTranslator reported errors.")
