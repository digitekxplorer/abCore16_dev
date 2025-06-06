# c_ply_compiler.py

import os
import sys
from ply.lex import lex
from ply.yacc import yacc
# import logging # No longer needed if parse(debug=True) is off

from ast_nodes import (
    Node, ProgramNode, StatementNode, AssignmentNode, PrintNode, IfNode, WhileNode,
    ExpressionNode, NumberNode, IdentifierNode, BinaryOpNode, UnaryOpNode,
    FunctionDefinitionNode, ReturnNode,
    ExpressionStatementNode, FunctionCallNode,
    ForNode, VarDeclNode
)

# --- Tokenizer (Lexer) Definition ---
# ... (tokens, t_ignore, t_rules, reserved, t_IDENTIFIER, t_NUMBER, etc. - NO CHANGES HERE) ...
tokens = (
    'NUMBER', 'IDENTIFIER',
    'PLUS', 'MINUS', 'TIMES',
    'ASSIGN', 'SEMI',
    'LPAREN', 'RPAREN', 'LBRACE', 'RBRACE', 'COMMA',
    'EQ', 'NEQ', 'LE', 'GE', 'LT', 'GT',
    'AND_LOGICAL', 'OR_LOGICAL', 'NOT_LOGICAL',
    'PRINT', 'IF', 'ELSE', 'WHILE', 'FOR',
    'FUNC', 'RETURN', 'VAR'
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
t_PLUS = r'\+'
t_MINUS = r'-'
t_TIMES = r'\*'
t_SEMI = r';'
t_LPAREN = r'\('
t_RPAREN = r'\)'
t_LBRACE = r'\{'
t_RBRACE = r'\}'
t_COMMA = r','

reserved = {
    'print': 'PRINT', 'if': 'IF', 'else': 'ELSE', 'while': 'WHILE', 'for': 'FOR',
    'func': 'FUNC', 'return': 'RETURN', 'var': 'VAR',
}


def t_IDENTIFIER(t):
    r'[a-zA-Z_][a-zA-Z_0-9]*'
    t.type = reserved.get(t.value.lower(), 'IDENTIFIER')
    return t


def t_NUMBER(t):
    r'\d+'
    try:
        t.value = int(t.value)
    except ValueError:
        print(f"PLY Lexer: Int value too large '{t.value}' line {t.lexer.lineno}");
        t.value = 0
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


lexer_ply = lex(debug=0)  # Lexer debug usually kept at 0 unless debugging tokenization

# --- Parser (YACC) Definition ---
# ... (precedence, start symbol - NO CHANGES HERE) ...
precedence = (
    ('left', 'OR_LOGICAL'), ('left', 'AND_LOGICAL'),
    ('nonassoc', 'EQ', 'NEQ', 'LT', 'GT', 'LE', 'GE'),
    ('left', 'PLUS', 'MINUS'), ('left', 'TIMES'),
    ('right', 'NOT_LOGICAL', 'UMINUS')
)
start = 'program'


# ... (All your p_rule functions: p_program, p_top_level_declaration_list, ...,
#      p_for_initializer, p_for_initializer_opt,
#      p_for_cond_update_item, p_for_cond_update_opt, p_for_statement,
#      p_expression, ..., p_empty - NO CHANGES TO THE RULE LOGIC ITSELF) ...
# --- Make sure any "print(f"DEBUG: p_expression_statement...")" lines ARE REMOVED from p_rules ---
def p_program(p):
    '''program : top_level_declaration_list'''
    p[0] = ProgramNode(p[1] if p[1] is not None else [], line_no=1)


def p_top_level_declaration_list(p):
    '''top_level_declaration_list : top_level_declaration_list top_level_declaration
                                  | empty'''
    if len(p) == 3:
        lst = p[1] if p[1] is not None else []
        if p[2] is not None: lst.append(p[2])
        p[0] = lst
    else:
        p[0] = []


def p_top_level_declaration(p):
    '''top_level_declaration : function_definition
                             | variable_declaration_statement
                             | statement_for_global_scope'''
    p[0] = p[1]


def p_statement_for_global_scope(p):
    '''statement_for_global_scope : assignment_statement
                                  | print_statement
                                  | expression_statement
                                  | empty_statement'''
    p[0] = p[1]


def p_variable_declaration_statement(p):
    '''variable_declaration_statement : VAR IDENTIFIER SEMI
                                      | VAR IDENTIFIER ASSIGN expression SEMI'''
    if len(p) == 4:
        p[0] = VarDeclNode(IdentifierNode(p[2], line_no=p.lineno(2)), None, line_no=p.lineno(1))
    else:
        p[0] = VarDeclNode(IdentifierNode(p[2], line_no=p.lineno(2)), p[4], line_no=p.lineno(1))


def p_function_definition(p):
    '''function_definition : FUNC IDENTIFIER LPAREN parameter_list_opt RPAREN block_statement'''
    p[0] = FunctionDefinitionNode(IdentifierNode(p[2], line_no=p.lineno(2)), p[4], p[6], line_no=p.lineno(1))


def p_parameter_list_opt(p):
    '''parameter_list_opt : parameter_list
                          | empty'''
    p[0] = p[1] if p[1] is not None else []


def p_parameter_list(p):
    '''parameter_list : IDENTIFIER
                      | parameter_list COMMA IDENTIFIER'''
    if len(p) == 2:
        p[0] = [IdentifierNode(p[1], line_no=p.lineno(1))]
    else:
        p[1].append(IdentifierNode(p[3], line_no=p.lineno(3)));
        p[0] = p[1]


def p_statement_list(p):
    '''statement_list : statement_list statement
                      | empty'''
    if len(p) == 3:
        lst = p[1] if p[1] is not None else []
        if p[2] is not None: lst.append(p[2])
        p[0] = lst
    else:
        p[0] = []


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
                 | variable_declaration_statement'''
    p[0] = p[1]


def p_expression_statement(p):
    '''expression_statement : expression SEMI'''
    # REMOVE DEBUG PRINT: print(f"DEBUG: p_expression_statement: p[1] is {p[1]!r}, type is {type(p[1])}")
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
    p[0] = p[2] if len(p) == 3 else None


def p_while_statement(p):
    '''while_statement : WHILE LPAREN expression RPAREN block_statement'''
    p[0] = WhileNode(p[3], p[5], line_no=p.lineno(1))


def p_for_initializer(p):
    '''for_initializer : VAR IDENTIFIER ASSIGN expression
                       | VAR IDENTIFIER
                       | IDENTIFIER ASSIGN expression
                       | expression
    '''
    if p.slice[1].type == 'VAR':
        if len(p) == 5:
            p[0] = VarDeclNode(IdentifierNode(p[2], line_no=p.lineno(2)), p[4], line_no=p.lineno(1))
        else:
            p[0] = VarDeclNode(IdentifierNode(p[2], line_no=p.lineno(2)), None, line_no=p.lineno(1))
    elif len(p) == 4 and p.slice[2].type == 'ASSIGN':
        p[0] = AssignmentNode(IdentifierNode(p[1], line_no=p.lineno(1)), p[3], line_no=p.lineno(1))
    elif len(p) == 2:
        p[0] = p[1]
    else:
        p[0] = None


def p_for_initializer_opt(p):
    '''for_initializer_opt : for_initializer
                           | empty'''
    p[0] = p[1]


def p_for_cond_update_item(p):
    '''for_cond_update_item : IDENTIFIER ASSIGN expression
                            | expression
    '''
    if len(p) == 4 and p.slice[2].type == 'ASSIGN':
        p[0] = AssignmentNode(IdentifierNode(p[1], line_no=p.lineno(1)), p[3], line_no=p.lineno(1))
    elif len(p) == 2:
        p[0] = p[1]
    else:
        p[0] = None


def p_for_cond_update_opt(p):
    '''for_cond_update_opt : for_cond_update_item
                           | empty'''
    p[0] = p[1]


def p_for_statement(p):
    '''for_statement : FOR LPAREN for_initializer_opt SEMI for_cond_update_opt SEMI for_cond_update_opt RPAREN block_statement'''
    init_content = p[3]
    cond_content = p[5]
    update_content = p[7]
    body_node = p[9]
    init_node_for_fornode = None
    if init_content is not None:
        if isinstance(init_content, VarDeclNode):
            init_node_for_fornode = init_content
        elif isinstance(init_content, (ExpressionNode, AssignmentNode)):
            line_num = init_content.line_no if hasattr(init_content,
                                                       'line_no') and init_content.line_no is not None else p.lineno(1)
            init_node_for_fornode = ExpressionStatementNode(init_content, line_no=line_num)
        else:
            init_node_for_fornode = None

    condition_expr_node = cond_content
    update_stmt_node = None
    if update_content is not None:
        if isinstance(update_content, (ExpressionNode, AssignmentNode)):
            line_num = update_content.line_no if hasattr(update_content,
                                                         'line_no') and update_content.line_no is not None else p.lineno(
                1)
            update_stmt_node = ExpressionStatementNode(update_content, line_no=line_num)
        else:
            update_stmt_node = None

    p[0] = ForNode(init_node_for_fornode, condition_expr_node, update_stmt_node, body_node, line_no=p.lineno(1))


def p_expression(p):
    '''expression : expression OR_LOGICAL expression_and
                  | expression_and'''
    if len(p) == 2:
        p[0] = p[1]
    else:
        p[0] = BinaryOpNode(p[2], p[1], p[3], line_no=p.slice[2].lineno)


# ... (p_expression_and through p_primary_expression - NO CHANGES HERE) ...
def p_expression_and(p):
    '''expression_and : expression_and AND_LOGICAL expression_equality
                      | expression_equality'''
    if len(p) == 2:
        p[0] = p[1]
    else:
        p[0] = BinaryOpNode(p[2], p[1], p[3], line_no=p.slice[2].lineno)


def p_expression_equality(p):
    '''expression_equality : expression_equality EQ expression_comparison
                           | expression_equality NEQ expression_comparison
                           | expression_comparison'''
    if len(p) == 2:
        p[0] = p[1]
    else:
        p[0] = BinaryOpNode(p[2], p[1], p[3], line_no=p.slice[2].lineno)


def p_expression_comparison(p):
    '''expression_comparison : expression_comparison LT expression_additive
                             | expression_comparison GT expression_additive
                             | expression_comparison LE expression_additive
                             | expression_comparison GE expression_additive
                             | expression_additive'''
    if len(p) == 2:
        p[0] = p[1]
    else:
        p[0] = BinaryOpNode(p[2], p[1], p[3], line_no=p.slice[2].lineno)


def p_expression_additive(p):
    '''expression_additive : expression_additive PLUS expression_multiplicative
                           | expression_additive MINUS expression_multiplicative
                           | expression_multiplicative'''
    if len(p) == 2:
        p[0] = p[1]
    else:
        p[0] = BinaryOpNode(p[2], p[1], p[3], line_no=p.slice[2].lineno)


def p_expression_multiplicative(p):
    '''expression_multiplicative : expression_multiplicative TIMES expression_unary
                                 | expression_unary'''
    if len(p) == 2:
        p[0] = p[1]
    else:
        p[0] = BinaryOpNode(p[2], p[1], p[3], line_no=p.slice[2].lineno)


def p_expression_unary(p):
    '''expression_unary : NOT_LOGICAL expression_unary
                        | MINUS expression_unary %prec UMINUS
                        | primary_expression'''
    if len(p) == 2:
        p[0] = p[1]
    else:
        p[0] = UnaryOpNode(p[1], p[2], line_no=p.slice[1].lineno)


def p_primary_expression(p):
    '''primary_expression : NUMBER
                          | IDENTIFIER
                          | LPAREN expression RPAREN
                          | function_call_actual'''
    if p.slice[1].type == 'NUMBER':
        p[0] = NumberNode(p[1], line_no=p.lineno(1))
    elif p.slice[1].type == 'IDENTIFIER':
        p[0] = IdentifierNode(p[1], line_no=p.lineno(1))
    elif p.slice[1].type == 'LPAREN':
        p[0] = p[2]
    else:
        p[0] = p[1]


# ... (p_function_call_actual, p_argument_list_opt, p_argument_list, p_empty - NO CHANGES HERE) ...
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
    if len(p) == 2:
        p[0] = [p[1]]
    else:
        p[1].append(p[3]);
        p[0] = p[1]


def p_empty(p):
    '''empty :'''
    p[0] = None


_ply_parser_errors_found = False


def p_error(p):
    global _ply_parser_errors_found;
    _ply_parser_errors_found = True
    if p:
        print(f"PLY Parser: Error token '{p.type}' ('{p.value}') line {p.lineno} pos {p.lexpos}")
    else:
        print(f"PLY Parser: Syntax error at EOF.")


# Changed debug to 0 to silence parser.out generation for normal runs.
# write_tables can be True, tabmodule ensures c_ssl_parsetab.py is used/generated.
parser_ply = yacc(debug=0, write_tables=True, tabmodule="c_ssl_parsetab")
# REMOVED: print("DEBUG: c_ply_compiler.py: parser_ply object created/recreated.")

from code_generator import SALCodeGenerator


def compile_c_ssl_string_to_sal(c_ssl_code_string):
    global _ply_parser_errors_found
    _ply_parser_errors_found = False
    lexer_ply.lineno = 1

    # REMOVED: print("\nPLY: Attempting to parse with runtime debugging...")
    # Changed debug to False for normal operation
    ast = parser_ply.parse(input=c_ssl_code_string, lexer=lexer_ply, tracking=True, debug=False)
    # REMOVED: print("PLY: Parsing attempt finished.\n")

    if _ply_parser_errors_found or not ast:
        if not ast and c_ssl_code_string.strip() and not _ply_parser_errors_found:
            print(
                "C-SSL Parsing FAILED: No AST generated (non-empty input), but no PLY errors reported by p_error. Check grammar or yacc debug output.")
        elif not ast and not c_ssl_code_string.strip():
            print("C-SSL Info: Input empty or comments only.");
            return "// No effective input", False
        elif _ply_parser_errors_found:
            print("C-SSL Parsing FAILED due to syntax errors reported by p_error.")
        else:
            print("C-SSL Parsing FAILED: Unknown reason, no AST, no p_error. Check yacc debug output if enabled.")
        return None, True

    code_gen = SALCodeGenerator()
    generated_sal_code = ""
    code_gen_had_errors = False
    try:
        generated_sal_code = code_gen.generate(ast)
    except Exception as e:
        print(f"FATAL C-SSL CodeGen Error: {e}")
        import traceback
        traceback.print_exc()
        code_gen_had_errors = True

    if code_gen_had_errors or (
            ast and not generated_sal_code.strip() and hasattr(ast, 'statements') and ast.statements):
        if not generated_sal_code.strip() and not code_gen_had_errors and hasattr(ast, 'statements') and ast.statements:
            print("C-SSL Compilation generated empty SAL code from non-empty AST without explicit codegen errors.")
        else:
            print("C-SSL Compilation FAILED during code generation.")
        return None, True

    return generated_sal_code, False


if __name__ == '__main__':
    # ... (if __name__ block can remain as is for your testing) ...
    test_ssl_for_var_init_content = """
    func main() {
        var sum_total; 
        sum_total = 0;

        for (var i = 1; i <= 2; i = i + 1) { 
            print i; 
            sum_total = sum_total + i;
        }

        print 1000; 

        for (var j = 5; j >= 3; j = j - 1) { 
            print j; 
            sum_total = sum_total + j;
        }

        print 2000;
        print sum_total; 

        var k; 
        for (k = 10; k < 12; k = k+1) { 
            print k; 
        }
    }
    """

    ssl_input_file_path = "test_for_var_init_ply_direct.ssl"
    sal_output_file_path = "SAL_from_c_ply_for_var_init_direct.sal"

    try:
        with open(ssl_input_file_path, 'w') as f:
            f.write(test_ssl_for_var_init_content)
        print(f"Test SSL content written to '{ssl_input_file_path}'")
    except Exception as e:
        print(f"Error creating test file '{ssl_input_file_path}': {e}.")
        sys.exit(1)

    print(f"\n--- Running c_ply_compiler.py (For Loop Var Init Test) directly from '{ssl_input_file_path}' ---")

    generated_sal, had_errors = compile_c_ssl_string_to_sal(test_ssl_for_var_init_content)

    if had_errors or generated_sal is None:
        print("\nC-SSL COMPILATION FAILED (For Loop Var Init Test - Direct Run).")
    else:
        print("\nC-SSL COMPILATION SUCCESSFUL (For Loop Var Init Test - Direct Run).")
        final_sal_for_test = generated_sal.strip()
        if final_sal_for_test and not final_sal_for_test.upper().endswith("HALT"):
            final_sal_for_test += "\nHALT // Auto-added by c_ply_compiler.py __main__ for testing"
            print("(Appended HALT for standalone SAL testing in c_ply_compiler.py __main__)")
        elif not final_sal_for_test:
            final_sal_for_test = "HALT // Program was empty, HALT added by c_ply_compiler.py __main__"
            print("(Program was empty, HALT added for standalone SAL testing in c_ply_compiler.py __main__)")

        try:
            with open(sal_output_file_path, 'w') as f:
                f.write(final_sal_for_test)
            print(f"Full SAL saved to '{sal_output_file_path}'")
        except IOError as e:
            print(f"Error saving SAL: {e}")
