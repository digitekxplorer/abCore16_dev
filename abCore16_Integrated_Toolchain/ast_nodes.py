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


class AssignmentNode(StatementNode):
    def __init__(self, target_name, value_expr, line_no=None):
        super().__init__(line_no)
        self.target_name = target_name  # Can be IdentifierNode or ArrayAccessNode
        self.value_expr = value_expr  # ExpressionNode

    def __repr__(self):
        return f"AssignmentNode(target={self.target_name!r}, value_expr={self.value_expr!r})"


class VarDeclNode(StatementNode):
    """Represents a variable declaration, e.g., 'var x;' or 'var x = 10;'."""

    def __init__(self, var_name_node, init_expr_node, line_no=None):
        super().__init__(line_no)
        self.var_name_node = var_name_node  # IdentifierNode for the variable name
        self.init_expr_node = init_expr_node  # ExpressionNode for initializer, or None

    def __repr__(self):
        return f"VarDeclNode(var_name='{self.var_name_node.name}', initialized={self.init_expr_node is not None})"


class ArrayDeclNode(StatementNode):
    """Represents a global array declaration, e.g., 'var my_arr[10];'."""
    def __init__(self, var_name_node, size_value, line_no=None):
        super().__init__(line_no)
        self.var_name_node = var_name_node  # IdentifierNode
        self.size = size_value              # Integer value for the size

    def __repr__(self):
        return f"ArrayDeclNode(name='{self.var_name_node.name}', size={self.size})"


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
        self.init_node = init_node
        self.condition_expr_node = condition_expr_node
        self.update_expr_stmt_node = update_expr_stmt_node
        self.body_node = body_node

    def __repr__(self):
        init_repr = "None"
        if self.init_node: init_repr = f"{self.init_node!r}"
        cond_repr = "None"
        if self.condition_expr_node: cond_repr = f"{self.condition_expr_node!r}"
        update_repr = "None"
        if self.update_expr_stmt_node:
            if isinstance(self.update_expr_stmt_node, ExpressionStatementNode) and self.update_expr_stmt_node.expression:
                update_repr = f"ExprStmt({self.update_expr_stmt_node.expression!r})"
            else:
                update_repr = f"{self.update_expr_stmt_node!r}"
        body_stmts_count = len(self.body_node.statements) if self.body_node and hasattr(self.body_node, 'statements') else 0
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


class IdentifierNode(ExpressionNode):
    def __init__(self, name, line_no=None):
        super().__init__(line_no)
        self.name = name

    def __repr__(self):
        return f"IdentifierNode(name='{self.name}')"


class ArrayAccessNode(ExpressionNode):
    """Represents accessing an array element, e.g., 'my_arr[i]'."""
    def __init__(self, name_node, index_expr_node, line_no=None):
        super().__init__(line_no)
        self.name_node = name_node          # IdentifierNode for the array name
        self.index_expr_node = index_expr_node # ExpressionNode for the index

    def __repr__(self):
        return f"ArrayAccessNode(name='{self.name_node.name}', index={self.index_expr_node!r})"


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


class FunctionDefinitionNode(Node):
    def __init__(self, name_node, params_nodes, body_node, line_no=None):
        super().__init__(line_no)
        self.name_node = name_node  # IdentifierNode
        self.params_nodes = params_nodes  # List of IdentifierNodes
        self.body_node = body_node  # ProgramNode

    def __repr__(self):
        params_repr = [p.name for p in self.params_nodes] if self.params_nodes else []
        body_stmts_count = len(self.body_node.statements) if self.body_node and hasattr(self.body_node, 'statements') else 0
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
        self.expression = expression

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

class PostfixOpNode(ExpressionNode):
    """Node for postfix operations like p++ or p--."""
    def __init__(self, op, operand, line_no=None):
        self.op = op          # The operator string, e.g., '++' or '--'
        self.operand = operand # The node being operated on (e.g., IdentifierNode for 'p')
        self.line_no = line_no

    def __repr__(self):
        return f"PostfixOpNode({self.op!r}, {self.operand!r})"

    def accept(self, visitor):
        # We assume a visitor will have a method like visit_PostfixOpNode
        if hasattr(visitor, 'visit_PostfixOpNode'):
            return visitor.visit_PostfixOpNode(self)
        else:
            return visitor.generic_visit(self)

class BreakNode(StatementNode):
    """Node for the 'break' statement."""
    def __repr__(self):
        return "BreakNode"

    def accept(self, visitor):
        if hasattr(visitor, 'visit_BreakNode'):
            return visitor.visit_BreakNode(self)
        else:
            return visitor.generic_visit(self)


class CaseNode(StatementNode):
    """Node for a single 'case' or 'default' block within a switch."""
    def __init__(self, value_expr, statements, line_no=None):
        # value_expr is a NumberNode for 'case', or None for 'default'
        self.value_expr = value_expr
        self.statements = statements if statements is not None else []
        self.line_no = line_no

    def __repr__(self):
        val_repr = "DEFAULT" if self.value_expr is None else repr(self.value_expr)
        return f"CaseNode({val_repr}, {self.statements!r})"

    def accept(self, visitor):
        if hasattr(visitor, 'visit_CaseNode'):
            return visitor.visit_CaseNode(self)
        else:
            return visitor.generic_visit(self)


class SwitchNode(StatementNode):
    """Node for a 'switch' statement."""
    def __init__(self, condition, cases, line_no=None):
        self.condition = condition # The expression in switch ( ... )
        self.cases = cases         # A list of CaseNode objects
        self.line_no = line_no

    def __repr__(self):
        return f"SwitchNode({self.condition!r}, {self.cases!r})"

    def accept(self, visitor):
        if hasattr(visitor, 'visit_SwitchNode'):
            return visitor.visit_SwitchNode(self)
        else:
            return visitor.generic_visit(self)
