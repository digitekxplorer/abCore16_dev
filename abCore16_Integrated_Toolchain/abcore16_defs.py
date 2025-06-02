# abcore16_defs.py
"""
Centralized definitions for the abCore16 microprocessor project.
Includes opcodes, register names, instruction formats, and other constants.
"""

# --- Opcodes ---
# Mnemonic -> Opcode Value
OPCODES = {
    "NOP":   0x00, "LOAD":  0x01, "STORE": 0x02, "LOADM": 0x03,
    "ADD":   0x10, "SUB":   0x11, "MUL":   0x12,
    "INC":   0x13, "DEC":   0x14,
    "AND":   0x20, "OR":    0x21, "XOR":   0x22, "NOT":   0x23, # Bitwise NOT
    "SHL":   0x24, "SHR":   0x25,
    "L_AND": 0x26, "L_OR":  0x27, "L_NOT": 0x28, # Logical (Boolean) NOT
    "INP":   0x30, "OUT":   0x31,
    "INM":   0x32, "OUTM":  0x33,
    "CMP":   0x40,
    "JMP":   0x50, "JMPZ":  0x51, "JMPN":  0x52,
    "JE":    0x53, "JNE":   0x54, "JS":    0x55, "JNS":   0x56,
    "JC":    0x57, "JNC":   0x58, "JO":    0x59, "JNO":   0x5A,
    "PUSH":  0x60, "POP":   0x61,
    "CALL":  0x70, "RET":   0x71,
    "MOV":   0x80,
    "HALT":  0xFF
}

# Opcode Value -> Mnemonic (for disassembler, simulator logs)
REVERSE_OPCODES = {v: k for k, v in OPCODES.items()}

# --- Registers ---
# Numerical Code -> String Name
REG_NAMES = {
    0: 'R0', 1: 'R1', 2: 'R2', 3: 'R3',
    4: 'R4', 5: 'R5', 6: 'R6', 7: 'R7'
}

# String Name -> Numerical Code
REG_CODES = {v: k for k, v in REG_NAMES.items()}

# Set of valid register names (for validation)
VALID_REGISTERS = set(REG_CODES.keys())

# --- Instruction Formats ---
# Mnemonic: (num_total_bytes_including_opcode, [list_of_operand_types])
# Operand Types:
#   'R'   : Register (1 byte for code)
#   'I8'  : 8-bit Immediate (1 byte)
#   'I16' : 16-bit Immediate (2 bytes, Little Endian: Low, High)
#   'A16' : 16-bit Address (2 bytes, Little Endian: Low, High)
INSTRUCTION_FORMATS = {
    "NOP":   (1, []), "HALT":  (1, []), "RET":   (1, []),
    "LOAD":  (4, ['R', 'I16']),      # Op(1), Reg(1), Imm_L(1), Imm_H(1)
    "STORE": (4, ['R', 'A16']),      # Op(1), Reg(1), Addr_L(1), Addr_H(1)
    "LOADM": (4, ['R', 'A16']),
    "INM":   (4, ['R', 'A16']),
    "OUTM":  (4, ['R', 'A16']),
    "ADD":   (3, ['R', 'R']),        # Op(1), Reg1(1), Reg2(1)
    "SUB":   (3, ['R', 'R']),
    "MUL":   (3, ['R', 'R']),
    "AND":   (3, ['R', 'R']),        # Bitwise
    "OR":    (3, ['R', 'R']),         # Bitwise
    "XOR":   (3, ['R', 'R']),        # Bitwise
    "CMP":   (3, ['R', 'R']),
    "MOV":   (3, ['R', 'R']),
    "INC":   (2, ['R']),             # Op(1), Reg(1)
    "DEC":   (2, ['R']),
    "NOT":   (2, ['R']),             # Bitwise NOT
    "INP":   (2, ['R']),
    "OUT":   (2, ['R']),
    "PUSH":  (2, ['R']),
    "POP":   (2, ['R']),
    "SHL":   (3, ['R', 'I8']),       # Op(1), Reg(1), Imm8(1)
    "SHR":   (3, ['R', 'I8']),
    "L_AND": (4, ['R', 'R', 'R']),   # Op(1), Rd(1), Rs1(1), Rs2(1)
    "L_OR":  (4, ['R', 'R', 'R']),
    "L_NOT": (3, ['R', 'R']),       # Op(1), Rd(1), Rs(1) (Logical NOT)
    "JMP":   (3, ['A16']),           # Op(1), Addr_L(1), Addr_H(1)
    "JE":    (3, ['A16']), "JNE":   (3, ['A16']),
    "JS":    (3, ['A16']), "JNS":   (3, ['A16']),
    "JC":    (3, ['A16']), "JNC":   (3, ['A16']),
    "JO":    (3, ['A16']), "JNO":   (3, ['A16']),
    "CALL":  (3, ['A16']),
    "JMPZ":  (4, ['R', 'A16']),      # Op(1), Reg(1), Addr_L(1), Addr_H(1)
    "JMPN":  (4, ['R', 'A16'])
}

# --- Numeric Limits (Unsigned) ---
MAX_IMMEDIATE_16BIT = 0xFFFF  # 65535
MAX_ADDRESS_16BIT   = 0xFFFF  # 65535 (for PC, SP, memory addresses)
MAX_IMMEDIATE_8BIT  = 0xFF    # 255 (for shift amounts)

# --- Default MMIO Addresses (16-bit) ---
DEFAULT_MMIO_INPUT_ADDR  = 0x00FE  # For INP instruction (reads 16-bit word)
DEFAULT_MMIO_OUTPUT_ADDR = 0x00FF  # For OUT instruction (writes 16-bit word)

# --- Starting address for SSL variables (16-bit) ---
START_ADDR_SSL_VARIABLES = 0x1000  # Used in code_generator.py