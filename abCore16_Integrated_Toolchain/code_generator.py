# code_generator.py

# --- Import AST Node Classes from ast_nodes.py ---
from ast_nodes import (
    Node, ProgramNode, StatementNode, AssignmentNode, PrintNode, IfNode, WhileNode,
    ExpressionNode, NumberNode, IdentifierNode, BinaryOpNode, UnaryOpNode
)
# --- Starting SSL variables address  ---
from abcore16_defs import (
    START_ADDR_SSL_VARIABLES
)


class SALCodeGenerator:
    def __init__(self):
        self.sal_code = []
        self.label_counter = 0

        # --- Symbol Table for SSL Variables ---
        self.variable_symbol_table = {}
        self.next_available_data_address = START_ADDR_SSL_VARIABLES  # Starting address for SSL variables
        # Ensure this is safe in your memory map

        # --- Temporary Register Management (Stack-Based Pool) ---
        self._compiler_temp_pool_master = ["R7", "R6"]
        self._available_temp_regs = []
        self._currently_used_temps = set()

    def _initialize_temp_regs(self):
        self._available_temp_regs = list(self._compiler_temp_pool_master)
        self._available_temp_regs.reverse()  # So R7 is popped first, then R6
        self._currently_used_temps = set()

    def _new_temp(self):
        if not self._available_temp_regs:
            print("FATAL CODEGEN ERROR: Ran out of dedicated temporary registers (R6, R7).")
            print("  Consider implementing register spilling or simplifying the SSL expression.")
            raise Exception("Compiler out of temporary registers")
        temp_reg = self._available_temp_regs.pop()
        self._currently_used_temps.add(temp_reg)
        # print(f"// DEBUG CG: Alloc Temp: {temp_reg}")
        return temp_reg

    def _free_temp(self, reg_name):
        if reg_name in self._compiler_temp_pool_master:
            if reg_name not in self._currently_used_temps:
                # print(f"// WARNING CG: Attempt to free temp '{reg_name}' not marked as used or already freed.")
                if reg_name not in self._available_temp_regs:  # Defensive
                    self._available_temp_regs.append(reg_name)
                return
            self._available_temp_regs.append(reg_name)
            self._currently_used_temps.remove(reg_name)
            # print(f"// DEBUG CG: Freed Temp: {reg_name}")

    def _get_or_allocate_ssl_variable_address(self, var_name_str):
        var_name_upper = var_name_str.upper()
        if var_name_upper not in self.variable_symbol_table:
            assigned_address = self.next_available_data_address
            self.variable_symbol_table[var_name_upper] = assigned_address
            self.next_available_data_address += 1
            self.emit(f"// SSL Variable '{var_name_str}' assigned data memory word address 0x{assigned_address:04X}")
            return assigned_address
        return self.variable_symbol_table[var_name_upper]

    def emit(self, sal_instruction):
        self.sal_code.append(sal_instruction)

    def new_label(self, prefix="LBL"):
        self.label_counter += 1
        return f"_{prefix.upper()}_{self.label_counter}"

    def generate(self, ast_root_node):
        self.sal_code = []
        self._initialize_temp_regs()
        self.variable_symbol_table = {}
        self.next_available_data_address = 0x1000

        if ast_root_node:
            ast_root_node.accept(self)

        if self._currently_used_temps:
            print(f"// WARNING CG: End of generation, temps still used: {self._currently_used_temps}")
        return "\n".join(self.sal_code)

    # --- Visitor Methods ---

    def visit_ProgramNode(self, node):
        if node and node.statements:
            for stmt in node.statements:
                if stmt:
                    stmt.accept(self)

    def visit_NumberNode(self, node):
        temp_reg = self._new_temp()
        self.emit(f"LOAD {temp_reg} #{node.value}")
        return temp_reg

    def visit_IdentifierNode(self, node):  # When an identifier is used as a value (RHS)
        name_upper = node.name.upper()
        if name_upper in ["R0", "R1", "R2", "R3", "R4", "R5"]:  # GPRs
            return name_upper
        else:  # SSL variable
            var_address = self._get_or_allocate_ssl_variable_address(node.name)
            temp_reg = self._new_temp()
            self.emit(f"// Loading SSL variable '{node.name}' (from 0x{var_address:04X}) into temp {temp_reg}")
            self.emit(f"LOADM {temp_reg} 0x{var_address:04X}")
            return temp_reg

    def visit_AssignmentNode(self, node):  # target = expression
        # node.target_name is an IdentifierNode
        # node.value_expr is an ExpressionNode
        expr_result_reg = node.value_expr.accept(self)

        target_name_upper = node.target_name.name.upper()

        if target_name_upper in ["R0", "R1", "R2", "R3", "R4", "R5"]:  # Assigning to GPR
            if expr_result_reg != target_name_upper:
                self.emit(f"MOV {target_name_upper} {expr_result_reg}")
        else:  # Assigning to SSL variable
            var_address = self._get_or_allocate_ssl_variable_address(node.target_name.name)
            self.emit(f"// Storing to SSL variable '{node.target_name.name}' (at 0x{var_address:04X})")
            self.emit(f"STORE {expr_result_reg} 0x{var_address:04X}")

        if expr_result_reg in self._compiler_temp_pool_master:
            self._free_temp(expr_result_reg)

    def visit_PrintNode(self, node):
        expr_result_reg = node.expression.accept(self)
        self.emit(f"OUT {expr_result_reg}")
        if expr_result_reg in self._compiler_temp_pool_master:
            self._free_temp(expr_result_reg)

    def visit_BinaryOpNode(self, node):
        reg_left = node.left.accept(self)
        reg_right = node.right.accept(self)
        op_token = node.op

        result_target_reg = ""
        left_was_gpr = reg_left in ["R0", "R1", "R2", "R3", "R4", "R5"]

        if left_was_gpr:
            result_target_reg = self._new_temp()
            self.emit(
                f"MOV {result_target_reg} {reg_left} // Preserve GPR {reg_left} by copying to {result_target_reg}")
        else:
            result_target_reg = reg_left  # Reuse temp reg_left

        if op_token in ['+', '-', '*']:
            sal_op = {"+": "ADD", "-": "SUB", "*": "MUL"}[op_token]
            self.emit(f"{sal_op} {result_target_reg} {reg_right}")

        elif op_token in ['==', '!=', '<', '>', '<=', '>=']:
            true_label = self.new_label("CMPTRUE")
            end_label = self.new_label("CMPEND")

            self.emit(f"CMP {reg_left} {reg_right}")  # Compare original GPRs or temps

            jump_if_true_instr = None
            # CRITICAL: This comparison logic needs significant improvement for correctness.
            if op_token == '==':
                jump_if_true_instr = "JE"
            elif op_token == '!=':
                jump_if_true_instr = "JNE"
            elif op_token == '<':
                jump_if_true_instr = "JS"  # Highly Simplistic (Signed Less Than)
            elif op_token == '>':  # Highly Simplistic (Signed Greater Than using JNS/JNE pattern)
                # For A > B (signed): ( (SF XOR OF) == 0 ) AND (ZF == 0)
                # The sequence below is an attempt, but likely needs specific flag combination checks
                # For z > 0 where z is in reg_left and 0 is in reg_right (after CMP reg_left, reg_right)
                # True if SF=0 (not neg) AND ZF=0 (not zero)
                false_gt_label = self.new_label("NOT_GT")
                self.emit(f"JS {false_gt_label}    // If (L-R) is negative, L is not > R")
                self.emit(f"JE {false_gt_label}    // If (L-R) is zero, L is not > R")
                # If here, L > R (assuming no overflow complicated SF for negative results)
                self.emit(f"LOAD {result_target_reg} #1 // True for > ")
                self.emit(f"JMP {end_label}")
                self.emit(f"{false_gt_label}:")
                self.emit(f"LOAD {result_target_reg} #0 // False for > ")
                self.emit(f"{end_label}:")
                jump_if_true_instr = "HANDLED_GT"  # Mark as handled to skip generic below

            if jump_if_true_instr and jump_if_true_instr != "HANDLED_GT":
                self.emit(f"{jump_if_true_instr} {true_label}")
                self.emit(f"LOAD {result_target_reg} #0    // False case")
                self.emit(f"JMP {end_label}")
                self.emit(f"{true_label}:")
                self.emit(f"LOAD {result_target_reg} #1    // True case")
                self.emit(f"{end_label}:")
            elif not jump_if_true_instr:  # Fallback if no specific jump was determined by simple mapping
                self.emit(f"// Comparison op {op_token} SAL generation for 0/1 result needs flag sequence")
                self.emit(f"LOAD {result_target_reg} #0 // Default to false for {op_token}")

        elif op_token == '&&':
            self.emit(f"L_AND {result_target_reg} {reg_left} {reg_right}")
        elif op_token == '||':
            self.emit(f"L_OR {result_target_reg} {reg_left} {reg_right}")
        else:
            self.emit(f"// visit_BinaryOpNode: Unhandled operator {op_token}")
            self.emit(f"LOAD {result_target_reg} #0 // Error: Unhandled binary op")

        # Free original reg_left IF it was a GPR AND we copied it to result_target_reg (which is a temp)
        # No, reg_left itself (if GPR) is not freed. If it was copied to result_target_reg (a temp),
        # then result_target_reg will be freed by the caller if it's a temp.
        # If reg_left was a temp and *is* result_target_reg, it's also freed by the caller.
        # If reg_left was a temp and result_target_reg is a *different* temp (should not happen with current logic), then free reg_left.
        if reg_left in self._compiler_temp_pool_master and reg_left != result_target_reg:
            self._free_temp(reg_left)  # This case is if left was temp and result went to a *new* temp

        if reg_right in self._compiler_temp_pool_master:
            self._free_temp(reg_right)  # Right operand temp is always consumed

        return result_target_reg

    def visit_UnaryOpNode(self, node):
        operand_reg = node.operand.accept(self)
        op_token = node.op

        operand_was_gpr = operand_reg in ["R0", "R1", "R2", "R3", "R4", "R5"]
        # If operand was GPR, result must go to a new temp.
        # If operand was temp, result can go back into that same temp.
        result_target_reg = self._new_temp() if operand_was_gpr else operand_reg

        if op_token == '-':  # Unary Minus: result = 0 - operand
            reg_for_zero = self._new_temp()
            self.emit(f"LOAD {reg_for_zero} #0")
            self.emit(f"MOV {result_target_reg} {reg_for_zero} ")  # result_target = 0
            self.emit(f"SUB {result_target_reg} {operand_reg}")  # result_target = 0 - operand
            self._free_temp(reg_for_zero)
        elif op_token == '!':  # Logical NOT (SSL '!')
            self.emit(f"L_NOT {result_target_reg} {operand_reg}")
        else:
            self.emit(f"// visit_UnaryOpNode: Unhandled operator {op_token}")
            self.emit(f"LOAD {result_target_reg} #0 // Error: Unhandled unary op")

        # If original operand_reg was a temp AND it's different from where the result ended up
        # (e.g. operand was R7, result went to R6 because R7 was also used for 0), free original.
        # Current logic: if operand_was_gpr, result_target_reg is a new temp. operand_reg (GPR) is not freed.
        # If operand_was_temp, result_target_reg is operand_reg. It will be freed by caller.
        if operand_reg in self._compiler_temp_pool_master and operand_reg != result_target_reg:
            self._free_temp(operand_reg)

        return result_target_reg

    def visit_IfNode(self, node):
        label_for_else_code = self.new_label("ELSE")
        label_for_endif_code = self.new_label("ENDIF")
        jump_target_if_false = label_for_else_code if node.false_block else label_for_endif_code

        condition_result_reg = node.condition.accept(self)  # Holds 0 (false) or 1 (true)

        temp_for_zero_val = self._new_temp()
        self.emit(f"LOAD {temp_for_zero_val} #0")
        self.emit(f"CMP {condition_result_reg} {temp_for_zero_val}")  # Sets ZF if condition_result_reg is 0
        self._free_temp(temp_for_zero_val)

        self.emit(f"JE {jump_target_if_false} // If condition evaluated to 0 (false), ZF is set")

        if condition_result_reg in self._compiler_temp_pool_master:
            self._free_temp(condition_result_reg)

        if node.true_block: node.true_block.accept(self)

        if node.false_block:
            self.emit(f"JMP {label_for_endif_code} // True block done, skip ELSE")
            self.emit(f"{label_for_else_code}:")
            node.false_block.accept(self)

        self.emit(f"{label_for_endif_code}:")

    def visit_WhileNode(self, node):
        condition_check_label = self.new_label("WCOND")
        loop_body_label = self.new_label("WLOOPBODY")
        loop_end_label = self.new_label("WEND")

        self.emit(f"JMP {condition_check_label} // Initial jump to condition check")
        self.emit(f"{loop_body_label}:")

        if node.body_block: node.body_block.accept(self)

        self.emit(f"{condition_check_label}:")
        condition_result_reg = node.condition.accept(self)  # Holds 0 (false) or 1 (true)

        temp_for_zero_val = self._new_temp()
        self.emit(f"LOAD {temp_for_zero_val} #0")
        self.emit(f"CMP {condition_result_reg} {temp_for_zero_val}")  # Sets ZF if condition_result_reg is 0
        self._free_temp(temp_for_zero_val)

        # If condition_result_reg is NOT zero (condition is true), ZF is clear. Jump to loop_body_label.
        self.emit(f"JNE {loop_body_label} // If condition is true (non-zero), ZF is clear, repeat body")
        # If condition_result_reg IS zero (condition is false), ZF is true. Fall through to loop_end_label.

        self.emit(f"{loop_end_label}:")

        if condition_result_reg in self._compiler_temp_pool_master:
            self._free_temp(condition_result_reg)

    def generic_visit(self, node):
        if node is None: return
        print(f"// WARNING CG: No specific visit method for AST node type: {type(node).__name__}.")
        # Attempt to recurse common structural attributes
        for attr_name in ['statements', 'true_block', 'false_block', 'body_block',
                          'expression', 'condition',
                          'left', 'right', 'operand',  # For expressions
                          'target_name', 'value_expr']:  # For Assignment
            if hasattr(node, attr_name):
                attr_value = getattr(node, attr_name)
                if isinstance(attr_value, Node):
                    attr_value.accept(self)
                elif isinstance(attr_value, list):
                    for item in attr_value:
                        if isinstance(item, Node):
                            item.accept(self)
