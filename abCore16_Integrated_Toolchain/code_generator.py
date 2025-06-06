# code_generator.py

from ast_nodes import (
    Node, ProgramNode, StatementNode, AssignmentNode, PrintNode, IfNode, WhileNode,
    ExpressionNode, NumberNode, IdentifierNode, BinaryOpNode, UnaryOpNode,
    FunctionDefinitionNode, ReturnNode,
    ExpressionStatementNode, FunctionCallNode,
    ForNode, VarDeclNode
)


class SALCodeGenerator:
    def __init__(self):
        self.sal_code = []
        self.label_counter = 0

        self.symbol_tables = [{}]
        self.scope_stack_info = [{'type': 'global', 'var_count': 0, 'base_offset': 0x1000, 'name': '_global'}]

        self.next_available_global_data_address = 0x1000

        self._compiler_temp_pool_master = ["R7", "R6"]
        self._available_temp_regs = []
        self._currently_used_temps = set()

        self.current_function_context = None
        self.function_meta_map = {}
        self.return_value_reg = "R0"
        self.frame_pointer_reg = "R5"

    def _initialize_temp_regs(self):
        self._available_temp_regs = list(self._compiler_temp_pool_master)
        self._available_temp_regs.reverse()
        self._currently_used_temps = set()

    def _new_temp(self):
        if not self._available_temp_regs:
            raise Exception("FATAL CODEGEN ERROR: Ran out of temporary registers.")
        temp_reg = self._available_temp_regs.pop()
        self._currently_used_temps.add(temp_reg)
        return temp_reg

    def _free_temp(self, reg_name):
        if reg_name in self._compiler_temp_pool_master:
            if reg_name in self._currently_used_temps:
                self._available_temp_regs.append(reg_name)
                self._currently_used_temps.remove(reg_name)

    def emit(self, sal_instruction):
        self.sal_code.append(sal_instruction)

    def new_label(self, prefix="LBL"):
        self.label_counter += 1
        return f"_{prefix.upper()}_{self.label_counter}"

    def _enter_scope(self, scope_type='block', scope_name='_block'):
        self.symbol_tables.append({})
        self.scope_stack_info.append({'type': scope_type, 'name': scope_name, 'var_count_in_this_exact_scope': 0})

    def _exit_scope(self):
        if len(self.symbol_tables) > 1:
            self.symbol_tables.pop()
            self.scope_stack_info.pop()
        # else: print("// WARN CG: Attempt to pop global scope during exit_scope") # Avoid excessive noise

    def _add_symbol(self, name, symbol_type, location_or_offset, size=1):
        name_upper = name.upper()
        current_scope_sym_table = self.symbol_tables[-1]
        if name_upper in current_scope_sym_table:
            raise Exception(
                f"CodeGen Error: Symbol '{name}' redefined in current scope ('{self.scope_stack_info[-1]['name']}').")

        current_scope_sym_table[name_upper] = {'type': symbol_type, 'loc': location_or_offset, 'size': size,
                                               'scope_name': self.scope_stack_info[-1]['name']}

        if symbol_type == 'local':
            # Increment var_count for the *innermost function scope*
            for scope_info_entry in reversed(self.scope_stack_info):
                if scope_info_entry['type'] == 'function':
                    scope_info_entry['var_count'] = scope_info_entry.get('var_count', 0) + 1
                    break
            # Also track vars declared in this specific scope if needed for more granular scoping later
            self.scope_stack_info[-1]['var_count_in_this_exact_scope'] += 1

    def _lookup_symbol(self, name):
        name_upper = name.upper()
        for scope_table in reversed(self.symbol_tables):
            if name_upper in scope_table:
                return scope_table[name_upper]
        return None

    def _allocate_storage_for_decl(self, var_name_node):
        var_name = var_name_node.name
        if var_name.upper() in self.symbol_tables[-1]:  # Check current immediate scope
            raise Exception(
                f"CodeGen Error: Variable '{var_name}' (Line: {var_name_node.line_no}) already declared in this scope.")

        symbol_type = 'global'
        location = 0
        is_in_function_scope = False
        function_scope_info_for_local = None

        # Find the innermost 'function' typed scope in scope_stack_info
        for scope_info_entry in reversed(self.scope_stack_info):
            if scope_info_entry['type'] == 'function':
                is_in_function_scope = True
                function_scope_info_for_local = scope_info_entry
                break

        if is_in_function_scope:
            symbol_type = 'local'
            # 'fp_offset_next_local' is part of the function_scope_info, initialized in visit_FunctionDefinitionNode
            location = function_scope_info_for_local['fp_offset_next_local']
            function_scope_info_for_local['fp_offset_next_local'] -= 1
            self.emit(f"// Local Var '{var_name}' (Line: {var_name_node.line_no}) will be at FP{location}")
        else:  # Global scope
            symbol_type = 'global'
            location = self.next_available_global_data_address
            self.next_available_global_data_address += 1
            self.emit(
                f"// Global Var '{var_name}' (Line: {var_name_node.line_no}) assigned data memory 0x{location:04X}")

        self._add_symbol(var_name, symbol_type, location)  # This also updates function's var_count if local
        return self._lookup_symbol(var_name)

        # --- Main Generation Logic ---

    def generate(self, ast_root_node):
        self.sal_code = []
        self._initialize_temp_regs()
        self.symbol_tables = [{'type': 'global', 'name': '_global'}]  # Base global symbol table
        self.scope_stack_info = [{'type': 'global', 'var_count': 0, 'name': '_global'}]  # Base global scope info
        self.next_available_global_data_address = 0x1000
        self.current_function_context = None
        self.function_meta_map = {}

        if not isinstance(ast_root_node, ProgramNode): return ""

        # 1st Pass: Collect function metadata AND count their local variables
        if hasattr(ast_root_node, 'statements'):
            for stmt in ast_root_node.statements:
                if isinstance(stmt, FunctionDefinitionNode):
                    func_name_upper = stmt.name_node.name.upper()
                    if func_name_upper in self.function_meta_map:
                        raise Exception(
                            f"CodeGen Error: Function '{func_name_upper}' redefined (Line: {stmt.line_no}).")

                    sal_label = self.new_label(f"FUNC_{func_name_upper}")
                    epilogue_label = self.new_label(f"EPILOGUE_{func_name_upper}")
                    param_names = [p.name.upper() for p in stmt.params_nodes]

                    # Temporarily enter a 'function' scope context for counting
                    self._enter_scope('function', func_name_upper + "_countscope")
                    # No need to manage fp_offset_next_local for counting, just var_count
                    num_locals = self._count_local_vars_recursive(stmt.body_node)
                    self._exit_scope()

                    self.function_meta_map[func_name_upper] = {
                        'sal_label': sal_label,
                        'param_names': param_names,
                        'epilogue_label': epilogue_label,
                        'num_locals_from_scan': num_locals
                    }

        main_code_generated = False
        # Global scope processing happens before function definitions are emitted
        if hasattr(ast_root_node, 'statements'):
            for stmt in ast_root_node.statements:
                if not isinstance(stmt, FunctionDefinitionNode):  # Process non-function global statements
                    if stmt:
                        stmt.accept(self)
                        main_code_generated = True

        functions_exist = bool(self.function_meta_map)
        # Determine overall program HALT or MAIN call
        if "MAIN" in self.function_meta_map:
            if not main_code_generated:  # Only call main if no other global code was generated
                self.emit(f"CALL {self.function_meta_map['MAIN']['sal_label']}")
            # Always HALT after main (or after global code if main was part of it)
            if not self.sal_code or self.sal_code[-1].strip().upper() != "HALT":
                self.emit("HALT // Auto-HALT (after main or global code)")
        elif main_code_generated:  # Global code but no main function
            if not self.sal_code or self.sal_code[-1].strip().upper() != "HALT":
                self.emit("HALT // Auto-HALT after global statements, no main() func")
        elif functions_exist:  # Only other functions, no main, no global statements
            self.emit("HALT // No main() function or global code to execute.")
        elif not self.sal_code:  # Truly empty input
            self.emit("HALT // Empty program.")

        if functions_exist:
            self.emit("\n// --- Function Definitions ---")
            if hasattr(ast_root_node, 'statements'):
                for stmt in ast_root_node.statements:
                    if isinstance(stmt, FunctionDefinitionNode):
                        if stmt: stmt.accept(self)

        if self._currently_used_temps:
            print(
                f"// WARNING CG: End of gen, {len(self._currently_used_temps)} temp regs used: {self._currently_used_temps}")
        return "\n".join(self.sal_code)

    def _count_local_vars_recursive(self, ast_node):
        count = 0
        if ast_node is None: return 0
        if isinstance(ast_node, VarDeclNode):
            count += 1
        elif isinstance(ast_node, ProgramNode) and ast_node.statements:
            for stmt_in_block in ast_node.statements:  # Renamed to avoid conflict
                count += self._count_local_vars_recursive(stmt_in_block)
        elif isinstance(ast_node, IfNode):
            count += self._count_local_vars_recursive(ast_node.true_block)
            if ast_node.false_block:
                count += self._count_local_vars_recursive(ast_node.false_block)
        elif isinstance(ast_node, WhileNode):
            count += self._count_local_vars_recursive(ast_node.body_block)
        elif isinstance(ast_node, ForNode):
            if isinstance(ast_node.init_node, VarDeclNode): count += 1
            count += self._count_local_vars_recursive(ast_node.body_node)
        return count

    # --- Visitor Methods ---
    def visit_VarDeclNode(self, node):
        symbol_info = self._allocate_storage_for_decl(node.var_name_node)
        if node.init_expr_node:
            expr_val_reg = node.init_expr_node.accept(self)
            if symbol_info['type'] == 'global':
                self.emit(f"STORE {expr_val_reg}, 0x{symbol_info['loc']:04X}")
            elif symbol_info['type'] == 'local':
                self.emit(f"STORFR {expr_val_reg}, {self.frame_pointer_reg}, #{symbol_info['loc']}")
            if expr_val_reg in self._compiler_temp_pool_master:
                self._free_temp(expr_val_reg)

    def visit_ProgramNode(self, node):
        if node and node.statements:
            for stmt_node in node.statements:
                if stmt_node:
                    stmt_node.accept(self)

    def visit_FunctionDefinitionNode(self, node):
        func_name_upper = node.name_node.name.upper()
        func_meta = self.function_meta_map.get(func_name_upper)
        if not func_meta:
            raise Exception(f"CodeGen Error: Meta info for func '{func_name_upper}' not found.")

        original_outer_context = self.current_function_context
        self.current_function_context = {
            'name': func_name_upper,
            'sal_label': func_meta['sal_label'],
            'epilogue_label': func_meta['epilogue_label'],
            'param_map': {},
            'num_locals_from_scan': func_meta['num_locals_from_scan']
        }

        self._enter_scope('function', scope_name=func_name_upper)
        current_function_scope_info = self.scope_stack_info[-1]
        current_function_scope_info['fp_offset_next_local'] = -1
        current_function_scope_info['var_count'] = 0

        for i, param_node in enumerate(node.params_nodes):
            param_name_upper = param_node.name.upper()
            offset = 2 + i
            self.current_function_context['param_map'][param_name_upper] = offset
            self._add_symbol(param_node.name, 'param', offset)

        self.emit(f"\n// Function: {node.name_node.name}({', '.join(p.name for p in node.params_nodes)})")
        self.emit(f"{self.current_function_context['sal_label']}:")
        self.emit(f"PUSH {self.frame_pointer_reg}")
        self.emit(f"MOVFRSP {self.frame_pointer_reg}")

        num_locals_to_alloc = self.current_function_context['num_locals_from_scan']
        if num_locals_to_alloc > 0:
            self.emit(f"// Allocate space for {num_locals_to_alloc} local(s) on stack")
            for _ in range(num_locals_to_alloc):
                self.emit(f"PUSH R0 // Allocate 1 word for local (actual value pushed is junk)")

        if node.body_node:
            node.body_node.accept(self)

        needs_implicit_jmp_to_epilogue = True
        if self.sal_code:
            last_sal_instr = self.sal_code[-1].strip().upper()
            if last_sal_instr == "RET" or \
                    (last_sal_instr.startswith("JMP") and self.current_function_context and \
                     last_sal_instr.endswith(self.current_function_context['epilogue_label'])):
                needs_implicit_jmp_to_epilogue = False

        if needs_implicit_jmp_to_epilogue and self.current_function_context:
            self.emit(f"JMP {self.current_function_context['epilogue_label']}")

        self.emit(f"{self.current_function_context['epilogue_label']}:")
        if num_locals_to_alloc > 0:
            self.emit(f"MOVTOSP {self.frame_pointer_reg}")
        self.emit(f"POP {self.frame_pointer_reg}")
        self.emit(f"RET")

        self._exit_scope()
        self.current_function_context = original_outer_context

    def visit_IdentifierNode(self, node):
        name_upper = node.name.upper()
        if name_upper in ["R0", "R1", "R2", "R3", "R4"]:
            return name_upper

        symbol_info = self._lookup_symbol(node.name)
        if not symbol_info:
            # For now, assume undeclared variables are an error during code generation
            # This makes the language stricter and helps catch typos.
            # Implicit global declaration was problematic for scope restoration.
            raise Exception(f"CodeGen Error: Undeclared identifier '{node.name}' (Line: {node.line_no})")

        temp_reg = self._new_temp()
        if symbol_info['type'] == 'global':
            self.emit(f"LOADM {temp_reg}, 0x{symbol_info['loc']:04X}")
        elif symbol_info['type'] == 'param' or symbol_info['type'] == 'local':
            self.emit(f"LOADFR {temp_reg}, {self.frame_pointer_reg}, #{symbol_info['loc']}")
        else:
            raise Exception(f"CodeGen Error: Unknown symbol type '{symbol_info['type']}' for '{node.name}'")
        return temp_reg

    def visit_AssignmentNode(self, node):
        self.emit(f"// Assignment to '{node.target_name.name}' (Line: {node.line_no})")
        expr_val_reg = node.value_expr.accept(self)

        target_name_node = node.target_name
        target_name = target_name_node.name
        symbol_info = self._lookup_symbol(target_name)

        if not symbol_info:
            raise Exception(f"CodeGen Error: Assignment to undeclared variable '{target_name}' (Line: {node.line_no})")

        if symbol_info['type'] == 'global':
            self.emit(f"STORE {expr_val_reg}, 0x{symbol_info['loc']:04X}")
        elif symbol_info['type'] == 'param' or symbol_info['type'] == 'local':
            self.emit(f"STORFR {expr_val_reg}, {self.frame_pointer_reg}, #{symbol_info['loc']}")
        elif target_name.upper() in ["R0", "R1", "R2", "R3",
                                     "R4"]:  # Should not happen if parser makes IdentifierNode for target
            if expr_val_reg != target_name.upper():
                self.emit(f"MOV {target_name.upper()}, {expr_val_reg}")
        else:
            raise Exception(
                f"CodeGen Error: Unknown symbol type '{symbol_info['type']}' for assignment to '{target_name}'")

        if expr_val_reg in self._compiler_temp_pool_master:
            self._free_temp(expr_val_reg)

    def visit_ForNode(self, node):
        self.emit(f"// FOR Loop Start (Line: {node.line_no if node.line_no else 'N/A'})")

        # For-loop initializer might declare a variable.
        # This variable is treated as local to the containing function.
        # self._enter_scope('for_construct_scope') # Optional if for-var has tighter scope than function

        if node.init_node:
            self.emit(f"// FOR Init")
            node.init_node.accept(self)

            # if isinstance(node.init_node, VarDeclNode) : self._exit_scope() # if init_var scope ends after init

        loop_body_label = self.new_label("FOR_BODY")
        loop_condition_label = self.new_label("FOR_COND")
        loop_update_target_label = self.new_label("FOR_UPDATE")
        loop_end_label = self.new_label("FOR_END")

        self.emit(f"JMP {loop_condition_label}")

        self.emit(f"{loop_body_label}:")
        # self._enter_scope('for_body_block') # For true C-style block scope for vars declared in {}
        if node.body_node:
            node.body_node.accept(self)
        # self._exit_scope() # Exit for_body_block

        self.emit(f"{loop_update_target_label}:")
        if node.update_expr_stmt_node:
            self.emit(f"// FOR Update")
            node.update_expr_stmt_node.accept(self)

        self.emit(f"JMP {loop_condition_label}")

        self.emit(f"{loop_condition_label}:")
        if node.condition_expr_node:
            self.emit(f"// FOR Condition")
            self._generate_conditional_branch(node.condition_expr_node, loop_body_label, loop_end_label)
        else:
            self.emit(f"JMP {loop_body_label} // FOR: No condition, infinite loop")

        self.emit(f"{loop_end_label}:")
        self.emit(f"// FOR Loop End")
        # if isinstance(node.init_node, VarDeclNode) : self._exit_scope() # Exit outer for_construct_scope if used

    def visit_PrintNode(self, node):
        self.emit(f"// Print statement (Line: {node.line_no})")
        expr_result_reg = node.expression.accept(self);
        self.emit(f"OUT {expr_result_reg}")
        if expr_result_reg in self._compiler_temp_pool_master:
            self._free_temp(expr_result_reg)

    def _generate_conditional_branch(self, condition_node, true_branch_label, false_branch_label):
        if isinstance(condition_node, BinaryOpNode):
            op = condition_node.op
            if op == '&&':
                lbl_eval_right = self.new_label("AND_RIGHT")
                self._generate_conditional_branch(condition_node.left, lbl_eval_right, false_branch_label)
                self.emit(f"{lbl_eval_right}:")
                self._generate_conditional_branch(condition_node.right, true_branch_label, false_branch_label)
                return
            if op == '||':
                lbl_eval_right = self.new_label("OR_RIGHT")
                self._generate_conditional_branch(condition_node.left, true_branch_label, lbl_eval_right)
                self.emit(f"{lbl_eval_right}:")
                self._generate_conditional_branch(condition_node.right, true_branch_label, false_branch_label)
                return

            if op in ['==', '!=', '<', '>', '<=', '>=']:
                reg_left = condition_node.left.accept(self)
                reg_right = condition_node.right.accept(self)
                self.emit(f"CMP {reg_left}, {reg_right}")
                if reg_left in self._compiler_temp_pool_master: self._free_temp(reg_left)
                if reg_right in self._compiler_temp_pool_master: self._free_temp(reg_right)

                if op == '==':
                    self.emit(f"JE {true_branch_label}")
                elif op == '!=':
                    self.emit(f"JNE {true_branch_label}")
                elif op == '<':  # Signed A < B  (SF != OF)
                    lbl_sf1 = self.new_label("SLT_SF1")
                    self.emit(f"JS {lbl_sf1}")  # SF=1?
                    # SF=0 path
                    self.emit(f"JO {true_branch_label}")  # SF=0, OF=1 -> true
                    self.emit(f"JMP {false_branch_label}")  # SF=0, OF=0 -> false
                    self.emit(f"{lbl_sf1}:")  # SF=1 path
                    self.emit(f"JNO {true_branch_label}")  # SF=1, OF=0 -> true
                    # Fallthrough (SF=1, OF=1) is false for <
                elif op == '>=':  # Signed A >= B (SF == OF)
                    lbl_sf1 = self.new_label("SGE_SF1")
                    self.emit(f"JS {lbl_sf1}")  # SF=1?
                    # SF=0 path
                    self.emit(f"JNO {true_branch_label}")  # SF=0, OF=0 -> true
                    self.emit(f"JMP {false_branch_label}")  # SF=0, OF=1 -> false
                    self.emit(f"{lbl_sf1}:")  # SF=1 path
                    self.emit(f"JO {true_branch_label}")  # SF=1, OF=1 -> true
                    # Fallthrough (SF=1, OF=0) is false for >=
                elif op == '>':  # Signed A > B (ZF=0 AND SF==OF)
                    self.emit(f"JE {false_branch_label}")  # if ZF=1, A=B, so not A>B
                    # Now check SF==OF
                    lbl_sf1 = self.new_label("SGT_SF1")
                    self.emit(f"JS {lbl_sf1}")
                    # SF=0 path
                    self.emit(f"JNO {true_branch_label}")  # SF=0, OF=0 -> true
                    self.emit(f"JMP {false_branch_label}")
                    self.emit(f"{lbl_sf1}:")
                    self.emit(f"JO {true_branch_label}")
                elif op == '<=':  # Signed A <= B (ZF=1 OR SF!=OF)
                    self.emit(f"JE {true_branch_label}")
                    # Now check SF!=OF
                    lbl_sf1 = self.new_label("SLE_SF1")
                    self.emit(f"JS {lbl_sf1}")
                    # SF=0 path
                    self.emit(f"JO {true_branch_label}")
                    self.emit(f"JMP {false_branch_label}")
                    self.emit(f"{lbl_sf1}:")
                    self.emit(f"JNO {true_branch_label}")

                self.emit(f"JMP {false_branch_label}")  # Default if no specific condition matched for <,>,<=,>=
                return

        elif isinstance(condition_node, UnaryOpNode) and condition_node.op == '!':
            self._generate_conditional_branch(condition_node.operand, false_branch_label, true_branch_label)
            return

        result_reg = condition_node.accept(self)
        temp_zero_reg = self._new_temp()
        self.emit(f"LOAD {temp_zero_reg}, #0")
        self.emit(f"CMP {result_reg}, {temp_zero_reg}")
        self._free_temp(temp_zero_reg)
        if result_reg in self._compiler_temp_pool_master:
            self._free_temp(result_reg)
        self.emit(f"JNE {true_branch_label}")
        self.emit(f"JMP {false_branch_label}")

    def visit_IfNode(self, node):
        self.emit(f"// IF Statement Start (Line: {node.line_no})")
        true_label = self.new_label("IF_TRUE")
        end_if_label = self.new_label("IF_END")
        false_destination_label = end_if_label
        if node.false_block:
            else_label = self.new_label("IF_ELSE")
            false_destination_label = else_label

        self._generate_conditional_branch(node.condition, true_label, false_destination_label)
        self.emit(f"{true_label}:")
        if node.true_block:
            node.true_block.accept(self)
        if node.false_block:
            self.emit(f"JMP {end_if_label}")
            self.emit(f"{else_label}:")
            node.false_block.accept(self)
        self.emit(f"{end_if_label}:")
        self.emit(f"// IF Statement End")

    def visit_WhileNode(self, node):
        self.emit(f"// WHILE Loop Start (Line: {node.line_no})")
        condition_label = self.new_label("WHILE_COND")
        body_label = self.new_label("WHILE_BODY")
        end_while_label = self.new_label("WHILE_END")

        self.emit(f"JMP {condition_label}")
        self.emit(f"{body_label}:")
        if node.body_block:
            node.body_block.accept(self)
        self.emit(f"JMP {condition_label}")
        self.emit(f"{condition_label}:")
        self._generate_conditional_branch(node.condition, body_label, end_while_label)
        self.emit(f"{end_while_label}:")
        self.emit(f"// WHILE Loop End")

    def visit_NumberNode(self, node):
        reg = self._new_temp()
        self.emit(f"LOAD {reg}, #{node.value}")
        return reg

    def visit_BinaryOpNode(self, node):
        reg_left = node.left.accept(self)
        reg_right = node.right.accept(self)
        op = node.op
        result_reg = reg_left  # Attempt to reuse left operand's register

        # If reg_left isn't a temp (e.g., R0-R4), allocate a new temp for the result
        if reg_left not in self._compiler_temp_pool_master:
            result_reg = self._new_temp()
            self.emit(f"MOV {result_reg}, {reg_left}")  # Copy to new temp

        if op == '+':
            self.emit(f"ADD {result_reg}, {reg_right}")
        elif op == '-':
            self.emit(f"SUB {result_reg}, {reg_right}")
        elif op == '*':
            self.emit(f"MUL {result_reg}, {reg_right}")
        elif op == '&&':
            self.emit(f"L_AND {result_reg}, {result_reg}, {reg_right}")
        elif op == '||':
            self.emit(f"L_OR {result_reg}, {result_reg}, {reg_right}")
        elif op in ['==', '!=', '<', '>', '<=', '>=']:
            # For expressions, we want to set result_reg to 1 (true) or 0 (false)
            self.emit(f"CMP {result_reg}, {reg_right}")  # result_reg still holds value of left_expr

            true_lbl = self.new_label("BINOP_TRUE")
            end_lbl = self.new_label("BINOP_END")

            # Generate conditional jumps based on the operation
            if op == '==':
                self.emit(f"JE {true_lbl}")
            elif op == '!=':
                self.emit(f"JNE {true_lbl}")
            elif op == '<':  # SF != OF
                lbl_sf1 = self.new_label("SLT_SF1_BIN")
                self.emit(f"JS {lbl_sf1}");
                self.emit(f"JO {true_lbl}");
                self.emit(f"JMP {end_lbl}");
                self.emit(f"{lbl_sf1}:");
                self.emit(f"JNO {true_lbl}");
            elif op == '>=':  # SF == OF
                lbl_sf1 = self.new_label("SGE_SF1_BIN")
                self.emit(f"JS {lbl_sf1}");
                self.emit(f"JNO {true_lbl}");
                self.emit(f"JMP {end_lbl}");
                self.emit(f"{lbl_sf1}:");
                self.emit(f"JO {true_lbl}");
            elif op == '>':  # ZF=0 AND SF==OF
                self.emit(f"JE {end_lbl}");
                lbl_sf1 = self.new_label("SGT_SF1_BIN")
                self.emit(f"JS {lbl_sf1}");
                self.emit(f"JNO {true_lbl}");
                self.emit(f"JMP {end_lbl}");
                self.emit(f"{lbl_sf1}:");
                self.emit(f"JO {true_lbl}");
            elif op == '<=':  # ZF=1 OR SF!=OF
                self.emit(f"JE {true_lbl}");
                lbl_sf1 = self.new_label("SLE_SF1_BIN")
                self.emit(f"JS {lbl_sf1}");
                self.emit(f"JO {true_lbl}");
                self.emit(f"JMP {end_lbl}");
                self.emit(f"{lbl_sf1}:");
                self.emit(f"JNO {true_lbl}");

            self.emit(f"JMP {end_lbl}");  # Fallthrough if direct JE/JNE didn't jump

            self.emit(f"{end_lbl}:")  # Path for result = 0 (false)
            self.emit(f"LOAD {result_reg}, #0")
            self.emit(f"JMP {true_lbl}_MERGE")  # Avoid re-executing true_lbl path
            self.emit(f"{true_lbl}:")  # Path for result = 1 (true)
            self.emit(f"LOAD {result_reg}, #1")
            self.emit(f"{true_lbl}_MERGE:")  # Common exit point
        else:
            self.emit(f"// ERROR: Unhandled binary operator '{op}' for expression result")
            self.emit(f"LOAD {result_reg}, #-1")  # Error value

        if reg_right in self._compiler_temp_pool_master:
            self._free_temp(reg_right)
        # If reg_left was not a temp and result_reg is a new temp, reg_left is untouched.
        # If reg_left was a temp, result_reg is reg_left, so it's returned (still marked as used).
        return result_reg

    def visit_UnaryOpNode(self, node):
        operand_reg = node.operand.accept(self)
        op = node.op
        result_reg = operand_reg  # Try to reuse
        new_temp_for_result = False

        if operand_reg not in self._compiler_temp_pool_master:
            result_reg = self._new_temp()
            self.emit(f"MOV {result_reg}, {operand_reg}")
            new_temp_for_result = True

        if op == '-':
            temp_zero_reg = self._new_temp()
            self.emit(f"LOAD {temp_zero_reg}, #0")
            # SUB result_reg, temp_zero_reg, result_reg ; if SUB Rdest, Rsrc1, Rsrc2
            # SUB result_reg, temp_zero_reg ; if SUB Rdest_src1, Rsrc2
            # To do 0 - X, need to do: MOV temp, 0; SUB temp, X; MOV result, temp
            # Or, if SUB can be Rdest, Rsrc1, Rsrc2: SUB result_reg, temp_zero_reg, result_reg
            # Assuming SUB Rd, Rs means Rd = Rd - Rs
            # So, to get 0 - operand_reg:
            # 1. result_reg = 0 (if it's a new temp) or operand_reg (if reusing)
            # 2. If reusing operand_reg: MOV temp_zero_reg, #0; SUB temp_zero_reg, result_reg; MOV result_reg, temp_zero_reg
            self.emit(
                f"SUB {temp_zero_reg}, {result_reg}")  # temp_zero_reg = 0 - original_value (which is in result_reg)
            self.emit(f"MOV {result_reg}, {temp_zero_reg}")  # result_reg = new_negated_value
            self._free_temp(temp_zero_reg)
        elif op == '!':  # Logical NOT
            self.emit(f"L_NOT {result_reg}, {result_reg}")
        else:
            self.emit(f"// ERROR: Unhandled unary operator '{op}'")
            self.emit(f"LOAD {result_reg}, #-1")

        # If operand_reg was a GPR (R0-R4) and we made result_reg a new temp, operand_reg is untouched.
        # If operand_reg was a temp (R6/R7) AND we made result_reg a new temp (which shouldn't happen with current logic),
        # then original operand_reg should be freed. But current logic reuses if operand_reg is temp.
        if new_temp_for_result and operand_reg in self._compiler_temp_pool_master:
            self._free_temp(operand_reg)  # This case seems unlikely with current _new_temp/MOV logic

        return result_reg

    def visit_ExpressionStatementNode(self, node):
        if node.expression:
            # An assignment node doesn't "return" a register in the same way an arithmetic expr does.
            # Its visitor handles its own temporaries.
            if isinstance(node.expression, AssignmentNode):
                node.expression.accept(self)  # Just execute it for side effects
            else:  # For other expressions, they might return a temp register
                result_reg = node.expression.accept(self)
                if result_reg and isinstance(result_reg, str) and result_reg in self._compiler_temp_pool_master:
                    self._free_temp(result_reg)

    def generic_visit(self, node):
        if node is None: return
        self.emit(f"// WARNING: Generic visit for AST node type {type(node).__name__} (value: {node!r})")
