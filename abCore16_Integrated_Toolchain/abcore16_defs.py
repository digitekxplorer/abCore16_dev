# abcore16_defs.py
"""
Centralized definitions for the abCore16 microprocessor project.
Includes opcodes, register names, instruction formats, and other constants.
"""

# --- Opcodes ---
# Mnemonic -> Opcode Value
OPCODES = {
    "NOP":   0x00, "LOAD":  0x01, "STORE": 0x02, "LOADM": 0x03,
    "LOADFR":0x04,
    "STORFR":0x05,
    # Gap: 0x06 - 0x0F currently unused

    "ADD":   0x10, "SUB":   0x11, "MUL":   0x12,
    "INC":   0x13, "DEC":   0x14,

    "AND":   0x20, "OR":    0x21, "XOR":   0x22, "NOT":   0x23,
    "SHL":   0x24, "SHR":   0x25,
    "L_AND": 0x26, "L_OR":  0x27, "L_NOT": 0x28,

    "INP":   0x30, "OUT":   0x31,
    "INM":   0x32, "OUTM":  0x33,

    "CMP":   0x40,

    "JMP":   0x50, "JMPZ":  0x51, "JMPN":  0x52,
    "JE":    0x53, "JNE":   0x54, "JS":    0x55, "JNS":   0x56,
    "JC":    0x57, "JNC":   0x58, "JO":    0x59, "JNO":   0x5A,

    "PUSH":  0x60, "POP":   0x61,

    "CALL":  0x70, "RET":   0x71,

    "MOV":   0x80,
    "MOVFRSP": 0x81, # <<< NEW: Move From SP (Rd = SP)
    "MOVTOSP": 0x82, # <<< NEW: Move To SP (SP = Rs)
    # 0x83 onwards available for MOV variants or other instructions

    "HALT":  0xFF
}

REVERSE_OPCODES = {v: k for k, v in OPCODES.items()}

REG_NAMES = {
    0: 'R0', 1: 'R1', 2: 'R2', 3: 'R3',
    4: 'R4', 5: 'R5', 6: 'R6', 7: 'R7'
}
REG_CODES = {v: k for k, v in REG_NAMES.items()}
VALID_REGISTERS = set(REG_CODES.keys())

INSTRUCTION_FORMATS = {
    "NOP":   (1, []), "HALT":  (1, []), "RET":   (1, []),
    "LOAD":  (4, ['R', 'I16']), "STORE": (4, ['R', 'A16']), "LOADM": (4, ['R', 'A16']),
    "LOADFR": (5, ['R', 'R', 'S16']), "STORFR": (5, ['R', 'R', 'S16']),
    "INM":   (4, ['R', 'A16']), "OUTM":  (4, ['R', 'A16']),
    "ADD":   (3, ['R', 'R']), "SUB":   (3, ['R', 'R']), "MUL":   (3, ['R', 'R']),
    "AND":   (3, ['R', 'R']), "OR":    (3, ['R', 'R']), "XOR":   (3, ['R', 'R']),
    "CMP":   (3, ['R', 'R']),
    "MOV":   (3, ['R', 'R']),
    "MOVFRSP": (2, ['R']),      # Op(1), Rd(1) <<< NEW
    "MOVTOSP": (2, ['R']),      # Op(1), Rs(1) <<< NEW
    "INC":   (2, ['R']), "DEC":   (2, ['R']), "NOT":   (2, ['R']),
    "INP":   (2, ['R']), "OUT":   (2, ['R']),
    "PUSH":  (2, ['R']), "POP":   (2, ['R']),
    "SHL":   (3, ['R', 'I8']), "SHR":   (3, ['R', 'I8']),
    "L_AND": (4, ['R', 'R', 'R']), "L_OR":  (4, ['R', 'R', 'R']), "L_NOT": (3, ['R', 'R']),
    "JMP":   (3, ['A16']), "JE": (3, ['A16']), "JNE": (3, ['A16']),
    "JS":    (3, ['A16']), "JNS": (3, ['A16']), "JC": (3, ['A16']), "JNC": (3, ['A16']),
    "JO":    (3, ['A16']), "JNO": (3, ['A16']), "CALL":  (3, ['A16']),
    "JMPZ":  (4, ['R', 'A16']), "JMPN":  (4, ['R', 'A16'])
}

MAX_IMMEDIATE_16BIT = 0xFFFF
MAX_ADDRESS_16BIT   = 0xFFFF
MAX_IMMEDIATE_8BIT  = 0xFF
MIN_SIGNED_IMMEDIATE_16BIT = -32768
MAX_SIGNED_IMMEDIATE_16BIT = 32767
DEFAULT_MMIO_INPUT_ADDR  = 0x00FE
DEFAULT_MMIO_OUTPUT_ADDR = 0x00FF
START_ADDR_SSL_VARIABLES = 0x1000
