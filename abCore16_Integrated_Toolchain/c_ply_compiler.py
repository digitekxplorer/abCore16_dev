# c_ply_compiler.py
# FINAL CORRECTED VERSION: Fixes parser grammar for the 'interrupt' keyword
# using an unambiguous, robust structure.

import os
import sys
from ply.lex import lex
from ply.yacc import yacc

from ast_nodes import (
    Node, ProgramNode, StatementNode, AssignmentNode, PrintNode, IfNode, WhileNode,
    ExpressionNode, NumberNode, IdentifierNode, BinaryOpNode, UnaryOpNode,
    FunctionDefinitionNode, ReturnNode,
    ExpressionStatementNode, FunctionCallNode,
    ForNode, VarDeclNode,
    ArrayDeclNode, ArrayAccessNode, PostfixOpNode,
    SwitchNode, CaseNode, BreakNode,
    StringLiteralNode,
    CharLiteralNode
)

# --- Tokenizer (Lexer) Definition ---
tokens = (
    'NUMBER', 'IDENTIFIER', 'STRING_LITERAL', 'CHAR_LITERAL',
    'PLUS', 'MINUS', 'STAR', 'PLUSPLUS', 'MINUSMINUS',
    'AMPERSAND', 'ASSIGN', 'SEMI',
    'LPAREN', 'RPAREN', 'LBRACE', 'RBRACE', 'LBRACKET', 'RBRACKET', 'COMMA', 'COLON',
    'EQ', 'NEQ', 'LE', 'GE', 'LT', 'GT',
    'AND_LOGICAL', 'OR_LOGICAL', 'NOT_LOGICAL',
    'BITWISE_OR', 'BITWISE_XOR', 'BITWISE_NOT',
    'PRINT', 'IF', 'ELSE', 'WHILE', 'FOR',
    'FUNC', 'RETURN', 'INT', 'CHAR',
    'SWITCH', 'CASE', 'DEFAULT', 'BREAK',
    'INTERRUPT'
)
t_ignore = ' \t'
t_EQ = r'=='
t_NEQ = r'!='
t_LE = r'<='
t_GE = r'>='
t_AND_LOGICAL = r'&&'
t_OR_LOGICAL = r'\|\|'
t_LT = r'<'
t_GT = r'>'
t_ASSIGN = r'='
t_NOT_LOGICAL = r'!'
t_PLUSPLUS = r'\+\+'
t_MINUSMINUS = r'--'
t_PLUS = r'\+'
t_MINUS = r'-'
t_SEMI = r';'
t_LPAREN = r'\('
t_RPAREN = r'\)'
t_LBRACE = r'\{'
t_RBRACE = r'\}'
t_LBRACKET = r'\['
t_RBRACKET = r'\]'
t_COMMA = r','
t_COLON = r':'
t_AMPERSAND = r'&'
t_STAR = r'\*'
t_BITWISE_OR = r'\|'
t_BITWISE_XOR = r'\^'
t_BITWISE_NOT = r'~'
reserved = {
    'print': 'PRINT', 'if': 'IF', 'else': 'ELSE', 'while': 'WHILE', 'for': 'FOR',
    'func': 'FUNC', 'return': 'RETURN', 'int': 'INT', 'char': 'CHAR',
    'switch': 'SWITCH', 'case': 'CASE', 'default': 'DEFAULT', 'break': 'BREAK',
    'interrupt': 'INTERRUPT'
}
def t_STRING_LITERAL(t):
    r'\"([^"\\]|\\.)*\"'
    str_val = t.value[1:-1]
    t.value = str_val.encode().decode('unicode_escape')
    return t

def t_CHAR_LITERAL(t):
    r"'([^\\']|\\.)'"
    char_val = t.value[1:-1]
    t.value = char_val.encode().decode('unicode_escape')
    return t

def t_IDENTIFIER(t):
    r'[a-zA-Z_][a-zA-Z_0-9]*'
    t.type = reserved.get(t.value.lower(), 'IDENTIFIER')
    return t
def t_NUMBER(t):
    r'0x[0-9a-fA-F]+|\d+'
    try:
        if t.value.startswith(('0x', '0X')): t.value = int(t.value, 16)
        else: t.value = int(t.value, 10)
    except ValueError:
        print(f"PLY Lexer: Int value too large '{t.value}' line {t.lexer.lineno}"); t.value = 0
    return t
def t_newline(t):
    r'\n+'
    t.lexer.lineno += len(t.value)
def t_COMMENT(t):
    r'//.*'
    pass
def t_error(t):
    print(f"PLY Lexer: Illegal char '{t.value[0]}' line {t.lexer.lineno} offset {t.lexpos}")
    t.lexer.skip(1)
lexer_ply = lex(debug=0)

# --- Parser (YACC) Definition ---
precedence = (
    ('left', 'OR_LOGICAL'), ('left', 'AND_LOGICAL'), ('left', 'BITWISE_OR'),
    ('left', 'BITWISE_XOR'), ('left', 'AMPERSAND'), ('nonassoc', 'EQ', 'NEQ', 'LT', 'GT', 'LE', 'GE'),
    ('left', 'PLUS', 'MINUS'), ('left', 'STAR'),
    ('right', 'NOT_LOGICAL', 'BITWISE_NOT', 'UMINUS', 'UNARY_PTR'),
    ('left', 'PLUSPLUS', 'MINUSMINUS'), ('right', 'IFX'), ('right', 'ELSE')
)
start = 'program'

def p_type_specifier(p):
    '''type_specifier : INT
                      | CHAR'''
    p[0] = p[1]

def p_declaration_statement(p):
    '''declaration_statement : variable_declaration
                             | array_declaration'''
    p[0] = p[1]

def p_variable_declaration(p):
    '''variable_declaration : type_specifier IDENTIFIER SEMI
                            | type_specifier IDENTIFIER ASSIGN expression SEMI
                            | type_specifier STAR IDENTIFIER SEMI
                            | type_specifier STAR IDENTIFIER ASSIGN expression SEMI'''
    type_name = p[1]
    if p[2] == '*':
        if len(p) == 5:
            p[0] = VarDeclNode(type_name, IdentifierNode(p[3], line_no=p.lineno(3)), None, is_pointer=True, line_no=p.lineno(1))
        else:
            p[0] = VarDeclNode(type_name, IdentifierNode(p[3], line_no=p.lineno(3)), p[5], is_pointer=True, line_no=p.lineno(1))
    else:
        if len(p) == 6:
            p[0] = VarDeclNode(type_name, IdentifierNode(p[2], line_no=p.lineno(2)), p[4], line_no=p.lineno(1))
        else:
            p[0] = VarDeclNode(type_name, IdentifierNode(p[2], line_no=p.lineno(2)), None, line_no=p.lineno(1))

def p_array_declaration(p):
    '''array_declaration : type_specifier IDENTIFIER LBRACKET NUMBER RBRACKET SEMI'''
    type_name = p[1]
    size = p[4]
    if not isinstance(size, int) or size <= 0:
        print(f"FATAL PARSE ERROR: Array size for '{p[2]}' must be a positive integer, got '{size}' on line {p.lineno(4)}.")
    p[0] = ArrayDeclNode(type_name, IdentifierNode(p[2], line_no=p.lineno(2)), size, line_no=p.lineno(1))

def p_program(p):
    '''program : top_level_declaration_list'''
    p[0] = ProgramNode(p[1] if p[1] is not None else [], line_no=1)
def p_top_level_declaration_list(p):
    '''top_level_declaration_list : top_level_declaration_list top_level_declaration
                                  | empty'''
    if len(p) == 3: lst = p[1] if p[1] is not None else []; lst.append(p[2]); p[0] = lst
    else: p[0] = []
def p_top_level_declaration(p):
    '''top_level_declaration : function_definition
                             | declaration_statement
                             | statement_for_global_scope'''
    p[0] = p[1]
def p_statement_for_global_scope(p):
    '''statement_for_global_scope : assignment_statement
                                  | print_statement
                                  | expression_statement
                                  | empty_statement'''
    p[0] = p[1]

# --- MODIFIED FOR INTERRUPT SUPPORT: This is the new, unambiguous grammar structure ---
def p_function_definition(p):
    '''function_definition : interrupt_specifier FUNC IDENTIFIER LPAREN parameter_list_opt RPAREN block_statement'''
    is_interrupt = p[1]
    name_node = IdentifierNode(p[3], line_no=p.lineno(3))
    params = p[5]
    body = p[7]
    p[0] = FunctionDefinitionNode(name_node, params, body, is_interrupt=is_interrupt, line_no=p.lineno(2))

def p_interrupt_specifier(p):
    '''interrupt_specifier : INTERRUPT
                           | empty'''
    p[0] = (len(p) > 1 and p.slice[1].type == 'INTERRUPT')
# --- END MODIFICATION ---

def p_parameter_list_opt(p):
    '''parameter_list_opt : parameter_list
                          | empty'''
    p[0] = p[1] if p[1] is not None else []
def p_parameter_list(p):
    '''parameter_list : IDENTIFIER
                      | parameter_list COMMA IDENTIFIER'''
    if len(p) == 2: p[0] = [IdentifierNode(p[1], line_no=p.lineno(1))]
    else: p[1].append(IdentifierNode(p[3], line_no=p.lineno(3))); p[0] = p[1]
def p_statement_list(p):
    '''statement_list : statement_list statement
                      | empty'''
    if len(p) == 3:
        lst = p[1] if p[1] is not None else [];
        if p[2] is not None: lst.append(p[2])
        p[0] = lst
    else: p[0] = []
def p_statement(p):
    '''statement : assignment_statement
                 | print_statement
                 | if_statement
                 | while_statement
                 | for_statement
                 | block_statement
                 | return_statement
                 | empty_statement
                 | expression_statement
                 | declaration_statement
                 | switch_statement
                 | break_statement'''
    p[0] = p[1]
def p_expression_statement(p):
    '''expression_statement : expression SEMI'''
    p[0] = ExpressionStatementNode(p[1], line_no=p.slice[1].lineno if hasattr(p.slice[1], 'lineno') else p.lineno(1))
def p_block_statement(p):
    '''block_statement : LBRACE statement_list RBRACE'''
    p[0] = ProgramNode(p[2] if p[2] is not None else [], line_no=p.lineno(1))
def p_return_statement(p):
    '''return_statement : RETURN expression SEMI
                        | RETURN SEMI'''
    p[0] = ReturnNode(p[2] if len(p) == 4 else None, line_no=p.lineno(1))
def p_empty_statement(p):
    '''empty_statement : SEMI'''
    p[0] = None
def p_assignment_statement(p):
    '''assignment_statement : IDENTIFIER ASSIGN expression SEMI
                            | array_access ASSIGN expression SEMI
                            | STAR expression ASSIGN expression SEMI'''
    if p.slice[1].type == 'STAR': p[0] = AssignmentNode(UnaryOpNode('*', p[2], line_no=p.lineno(1)), p[4], line_no=p.lineno(3))
    elif isinstance(p[1], str): p[0] = AssignmentNode(IdentifierNode(p[1], line_no=p.lineno(1)), p[3], line_no=p.lineno(2))
    else: p[0] = AssignmentNode(p[1], p[3], line_no=p.lineno(2))
def p_print_statement(p):
    '''print_statement : PRINT expression SEMI'''
    p[0] = PrintNode(p[2], line_no=p.lineno(1))
def p_if_statement(p):
    '''if_statement : IF LPAREN expression RPAREN statement %prec IFX
                    | IF LPAREN expression RPAREN statement ELSE statement'''
    if len(p) == 6: p[0] = IfNode(p[3], p[5], None, line_no=p.lineno(1))
    else: p[0] = IfNode(p[3], p[5], p[7], line_no=p.lineno(1))
def p_while_statement(p):
    '''while_statement : WHILE LPAREN expression RPAREN block_statement'''
    p[0] = WhileNode(p[3], p[5], line_no=p.lineno(1))
def p_for_initializer(p):
    '''for_initializer : type_specifier IDENTIFIER ASSIGN expression
                       | type_specifier IDENTIFIER
                       | IDENTIFIER ASSIGN expression
                       | expression'''
    if p.slice[1].type in ['INT', 'CHAR']:
        type_name = p[1]
        if len(p) == 5: p[0] = VarDeclNode(type_name, IdentifierNode(p[2], line_no=p.lineno(2)), p[4], line_no=p.lineno(1))
        else: p[0] = VarDeclNode(type_name, IdentifierNode(p[2], line_no=p.lineno(2)), None, line_no=p.lineno(1))
    elif len(p) == 4 and p.slice[2].type == 'ASSIGN': p[0] = AssignmentNode(IdentifierNode(p[1], line_no=p.lineno(1)), p[3], line_no=p.lineno(1))
    elif len(p) == 2: p[0] = p[1]
    else: p[0] = None
def p_for_initializer_opt(p):
    '''for_initializer_opt : for_initializer
                           | empty'''
    p[0] = p[1]
def p_for_cond_update_item(p):
    '''for_cond_update_item : IDENTIFIER ASSIGN expression
                            | expression'''
    if len(p) == 4 and p.slice[2].type == 'ASSIGN': p[0] = AssignmentNode(IdentifierNode(p[1], line_no=p.lineno(1)), p[3], line_no=p.lineno(1))
    elif len(p) == 2: p[0] = p[1]
    else: p[0] = None
def p_for_cond_update_opt(p):
    '''for_cond_update_opt : for_cond_update_item
                           | empty'''
    p[0] = p[1]
def p_for_statement(p):
    '''for_statement : FOR LPAREN for_initializer_opt SEMI for_cond_update_opt SEMI for_cond_update_opt RPAREN block_statement'''
    init_content=p[3]; cond_content=p[5]; update_content=p[7]; body_node=p[9]; init_node_for_fornode=None
    if init_content is not None:
        if isinstance(init_content,VarDeclNode): init_node_for_fornode=init_content
        elif isinstance(init_content,(ExpressionNode,AssignmentNode)):
            line_num=init_content.line_no if hasattr(init_content,'line_no') and init_content.line_no is not None else p.lineno(1)
            init_node_for_fornode=ExpressionStatementNode(init_content,line_no=line_num)
    condition_expr_node=cond_content; update_stmt_node=None
    if update_content is not None:
        if isinstance(update_content,(ExpressionNode,AssignmentNode)):
            line_num=update_content.line_no if hasattr(update_content,'line_no') and update_content.line_no is not None else p.lineno(1)
            update_stmt_node=ExpressionStatementNode(update_content,line_no=line_num)
    p[0]=ForNode(init_node_for_fornode,condition_expr_node,update_stmt_node,body_node,line_no=p.lineno(1))
def p_switch_statement(p):
    '''switch_statement : SWITCH LPAREN expression RPAREN LBRACE case_list RBRACE'''
    p[0] = SwitchNode(p[3], p[6], line_no=p.lineno(1))
def p_case_list(p):
    '''case_list : case_list case_block
                 | empty'''
    if len(p) == 3: lst = p[1] if p[1] is not None else []; lst.append(p[2]); p[0] = lst
    else: p[0] = []
def p_case_block(p):
    '''case_block : case_label statement_list'''
    value_node, line_num = p[1]; p[0] = CaseNode(value_node, p[2], line_no=line_num)
def p_case_label(p):
    '''case_label : CASE NUMBER COLON
                  | DEFAULT COLON'''
    if len(p) == 4: value_node = NumberNode(p[2], line_no=p.lineno(2)); p[0] = (value_node, p.lineno(1))
    else: p[0] = (None, p.lineno(1))
def p_break_statement(p):
    '''break_statement : BREAK SEMI'''
    p[0] = BreakNode()
def p_expression(p):
    '''expression : expression OR_LOGICAL expression_and
                  | expression_and'''
    if len(p) == 2: p[0] = p[1]
    else: p[0] = BinaryOpNode(p[2], p[1], p[3], line_no=p.slice[2].lineno)
def p_expression_and(p):
    '''expression_and : expression_and AND_LOGICAL expression_bitwise_or
                      | expression_bitwise_or'''
    if len(p) == 2: p[0] = p[1]
    else: p[0] = BinaryOpNode(p[2], p[1], p[3], line_no=p.slice[2].lineno)
def p_expression_bitwise_or(p):
    '''expression_bitwise_or : expression_bitwise_or BITWISE_OR expression_bitwise_xor
                             | expression_bitwise_xor'''
    if len(p) == 2: p[0] = p[1]
    else: p[0] = BinaryOpNode('|', p[1], p[3], line_no=p.slice[2].lineno)
def p_expression_bitwise_xor(p):
    '''expression_bitwise_xor : expression_bitwise_xor BITWISE_XOR expression_bitwise_and
                              | expression_bitwise_and'''
    if len(p) == 2: p[0] = p[1]
    else: p[0] = BinaryOpNode('^', p[1], p[3], line_no=p.slice[2].lineno)
def p_expression_bitwise_and(p):
    '''expression_bitwise_and : expression_bitwise_and AMPERSAND expression_equality
                              | expression_equality'''
    if len(p) == 2: p[0] = p[1]
    else: p[0] = BinaryOpNode('&', p[1], p[3], line_no=p.slice[2].lineno)
def p_expression_equality(p):
    '''expression_equality : expression_equality EQ expression_comparison
                           | expression_equality NEQ expression_comparison
                           | expression_comparison'''
    if len(p) == 2: p[0] = p[1]
    else: p[0] = BinaryOpNode(p[2], p[1], p[3], line_no=p.slice[2].lineno)
def p_expression_comparison(p):
    '''expression_comparison : expression_comparison LT expression_additive
                             | expression_comparison GT expression_additive
                             | expression_comparison LE expression_additive
                             | expression_comparison GE expression_additive
                             | expression_additive'''
    if len(p) == 2: p[0] = p[1]
    else: p[0] = BinaryOpNode(p[2], p[1], p[3], line_no=p.slice[2].lineno)
def p_expression_additive(p):
    '''expression_additive : expression_additive PLUS expression_multiplicative
                           | expression_additive MINUS expression_multiplicative
                           | expression_multiplicative'''
    if len(p) == 2: p[0] = p[1]
    else: p[0] = BinaryOpNode(p[2], p[1], p[3], line_no=p.slice[2].lineno)
def p_expression_multiplicative(p):
    '''expression_multiplicative : expression_multiplicative STAR expression_unary
                                 | expression_unary'''
    if len(p) == 2: p[0] = p[1]
    else: p[0] = BinaryOpNode(p[2], p[1], p[3], line_no=p.slice[2].lineno)
def p_expression_unary(p):
    '''expression_unary : NOT_LOGICAL expression_unary
                        | MINUS expression_unary %prec UMINUS
                        | AMPERSAND expression_unary %prec UNARY_PTR
                        | STAR expression_unary %prec UNARY_PTR
                        | BITWISE_NOT expression_unary
                        | postfix_expression'''
    if len(p) == 2: p[0] = p[1]
    else: op_symbol = '~' if p.slice[1].type == 'BITWISE_NOT' else p[1]; p[0] = UnaryOpNode(op_symbol, p[2], line_no=p.slice[1].lineno)
def p_postfix_expression(p):
    '''postfix_expression : primary_expression
                          | postfix_expression PLUSPLUS
                          | postfix_expression MINUSMINUS'''
    if len(p) == 2: p[0] = p[1]
    else: p[0] = PostfixOpNode(p[2], p[1], line_no=p.lineno(2))
def p_primary_expression(p):
    '''primary_expression : NUMBER
                          | STRING_LITERAL
                          | CHAR_LITERAL
                          | IDENTIFIER
                          | LPAREN expression RPAREN
                          | function_call_actual
                          | array_access'''
    if p.slice[1].type == 'NUMBER': p[0] = NumberNode(p[1], line_no=p.lineno(1))
    elif p.slice[1].type == 'STRING_LITERAL': p[0] = StringLiteralNode(p[1], line_no=p.lineno(1))
    elif p.slice[1].type == 'CHAR_LITERAL': p[0] = CharLiteralNode(p[1], line_no=p.lineno(1))
    elif p.slice[1].type == 'IDENTIFIER': p[0] = IdentifierNode(p[1], line_no=p.lineno(1))
    elif p.slice[1].type == 'LPAREN': p[0] = p[2]
    else: p[0] = p[1]
def p_array_access(p):
    '''array_access : IDENTIFIER LBRACKET expression RBRACKET'''
    p[0] = ArrayAccessNode(IdentifierNode(p[1], line_no=p.lineno(1)), p[3], line_no=p.lineno(1))
def p_function_call_actual(p):
    '''function_call_actual : IDENTIFIER LPAREN argument_list_opt RPAREN'''
    p[0] = FunctionCallNode(IdentifierNode(p[1], line_no=p.lineno(1)), p[3], line_no=p.lineno(1))
def p_argument_list_opt(p):
    '''argument_list_opt : argument_list
                         | empty'''
    p[0] = p[1] if p[1] is not None else []
def p_argument_list(p):
    '''argument_list : expression
                     | argument_list COMMA expression'''
    if len(p) == 2: p[0] = [p[1]]
    else: p[1].append(p[3]); p[0] = p[1]
def p_empty(p):
    '''empty :'''
    p[0] = None
_ply_parser_errors_found = False
def p_error(p):
    global _ply_parser_errors_found; _ply_parser_errors_found = True
    if p: print(f"PLY Parser: Error token '{p.type}' ('{p.value}') line {p.lineno} pos {p.lexpos}")
    else: print(f"PLY Parser: Syntax error at EOF.")
parser_ply = yacc(debug=0, write_tables=True, tabmodule="c_ssl_parsetab", debugfile="parser.out")
from code_generator import SALCodeGenerator
def compile_c_ssl_string_to_sal(c_ssl_code_string):
    global _ply_parser_errors_found
    _ply_parser_errors_found = False; lexer_ply.lineno = 1
    ast = parser_ply.parse(input=c_ssl_code_string, lexer=lexer_ply, tracking=True, debug=False)
    if _ply_parser_errors_found or not ast:
        if not ast and c_ssl_code_string.strip() and not _ply_parser_errors_found: print("C-SSL Parsing FAILED: No AST generated (non-empty input), but no PLY errors reported.")
        elif not ast and not c_ssl_code_string.strip(): print("C-SSL Info: Input empty or comments only."); return "// No effective input", False
        elif _ply_parser_errors_found: print("C-SSL Parsing FAILED due to syntax errors reported by p_error.")
        else: print("C-SSL Parsing FAILED: Unknown reason, no AST, no p_error.")
        return None, True
    code_gen = SALCodeGenerator()
    generated_sal_code = ""; code_gen_had_errors = False
    try: generated_sal_code = code_gen.generate(ast)
    except Exception as e: print(f"FATAL C-SSL CodeGen Error: {e}"); import traceback; traceback.print_exc(); code_gen_had_errors = True
    if code_gen_had_errors or (ast and not generated_sal_code.strip() and hasattr(ast, 'statements') and ast.statements):
        if not generated_sal_code.strip() and not code_gen_had_errors and hasattr(ast, 'statements') and ast.statements: print("C-SSL Compilation generated empty SAL code from non-empty AST.")
        else: print("C-SSL Compilation FAILED during code generation.")
        return None, True
    return generated_sal_code, False
if __name__ == '__main__':
    test_char_and_string = """
    func main() {
        int i = 123;
        char c;
        char *pc; // Test pointer declaration
        c = 'X';    // Test char literal
        char name[10];
        print "This is a test string with a newline.\\n";
    }
    """
    ssl_file = "test_char_direct.ssl"
    try:
        with open(ssl_file, 'w') as f: f.write(test_char_and_string)
        print(f"Test SSL written to '{ssl_file}'")
    except Exception as e: print(f"Error creating test file '{ssl_file}': {e}."); sys.exit(1)
    print(f"\n--- Running c_ply_compiler.py directly with 'char' and string literals ---")
    generated_sal, had_errors = compile_c_ssl_string_to_sal(test_char_and_string)
    if had_errors or generated_sal is None:
        print("\nC-SSL COMPILATION FAILED.")
    else:
        print("\nC-SSL PARSING SUCCESSFUL.")
        print("NOTE: Code generation is not yet fully implemented for these new types.")
        print("\n--- Generated SAL (may be incorrect) ---")
        print(generated_sal)
