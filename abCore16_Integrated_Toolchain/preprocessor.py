# preprocessor.py
# Final version with #include and conditional compilation support.

import re
import os


class Preprocessor:
    def __init__(self):
        self.macros = {}
        self.errors = []
        self.included_files = set()
        self.base_dir = '.'
        # --- NEW: Stack for conditional compilation ---
        # Each element is a tuple: (is_block_active, has_active_branch_been_found)
        self.if_stack = []

    def _is_active(self):
        """Checks if the current preprocessor state is active (i.e., not inside a false #if block)."""
        if not self.if_stack:
            return True  # We are in the top-level scope, always active
        # The block is active only if the top of the stack is active
        return self.if_stack[-1][0]

    def _parse_define(self, line):
        """Parses a #define directive and stores it."""
        match = re.match(r'^\s*#\s*define\s+([a-zA-Z_][a-zA-Z_0-9]*)(\(.*\))?(.*)', line)
        if not match:
            self.errors.append(f"Malformed #define directive: {line}")
            return
        name, args_str, body_str = match.groups()
        body = body_str.strip()
        if name in self.macros:
            print(f"Preprocessor WARNING: Macro '{name}' is being redefined.")
        if args_str:
            args = [arg.strip() for arg in args_str.strip('()').split(',') if arg.strip()]
            self.macros[name] = {'args': args, 'body': body}
        else:
            self.macros[name] = body

    def _expand_macros_in_line(self, line):
        # This method remains unchanged
        for _ in range(100):
            original_line = line
            for name, definition in self.macros.items():
                if isinstance(definition, str):
                    line = re.sub(r'\b' + name + r'\b', definition, line)
                else:
                    pattern = r'\b' + name + r'\s*\(([^)]*)\)'

                    def repl(m):
                        call_args = [arg.strip() for arg in m.group(1).split(',')]
                        if len(call_args) != len(definition['args']):
                            self.errors.append(
                                f"Macro '{name}' expected {len(definition['args'])} args, got {len(call_args)}.")
                            return m.group(0)
                        expanded_body = definition['body']
                        for i, arg_name in enumerate(definition['args']):
                            expanded_body = re.sub(r'\b' + arg_name + r'\b', call_args[i], expanded_body)
                        return expanded_body

                    line = re.sub(pattern, repl, line)
            if line == original_line:
                return line
        self.errors.append(f"Possible infinite macro recursion in line: {line}")
        return line

    def _process_file_recursive(self, filepath):
        """
        Reads a single file and processes all directives (#include, #define, #ifdef, etc.).
        Returns a list of code lines to be processed in the second pass.
        """
        abs_filepath = os.path.abspath(filepath)
        if abs_filepath in self.included_files and not self.if_stack:
            # Standard include guard behavior: only include a file once at the top level.
            # Allows for re-inclusion inside conditional blocks if necessary, though unusual.
            return []
        self.included_files.add(abs_filepath)

        processed_lines = []
        current_dir = os.path.dirname(abs_filepath)

        try:
            with open(abs_filepath, 'r') as f:
                for line_num, line in enumerate(f, 1):
                    stripped_line = line.strip()

                    # --- CONDITIONAL COMPILATION LOGIC ---
                    ifdef_match = re.match(r'^\s*#\s*ifdef\s+([a-zA-Z_][a-zA-Z_0-9]*)', stripped_line)
                    ifndef_match = re.match(r'^\s*#\s*ifndef\s+([a-zA-Z_][a-zA-Z_0-9]*)', stripped_line)
                    else_match = re.match(r'^\s*#\s*else', stripped_line)
                    endif_match = re.match(r'^\s*#\s*endif', stripped_line)

                    if ifdef_match:
                        macro_name = ifdef_match.group(1)
                        parent_active = self._is_active()
                        is_defined = macro_name in self.macros
                        # This block is active if the parent is active AND the macro is defined
                        is_active_now = parent_active and is_defined
                        self.if_stack.append((is_active_now, is_defined))
                        continue  # Move to next line

                    if ifndef_match:
                        macro_name = ifndef_match.group(1)
                        parent_active = self._is_active()
                        is_defined = macro_name in self.macros
                        # This block is active if the parent is active AND the macro is NOT defined
                        is_active_now = parent_active and not is_defined
                        self.if_stack.append((is_active_now, not is_defined))
                        continue

                    if else_match:
                        if not self.if_stack:
                            self.errors.append(f"Found #else without #if at {filepath}:{line_num}")
                            continue
                        parent_active = all(s[0] for s in self.if_stack[:-1])
                        _, has_found_true_branch = self.if_stack[-1]
                        # Activate if parent is active and no previous branch in this #if was taken
                        is_active_now = parent_active and not has_found_true_branch
                        self.if_stack[-1] = (is_active_now, True)  # Mark that a branch has been taken
                        continue

                    if endif_match:
                        if not self.if_stack:
                            self.errors.append(f"Found #endif without #if at {filepath}:{line_num}")
                            continue
                        self.if_stack.pop()
                        continue

                    # --- REGULAR DIRECTIVE AND CODE PROCESSING ---
                    # Only process if we are in an active block
                    if not self._is_active():
                        continue

                    include_match = re.match(r'^\s*#\s*include\s*"(.*)"', stripped_line)
                    if include_match:
                        include_filename = include_match.group(1)
                        include_filepath = os.path.join(current_dir, include_filename)
                        processed_lines.extend(self._process_file_recursive(include_filepath))
                    elif re.match(r'^\s*#\s*define', stripped_line):
                        self._parse_define(stripped_line)
                    else:
                        processed_lines.append(line)
        except FileNotFoundError:
            self.errors.append(f"File not found: {abs_filepath}")

        return processed_lines

    def process(self, main_filepath):
        """Main entry point. Processes a source file and all its includes."""
        # Reset state for a new run
        self.macros = {}
        self.errors = []
        self.included_files = set()
        self.if_stack = []
        self.base_dir = os.path.dirname(os.path.abspath(main_filepath))

        print(f"PREPROCESSOR: Starting pass 1 on main file '{main_filepath}'...")
        all_lines = self._process_file_recursive(main_filepath)

        if self.if_stack:
            self.errors.append("Unterminated #if/#ifdef block at end of file.")

        if self.errors:
            return "", True

        print("PREPROCESSOR: Starting pass 2 for macro expansion...")
        output_code = []
        for line in all_lines:
            parts = line.split('//', 1)
            code_part = parts[0]
            comment_part = f"//{parts[1]}\n" if len(parts) > 1 else "\n"

            expanded_code = self._expand_macros_in_line(code_part)
            # Append code part and comment part separately to preserve newlines
            output_code.append(expanded_code)
            if not line.endswith('\n'):
                # Add newline if original line didn't have one but comment does
                if comment_part != '\n':
                    output_code.append(comment_part)
            else:
                if expanded_code:  # Only add newline if there is code
                    output_code.append(comment_part)
                else:  # Preserve empty lines
                    output_code.append('\n')

        final_code = "".join(line for line in output_code if line is not None)
        had_errors = len(self.errors) > 0

        return final_code, had_errors
