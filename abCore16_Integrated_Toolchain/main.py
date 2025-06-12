# main.py
# June 2, 2025
# Use to run
# python main.py --sal-input SAL_code_gen.sal
# or from C-like file
# python main.py test_program.ssl
# or extensive core16-C testing
# python main.py test_c_like_features.ssl

import os
import traceback
import sys
import argparse

# Toolchain components
from simple_translator import SimpleTranslator
from simple_assembler import SimpleAssembler
from simple_disassembler import SimpleDisassembler
from microprocessor_simulator import MicroprocessorSimulator

# Import the C-like SSL (PLY-based) compiler function
try:
    from c_ply_compiler import compile_c_ssl_string_to_sal
except ImportError:
    print("ERROR: Could not import 'compile_c_ssl_string_to_sal' from 'c_ply_compiler.py'.")
    print("       Ensure 'c_ply_compiler.py' is in the same directory and has no import errors itself.")
    sys.exit(1)


def run_toolchain_from_sal(
        sal_code_string,
        source_description="SAL Code",
        output_binary_file="program.bin",
        output_listing_file="program.asm",
        output_disassembled_file="program_disassembled.sal",
        sim_data_memory_size=8192,
        sim_stack_size=256,
        sim_program_memory_capacity=65536
):
    print(
        f"==============================================\n  STARTING TOOLCHAIN FOR PRE-COMPILED: {source_description}  \n==============================================")
    if not sal_code_string or not any(
            l.strip() and not l.strip().startswith(tuple([';', '//'])) for l in sal_code_string.split('\n')):
        print_toolchain_failure(source_description, "EMPTY SAL INPUT");
        return False

    assembler = SimpleAssembler()
    print("\n--- ASSEMBLER: Assembling SAL Code ---")
    if not assembler.assemble_to_file(sal_code_string, output_binary_file, output_listing_file):
        print_toolchain_failure(source_description, "ASSEMBLY");
        return False

    disassembler = SimpleDisassembler()
    print(f"\n--- DISASSEMBLER: Disassembling '{output_binary_file}' ---")
    try:
        with open(output_binary_file, "rb") as f:
            binary_content = f.read()
        if binary_content:
            disassembled_sal_output = disassembler.disassemble(binary_content)
            with open(output_disassembled_file, "w") as f_dis_out:
                f_dis_out.write(disassembled_sal_output if disassembled_sal_output else "")
            print(f"DISASSEMBLER: Output successfully written to '{output_disassembled_file}'")
            if disassembler.errors:
                print("DISASSEMBLER: Encountered errors during disassembly:")
                for err in disassembler.errors: print(f"  - {err}")
        else:
            print("DISASSEMBLER: Binary file is empty, skipping disassembly.")
    except Exception as e_dis:
        print(f"DISASSEMBLER: An error occurred during disassembly - {e_dis}");
        traceback.print_exc()

    # --- CORRECTED SIMULATOR INSTANTIATION ---
    simulator = MicroprocessorSimulator(
        data_memory_size=sim_data_memory_size,  # Use the function parameter
        stack_size=sim_stack_size,  # Use the function parameter (simulator expects 'stack_size')
        program_memory_capacity=sim_program_memory_capacity  # Use the function parameter
    )
    # --- END CORRECTION ---

    print("\n--- SIMULATOR: Loading and Running Binary File ---")
    simulation_log = simulator.run_program(output_binary_file)
    print("\n--- SIMULATOR: Simulation Log ---");
    print(simulation_log if simulation_log else "// No simulation log generated.")
    print("\n--- SIMULATOR: Final Simulator Register States ---");
    simulator.print_final_state()
    print_toolchain_success(source_description);
    return True


def run_full_toolchain_from_original_ssl(
        ssl_ab_code,
        source_description="Original SSL (.ab) Code",
        output_binary_file="program.bin",
        output_listing_file="program.asm",
        output_disassembled_file="program_disassembled.sal",
        sim_data_memory_size=8192,
        sim_stack_size=256,
        sim_program_memory_capacity=65536
):
    print(
        f"==============================================\n  STARTING ORIGINAL SSL (.ab) TOOLCHAIN FOR: {source_description}  \n==============================================")

    compiler = SimpleTranslator()
    print("\n--- TRANSLATOR (simple_translator.py): Translating Original SSL ---")
    compiled_sal_string, compilation_had_errors = compiler.translate_program(ssl_ab_code)

    if compilation_had_errors:
        print_toolchain_failure(source_description, "TRANSLATION (Original SSL)");
        return False
    if not compiled_sal_string or not any(
            line.strip() and not line.strip().startswith(tuple([';', '//'])) for line in
            compiled_sal_string.split('\n')):
        print_toolchain_failure(source_description, "EMPTY SAL (from Original SSL)");
        return False

    # print("\n--- COMPILER (simple_translator.py): Generated SAL ---") # Verbose
    # print(compiled_sal_string) # Verbose

    return run_toolchain_from_sal(
        compiled_sal_string,
        f"Translated from {source_description}",
        output_binary_file, output_listing_file, output_disassembled_file,
        sim_data_memory_size, sim_stack_size, sim_program_memory_capacity
    )


def run_full_toolchain_from_c_ssl(
        c_ssl_code_string,
        source_description="C-like SSL (.ssl) Code",
        output_ply_sal_file="program_ply_generated.sal",
        output_binary_file="program.bin",
        output_listing_file="program.asm",
        output_disassembled_file="program_disassembled.sal",
        sim_data_memory_size=8192,
        sim_stack_size=256,
        sim_program_memory_capacity=65536
):
    print(
        f"==============================================\n  STARTING C-LIKE SSL (.ssl) TOOLCHAIN FOR: {source_description}  \n==============================================")

    print("\n--- COMPILER (PLY-based via c_ply_compiler.py): Compiling C-like SSL ---")

    generated_sal_string, ply_compilation_had_errors = compile_c_ssl_string_to_sal(c_ssl_code_string)

    if ply_compilation_had_errors or generated_sal_string is None:
        print_toolchain_failure(source_description, "COMPILATION (C-like SSL with PLY)");
        return False
    if not generated_sal_string.strip() or not any(
            line.strip() and not line.strip().startswith(tuple([';', '//'])) for line in
            generated_sal_string.split('\n')):
        print_toolchain_failure(source_description, "EMPTY SAL (from C-like SSL)");
        return False

    print("\n--- COMPILER (PLY-based): Generated SAL successfully ---")

    try:
        with open(output_ply_sal_file, 'w') as f_sal:
            f_sal.write(generated_sal_string)
        print(f"PLY COMPILER: Generated SAL saved to '{output_ply_sal_file}'")
    except IOError as e:
        print(f"PLY COMPILER: Error writing generated SAL to '{output_ply_sal_file}': {e}")

    sal_for_assembler = generated_sal_string
    lines = [line.strip() for line in generated_sal_string.strip().split('\n')
             if line.strip() and not line.strip().startswith(tuple(['//', ';']))]
    if not lines or lines[-1].upper() != "HALT":
        sal_for_assembler = generated_sal_string.strip() + "\nHALT\n"
        print("(Appended HALT to PLY-generated SAL for assembler)")

    return run_toolchain_from_sal(
        sal_for_assembler,
        f"Compiled from {source_description} (via PLY)",
        output_binary_file, output_listing_file, output_disassembled_file,
        sim_data_memory_size, sim_stack_size, sim_program_memory_capacity
    )


def print_toolchain_failure(source_description, stage):
    print(
        f"==============================================\n       TOOLCHAIN FAILED ({stage.upper()}) FOR: {source_description}       \n==============================================")


def print_toolchain_success(source_description):
    print(
        f"\n==============================================\n       TOOLCHAIN COMPLETE FOR: {source_description}       \n==============================================")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="abCore16 Toolchain Orchestrator. Processes .ab, .ssl, .sal, or .asm files.",
        formatter_class=argparse.RawTextHelpFormatter
    )
    parser.add_argument(
        "input_file",
        help="Input file to process.\n"
             "  .ab  - Original Simple Source Language (SSL)\n"
             "  .ssl - C-like Simple Source Language (processed by PLY compiler)\n"
             "  .sal - Simple Assembly Language (direct to assembler)\n"
             "  .asm - Simple Assembly Language (direct to assembler)"
    )
    parser.add_argument(
        "--sal-input",  # Re-added this flag for explicit control
        action="store_true",
        help="Force treatment of the input file as a pre-compiled SAL file (skips SSL compilation)."
    )

    args = parser.parse_args()
    source_file_to_process = args.input_file
    force_sal_input_mode = args.sal_input

    base_filename = os.path.splitext(source_file_to_process)[0]
    output_binary_file = f"{base_filename}.bin"
    output_listing_file = f"{base_filename}.asm"
    output_disassembled_file = f"{base_filename}_disassembled.sal"
    ply_generated_sal_intermediate_file = f"{base_filename}_from_ply.sal"

    SIM_DATA_MEMORY_SIZE = 8192
    SIM_STACK_SIZE_WORDS = 256
    SIM_PROG_MEM_CAPACITY_BYTES = 65536

    if os.path.exists(source_file_to_process):
        print(f"Found source file: {source_file_to_process}")
        try:
            with open(source_file_to_process, 'r') as f:
                file_content = f.read()

            if not file_content.strip():
                print(f"Error: Input file '{source_file_to_process}' is empty or contains only whitespace.")
                sys.exit(1)

            success = False
            file_ext = ""
            # Robust way to get extension, handles filenames without '.'
            if '.' in os.path.basename(source_file_to_process):
                file_ext = source_file_to_process.lower().split('.')[-1]

            is_sal_file_type_by_extension = file_ext in ["sal", "asm"]

            if force_sal_input_mode or is_sal_file_type_by_extension:
                if force_sal_input_mode and not is_sal_file_type_by_extension:
                    print(
                        f"Info: --sal-input flag used, treating '{source_file_to_process}' as SAL despite extension '{file_ext}'.")
                elif is_sal_file_type_by_extension and not force_sal_input_mode:  # Auto-detected
                    print(f"Info: Detected SAL/ASM extension, treating '{source_file_to_process}' as SAL input.")

                success = run_toolchain_from_sal(
                    file_content,
                    source_description=f"SAL/ASM File '{source_file_to_process}'",
                    output_binary_file=output_binary_file,
                    output_listing_file=output_listing_file,
                    output_disassembled_file=output_disassembled_file,
                    sim_data_memory_size=SIM_DATA_MEMORY_SIZE,
                    sim_stack_size=SIM_STACK_SIZE_WORDS,
                    sim_program_memory_capacity=SIM_PROG_MEM_CAPACITY_BYTES
                )
            elif file_ext == "ab":
                success = run_full_toolchain_from_original_ssl(
                    file_content,
                    source_description=f"Original SSL File '{source_file_to_process}'",
                    output_binary_file=output_binary_file,
                    output_listing_file=output_listing_file,
                    output_disassembled_file=output_disassembled_file,
                    sim_data_memory_size=SIM_DATA_MEMORY_SIZE,
                    sim_stack_size=SIM_STACK_SIZE_WORDS,
                    sim_program_memory_capacity=SIM_PROG_MEM_CAPACITY_BYTES
                )
            elif file_ext == "ssl":
                success = run_full_toolchain_from_c_ssl(
                    file_content,
                    source_description=f"C-like SSL File '{source_file_to_process}'",
                    output_ply_sal_file=ply_generated_sal_intermediate_file,
                    output_binary_file=output_binary_file,
                    output_listing_file=output_listing_file,
                    output_disassembled_file=output_disassembled_file,
                    sim_data_memory_size=SIM_DATA_MEMORY_SIZE,
                    sim_stack_size=SIM_STACK_SIZE_WORDS,
                    sim_program_memory_capacity=SIM_PROG_MEM_CAPACITY_BYTES
                )
            else:
                print(f"Error: Unknown file extension '.{file_ext}' for '{source_file_to_process}'.")
                print(
                    "       Cannot determine processing path. Use .ab, .ssl, .sal, .asm, or use --sal-input flag for SAL files with other extensions.")
                print_toolchain_failure(f"File '{source_file_to_process}'", "UNKNOWN FILE TYPE")

            if success:
                print(f"\nSuccessfully processed '{source_file_to_process}'.")
            else:
                print(f"\nProcessing of '{source_file_to_process}' FAILED or encountered errors.")

        except Exception as e:
            print(f"An UNEXPECTED error occurred while processing file '{source_file_to_process}': {e}")
            traceback.print_exc()
    else:
        print(f"Error: Source file '{source_file_to_process}' not found.")
