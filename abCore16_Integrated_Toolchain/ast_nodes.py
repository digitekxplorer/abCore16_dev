# ast_nodes.py
# Contains class definitions for Abstract Syntax Tree nodes
# used by the PLY-based C-like SSL compiler.

class Node:
    """Base class for all AST nodes."""

    def __init__(self, line_no=None):
        self.line_no = line_no

    def accept(self, visitor):
        method_name = 'visit_' + self.__class__.__name__
        visitor_method = getattr(visitor, method_name, None)

        if visitor_method:
            return visitor_method(self)
        elif hasattr(visitor, 'generic_visit'):
            return visitor.generic_visit(self)
        else:
            return None


class ProgramNode(Node):
    """Represents the entire program or a block of statements."""

    def __init__(self, statements, line_no=None):
        super().__init__(line_no)
        self.statements = statements if statements is not None else []

    def __repr__(self):
        return f"ProgramNode(statements_count={len(self.statements)})"


class StatementNode(Node):
    pass


class ExpressionNode(Node):
    pass


class AssignmentNode(StatementNode):  # Can also be used as an expression in some contexts
    def __init__(self, target_name, value_expr, line_no=None):
        super().__init__(line_no)
        self.target_name = target_name  # IdentifierNode
        self.value_expr = value_expr  # ExpressionNode

    def __repr__(self):
        return f"AssignmentNode(target='{self.target_name.name}', value_expr={self.value_expr!r})"


class VarDeclNode(StatementNode):
    """Represents a variable declaration, e.g., 'var x;' or 'var x = 10;'."""

    def __init__(self, var_name_node, init_expr_node, line_no=None):
        super().__init__(line_no)
        self.var_name_node = var_name_node  # IdentifierNode for the variable name
        self.init_expr_node = init_expr_node  # ExpressionNode for initializer, or None

    def __repr__(self):
        return f"VarDeclNode(var_name='{self.var_name_node.name}', initialized={self.init_expr_node is not None})"


class PrintNode(StatementNode):
    def __init__(self, expression, line_no=None):
        super().__init__(line_no)
        self.expression = expression  # ExpressionNode

    def __repr__(self):
        return f"PrintNode(expr={self.expression!r})"


class IfNode(StatementNode):
    def __init__(self, condition, true_block, false_block=None, line_no=None):
        super().__init__(line_no)
        self.condition = condition  # ExpressionNode
        self.true_block = true_block  # ProgramNode
        self.false_block = false_block  # ProgramNode or None

    def __repr__(self):
        return f"IfNode(condition={self.condition!r}, has_else={self.false_block is not None})"


class WhileNode(StatementNode):
    def __init__(self, condition, body_block, line_no=None):
        super().__init__(line_no)
        self.condition = condition  # ExpressionNode
        self.body_block = body_block  # ProgramNode

    def __repr__(self):
        return f"WhileNode(condition={self.condition!r})"


class ForNode(StatementNode):
    def __init__(self, init_node, condition_expr_node, update_expr_stmt_node, body_node, line_no=None):
        super().__init__(line_no)
        # init_node can be:
        # 1. VarDeclNode (for `for (var i = 0; ...`)
        # 2. ExpressionStatementNode (for `for (i = 0; ...` where i is pre-declared)
        # 3. None (for `for ( ; ...`)
        self.init_node = init_node

        # condition_expr_node will be an ExpressionNode or AssignmentNode (if grammar allows it as expr) or None
        self.condition_expr_node = condition_expr_node

        # update_expr_stmt_node will be an ExpressionStatementNode (wrapping the update expression/assignment) or None
        self.update_expr_stmt_node = update_expr_stmt_node

        # body_node will be a ProgramNode (representing the block statement)
        self.body_node = body_node

    def __repr__(self):
        init_repr = "None"
        if self.init_node:
            init_repr = f"{self.init_node!r}"

        cond_repr = "None"
        if self.condition_expr_node:
            cond_repr = f"{self.condition_expr_node!r}"

        update_repr = "None"
        if self.update_expr_stmt_node:
            # If it's an ExpressionStatementNode, show its internal expression for better repr
            if isinstance(self.update_expr_stmt_node,
                          ExpressionStatementNode) and self.update_expr_stmt_node.expression:
                update_repr = f"ExprStmt({self.update_expr_stmt_node.expression!r})"
            else:
                update_repr = f"{self.update_expr_stmt_node!r}"

        body_stmts_count = len(self.body_node.statements) if self.body_node and hasattr(self.body_node,
                                                                                        'statements') else 0

        return (f"ForNode(init={init_repr}, "
                f"cond={cond_repr}, "
                f"update={update_repr}, "
                f"body_stmts={body_stmts_count})")


class NumberNode(ExpressionNode):
    def __init__(self, value, line_no=None):
        super().__init__(line_no)
        self.value = value

    def __repr__(self):
        return f"NumberNode(value={self.value})"


class IdentifierNode(ExpressionNode):  # Also used as target in AssignmentNode and var_name in VarDeclNode
    def __init__(self, name, line_no=None):
        super().__init__(line_no)
        self.name = name

    def __repr__(self):
        return f"IdentifierNode(name='{self.name}')"


class BinaryOpNode(ExpressionNode):
    def __init__(self, op, left, right, line_no=None):
        super().__init__(line_no)
        self.op = op
        self.left = left  # ExpressionNode
        self.right = right  # ExpressionNode

    def __repr__(self):
        return f"BinaryOpNode(op='{self.op}', left={self.left!r}, right={self.right!r})"


class UnaryOpNode(ExpressionNode):
    def __init__(self, op, operand, line_no=None):
        super().__init__(line_no)
        self.op = op
        self.operand = operand  # ExpressionNode

    def __repr__(self):
        return f"UnaryOpNode(op='{self.op}', operand={self.operand!r})"


class FunctionDefinitionNode(Node):  # A top-level declaration
    def __init__(self, name_node, params_nodes, body_node, line_no=None):
        super().__init__(line_no)
        self.name_node = name_node  # IdentifierNode
        self.params_nodes = params_nodes  # List of IdentifierNodes
        self.body_node = body_node  # ProgramNode

    def __repr__(self):
        params_repr = [p.name for p in self.params_nodes] if self.params_nodes else []
        body_stmts_count = len(self.body_node.statements) if self.body_node and hasattr(self.body_node,
                                                                                        'statements') else 0
        return f"FunctionDefinitionNode(name='{self.name_node.name}', params={params_repr}, body_stmts={body_stmts_count})"


class ReturnNode(StatementNode):
    def __init__(self, expr_node, line_no=None):
        super().__init__(line_no)
        self.expr_node = expr_node  # ExpressionNode or None

    def __repr__(self):
        return f"ReturnNode(expr_present={self.expr_node is not None})"


class ExpressionStatementNode(StatementNode):
    def __init__(self, expression, line_no=None):
        super().__init__(line_no)
        self.expression = expression  # ExpressionNode (could be AssignmentNode if assignment is an expression)

    def __repr__(self):
        return f"ExpressionStatementNode(expr={self.expression!r})"


class FunctionCallNode(ExpressionNode):
    def __init__(self, name_node, args_nodes, line_no=None):
        super().__init__(line_no)
        self.name_node = name_node  # IdentifierNode
        self.args_nodes = args_nodes  # List of ExpressionNodes

    def __repr__(self):
        args_repr_str = ", ".join([repr(arg) for arg in self.args_nodes]) if self.args_nodes else ""
        return f"FunctionCallNode(name='{self.name_node.name}', args=[{args_repr_str}])"
        
