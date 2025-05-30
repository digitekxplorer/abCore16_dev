# simple_disassembler.py
import re
import os  # For os.path.basename in standalone test

# These should ideally be shared with the assembler and simulator, or loaded from a common config
OPCODES_DIS = {  # Value -> Mnemonic
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

REG_NAMES_DIS = {0: 'R0', 1: 'R1', 2: 'R2', 3: 'R3', 4: 'R4', 5: 'R5', 6: 'R6', 7: 'R7'}

# Instruction formats (Opcode_Mnemonic: (num_total_bytes_including_opcode, [operand_types]))
# Operand Types: R=Register(1B), I8=Immediate8bit(1B), I16=Immediate16bit(2B), A16=Address16bit(2B)
INSTRUCTION_FORMATS = {
    "NOP": (1, []), "HALT": (1, []), "RET": (1, []),
    "LOAD": (4, ['R', 'I16']),
    "STORE": (4, ['R', 'A16']), "LOADM": (4, ['R', 'A16']),
    "INM": (4, ['R', 'A16']), "OUTM": (4, ['R', 'A16']),
    "ADD": (3, ['R', 'R']), "SUB": (3, ['R', 'R']), "MUL": (3, ['R', 'R']),
    "AND": (3, ['R', 'R']), "OR": (3, ['R', 'R']), "XOR": (3, ['R', 'R']),
    "CMP": (3, ['R', 'R']), "MOV": (3, ['R', 'R']),
    "INC": (2, ['R']), "DEC": (2, ['R']), "NOT": (2, ['R']),
    "INP": (2, ['R']), "OUT": (2, ['R']),
    "PUSH": (2, ['R']), "POP": (2, ['R']),
    "SHL": (3, ['R', 'I8']), "SHR": (3, ['R', 'I8']),
    "JMP": (3, ['A16']), "JE": (3, ['A16']), "JNE": (3, ['A16']),
    "JS": (3, ['A16']), "JNS": (3, ['A16']), "JC": (3, ['A16']),
    "JNC": (3, ['A16']), "JO": (3, ['A16']), "JNO": (3, ['A16']),
    "CALL": (3, ['A16']),
    "JMPZ": (4, ['R', 'A16']), "JMPN": (4, ['R', 'A16'])
}


class SimpleDisassembler:
    def __init__(self):
        self.program_bytes = []
        self.pc = 0  # Current byte offset being processed
        self.output_lines = []
        self.errors = []
        self.potential_labels = {}  # label_address -> label_name

    def _fetch_byte(self):
        if self.pc >= len(self.program_bytes):
            # Error will be logged by the main disassemble loop if it tries to fetch past EOF
            return None
        byte = self.program_bytes[self.pc]
        self.pc += 1
        return byte

    def _fetch_word_le(self):
        low_byte = self._fetch_byte()
        if low_byte is None: return None
        high_byte = self._fetch_byte()
        if high_byte is None: return None
        return (high_byte << 8) | low_byte

    def _format_operand(self, operand_val, op_type_str, current_addr_for_error_log):
        if op_type_str == 'R':
            if operand_val in REG_NAMES_DIS:
                return REG_NAMES_DIS[operand_val]
            else:
                self.errors.append(
                    f"Disassembly Error @{current_addr_for_error_log:04X}h: Invalid register code {operand_val}")
                return f"R_ERR({operand_val})"
        elif op_type_str == 'I16':
            return f"#0x{operand_val:04X}"  # Show 16-bit immediates as hex, with #
        elif op_type_str == 'I8':
            return f"#{operand_val}"  # Show 8-bit immediates as decimal, with #
        elif op_type_str == 'A16':
            # If this address is a known label target, use the label name
            if operand_val in self.potential_labels:
                return self.potential_labels[operand_val]
            return f"0x{operand_val:04X}"  # Show all addresses as hex

        self.errors.append(
            f"Disassembly Error @{current_addr_for_error_log:04X}h: Unknown operand type '{op_type_str}' for value {operand_val}")
        return f"UNK_OP_TYPE({operand_val})"

    def _pre_scan_for_labels(self):
        """First pass: identify potential jump/call targets to create labels."""
        self.potential_labels = {}
        scan_pc = 0
        while scan_pc < len(self.program_bytes):
            instr_start_addr = scan_pc
            if scan_pc >= len(self.program_bytes): break  # Safety for EOF

            opcode_byte = self.program_bytes[scan_pc]
            opcode_str = OPCODES_DIS.get(opcode_byte)

            current_instr_len = 0
            target_addr = -1

            if opcode_str and opcode_str in INSTRUCTION_FORMATS:
                instr_total_bytes, op_types = INSTRUCTION_FORMATS[opcode_str]
                current_instr_len = instr_total_bytes

                # Check if this instruction has an A16 operand that is a jump target
                if op_types:  # If there are operands
                    # For JMPZ/JMPN R, A16, the address is the second operand type
                    if (opcode_str in ["JMPZ", "JMPN"]) and len(op_types) == 2 and op_types[1] == 'A16':
                        # Opcode (1) + Reg (1) + AddrL (1) + AddrH (1)
                        if instr_start_addr + 3 < len(self.program_bytes):  # Enough bytes for Op, R, AddrL, AddrH
                            addr_l = self.program_bytes[instr_start_addr + 2]
                            addr_h = self.program_bytes[instr_start_addr + 3]
                            target_addr = (addr_h << 8) | addr_l
                    # For JMP/CALL/Jcc A16, the address is the first (and only) operand type
                    elif len(op_types) == 1 and op_types[0] == 'A16' and \
                            opcode_str in ["JMP", "JE", "JNE", "JS", "JNS", "JC", "JNC", "JO", "JNO", "CALL"]:
                        # Opcode (1) + AddrL (1) + AddrH (1)
                        if instr_start_addr + 2 < len(self.program_bytes):  # Enough bytes for Op, AddrL, AddrH
                            addr_l = self.program_bytes[instr_start_addr + 1]
                            addr_h = self.program_bytes[instr_start_addr + 2]
                            target_addr = (addr_h << 8) | addr_l

                if target_addr != -1:
                    if target_addr not in self.potential_labels:
                        self.potential_labels[target_addr] = f"L_{target_addr:04X}"
            else:  # Unknown opcode
                current_instr_len = 1  # Assume 1 byte to advance

            if current_instr_len == 0:  # Should not happen for known opcodes
                # self.errors.append(f"Warning (Pre-scan): Opcode {opcode_str} has zero length at {instr_start_addr:04X}h. Skipping.")
                scan_pc += 1  # Minimal advance to avoid infinite loop
            else:
                scan_pc += current_instr_len
        # print(f"Debug: Potential Labels Found: {self.potential_labels}")

    def disassemble(self, machine_code_bytes):
        self.program_bytes = list(machine_code_bytes)
        self.pc = 0
        self.output_lines = []
        self.errors = []
        processed_addresses = set()

        self._pre_scan_for_labels()  # Populate self.potential_labels

        while self.pc < len(self.program_bytes):
            current_addr = self.pc  # Address of the opcode

            if current_addr in self.potential_labels and current_addr not in processed_addresses:
                self.output_lines.append(f"{self.potential_labels[current_addr]}:")
                processed_addresses.add(current_addr)

            opcode_byte = self._fetch_byte()  # PC advances past opcode
            if opcode_byte is None: break

            opcode_str = OPCODES_DIS.get(opcode_byte)
            if not opcode_str:
                self.output_lines.append(f"{current_addr:04X}h:  DB 0x{opcode_byte:02X} ; Unknown Opcode")
                self.errors.append(f"Unknown opcode 0x{opcode_byte:02X} at address {current_addr:04X}h")
                continue  # Try to disassemble next byte

            operands_str_list = []
            num_expected_ops_in_format, operand_types_in_format = INSTRUCTION_FORMATS.get(opcode_str, (0, []))

            # Fetch and format operands based on INSTRUCTION_FORMATS
            operand_values_fetched = []
            fetch_error = False
            for op_type in operand_types_in_format:
                if op_type == 'R' or op_type == 'I8':
                    op_val = self._fetch_byte()
                    if op_val is None: fetch_error = True; break
                    operand_values_fetched.append(op_val)
                elif op_type == 'I16' or op_type == 'A16':
                    op_val = self._fetch_word_le()
                    if op_val is None: fetch_error = True; break
                    operand_values_fetched.append(op_val)
                else:
                    self.errors.append(
                        f"Internal Disasm Error: Unknown operand type '{op_type}' for {opcode_str} at {current_addr:04X}h")
                    fetch_error = True;
                    break

            if fetch_error:
                self.errors.append(
                    f"Disassembly Error: Unexpected EOF while fetching operands for {opcode_str} at {current_addr:04X}h.")
                # Attempt to add what was fetched before error
                sal_instruction_partial = opcode_str
                if operand_values_fetched:  # If some operands were fetched before EOF
                    partial_ops_str = [f"0x{op:02X}" for op in operand_values_fetched]  # Show raw bytes
                    sal_instruction_partial += " " + ", ".join(partial_ops_str) + " ; ... (EOF)"
                self.output_lines.append(f"{current_addr:04X}h:  {sal_instruction_partial}")
                break  # Stop disassembly on fetch error

            for i in range(len(operand_values_fetched)):
                op_type = operand_types_in_format[i]
                op_val = operand_values_fetched[i]
                operands_str_list.append(self._format_operand(op_val, op_type, current_addr))

            sal_instruction = opcode_str
            if operands_str_list:
                sal_instruction += " " + ", ".join(operands_str_list)

            self.output_lines.append(f"{current_addr:04X}h:  {sal_instruction}")

        if self.errors:
            self.output_lines.append("\n; --- Disassembly Errors/Warnings ---")
            for err in self.errors:
                self.output_lines.append(f"; {err}")

        return "\n".join(self.output_lines)


# Standalone test
if __name__ == "__main__":
    from simple_assembler import SimpleAssembler

    sample_sal_for_disassembly_r_regs_16bit_addr = """
    START:
        LOAD R0, #30000
        STORE R0, 0x0200  ; Use 16-bit address
        LOADM R1, 0x0200
        OUT R1
        CALL SUB1
        JMP START
    SUB1:
        INC R1
        RET
    HALT_FINAL:
        HALT
    """
    assembler = SimpleAssembler()
    bin_file_to_disassemble = "test_r_regs_16addr_dis_v2.bin"
    asm_listing_file = "test_r_regs_16addr_dis_v2.asm"

    if assembler.assemble_to_file(sample_sal_for_disassembly_r_regs_16bit_addr, bin_file_to_disassemble,
                                  asm_listing_file):
        print(f"\n--- Testing Disassembler with '{bin_file_to_disassemble}' (16-bit Addr) ---")

        disassembler = SimpleDisassembler()
        try:
            with open(bin_file_to_disassemble, "rb") as f_bin:
                machine_code = f_bin.read()
            if machine_code:
                disassembled_sal = disassembler.disassemble(machine_code)
                print("\n--- Disassembled SAL ---");
                print(disassembled_sal)
                disassembled_output_file = "test_r_regs_16addr_disassembled_v2.sal"
                with open(disassembled_output_file, "w") as f_dis_out:
                    f_dis_out.write(disassembled_sal)
                print(f"\nDisassembled output also written to '{disassembled_output_file}'")
            else:
                print("Machine code file empty.")
        except Exception as e:
            print(f"An error occurred during disassembly test: {e}")
    else:
        print(f"Failed to assemble test binary for the disassembler: {bin_file_to_disassemble}")
