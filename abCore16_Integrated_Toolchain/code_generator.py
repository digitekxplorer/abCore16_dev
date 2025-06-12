# code_generator.py

from ast_nodes import (
    Node, ProgramNode, StatementNode, AssignmentNode, PrintNode, IfNode, WhileNode,
    ExpressionNode, NumberNode, IdentifierNode, BinaryOpNode, UnaryOpNode,
    FunctionDefinitionNode, ReturnNode,
    ExpressionStatementNode, FunctionCallNode,
    ForNode, VarDeclNode,
    ArrayDeclNode, ArrayAccessNode
)

# --- Global Debug Switch for Code Generator ---
CG_DEBUG_VERBOSE = False  # Set to True to enable detailed CG prints, False to disable


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
        if reg_name is None: return
        if not isinstance(reg_name, str): return
        if reg_name in self._compiler_temp_pool_master:
            if reg_name in self._currently_used_temps:
                self._available_temp_regs.append(reg_name)
                self._currently_used_temps.remove(reg_name)

    def emit(self, sal_instruction):
        if CG_DEBUG_VERBOSE:
            if isinstance(sal_instruction, str):
                words = sal_instruction.replace(",", " ").split()
                if "None" in words:
                    print(f"CRITICAL_CG_EMIT: Emitting instruction with 'None' string as operand: [{sal_instruction}]")
                    raise ValueError(f"Attempting to emit instruction with 'None' string as operand: {sal_instruction}")
        self.sal_code.append(sal_instruction)

    def new_label(self, prefix="LBL"):
        self.label_counter += 1
        return f"_{prefix.upper()}_{self.label_counter}"

    def _enter_scope(self, scope_type='block', scope_name='_block'):
        if CG_DEBUG_VERBOSE: print(
            f"// DEBUG_SCOPE: Entering scope: {scope_name} (type: {scope_type}) Depth: {len(self.symbol_tables)}")
        self.symbol_tables.append({})
        self.scope_stack_info.append({'type': scope_type, 'name': scope_name, 'var_count_in_this_exact_scope': 0})

    def _exit_scope(self):
        if len(self.symbol_tables) > 1:
            if CG_DEBUG_VERBOSE: print(
                f"// DEBUG_SCOPE: Exiting scope: {self.scope_stack_info[-1]['name']} Depth: {len(self.symbol_tables) - 1}")
            self.symbol_tables.pop()
            self.scope_stack_info.pop()

    def _add_symbol(self, name, symbol_type, location_or_offset, size=1):
        name_upper = name.upper()
        current_scope_sym_table = self.symbol_tables[-1]
        if name_upper in current_scope_sym_table:
            raise Exception(
                f"CodeGen Error: Symbol '{name}' redefined in current scope ('{self.scope_stack_info[-1]['name']}').")

        current_scope_sym_table[name_upper] = {'type': symbol_type, 'loc': location_or_offset, 'size': size,
                                               'scope_name': self.scope_stack_info[-1]['name']}

        if symbol_type == 'local':
            function_scope_found = False
            for scope_info_entry in reversed(self.scope_stack_info):
                if scope_info_entry['type'] == 'function':
                    scope_info_entry['var_count'] = scope_info_entry.get('var_count', 0) + 1
                    function_scope_found = True
                    break
            self.scope_stack_info[-1]['var_count_in_this_exact_scope'] += 1

    def _lookup_symbol(self, name):
        name_upper = name.upper()
        for i, scope_table in enumerate(reversed(self.symbol_tables)):
            if name_upper in scope_table:
                return scope_table[name_upper]
        return None

    def _allocate_storage_for_decl(self, var_name_node):
        var_name = var_name_node.name
        if var_name.upper() in self.symbol_tables[-1]:
            raise Exception(
                f"CodeGen Error: Variable '{var_name}' (Line: {var_name_node.line_no}) already declared in this scope.")

        symbol_type = 'global'
        location = 0
        is_in_function_scope = False
        function_scope_info_for_local = None

        for scope_info_entry in reversed(self.scope_stack_info):
            if scope_info_entry['type'] == 'function':
                is_in_function_scope = True
                function_scope_info_for_local = scope_info_entry
                break

        if is_in_function_scope:
            symbol_type = 'local'
            if 'fp_offset_next_local' not in function_scope_info_for_local:
                raise Exception(
                    f"CodeGen Internal Error: fp_offset_next_local not set for function scope '{function_scope_info_for_local.get('name', 'UNKNOWN')}'.")
            location = function_scope_info_for_local['fp_offset_next_local']
            function_scope_info_for_local['fp_offset_next_local'] -= 1
            if CG_DEBUG_VERBOSE: self.emit(
                f"// DEBUG_CG_ALLOC: Local Var '{var_name}' (Line: {var_name_node.line_no}) assigned FP offset: {location}")
        else:
            symbol_type = 'global'
            location = self.next_available_global_data_address
            self.next_available_global_data_address += 1
            if CG_DEBUG_VERBOSE: self.emit(
                f"// DEBUG_CG_ALLOC: Global Var '{var_name}' (Line: {var_name_node.line_no}) assigned data memory 0x{location:04X}")

        self._add_symbol(var_name, symbol_type, location)
        return self._lookup_symbol(var_name)

    def _generate_address_of_array_element(self, node: ArrayAccessNode):
        """
        Generates SAL to calculate the address of an array element.
        Formula: address = base_address + index
        Returns the temporary register holding the final address.
        """
        array_name = node.name_node.name
        self.emit(f"// Calculating address for {array_name}[...]")

        symbol_info = self._lookup_symbol(array_name)
        if not symbol_info:
            raise Exception(f"CodeGen Error: Use of undeclared array '{array_name}' (Line: {node.line_no}).")
        if symbol_info['type'] != 'array':
            raise Exception(f"CodeGen Error: Symbol '{array_name}' is not an array (Line: {node.line_no}).")

        base_address = symbol_info['loc']

        # 1. Get the index value into a register
        index_reg = node.index_expr_node.accept(self)
        if index_reg is None or not isinstance(index_reg, str):
            raise Exception(f"CodeGen Error: Array index expression for '{array_name}' is invalid.")

        # 2. Get the base address into a register
        addr_reg = self._new_temp()
        self.emit(f"LOAD {addr_reg}, #{base_address}")

        # 3. Add them together: final_address = base_address + index
        self.emit(f"ADD {addr_reg}, {index_reg}")

        # 4. Clean up the index register if it was a temporary one
        self._free_temp(index_reg)

        # The final address is now in addr_reg
        return addr_reg

    def generate(self, ast_root_node):
        self.sal_code = []
        self._initialize_temp_regs()
        self.symbol_tables = [{'type': 'global', 'name': '_global'}]
        self.scope_stack_info = [{'type': 'global', 'var_count': 0, 'name': '_global'}]
        self.next_available_global_data_address = 0x1000
        self.current_function_context = None
        self.function_meta_map = {}

        if not isinstance(ast_root_node, ProgramNode): return ""

        if CG_DEBUG_VERBOSE: print(
            "// DEBUG_CG: Starting generate() - 1st Pass for function metadata and local counts.")
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

                    if CG_DEBUG_VERBOSE: print(f"// DEBUG_CG: Counting locals for function '{func_name_upper}'")
                    self._enter_scope('function', func_name_upper + "_countscope_pass")
                    self.scope_stack_info[-1]['fp_offset_next_local'] = -1
                    self.scope_stack_info[-1]['var_count'] = 0

                    num_locals = self._count_local_vars_recursive(stmt.body_node)
                    if CG_DEBUG_VERBOSE:
                        print(f"// DEBUG_CG: Function '{func_name_upper}' has {num_locals} local(s) from scan.")
                    self._exit_scope()

                    self.function_meta_map[func_name_upper] = {
                        'sal_label': sal_label,
                        'param_names': param_names,
                        'epilogue_label': epilogue_label,
                        'num_locals_from_scan': num_locals
                    }

        global_code_sal = []
        temp_sal_holder = self.sal_code
        self.sal_code = global_code_sal
        has_any_global_executable_code = False

        if hasattr(ast_root_node, 'statements'):
            for stmt in ast_root_node.statements:
                if not isinstance(stmt, FunctionDefinitionNode):
                    if stmt:
                        stmt.accept(self)
                        is_executable = not isinstance(stmt, (VarDeclNode, ArrayDeclNode)) or \
                                        (isinstance(stmt, VarDeclNode) and stmt.init_expr_node)
                        if is_executable:
                            has_any_global_executable_code = True

        self.sal_code = temp_sal_holder
        self.sal_code.extend(global_code_sal)

        main_called_or_global_code_ran = has_any_global_executable_code
        if "MAIN" in self.function_meta_map:
            self.emit(f"CALL {self.function_meta_map['MAIN']['sal_label']}")
            main_called_or_global_code_ran = True

        if main_called_or_global_code_ran:
            if not self.sal_code or self.sal_code[-1].strip().upper() != "HALT":
                self.emit("HALT // Auto-HALT after main logic/global code")
        elif bool(self.function_meta_map):
            self.emit("HALT // No main() or global executable code to run.")
        elif not self.sal_code:
            self.emit("HALT // Empty program.")

        if bool(self.function_meta_map):
            self.emit("\n// --- Function Definitions ---")
            if hasattr(ast_root_node, 'statements'):
                for stmt in ast_root_node.statements:
                    if isinstance(stmt, FunctionDefinitionNode):
                        if stmt: stmt.accept(self)

        if self._currently_used_temps and CG_DEBUG_VERBOSE:
            print(
                f"// WARNING CG: End of gen, {len(self._currently_used_temps)} temp regs used: {self._currently_used_temps}")
        return "\n".join(self.sal_code)

    def _count_local_vars_recursive(self, ast_node):
        count = 0
        if ast_node is None: return 0
        if isinstance(ast_node, VarDeclNode):
            is_in_function_for_counting = any(s['type'] == 'function' for s in reversed(self.scope_stack_info))
            if is_in_function_for_counting:
                count += 1
        elif isinstance(ast_node, ArrayDeclNode):
            pass  # Local arrays not supported, don't count
        elif isinstance(ast_node, ProgramNode) and hasattr(ast_node, 'statements'):
            for stmt_in_block in ast_node.statements:
                count += self._count_local_vars_recursive(stmt_in_block)
        elif isinstance(ast_node, IfNode):
            count += self._count_local_vars_recursive(ast_node.true_block)
            if ast_node.false_block:
                count += self._count_local_vars_recursive(ast_node.false_block)
        elif isinstance(ast_node, WhileNode):
            count += self._count_local_vars_recursive(ast_node.body_block)
        elif isinstance(ast_node, ForNode):
            if isinstance(ast_node.init_node, VarDeclNode):
                if any(s['type'] == 'function' for s in reversed(self.scope_stack_info)):
                    count += 1
            count += self._count_local_vars_recursive(ast_node.body_node)
        return count

    def visit_ArrayDeclNode(self, node):
        if CG_DEBUG_VERBOSE: self.emit(f"// ArrayDecl: {node.var_name_node.name}[{node.size}] (Line: {node.line_no})")
        if len(self.symbol_tables) > 1 or self.scope_stack_info[0]['type'] != 'global':
            raise Exception(
                f"CodeGen Error: Array '{node.var_name_node.name}' declared outside global scope. Local arrays not yet supported. (Line: {node.line_no})")
        array_name = node.var_name_node.name
        array_size = node.size
        if array_name.upper() in self.symbol_tables[-1]:
            raise Exception(
                f"CodeGen Error: Symbol '{array_name}' already declared in this scope (Line: {node.line_no}).")
        base_address = self.next_available_global_data_address
        self.emit(f"// Allocating {array_size} words for array '{array_name}' at 0x{base_address:04X}")
        self._add_symbol(array_name, 'array', base_address, size=array_size)
        self.next_available_global_data_address += array_size

    def visit_VarDeclNode(self, node):
        if CG_DEBUG_VERBOSE: self.emit(f"// VarDecl: {node.var_name_node.name} (Line: {node.line_no})")
        symbol_info = self._allocate_storage_for_decl(node.var_name_node)
        if node.init_expr_node:
            expr_val_reg = node.init_expr_node.accept(self)
            if expr_val_reg is None or not isinstance(expr_val_reg, str):
                raise Exception(
                    f"CodeGen Error: Initializer for '{node.var_name_node.name}' evaluated to invalid register: {expr_val_reg} (Line: {node.line_no}). Type: {type(expr_val_reg)}")
            if not symbol_info:
                raise Exception(
                    f"CodeGen Internal Error: Symbol info for '{node.var_name_node.name}' not found after allocation.")
            if symbol_info['type'] == 'global':
                self.emit(f"STORE {expr_val_reg}, 0x{symbol_info['loc']:04X}")
            elif symbol_info['type'] == 'local':
                self.emit(f"STORFR {expr_val_reg}, {self.frame_pointer_reg}, #{symbol_info['loc']}")
            else:
                raise Exception(
                    f"CodeGen: Cannot initialize VarDeclNode of unknown symbol type '{symbol_info['type']}'")
            if expr_val_reg in self._compiler_temp_pool_master:
                self._free_temp(expr_val_reg)

    def visit_ArrayAccessNode(self, node):
        addr_reg = self._generate_address_of_array_element(node)
        value_reg = self._new_temp()
        self.emit(f"LOADI {value_reg}, {addr_reg} // {value_reg} = Mem[{addr_reg}]")
        self._free_temp(addr_reg)
        return value_reg

    def visit_IdentifierNode(self, node):
        name_upper = node.name.upper()
        if name_upper in ["R0", "R1", "R2", "R3", "R4"]:
            return name_upper
        symbol_info = self._lookup_symbol(node.name)
        if not symbol_info:
            raise Exception(
                f"CodeGen Error: Undeclared identifier '{node.name}' (Line: {node.line_no if node.line_no else 'N/A'})")
        if symbol_info['type'] == 'array':
            raise Exception(
                f"CodeGen Error: Cannot use array '{node.name}' as a simple value. Use array access syntax like '{node.name}[index]'. (Line: {node.line_no})")
        temp_reg = self._new_temp()
        if symbol_info['type'] == 'global':
            self.emit(f"LOADM {temp_reg}, 0x{symbol_info['loc']:04X}")
        elif symbol_info['type'] == 'param' or symbol_info['type'] == 'local':
            self.emit(f"LOADFR {temp_reg}, {self.frame_pointer_reg}, #{symbol_info['loc']}")
        else:
            self._free_temp(temp_reg)
            raise Exception(
                f"CodeGen Error: Unknown symbol type '{symbol_info['type']}' for '{node.name}' during lookup")
        if temp_reg is None or not isinstance(temp_reg, str):
            raise Exception(
                f"CodeGen Error: visit_IdentifierNode for '{node.name}' about to return invalid register: {temp_reg}")
        return temp_reg

    def visit_AssignmentNode(self, node):
        target_node = node.target_name
        if isinstance(target_node, IdentifierNode):
            expr_val_reg = node.value_expr.accept(self)
            if expr_val_reg is None: raise Exception(f"RHS of assignment to '{target_node.name}' is invalid.")
            symbol_info = self._lookup_symbol(target_node.name)
            if not symbol_info: raise Exception(f"Assignment to undeclared variable '{target_node.name}'.")

            if symbol_info['type'] == 'global':
                self.emit(f"STORE {expr_val_reg}, 0x{symbol_info['loc']:04X}")
            elif symbol_info['type'] in ['param', 'local']:
                self.emit(f"STORFR {expr_val_reg}, {self.frame_pointer_reg}, #{symbol_info['loc']}")
            else:
                raise Exception(f"Invalid target symbol type '{symbol_info['type']}' for assignment.")
            self._free_temp(expr_val_reg)
        elif isinstance(target_node, ArrayAccessNode):
            self.emit(f"// Assignment to array element {target_node.name_node.name}[...]")
            addr_reg = self._generate_address_of_array_element(target_node)
            value_reg = node.value_expr.accept(self)
            if value_reg is None: raise Exception("RHS of array assignment is invalid.")
            self.emit(f"STORI {value_reg}, {addr_reg} // Mem[{addr_reg}] = {value_reg}")
            self._free_temp(addr_reg)
            self._free_temp(value_reg)
        else:
            raise Exception(f"CodeGen Error: Invalid target for assignment (Type: {type(target_node).__name__}).")

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
        if CG_DEBUG_VERBOSE: self.emit(
            f"// DEBUG_CG: Function '{func_name_upper}' allocating space for {num_locals_to_alloc} locals based on scan.")
        if num_locals_to_alloc > 0:
            for _ in range(num_locals_to_alloc):
                self.emit(f"PUSH R0 // Allocate 1 word for local")
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

    def visit_ForNode(self, node):
        if node.init_node:
            node.init_node.accept(self)
        loop_body_label = self.new_label("FOR_BODY")
        loop_condition_label = self.new_label("FOR_COND")
        loop_update_target_label = self.new_label("FOR_UPDATE")
        loop_end_label = self.new_label("FOR_END")
        self.emit(f"JMP {loop_condition_label}")
        self.emit(f"{loop_body_label}:")
        if node.body_node:
            node.body_node.accept(self)
        self.emit(f"{loop_update_target_label}:")
        if node.update_expr_stmt_node:
            node.update_expr_stmt_node.accept(self)
        self.emit(f"JMP {loop_condition_label}")
        self.emit(f"{loop_condition_label}:")
        if node.condition_expr_node:
            self._generate_conditional_branch(node.condition_expr_node, loop_body_label, loop_end_label)
        else:
            self.emit(f"JMP {loop_body_label} // FOR: No condition, infinite loop")
        self.emit(f"{loop_end_label}:")

    def visit_PrintNode(self, node):
        expr_result_reg = node.expression.accept(self);
        if expr_result_reg is None or not isinstance(expr_result_reg, str):
            raise Exception(
                f"CodeGen Error: Expression for PRINT evaluated to invalid register value: {expr_result_reg} (Line: {node.line_no}).")
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
                if reg_left is None or not isinstance(reg_left, str) or \
                        reg_right is None or not isinstance(reg_right, str):
                    raise Exception(
                        f"CodeGen Error: Operand for comparison '{op}' is not a valid register name. Left='{reg_left}', Right='{reg_right}'.")
                self.emit(f"CMP {reg_left}, {reg_right}")
                if reg_left in self._compiler_temp_pool_master: self._free_temp(reg_left)
                if reg_right in self._compiler_temp_pool_master: self._free_temp(reg_right)
                if op == '==':
                    self.emit(f"JE {true_branch_label}")
                elif op == '!=':
                    self.emit(f"JNE {true_branch_label}")
                elif op == '<':
                    lbl_sf1 = self.new_label("SLT_SF1");
                    self.emit(f"JS {lbl_sf1}");
                    self.emit(f"JO {true_branch_label}");
                    self.emit(f"JMP {false_branch_label}");
                    self.emit(f"{lbl_sf1}:");
                    self.emit(f"JNO {true_branch_label}");
                elif op == '>=':
                    lbl_sf1 = self.new_label("SGE_SF1");
                    self.emit(f"JS {lbl_sf1}");
                    self.emit(f"JNO {true_branch_label}");
                    self.emit(f"JMP {false_branch_label}");
                    self.emit(f"{lbl_sf1}:");
                    self.emit(f"JO {true_branch_label}");
                elif op == '>':
                    self.emit(f"JE {false_branch_label}");
                    lbl_sf1 = self.new_label("SGT_SF1");
                    self.emit(f"JS {lbl_sf1}");
                    self.emit(f"JNO {true_branch_label}");
                    self.emit(f"JMP {false_branch_label}");
                    self.emit(f"{lbl_sf1}:");
                    self.emit(f"JO {true_branch_label}");
                elif op == '<=':
                    self.emit(f"JE {true_branch_label}");
                    lbl_sf1 = self.new_label("SLE_SF1");
                    self.emit(f"JS {lbl_sf1}");
                    self.emit(f"JO {true_branch_label}");
                    self.emit(f"JMP {false_branch_label}");
                    self.emit(f"{lbl_sf1}:");
                    self.emit(f"JNO {true_branch_label}");
                self.emit(f"JMP {false_branch_label}")
                return
        elif isinstance(condition_node, UnaryOpNode) and condition_node.op == '!':
            self._generate_conditional_branch(condition_node.operand, false_branch_label, true_branch_label)
            return
        result_reg = condition_node.accept(self)
        if result_reg is None or not isinstance(result_reg, str):
            raise Exception(
                f"CodeGen Error: Condition node '{condition_node!r}' did not evaluate to a valid register name.")
        temp_zero_reg = self._new_temp()
        self.emit(f"LOAD {temp_zero_reg}, #0")
        self.emit(f"CMP {result_reg}, {temp_zero_reg}")
        self._free_temp(temp_zero_reg)
        if result_reg in self._compiler_temp_pool_master:
            self._free_temp(result_reg)
        self.emit(f"JNE {true_branch_label}")
        self.emit(f"JMP {false_branch_label}")

    def visit_IfNode(self, node):
        true_label = self.new_label("IF_TRUE")
        end_if_label = self.new_label("IF_END")
        false_destination_label = end_if_label
        if node.false_block:
            else_label = self.new_label("IF_ELSE")
            false_destination_label = else_label
        self._generate_conditional_branch(node.condition, true_label, false_destination_label)
        self.emit(f"{true_label}:")
        if node.true_block: node.true_block.accept(self)
        if node.false_block:
            self.emit(f"JMP {end_if_label}")
            self.emit(f"{else_label}:")
            node.false_block.accept(self)
        self.emit(f"{end_if_label}:")

    def visit_WhileNode(self, node):
        condition_label = self.new_label("WHILE_COND")
        body_label = self.new_label("WHILE_BODY")
        end_while_label = self.new_label("WHILE_END")
        self.emit(f"JMP {condition_label}")
        self.emit(f"{body_label}:")
        if node.body_block: node.body_block.accept(self)
        self.emit(f"JMP {condition_label}")
        self.emit(f"{condition_label}:")
        self._generate_conditional_branch(node.condition, body_label, end_while_label)
        self.emit(f"{end_while_label}:")

    def visit_NumberNode(self, node):
        reg = self._new_temp()
        self.emit(f"LOAD {reg}, #{node.value}")
        if reg is None:
            raise Exception("CodeGen Error: _new_temp returned None in visit_NumberNode")
        return reg

    def visit_BinaryOpNode(self, node):
        reg_left = node.left.accept(self)
        reg_right = node.right.accept(self)
        if reg_left is None or not isinstance(reg_left, str):
            raise Exception(
                f"CodeGen Error: Left operand for binary op '{node.op}' is invalid: {reg_left} (Node: {node.left!r})")
        if reg_right is None or not isinstance(reg_right, str):
            raise Exception(
                f"CodeGen Error: Right operand for binary op '{node.op}' is invalid: {reg_right} (Node: {node.right!r})")
        op = node.op
        result_reg = reg_left
        if reg_left not in self._compiler_temp_pool_master:
            result_reg = self._new_temp()
            self.emit(f"MOV {result_reg}, {reg_left}")
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
            self.emit(f"CMP {result_reg}, {reg_right}")
            true_lbl_bool = self.new_label("BOOL_TRUE_VAL")
            false_lbl_bool = self.new_label("BOOL_FALSE_VAL")
            end_lbl_bool = self.new_label("BOOL_END_VAL")
            if op == '==':
                self.emit(f"JE {true_lbl_bool}")
            elif op == '!=':
                self.emit(f"JNE {true_lbl_bool}")
            elif op == '<':
                lbl_sf1 = self.new_label("SLT_SF1_BINVAL");
                self.emit(f"JS {lbl_sf1}");
                self.emit(f"JO {true_lbl_bool}");
                self.emit(f"JMP {false_lbl_bool}");
                self.emit(f"{lbl_sf1}:");
                self.emit(f"JNO {true_lbl_bool}");
            elif op == '>=':
                lbl_sf1 = self.new_label("SGE_SF1_BINVAL");
                self.emit(f"JS {lbl_sf1}");
                self.emit(f"JNO {true_lbl_bool}");
                self.emit(f"JMP {false_lbl_bool}");
                self.emit(f"{lbl_sf1}:");
                self.emit(f"JO {true_lbl_bool}");
            elif op == '>':
                self.emit(f"JE {false_lbl_bool}");
                lbl_sf1 = self.new_label("SGT_SF1_BINVAL");
                self.emit(f"JS {lbl_sf1}");
                self.emit(f"JNO {true_lbl_bool}");
                self.emit(f"JMP {false_lbl_bool}");
                self.emit(f"{lbl_sf1}:");
                self.emit(f"JO {true_lbl_bool}");
            elif op == '<=':
                self.emit(f"JE {true_lbl_bool}");
                lbl_sf1 = self.new_label("SLE_SF1_BINVAL");
                self.emit(f"JS {lbl_sf1}");
                self.emit(f"JO {true_lbl_bool}");
                self.emit(f"JMP {false_lbl_bool}");
                self.emit(f"{lbl_sf1}:");
                self.emit(f"JNO {true_lbl_bool}");
            self.emit(f"JMP {false_lbl_bool}");
            self.emit(f"{true_lbl_bool}:")
            self.emit(f"LOAD {result_reg}, #1")
            self.emit(f"JMP {end_lbl_bool}")
            self.emit(f"{false_lbl_bool}:")
            self.emit(f"LOAD {result_reg}, #0")
            self.emit(f"{end_lbl_bool}:")
        else:
            self.emit(f"LOAD {result_reg}, #-1 // ERROR: Unhandled binary op '{op}'")
        if reg_right in self._compiler_temp_pool_master:
            self._free_temp(reg_right)
        if result_reg is None or not isinstance(result_reg, str):
            raise Exception(
                f"CodeGen Error: visit_BinaryOpNode op '{op}' terminally resulted in invalid register: {result_reg}")
        return result_reg

    def visit_UnaryOpNode(self, node):
        operand_reg = node.operand.accept(self)
        if operand_reg is None or not isinstance(operand_reg, str):
            raise Exception(
                f"CodeGen Error: Operand for unary op '{node.op}' did not evaluate to a valid register name. Got: {operand_reg}")
        op = node.op
        result_reg = operand_reg
        new_temp_for_result = False
        if operand_reg not in self._compiler_temp_pool_master:
            result_reg = self._new_temp()
            self.emit(f"MOV {result_reg}, {operand_reg}")
            new_temp_for_result = True
        if op == '-':
            temp_zero_reg = self._new_temp()
            self.emit(f"LOAD {temp_zero_reg}, #0")
            self.emit(f"SUB {temp_zero_reg}, {result_reg}")
            self.emit(f"MOV {result_reg}, {temp_zero_reg}")
            self._free_temp(temp_zero_reg)
        elif op == '!':
            self.emit(f"L_NOT {result_reg}, {result_reg}")
        else:
            self.emit(f"LOAD {result_reg}, #-1 // ERROR: Unhandled unary op '{op}'")
        if new_temp_for_result and operand_reg in self._compiler_temp_pool_master:
            self._free_temp(operand_reg)
        if result_reg is None or not isinstance(result_reg, str):
            raise Exception(
                f"CodeGen Error: visit_UnaryOpNode op '{op}' terminally resulted in invalid register: {result_reg}")
        return result_reg

    def visit_ExpressionStatementNode(self, node):
        if node.expression:
            if isinstance(node.expression, AssignmentNode):
                node.expression.accept(self)
            else:
                result_reg = node.expression.accept(self)
                if result_reg and isinstance(result_reg, str) and result_reg in self._compiler_temp_pool_master:
                    self._free_temp(result_reg)

    def visit_ReturnNode(self, node):
        if not self.current_function_context:
            raise Exception(f"CodeGen Error: Return statement outside of a function (Line: {node.line_no}).")
        if node.expr_node:
            expr_val_reg = node.expr_node.accept(self)
            if expr_val_reg is None or not isinstance(expr_val_reg, str):
                raise Exception(
                    f"CodeGen Error: Return expression evaluated to invalid register: {expr_val_reg} (Line: {node.line_no}). Type: {type(expr_val_reg)}")
            if expr_val_reg != self.return_value_reg:
                self.emit(f"MOV {self.return_value_reg}, {expr_val_reg}")
            if expr_val_reg in self._compiler_temp_pool_master and expr_val_reg != self.return_value_reg:
                self._free_temp(expr_val_reg)
        self.emit(f"JMP {self.current_function_context['epilogue_label']}")

    def visit_FunctionCallNode(self, node):
        func_name_upper = node.name_node.name.upper()
        func_meta = self.function_meta_map.get(func_name_upper)
        if not func_meta:
            raise Exception(f"CodeGen Error: Call to undefined function '{node.name_node.name}' (Line: {node.line_no})")
        num_expected_params = len(func_meta['param_names'])
        num_provided_args = len(node.args_nodes)
        if num_expected_params != num_provided_args:
            raise Exception(
                f"CodeGen Error: Function '{func_name_upper}' expects {num_expected_params} arg(s), got {num_provided_args} (Line: {node.line_no}).")
        self.emit(f"// Calling function: {node.name_node.name} ({num_provided_args} args)")
        temp_arg_regs_used = []
        for arg_expr_node in reversed(node.args_nodes):
            arg_val_reg = arg_expr_node.accept(self)
            if arg_val_reg is None or not isinstance(arg_val_reg, str):
                raise Exception(
                    f"CodeGen Error: Argument for call to '{func_name_upper}' evaluated to invalid register: {arg_val_reg}.")
            self.emit(f"PUSH {arg_val_reg}")
            if arg_val_reg in self._compiler_temp_pool_master:
                temp_arg_regs_used.append(arg_val_reg)
        for temp_reg in temp_arg_regs_used:
            self._free_temp(temp_reg)
        self.emit(f"CALL {func_meta['sal_label']}")
        if num_provided_args > 0:
            self.emit(f"// Caller cleaning up {num_provided_args} argument(s)")
            temp_dummy_for_cleanup = self._new_temp()
            for _ in range(num_provided_args):
                self.emit(f"POP {temp_dummy_for_cleanup}")
            self._free_temp(temp_dummy_for_cleanup)
        return self.return_value_reg

    def generic_visit(self, node):
        if node is None: return
        self.emit(f"// WARNING: Generic visit for AST node type {type(node).__name__} (value: {node!r})")
