# c_ply_compiler.py

import os
from ply.lex import lex
from ply.yacc import yacc

# --- Import AST Node Classes from ast_nodes.py ---
from ast_nodes import (
    Node, ProgramNode, StatementNode, AssignmentNode, PrintNode, IfNode, WhileNode,
    ExpressionNode, NumberNode, IdentifierNode, BinaryOpNode, UnaryOpNode
)

# --- End AST Node Import ---


# --- Tokenizer (Lexer) Definition ---
tokens = (
    'NUMBER', 'IDENTIFIER',
    'PLUS', 'MINUS', 'TIMES',
    'ASSIGN', 'SEMI',
    'LPAREN', 'RPAREN', 'LBRACE', 'RBRACE',
    'EQ', 'NEQ', 'LT', 'GT',
    'AND_LOGICAL', 'OR_LOGICAL', 'NOT_LOGICAL',
    # Keywords
    'PRINT', 'IF', 'ELSE', 'WHILE'
)

t_ignore = ' \t'  # Ignore spaces and tabs

# Simple token rules
t_PLUS = r'\+'
t_MINUS = r'-'
t_TIMES = r'\*'
t_ASSIGN = r'='
t_SEMI = r';'
t_LPAREN = r'\('
t_RPAREN = r'\)'
t_LBRACE = r'\{'
t_RBRACE = r'\}'
t_EQ = r'=='
t_NEQ = r'!='
t_LT = r'<'
t_GT = r'>'
t_AND_LOGICAL = r'&&'
t_OR_LOGICAL = r'\|\|'  # Pipe needs to be escaped
t_NOT_LOGICAL = r'!'

# Reserved words (keywords)
reserved = {
    'print': 'PRINT',
    'if': 'IF',
    'else': 'ELSE',
    'while': 'WHILE',
}


def t_IDENTIFIER(t):
    r'[a-zA-Z_][a-zA-Z_0-9]*'
    t.type = reserved.get(t.value.lower(), 'IDENTIFIER')  # Check for reserved words
    return t


def t_NUMBER(t):
    r'\d+'
    try:
        t.value = int(t.value)
    except ValueError:
        print(f"PLY Lexer: Integer value too large '{t.value}' at line {t.lexer.lineno}")
        t.value = 0  # Default or error
    return t


def t_newline(t):
    r'\n+'
    t.lexer.lineno += len(t.value)


# Comment rule (discard comments)
def t_COMMENT(t):
    r'//.*'
    pass  # No return value means token is discarded


# Error handling rule for lexer
def t_error(t):
    print(f"PLY Lexer: Illegal character '{t.value[0]}' at line {t.lexer.lineno} (offset {t.lexpos})")
    t.lexer.skip(1)


lexer_ply = lex(debug=0)  # Create the lexer instance ONCE at module level

# --- Parser (YACC) Definition ---
# Operator precedence and associativity
precedence = (
    ('left', 'OR_LOGICAL'),
    ('left', 'AND_LOGICAL'),
    ('nonassoc', 'EQ', 'NEQ', 'LT', 'GT'),
    ('left', 'PLUS', 'MINUS'),
    ('left', 'TIMES'),
    ('right', 'NOT_LOGICAL', 'UMINUS')
)

start = 'program'  # Explicitly define the start symbol for the grammar


def p_program(p):
    '''program : statement_list'''
    p[0] = ProgramNode(p[1] if p[1] is not None else [], line_no=1)


def p_statement_list(p):
    '''statement_list : statement_list statement
                      | empty'''
    if len(p) == 3:
        current_list = p[1] if p[1] is not None else []
        if p[2] is not None:
            p[0] = current_list + [p[2]]
        else:
            p[0] = current_list
    else:
        p[0] = []


def p_statement(p):  # CORRECTED INDENTATION HERE
    '''statement : assignment_statement
                 | print_statement
                 | if_statement
                 | while_statement
                 | block_statement
                 | empty_statement'''
    p[0] = p[1]  # This line is now correctly indented


def p_empty_statement(p):
    '''empty_statement : SEMI'''
    p[0] = None


def p_block_statement(p):
    '''block_statement : LBRACE statement_list RBRACE'''
    p[0] = ProgramNode(p[2] if p[2] is not None else [], line_no=p.lineno(1))


def p_assignment_statement(p):
    '''assignment_statement : IDENTIFIER ASSIGN expression SEMI'''
    p[0] = AssignmentNode(IdentifierNode(p[1], line_no=p.lineno(1)), p[3], line_no=p.lineno(1))


def p_print_statement(p):
    '''print_statement : PRINT expression SEMI'''
    p[0] = PrintNode(p[2], line_no=p.lineno(1))


def p_if_statement(p):
    '''if_statement : IF LPAREN expression RPAREN block_statement else_clause'''
    p[0] = IfNode(p[3], p[5], p[6], line_no=p.lineno(1))


def p_else_clause(p):
    '''else_clause : ELSE block_statement
                   | empty'''
    if len(p) == 3:
        p[0] = p[2]
    else:
        p[0] = None


def p_while_statement(p):
    '''while_statement : WHILE LPAREN expression RPAREN block_statement'''
    p[0] = WhileNode(p[3], p[5], line_no=p.lineno(1))


def p_expression_binop(p):
    '''expression : expression PLUS expression
                  | expression MINUS expression
                  | expression TIMES expression
                  | expression EQ expression
                  | expression NEQ expression
                  | expression LT expression
                  | expression GT expression
                  | expression AND_LOGICAL expression
                  | expression OR_LOGICAL expression
                  '''
    p[0] = BinaryOpNode(p[2], p[1], p[3], line_no=p.lineno(2))


def p_expression_unary(p):
    '''expression : MINUS expression %prec UMINUS
                  | NOT_LOGICAL expression'''
    p[0] = UnaryOpNode(p[1], p[2], line_no=p.lineno(1))


def p_expression_group(p):
    '''expression : LPAREN expression RPAREN'''
    p[0] = p[2]


def p_expression_number(p):
    '''expression : NUMBER'''
    p[0] = NumberNode(p[1], line_no=p.lineno(1))


def p_expression_identifier(p):
    '''expression : IDENTIFIER'''
    p[0] = IdentifierNode(p[1], line_no=p.lineno(1))


def p_empty(p):
    '''empty :'''
    p[0] = None


_ply_parser_errors_found = False


def p_error(p):
    global _ply_parser_errors_found
    _ply_parser_errors_found = True
    if p:
        print(f"PLY Parser: Syntax error at token '{p.type}' ('{p.value}') on line {p.lineno}")
    else:
        print(f"PLY Parser: Syntax error at EOF (End Of File). Check for unclosed braces or missing semicolons.")


parser_ply = yacc(debug=0, write_tables=True, tabmodule="c_ssl_parsetab")

# --- Import SALCodeGenerator ---
from code_generator import SALCodeGenerator


# --- The Reusable Compilation Function ---
def compile_c_ssl_string_to_sal(c_ssl_code_string):
    global _ply_parser_errors_found
    _ply_parser_errors_found = False

    lexer_ply.lineno = 1

    print("--- PLY COMPILER: Lexing & Parsing C-SSL ---")
    ast = parser_ply.parse(input=c_ssl_code_string, lexer=lexer_ply, tracking=True)

    if _ply_parser_errors_found or not ast:
        if not _ply_parser_errors_found and not ast and c_ssl_code_string.strip():
            print("C-SSL Compilation FAILED: No Abstract Syntax Tree was generated (possibly empty effective input).")
        elif not _ply_parser_errors_found and not ast:
            print("C-SSL Info: Input was empty or comments only, no AST generated.")
            return "", False
        else:
            print("C-SSL Compilation FAILED due to parsing errors (details above).")
        return None, True

    print("--- PLY COMPILER: Generating SAL from AST ---")
    code_gen = SALCodeGenerator()
    generated_sal_code = ""
    code_gen_had_errors = False
    try:
        generated_sal_code = code_gen.generate(ast)
    except Exception as e:
        print(f"FATAL C-SSL Code Generation Error: {e}")
        import traceback
        traceback.print_exc()
        code_gen_had_errors = True

    if code_gen_had_errors:
        print("C-SSL Compilation FAILED during code generation.")
        return None, True

    print("--- PLY COMPILER: SAL Generation Complete ---")
    return generated_sal_code, False


# --- Main block for testing c_ply_compiler.py directly (optional) ---
if __name__ == '__main__':
    ssl_input_file_path = "test_program.ssl"
    sal_output_file_path = "SAL_from_c_ply_direct_with_ast_nodes_import.sal"

    print(f"--- Running c_ply_compiler.py (with AST nodes imported) directly with '{ssl_input_file_path}' ---")

    ssl_content_to_compile = ""
    try:
        with open(ssl_input_file_path, 'r') as f:
            ssl_content_to_compile = f.read()
        print(f"Read {len(ssl_content_to_compile)} characters from '{ssl_input_file_path}'.")
    except FileNotFoundError:
        print(f"Error: Test SSL file '{ssl_input_file_path}' not found.")
        ssl_content_to_compile = None
    except Exception as e:
        print(f"Error reading test SSL file: {e}")
        ssl_content_to_compile = None

    if ssl_content_to_compile and ssl_content_to_compile.strip():
        generated_sal, had_errors = compile_c_ssl_string_to_sal(ssl_content_to_compile)
        if had_errors:
            print("\nC-SSL COMPILATION FAILED (direct run).")
        else:
            print("\n--- Generated SAL (direct run) ---");
            print(generated_sal or "// No SAL")
            print("C-SSL COMPILATION SUCCESSFUL.");
            try:
                with open(sal_output_file_path, 'w') as f:
                    f.write(generated_sal or "")
                print(f"SAL saved to '{sal_output_file_path}'")
            except IOError as e:
                print(f"Error saving SAL: {e}")
    elif ssl_content_to_compile is not None:
        print(f"Test SSL file '{ssl_input_file_path}' is empty or contains only whitespace.")
