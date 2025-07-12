# code_generator.py (with pointer type tracking)

from ast_nodes import (
    Node, ProgramNode, StatementNode, AssignmentNode, PrintNode, IfNode, WhileNode,
    ExpressionNode, NumberNode, IdentifierNode, BinaryOpNode, UnaryOpNode,
    FunctionDefinitionNode, ReturnNode,
    ExpressionStatementNode, FunctionCallNode,
    ForNode, VarDeclNode,
    ArrayDeclNode, ArrayAccessNode
)
from abcore16_defs import GLOBAL_DATA_START_ADDR

# --- Global Debug Switch for Code Generator ---
CG_DEBUG_VERBOSE = False


class SALCodeGenerator:
    def __init__(self):
        self.sal_code = []
        self.label_counter = 0

        self.symbol_tables = [{}]
        self.scope_stack_info = [
            {'type': 'global', 'var_count': 0, 'base_offset': GLOBAL_DATA_START_ADDR, 'name': '_global'}]

        self.next_available_global_data_address = GLOBAL_DATA_START_ADDR
        self._compiler_temp_pool_master = ["R7", "R6", "R4", "R3"]
        self._available_temp_regs = []
        self._currently_used_temps = set()
        self.current_function_context = None
        self.function_meta_map = {}
        self.return_value_reg = "R0"
        self.frame_pointer_reg = "R5"
        self.scratch_reg_1 = "R2"
        self.break_label_stack = []

    # ... (all methods from _initialize_temp_regs to _exit_scope are unchanged) ...
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

    # FIX: _add_symbol now includes data_type
    def _add_symbol(self, name, symbol_type, location_or_offset, size=2, data_type='word'):
        name_upper = name.upper()
        current_scope_sym_table = self.symbol_tables[-1]
        if name_upper in current_scope_sym_table:
            raise Exception(
                f"CodeGen Error: Symbol '{name}' redefined in current scope ('{self.scope_stack_info[-1]['name']}').")
        current_scope_sym_table[name_upper] = {
            'type': symbol_type,
            'loc': location_or_offset,
            'size': size,
            'scope_name': self.scope_stack_info[-1]['name'],
            'data_type': data_type  # 'word' or 'pointer'
        }

    # FIX: _update_symbol_type for promoting a var to a pointer
    def _update_symbol_type(self, name, new_data_type):
        name_upper = name.upper()
        for scope_table in reversed(self.symbol_tables):
            if name_upper in scope_table:
                scope_table[name_upper]['data_type'] = new_data_type
                if CG_DEBUG_VERBOSE: self.emit(f"// SYMBOL UPDATE: {name} is now a {new_data_type}")
                return
        raise Exception(f"CodeGen Internal Error: Cannot update type for unknown symbol '{name}'.")

    def _lookup_symbol(self, name):
        name_upper = name.upper()
        for i, scope_table in enumerate(reversed(self.symbol_tables)):
            if name_upper in scope_table:
                return scope_table[name_upper]
        return None

    # FIX: New helper to determine if an expression results in a pointer
    def _get_expression_type(self, node):
        if isinstance(node, IdentifierNode):
            symbol = self._lookup_symbol(node.name)
            return symbol['data_type'] if symbol else 'word'
        if isinstance(node, UnaryOpNode) and node.op == '&':
            return 'pointer'  # The result of an address-of operation is always a pointer
        if isinstance(node, UnaryOpNode) and node.op == '*':
            # The result of dereferencing a pointer is a word value
            return 'word'
        if isinstance(node, BinaryOpNode) and node.op in ['+', '-']:
            # If either side of an add/sub is a pointer, the result is a pointer
            left_type = self._get_expression_type(node.left)
            right_type = self._get_expression_type(node.right)
            if left_type == 'pointer' or right_type == 'pointer':
                return 'pointer'
        # Default case for numbers, other expressions
        return 'word'

    def _allocate_storage_for_decl(self, name_node, size_in_bytes=2, is_array=False, data_type='word'):
        var_name = name_node.name
        if var_name.upper() in self.symbol_tables[-1]:
            raise Exception(
                f"CodeGen Error: Variable '{var_name}' (Line: {name_node.line_no}) already declared in this scope.")

        is_in_function_scope = any(s['type'] == 'function' for s in self.scope_stack_info)
        if is_in_function_scope:
            symbol_type = 'local_array' if is_array else 'local'
            function_scope_info = next(s for s in reversed(self.scope_stack_info) if s['type'] == 'function')
            if 'fp_offset_next_local' not in function_scope_info:
                raise Exception("CodeGen Internal Error: fp_offset_next_local not set.")

            function_scope_info['fp_offset_next_local'] -= size_in_bytes
            location = function_scope_info['fp_offset_next_local']

            self._add_symbol(var_name, symbol_type, location, size=size_in_bytes, data_type=data_type)
        else:
            symbol_type = 'array' if is_array else 'global'
            location = self.next_available_global_data_address
            self.next_available_global_data_address += size_in_bytes
            self._add_symbol(var_name, symbol_type, location, size=size_in_bytes, data_type=data_type)
            if is_array:
                self.emit(
                    f"// Allocating {size_in_bytes // 2} words ({size_in_bytes} bytes) for global array '{var_name}' at 0x{location:04X}")

        return self._lookup_symbol(var_name)

    # ... (generate_address_of_array_element is unchanged) ...
    def _generate_address_of_array_element(self, node: ArrayAccessNode):
        array_name = node.name_node.name
        self.emit(f"// Calculating address for {array_name}[...]")
        symbol_info = self._lookup_symbol(array_name)
        if not symbol_info or symbol_info['type'] not in ['array', 'local_array']:
            raise Exception(f"CodeGen Error: '{array_name}' is not a declared array.")

        index_reg = node.index_expr_node.accept(self)
        addr_reg = self._new_temp()

        if symbol_info['type'] == 'local_array':
            self.emit(f"MOV {addr_reg}, {self.frame_pointer_reg}")
            offset_reg = self._new_temp()
            offset_val = symbol_info['loc']
            self.emit(f"LOAD {offset_reg}, #{abs(offset_val)}")
            self.emit(f"SUB {addr_reg}, {offset_reg}")
            self._free_temp(offset_reg)
        else:
            base_address = symbol_info['loc']
            self.emit(f"LOAD {addr_reg}, #{base_address}")

        self.emit(f"SHL {index_reg}, #1")
        self.emit(f"ADD {addr_reg}, {index_reg}")
        self._free_temp(index_reg)
        return addr_reg

    # ... (generate is unchanged) ...
    def generate(self, ast_root_node):
        self.sal_code = []
        self._initialize_temp_regs()
        self.symbol_tables = [{'type': 'global', 'name': '_global'}]
        self.scope_stack_info = [{'type': 'global', 'var_count': 0, 'name': '_global'}]
        self.next_available_global_data_address = GLOBAL_DATA_START_ADDR
        self.current_function_context = None
        self.function_meta_map = {}

        if not isinstance(ast_root_node, ProgramNode): return ""
        if CG_DEBUG_VERBOSE: print("// DEBUG_CG: Starting generate() - 1st Pass...")
        if hasattr(ast_root_node, 'statements'):
            for stmt in ast_root_node.statements:
                if isinstance(stmt, FunctionDefinitionNode):
                    func_name_upper = stmt.name_node.name.upper()
                    if func_name_upper in self.function_meta_map:
                        raise Exception(f"CodeGen Error: Function '{func_name_upper}' redefined.")
                    sal_label = self.new_label(f"FUNC_{func_name_upper}")
                    epilogue_label = self.new_label(f"EPILOGUE_{func_name_upper}")
                    param_names = [p.name.upper() for p in stmt.params_nodes]
                    self._enter_scope('function', func_name_upper + "_countscope_pass")
                    local_storage_bytes = self._calculate_local_storage_size_recursive(stmt.body_node)
                    self._exit_scope()
                    self.function_meta_map[func_name_upper] = {
                        'sal_label': sal_label,
                        'param_names': param_names,
                        'epilogue_label': epilogue_label,
                        'local_storage_bytes': local_storage_bytes
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
                        is_executable = not isinstance(stmt, (VarDeclNode, ArrayDeclNode)) or (
                                isinstance(stmt, VarDeclNode) and stmt.init_expr_node)
                        if is_executable: has_any_global_executable_code = True
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

    # ... (_calculate_local_storage_size_recursive and visit_ArrayDeclNode are unchanged) ...
    def _calculate_local_storage_size_recursive(self, ast_node):
        size = 0
        if ast_node is None:
            return 0

        is_in_function = any(s['type'] == 'function' for s in self.scope_stack_info)

        if isinstance(ast_node, VarDeclNode):
            if is_in_function:
                size += 2
        elif isinstance(ast_node, ArrayDeclNode):
            if is_in_function:
                size += ast_node.size * 2
        elif isinstance(ast_node, ProgramNode) and hasattr(ast_node, 'statements'):
            for stmt_in_block in ast_node.statements:
                size += self._calculate_local_storage_size_recursive(stmt_in_block)
        elif isinstance(ast_node, IfNode):
            size += self._calculate_local_storage_size_recursive(ast_node.true_block)
            if ast_node.false_block:
                size += self._calculate_local_storage_size_recursive(ast_node.false_block)
        elif isinstance(ast_node, ForNode):
            if isinstance(ast_node.init_node, VarDeclNode) and is_in_function:
                size += 2
            size += self._calculate_local_storage_size_recursive(ast_node.body_node)

        return size

    def visit_ArrayDeclNode(self, node):
        if CG_DEBUG_VERBOSE: self.emit(f"// ArrayDecl: {node.var_name_node.name}[{node.size}]")
        array_size_in_bytes = node.size * 2
        # For arrays, data_type can be considered 'pointer' as its name evaluates to its base address
        self._allocate_storage_for_decl(node.var_name_node, array_size_in_bytes, is_array=True, data_type='pointer')

    # FIX: visit_VarDeclNode now checks for pointer initialization
    def visit_VarDeclNode(self, node):
        if CG_DEBUG_VERBOSE: self.emit(f"// VarDecl: {node.var_name_node.name} (Line: {node.line_no})")

        var_data_type = 'word'
        if node.init_expr_node:
            var_data_type = self._get_expression_type(node.init_expr_node)

        symbol_info = self._allocate_storage_for_decl(node.var_name_node, is_array=False, data_type=var_data_type)

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
            elif symbol_info['type'] in ['local', 'local_array']:
                self.emit(f"STORFR {expr_val_reg}, {self.frame_pointer_reg}, #{symbol_info['loc']}")
            else:
                raise Exception(
                    f"CodeGen: Cannot initialize VarDeclNode of unknown symbol type '{symbol_info['type']}'")
            if expr_val_reg in self._compiler_temp_pool_master:
                self._free_temp(expr_val_reg)

    # ... (visit_ArrayAccessNode is unchanged) ...
    def visit_ArrayAccessNode(self, node):
        addr_reg = self._generate_address_of_array_element(node)
        value_reg = self._new_temp()
        self.emit(f"LOADI {value_reg}, {addr_reg} // {value_reg} = Mem[{addr_reg}]")
        self._free_temp(addr_reg)
        return value_reg

    def visit_IdentifierNode(self, node):
        name_upper = node.name.upper()
        if name_upper in ["R0", "R1", "R2", "R3", "R4", "R5"]:
            return name_upper
        symbol_info = self._lookup_symbol(node.name)
        if not symbol_info:
            raise Exception(
                f"CodeGen Error: Undeclared identifier '{node.name}' (Line: {node.line_no if node.line_no else 'N/A'})")

        if symbol_info['type'] in ['array', 'local_array']:
            # FIX: An array name on its own resolves to its base address, which is a pointer.
            self.emit(f"// Resolving array name '{node.name}' to its base address")
            temp_reg = self._new_temp()
            if symbol_info['type'] == 'array':  # Global array
                self.emit(f"LOAD {temp_reg}, #{symbol_info['loc']}")
            else:  # Local array
                self.emit(f"MOV {temp_reg}, {self.frame_pointer_reg}")
                offset_reg = self._new_temp()
                offset_val = symbol_info['loc']
                self.emit(f"LOAD {offset_reg}, #{abs(offset_val)}")
                self.emit(f"SUB {temp_reg}, {offset_reg}")
                self._free_temp(offset_reg)
            return temp_reg

        temp_reg = self._new_temp()
        if symbol_info['type'] == 'global':
            self.emit(f"LOADM {temp_reg}, 0x{symbol_info['loc']:04X}")
        elif symbol_info['type'] == 'param':
            self.emit(f"LOADFR {temp_reg}, {self.frame_pointer_reg}, #{symbol_info['loc']}")
        elif symbol_info['type'] == 'local':
            self.emit(f"LOADFR {temp_reg}, {self.frame_pointer_reg}, #{symbol_info['loc']}")
        else:
            self._free_temp(temp_reg)
            raise Exception(
                f"CodeGen Error: Unknown symbol type '{symbol_info['type']}' for '{node.name}' during lookup")
        if temp_reg is None or not isinstance(temp_reg, str):
            raise Exception(
                f"CodeGen Error: visit_IdentifierNode for '{node.name}' about to return invalid register: {temp_reg}")
        return temp_reg

    # FIX: visit_AssignmentNode now promotes variables to pointers on address assignment
    def visit_AssignmentNode(self, node):
        target_node = node.target_name

        if isinstance(target_node, IdentifierNode):
            # Check if we are assigning an address to this variable.
            # If so, its data_type becomes 'pointer'.
            value_type = self._get_expression_type(node.value_expr)
            if value_type == 'pointer':
                self._update_symbol_type(target_node.name, 'pointer')

        if isinstance(target_node, UnaryOpNode) and target_node.op == '*':
            self.emit(f"// --- Assignment to Dereferenced Pointer * (Line: {node.line_no}) ---")
            addr_reg = target_node.operand.accept(self)
            value_reg = node.value_expr.accept(self)
            self.emit(f"STORI {value_reg}, {addr_reg} // Storing value from {value_reg} into address in {addr_reg}")
            self._free_temp(value_reg)
            self._free_temp(addr_reg)
            return

        elif isinstance(target_node, IdentifierNode):
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
            value_reg = node.value_expr.accept(self)
            if value_reg is None: raise Exception("RHS of array assignment is invalid.")
            addr_reg = self._generate_address_of_array_element(target_node)
            self.emit(f"STORI {value_reg}, {addr_reg} // Mem[{addr_reg}] = {value_reg}")
            self._free_temp(addr_reg)
            self._free_temp(value_reg)
        else:
            raise Exception(f"CodeGen Error: Invalid target for assignment (Type: {type(target_node).__name__}).")

    # ... (rest of file is unchanged, including BinaryOpNode for now) ...
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
            'local_storage_bytes': func_meta['local_storage_bytes']
        }
        self._enter_scope('function', scope_name=func_name_upper)
        current_function_scope_info = self.scope_stack_info[-1]

        current_function_scope_info['fp_offset_next_local'] = 0

        for i, param_node in enumerate(node.params_nodes):
            param_name_upper = param_node.name.upper()
            offset = 6 + (i * 2)
            self.current_function_context['param_map'][param_name_upper] = offset
            self._add_symbol(param_node.name, 'param', offset)

        self.emit(f"\n// Function: {node.name_node.name}({', '.join(p.name for p in node.params_nodes)})")
        self.emit(f"{self.current_function_context['sal_label']}:")
        self.emit(f"PUSH {self.frame_pointer_reg}")
        self.emit(f"MOVFRSP {self.frame_pointer_reg}")

        local_storage_bytes_to_alloc = self.current_function_context['local_storage_bytes']
        if CG_DEBUG_VERBOSE: self.emit(
            f"// DEBUG_CG: Function '{func_name_upper}' allocating {local_storage_bytes_to_alloc} bytes for local storage.")

        if local_storage_bytes_to_alloc > 0:
            self.emit(f"// Allocating {local_storage_bytes_to_alloc} bytes on stack for locals")
            alloc_reg = self._new_temp()
            self.emit(f"LOAD {alloc_reg}, #{local_storage_bytes_to_alloc}")
            self.emit(f"MOVFRSP {self.scratch_reg_1}")
            self.emit(f"SUB {self.scratch_reg_1}, {alloc_reg}")
            self.emit(f"MOVTOSP {self.scratch_reg_1}")
            self._free_temp(alloc_reg)

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
        if local_storage_bytes_to_alloc > 0:
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
        loop_update_label = self.new_label("FOR_UPDATE")
        loop_end_label = self.new_label("FOR_END")

        self.emit(f"JMP {loop_condition_label}")
        self.emit(f"{loop_body_label}:")
        if node.body_node:
            node.body_node.accept(self)

        self.emit(f"{loop_update_label}:")
        if node.update_expr_stmt_node:
            node.update_expr_stmt_node.accept(self)

        self.emit(f"{loop_condition_label}:")
        if node.condition_expr_node:
            self._generate_conditional_branch(node.condition_expr_node, loop_body_label, loop_end_label)
        else:
            self.emit(f"JMP {loop_body_label} // FOR: No condition, infinite loop")
        self.emit(f"{loop_end_label}:")

    def visit_BreakNode(self, node):
        if not self.break_label_stack:
            raise Exception("CodeGen Error: 'break' statement found outside of a switch or loop.")

        # Get the label for the end of the current switch/loop
        end_label = self.break_label_stack[-1]
        self.emit(f"JMP {end_label}")

    def visit_SwitchNode(self, node):
        self.emit(f"// --- SWITCH statement (Line: {node.line_no}) ---")

        # Create unique labels for the switch structure
        end_switch_label = self.new_label("SWITCH_END")
        default_case_label = None  # We'll find this as we iterate
        case_labels = []

        # Push the end label onto the stack for 'break' statements to use
        self.break_label_stack.append(end_switch_label)

        # Step 1: Evaluate the switch expression and store its value
        self.emit(f"// Evaluate switch expression")
        expr_reg = node.condition.accept(self)

        # Step 2: Generate the dispatch chain of comparisons and jumps
        self.emit(f"// Dispatch chain")
        for i, case_node in enumerate(node.cases):
            case_body_label = self.new_label("CASE_BODY")
            case_labels.append(case_body_label)

            if case_node.value_expr is not None:  # This is a 'case X:'
                self.emit(f"// Comparing with case: {case_node.value_expr.value}")
                const_reg = case_node.value_expr.accept(self)
                self.emit(f"CMP {expr_reg}, {const_reg}")
                self.emit(f"JE {case_body_label}")
                self._free_temp(const_reg)
            else:  # This is the 'default:' case
                if default_case_label:
                    raise Exception("CodeGen Error: Multiple 'default' cases in one switch statement.")
                default_case_label = case_body_label

        self._free_temp(expr_reg)  # We're done with the expression value now

        # If a default case exists, jump to it. Otherwise, jump to the end.
        if default_case_label:
            self.emit(f"JMP {default_case_label} // No case matched, go to default")
        else:
            self.emit(f"JMP {end_switch_label} // No case matched and no default, exit switch")

        # Step 3: Generate the code for the body of each case
        self.emit(f"\n// Switch case bodies")
        for i, case_node in enumerate(node.cases):
            self.emit(f"{case_labels[i]}:")
            # The CaseNode doesn't need its own visit method; we can just process it here.
            # This is simpler because a CaseNode is just a container for statements.
            if case_node.statements:
                for stmt in case_node.statements:
                    stmt.accept(self)

        # Step 4: Add the end label and clean up the break stack
        self.emit(f"{end_switch_label}: // End of switch statement")
        self.break_label_stack.pop()

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
                self.emit(f"CMP {reg_left}, {reg_right}")
                self._free_temp(reg_left);
                self._free_temp(reg_right)

                if op == '==':
                    self.emit(f"JE {true_branch_label}")
                elif op == '!=':
                    self.emit(f"JNE {true_branch_label}")
                elif op == '<':
                    lbl = self.new_label("SLT");
                    self.emit(f"JS {lbl}");
                    self.emit(
                        f"JO {true_branch_label}");
                    self.emit(f"JMP {false_branch_label}");
                    self.emit(
                        f"{lbl}:");
                    self.emit(f"JNO {true_branch_label}")
                elif op == '>=':
                    lbl = self.new_label("SGE");
                    self.emit(f"JS {lbl}");
                    self.emit(
                        f"JNO {true_branch_label}");
                    self.emit(f"JMP {false_branch_label}");
                    self.emit(
                        f"{lbl}:");
                    self.emit(f"JO {true_branch_label}")
                elif op == '>':
                    self.emit(f"JE {false_branch_label}");
                    lbl = self.new_label("SGT");
                    self.emit(
                        f"JS {lbl}");
                    self.emit(f"JNO {true_branch_label}");
                    self.emit(
                        f"JMP {false_branch_label}");
                    self.emit(f"{lbl}:");
                    self.emit(f"JO {true_branch_label}")
                elif op == '<=':
                    self.emit(f"JE {true_branch_label}");
                    lbl = self.new_label("SLE");
                    self.emit(
                        f"JS {lbl}");
                    self.emit(f"JO {true_branch_label}");
                    self.emit(
                        f"JMP {false_branch_label}");
                    self.emit(f"{lbl}:");
                    self.emit(f"JNO {true_branch_label}")

                self.emit(f"JMP {false_branch_label}")
                return
        elif isinstance(condition_node, UnaryOpNode) and condition_node.op == '!':
            self._generate_conditional_branch(condition_node.operand, false_branch_label, true_branch_label)
            return

        result_reg = condition_node.accept(self)
        if result_reg is None or not isinstance(result_reg, str): raise Exception(
            f"CodeGen Error: Condition node '{condition_node!r}' did not evaluate to a valid register name.")
        temp_zero_reg = self._new_temp()
        self.emit(f"LOAD {temp_zero_reg}, #0")
        self.emit(f"CMP {result_reg}, {temp_zero_reg}")
        self._free_temp(temp_zero_reg);
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
        op = node.op
        if op in ['&&', '||']:
            # This logic is unchanged
            result_reg = self._new_temp()
            end_label = self.new_label("LOGICAL_OP_END")
            true_label = self.new_label("LOGICAL_OP_TRUE")
            false_label = self.new_label("LOGICAL_OP_FALSE")

            if op == '&&':
                eval_right_label = self.new_label("AND_RIGHT")
                self._generate_conditional_branch(node.left, eval_right_label, false_label)
                self.emit(f"{eval_right_label}:")
                self._generate_conditional_branch(node.right, true_label, false_label)
            else:  # ||
                eval_right_label = self.new_label("OR_RIGHT")
                self._generate_conditional_branch(node.left, true_label, eval_right_label)
                self.emit(f"{eval_right_label}:")
                self._generate_conditional_branch(node.right, true_label, false_label)

            self.emit(f"{true_label}:");
            self.emit(f"LOAD {result_reg}, #1");
            self.emit(f"JMP {end_label}")
            self.emit(f"{false_label}:");
            self.emit(f"LOAD {result_reg}, #0")
            self.emit(f"{end_label}:")
            return result_reg

        # FIX: Pointer Arithmetic Implementation
        if op in ['+', '-']:
            left_type = self._get_expression_type(node.left)
            right_type = self._get_expression_type(node.right)

            # Check for pointer arithmetic: pointer + word OR word + pointer
            if (left_type == 'pointer' and right_type == 'word') or \
                    (left_type == 'word' and right_type == 'pointer'):

                self.emit(f"// --- Pointer Arithmetic ({op}) ---")

                reg_ptr = None
                reg_int = None

                if left_type == 'pointer':
                    reg_ptr = node.left.accept(self)
                    reg_int = node.right.accept(self)
                else:  # right_type is pointer
                    reg_int = node.left.accept(self)
                    reg_ptr = node.right.accept(self)

                # Scale the integer value by the word size (2)
                self.emit(f"SHL {reg_int}, #1 // Scale integer for pointer arithmetic")

                # Perform the operation
                if op == '+':
                    self.emit(f"ADD {reg_ptr}, {reg_int}")
                else:  # Subtraction is only valid for `pointer - integer`
                    if left_type != 'pointer':
                        raise Exception("CodeGen Error: Cannot subtract a pointer from an integer.")
                    self.emit(f"SUB {reg_ptr}, {reg_int}")

                self._free_temp(reg_int)
                return reg_ptr  # The result is the new pointer address

        # --- Fallback to original integer/comparison logic ---
        reg_left = node.left.accept(self)
        reg_right = node.right.accept(self)
        if reg_left is None or reg_right is None: raise Exception(
            f"CodeGen Error: Invalid operand for binary op '{op}'.")

        result_reg = reg_left
        if reg_left not in self._compiler_temp_pool_master:
            result_reg = self._new_temp();
            self.emit(f"MOV {result_reg}, {reg_left}")

        # This part is unchanged
        if op == '*':
            self.emit(f"MUL {result_reg}, {reg_right}")
        elif op in ['==', '!=', '<', '>', '<=', '>=']:
            self.emit(f"CMP {result_reg}, {reg_right}")
            true_lbl = self.new_label("BOOL_TRUE");
            false_lbl = self.new_label("BOOL_FALSE");
            end_lbl = self.new_label("BOOL_END")
            if op == '==':
                self.emit(f"JE {true_lbl}")
            elif op == '!=':
                self.emit(f"JNE {true_lbl}")
            elif op == '<':
                lbl = self.new_label("SLT"); self.emit(f"JS {lbl}"); self.emit(f"JO {true_lbl}"); self.emit(
                    f"JMP {false_lbl}"); self.emit(f"{lbl}:"); self.emit(f"JNO {true_lbl}")
            elif op == '>=':
                lbl = self.new_label("SGE"); self.emit(f"JS {lbl}"); self.emit(f"JNO {true_lbl}"); self.emit(
                    f"JMP {false_lbl}"); self.emit(f"{lbl}:"); self.emit(f"JO {true_lbl}")
            elif op == '>':
                self.emit(f"JE {false_lbl}"); lbl = self.new_label("SGT"); self.emit(f"JS {lbl}"); self.emit(
                    f"JNO {true_lbl}"); self.emit(f"JMP {false_lbl}"); self.emit(f"{lbl}:"); self.emit(f"JO {true_lbl}")
            elif op == '<=':
                self.emit(f"JE {true_lbl}"); lbl = self.new_label("SLE"); self.emit(f"JS {lbl}"); self.emit(
                    f"JO {true_lbl}"); self.emit(f"JMP {false_lbl}"); self.emit(f"{lbl}:"); self.emit(f"JNO {true_lbl}")
            self.emit(f"JMP {false_lbl}")
            self.emit(f"{true_lbl}:");
            self.emit(f"LOAD {result_reg}, #1");
            self.emit(f"JMP {end_lbl}")
            self.emit(f"{false_lbl}:");
            self.emit(f"LOAD {result_reg}, #0")
            self.emit(f"{end_lbl}:")
        else:  # This handles '+' and '-' for pure integer ops
            if op == '+':
                self.emit(f"ADD {result_reg}, {reg_right}")
            elif op == '-':
                self.emit(f"SUB {result_reg}, {reg_right}")
            else:
                self.emit(f"LOAD {result_reg}, #-1 // ERROR: Unhandled binary op '{op}'")

        if reg_right in self._compiler_temp_pool_master: self._free_temp(reg_right)
        return result_reg

    def visit_UnaryOpNode(self, node):
        op = node.op

        if op == '&':
            self.emit(f"// --- Address-Of & (Line: {node.line_no}) ---")
            operand = node.operand
            if isinstance(operand, IdentifierNode):
                symbol = self._lookup_symbol(operand.name)
                if not symbol: raise Exception(
                    f"CodeGen Error: Cannot take address of undeclared variable '{operand.name}' on line {node.line_no}.")

                addr_reg = self._new_temp()
                # Using the data_type here is a bit redundant since array names resolve to pointers, but it's clear
                if symbol['data_type'] == 'pointer' and symbol['type'] in ['array', 'local_array']:
                    # This case handles &my_array
                    if symbol['type'] == 'array':  # global array
                        self.emit(f"LOAD {addr_reg}, #{symbol['loc']}")
                    else:  # local array
                        self.emit(f"MOV {addr_reg}, {self.frame_pointer_reg}")
                        offset_reg = self._new_temp()
                        self.emit(f"LOAD {offset_reg}, #{abs(symbol['loc'])}")
                        self.emit(f"SUB {addr_reg}, {offset_reg}")
                        self._free_temp(offset_reg)
                elif symbol['type'] == 'global':
                    self.emit(f"LOAD {addr_reg}, #{symbol['loc']}")
                elif symbol['type'] in ['local', 'param']:
                    self.emit(f"MOV {addr_reg}, {self.frame_pointer_reg}")
                    offset_reg = self._new_temp()
                    offset_val = symbol['loc']
                    self.emit(f"LOAD {offset_reg}, #{abs(offset_val)}")
                    if offset_val >= 0:
                        self.emit(f"ADD {addr_reg}, {offset_reg}")
                    else:
                        self.emit(f"SUB {addr_reg}, {offset_reg}")
                    self._free_temp(offset_reg)
                else:
                    self._free_temp(addr_reg)
                    raise Exception(
                        f"CodeGen Error: Cannot take address of symbol type '{symbol['type']}' for '{operand.name}'.")
                return addr_reg

            elif isinstance(operand, ArrayAccessNode):
                return self._generate_address_of_array_element(operand)

            else:
                raise Exception(
                    f"CodeGen Error: Address-of operator '&' can only be applied to variables or array elements on line {node.line_no}.")


        elif op == '*':
            self.emit(f"// --- Dereference * (as value) (Line: {node.line_no}) ---")
            addr_reg = node.operand.accept(self)
            value_reg = self._new_temp()
            self.emit(f"LOADI {value_reg}, {addr_reg} // {value_reg} = Mem[{addr_reg}]")
            self._free_temp(addr_reg)
            return value_reg

        operand_reg = node.operand.accept(self)
        if operand_reg is None: raise Exception(f"CodeGen Error: Operand for unary op '{op}' is invalid.")

        result_reg = operand_reg
        if operand_reg not in self._compiler_temp_pool_master:
            result_reg = self._new_temp();
            self.emit(f"MOV {result_reg}, {operand_reg}")

        if op == '-':
            temp_zero_reg = self._new_temp();
            self.emit(f"LOAD {temp_zero_reg}, #0")
            self.emit(f"SUB {temp_zero_reg}, {result_reg}");
            self.emit(f"MOV {result_reg}, {temp_zero_reg}")
            self._free_temp(temp_zero_reg)
        elif op == '!':
            self.emit(f"L_NOT {result_reg}, {result_reg}")
        else:
            self.emit(f"LOAD {result_reg}, #-1 // ERROR: Unhandled unary op '{op}'")

        if result_reg != operand_reg: self._free_temp(operand_reg)
        return result_reg

    def visit_PostfixOpNode(self, node):
        op = node.op
        operand_node = node.operand

        # The operand for ++/-- must be something we can assign back to (an "l-value").
        # For now, we'll just support simple identifiers.
        if not isinstance(operand_node, IdentifierNode):
            raise Exception(f"CodeGen Error: Target for '{op}' must be a variable on line {node.line_no}.")

        var_name = operand_node.name
        symbol_info = self._lookup_symbol(var_name)
        if not symbol_info:
            raise Exception(f"CodeGen Error: Cannot {op} undeclared variable '{var_name}' on line {node.line_no}.")

        self.emit(f"// --- Postfix '{op}' on variable '{var_name}' ---")

        # Step 1: Load the current value of the variable. This will be the result of the expression.
        self.emit(f"// Load current value of '{var_name}' to be the expression result.")
        result_reg = operand_node.accept(self)

        # Step 2: Create a second copy of the value that we can modify.
        # This prevents us from modifying the result register.
        val_to_modify_reg = self._new_temp()
        self.emit(f"MOV {val_to_modify_reg}, {result_reg}")

        # Step 3: Increment or decrement the copy.
        is_pointer = (symbol_info.get('data_type') == 'pointer')

        if is_pointer:
            # Pointer arithmetic: add/sub 2
            self.emit(f"// Pointer arithmetic scaling (size=2)")
            scale_reg = self._new_temp()
            self.emit(f"LOAD {scale_reg}, #2")
            if op == '++':
                self.emit(f"ADD {val_to_modify_reg}, {scale_reg}")
            else:  # '--'
                self.emit(f"SUB {val_to_modify_reg}, {scale_reg}")
            self._free_temp(scale_reg)
        else:
            # Integer arithmetic: add/sub 1
            if op == '++':
                self.emit(f"INC {val_to_modify_reg}")
            else:  # '--'
                self.emit(f"DEC {val_to_modify_reg}")

        # Step 4: Store the new, modified value back into the variable's memory location.
        self.emit(f"// Store updated value back into '{var_name}'")
        if symbol_info['type'] == 'global':
            self.emit(f"STORE {val_to_modify_reg}, 0x{symbol_info['loc']:04X}")
        elif symbol_info['type'] in ['local', 'param']:
            self.emit(f"STORFR {val_to_modify_reg}, {self.frame_pointer_reg}, #{symbol_info['loc']}")
        else:
            raise Exception(f"CodeGen Error: Cannot assign back to symbol of type '{symbol_info['type']}'.")

        # Free the register that held the modified value.
        self._free_temp(val_to_modify_reg)

        # Step 5: Return the register holding the *original* value.
        return result_reg

    def visit_ExpressionStatementNode(self, node):
        if node.expression:
            result_reg = node.expression.accept(self)
            if result_reg and isinstance(result_reg, str) and result_reg in self._compiler_temp_pool_master:
                self._free_temp(result_reg)

    def visit_ReturnNode(self, node):
        if not self.current_function_context:
            raise Exception(f"CodeGen Error: Return statement outside of a function (Line: {node.line_no}).")
        if node.expr_node:
            expr_val_reg = node.expr_node.accept(self)
            if expr_val_reg is None: raise Exception(f"CodeGen Error: Return expression evaluated to invalid register.")
            if expr_val_reg != self.return_value_reg: self.emit(f"MOV {self.return_value_reg}, {expr_val_reg}")
            if expr_val_reg in self._compiler_temp_pool_master and expr_val_reg != self.return_value_reg: self._free_temp(
                expr_val_reg)
        self.emit(f"JMP {self.current_function_context['epilogue_label']}")

    def visit_FunctionCallNode(self, node):
        func_name_upper = node.name_node.name.upper()

        if func_name_upper == "MMIO_WRITE":
            if len(node.args_nodes) != 2: raise Exception(
                f"CodeGen Error: mmio_write() requires 2 arguments, got {len(node.args_nodes)} on line {node.line_no}.")
            self.emit(f"// --- Built-in mmio_write Call (Line: {node.line_no}) ---")
            addr_reg = node.args_nodes[0].accept(self)
            value_reg = node.args_nodes[1].accept(self)
            self.emit(f"STORI {value_reg}, {addr_reg} // Mem[{addr_reg}] = {value_reg}")
            self._free_temp(addr_reg);
            self._free_temp(value_reg)
            return None
        if func_name_upper == "MMIO_READ":
            if len(node.args_nodes) != 1: raise Exception(
                f"CodeGen Error: mmio_read() requires 1 argument, got {len(node.args_nodes)} on line {node.line_no}.")
            self.emit(f"// --- Built-in mmio_read Call (Line: {node.line_no}) ---")
            addr_reg = node.args_nodes[0].accept(self)
            result_reg = self._new_temp()
            self.emit(f"LOADI {result_reg}, {addr_reg} // {result_reg} = Mem[{addr_reg}]")
            self._free_temp(addr_reg)
            return result_reg

        func_meta = self.function_meta_map.get(func_name_upper)
        if not func_meta: raise Exception(
            f"CodeGen Error: Call to undefined function '{node.name_node.name}' on line {node.line_no}.")

        num_expected_params = len(func_meta['param_names'])
        num_provided_args = len(node.args_nodes)
        if num_expected_params != num_provided_args: raise Exception(
            f"CodeGen Error: Function '{func_name_upper}' expects {num_expected_params} arg(s), got {num_provided_args} on line {node.line_no}.")

        self.emit(f"// Calling function: {node.name_node.name} ({num_provided_args} args)")
        temp_arg_regs_used = []
        for arg_expr_node in reversed(node.args_nodes):
            arg_val_reg = arg_expr_node.accept(self)
            if arg_val_reg is None: raise Exception(
                f"CodeGen Error: Argument for call to '{func_name_upper}' evaluated to invalid register.")
            self.emit(f"PUSH {arg_val_reg}")
            if arg_val_reg in self._compiler_temp_pool_master:
                temp_arg_regs_used.append(arg_val_reg)

        for temp_reg in temp_arg_regs_used:
            self._free_temp(temp_reg)

        self.emit(f"CALL {func_meta['sal_label']}")
        if num_provided_args > 0:
            self.emit(f"// Caller cleaning up {num_provided_args} argument(s) from stack")
            self.emit(f"MOVFRSP {self.scratch_reg_1}")
            self.emit(f"LOAD {self.return_value_reg}, #{num_provided_args * 2}")
            self.emit(f"ADD {self.scratch_reg_1}, {self.return_value_reg}")
            self.emit(f"MOVTOSP {self.scratch_reg_1}")

        return self.return_value_reg

    def generic_visit(self, node):
        if node is None: return
        self.emit(f"// WARNING: Generic visit for AST node type {type(node).__name__} (value: {node!r})")
