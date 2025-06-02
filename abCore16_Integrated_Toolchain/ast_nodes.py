# ast_nodes.py
# Contains class definitions for Abstract Syntax Tree nodes
# used by the PLY-based C-like SSL compiler.

class Node:
    """Base class for all AST nodes."""
    def __init__(self, line_no=None):
        self.line_no = line_no

    def accept(self, visitor):
        method_name = 'visit_' + self.__class__.__name__
        visitor_method = getattr(visitor, method_name, visitor.generic_visit)
        return visitor_method(self)

class ProgramNode(Node):
    """Represents the entire program or a block of statements."""
    def __init__(self, statements, line_no=None):
        super().__init__(line_no)
        self.statements = statements if statements is not None else []

class StatementNode(Node):
    pass

class AssignmentNode(StatementNode):
    def __init__(self, target_name, value_expr, line_no=None): # target_name is IdentifierNode, value_expr is ExpressionNode
        super().__init__(line_no)
        self.target_name = target_name
        self.value_expr = value_expr

class PrintNode(StatementNode):
    def __init__(self, expression, line_no=None):
        super().__init__(line_no)
        self.expression = expression

class IfNode(StatementNode):
    def __init__(self, condition, true_block, false_block=None, line_no=None):
        super().__init__(line_no)
        self.condition = condition
        self.true_block = true_block
        self.false_block = false_block

class WhileNode(StatementNode):
    def __init__(self, condition, body_block, line_no=None):
        super().__init__(line_no)
        self.condition = condition
        self.body_block = body_block

class ExpressionNode(Node):
    pass

class NumberNode(ExpressionNode):
    def __init__(self, value, line_no=None):
        super().__init__(line_no)
        self.value = value

class IdentifierNode(ExpressionNode):
    def __init__(self, name, line_no=None):
        super().__init__(line_no)
        self.name = name

class BinaryOpNode(ExpressionNode):
    def __init__(self, op, left, right, line_no=None): # op is the operator string e.g. '+'
        super().__init__(line_no)
        self.op = op
        self.left = left
        self.right = right

class UnaryOpNode(ExpressionNode):
    def __init__(self, op, operand, line_no=None): # op is the operator string e.g. '-'
        super().__init__(line_no)
        self.op = op
        self.operand = operand
