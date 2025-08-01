# ast_nodes.py
# Contains class definitions for Abstract Syntax Tree nodes
# used by the PLY-based C-like SSL compiler.
# MODIFIED: Added StringLiteralNode.

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

# --- CHANGE #1: New AST node for string literals ---
class StringLiteralNode(ExpressionNode):
    """Represents a string literal, e.g., "Hello"."""
    def __init__(self, value, line_no=None):
        super().__init__(line_no)
        self.value = value  # The raw string content

    def __repr__(self):
        # Display escaped characters for clarity in debug output
        return f'StringLiteralNode(value="{self.value.encode("unicode_escape").decode("utf-8")}")'

# --- ADD THIS NEW CLASS ---
class CharLiteralNode(ExpressionNode):
    """Represents a character literal, e.g., 'A'."""
    def __init__(self, value, line_no=None):
        super().__init__(line_no)
        self.value = value

    def __repr__(self):
        return f"CharLiteralNode(value='{self.value}')"


class AssignmentNode(StatementNode):
    def __init__(self, target_name, value_expr, line_no=None):
        super().__init__(line_no)
        self.target_name = target_name
        self.value_expr = value_expr

    def __repr__(self):
        return f"AssignmentNode(target={self.target_name!r}, value_expr={self.value_expr!r})"

class VarDeclNode(StatementNode):
    """Represents a variable declaration, e.g., 'int x;' or 'char c;'."""

    # The only change is adding 'is_pointer=False' to the constructor
    def __init__(self, data_type, var_name_node, init_expr_node, is_pointer=False, line_no=None):
        super().__init__(line_no)
        self.data_type = data_type
        self.var_name_node = var_name_node
        self.init_expr_node = init_expr_node
        self.is_pointer = is_pointer # And adding this line

    def __repr__(self):
        # Optional: Update repr to show pointer status
        ptr_str = "*" if self.is_pointer else ""
        return f"VarDeclNode(type='{self.data_type}{ptr_str}', var_name='{self.var_name_node.name}', initialized={self.init_expr_node is not None})"

class ArrayDeclNode(StatementNode):
    """Represents a global array declaration, e.g., 'int my_arr[10];'."""
    def __init__(self, data_type, var_name_node, size_value, line_no=None):
        super().__init__(line_no)
        self.data_type = data_type
        self.var_name_node = var_name_node
        self.size = size_value

    def __repr__(self):
        return f"ArrayDeclNode(type='{self.data_type}', name='{self.var_name_node.name}', size={self.size})"


class PrintNode(StatementNode):
    def __init__(self, expression, line_no=None):
        super().__init__(line_no)
        self.expression = expression

    def __repr__(self):
        return f"PrintNode(expr={self.expression!r})"


class IfNode(StatementNode):
    def __init__(self, condition, true_block, false_block=None, line_no=None):
        super().__init__(line_no)
        self.condition = condition
        self.true_block = true_block
        self.false_block = false_block

    def __repr__(self):
        return f"IfNode(condition={self.condition!r}, has_else={self.false_block is not None})"


class WhileNode(StatementNode):
    def __init__(self, condition, body_block, line_no=None):
        super().__init__(line_no)
        self.condition = condition
        self.body_block = body_block

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
    def __init__(self, name_node, index_expr_node, line_no=None):
        super().__init__(line_no)
        self.name_node = name_node
        self.index_expr_node = index_expr_node

    def __repr__(self):
        return f"ArrayAccessNode(name='{self.name_node.name}', index={self.index_expr_node!r})"


class BinaryOpNode(ExpressionNode):
    def __init__(self, op, left, right, line_no=None):
        super().__init__(line_no)
        self.op = op
        self.left = left
        self.right = right

    def __repr__(self):
        return f"BinaryOpNode(op='{self.op}', left={self.left!r}, right={self.right!r})"


class UnaryOpNode(ExpressionNode):
    def __init__(self, op, operand, line_no=None):
        super().__init__(line_no)
        self.op = op
        self.operand = operand

    def __repr__(self):
        return f"UnaryOpNode(op='{self.op}', operand={self.operand!r})"


class FunctionDefinitionNode(Node):
    def __init__(self, name_node, params_nodes, body_node, line_no=None):
        super().__init__(line_no)
        self.name_node = name_node
        self.params_nodes = params_nodes
        self.body_node = body_node

    def __repr__(self):
        params_repr = [p.name for p in self.params_nodes] if self.params_nodes else []
        body_stmts_count = len(self.body_node.statements) if self.body_node and hasattr(self.body_node, 'statements') else 0
        return f"FunctionDefinitionNode(name='{self.name_node.name}', params={params_repr}, body_stmts={body_stmts_count})"


class ReturnNode(StatementNode):
    def __init__(self, expr_node, line_no=None):
        super().__init__(line_no)
        self.expr_node = expr_node

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
        self.name_node = name_node
        self.args_nodes = args_nodes

    def __repr__(self):
        args_repr_str = ", ".join([repr(arg) for arg in self.args_nodes]) if self.args_nodes else ""
        return f"FunctionCallNode(name='{self.name_node.name}', args=[{args_repr_str}])"

class PostfixOpNode(ExpressionNode):
    def __init__(self, op, operand, line_no=None):
        self.op = op
        self.operand = operand
        self.line_no = line_no

    def __repr__(self):
        return f"PostfixOpNode({self.op!r}, {self.operand!r})"

    def accept(self, visitor):
        if hasattr(visitor, 'visit_PostfixOpNode'):
            return visitor.visit_PostfixOpNode(self)
        else:
            return visitor.generic_visit(self)

class BreakNode(StatementNode):
    def __repr__(self):
        return "BreakNode"

    def accept(self, visitor):
        if hasattr(visitor, 'visit_BreakNode'):
            return visitor.visit_BreakNode(self)
        else:
            return visitor.generic_visit(self)


class CaseNode(StatementNode):
    def __init__(self, value_expr, statements, line_no=None):
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
    def __init__(self, condition, cases, line_no=None):
        self.condition = condition
        self.cases = cases
        self.line_no = line_no

    def __repr__(self):
        return f"SwitchNode({self.condition!r}, {self.cases!r})"

    def accept(self, visitor):
        if hasattr(visitor, 'visit_SwitchNode'):
            return visitor.visit_SwitchNode(self)
        else:
            return visitor.generic_visit(self)
