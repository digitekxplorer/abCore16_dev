# main.py
# July 28, 2025
# MODIFIED: Uses centralized hardware memory size constant.

import os
import traceback
import sys
import argparse

# Toolchain components
from simple_translator import SimpleTranslator
from simple_assembler import SimpleAssembler
from simple_disassembler import SimpleDisassembler
from microprocessor_simulator import MicroprocessorSimulator
from preprocessor import Preprocessor
# --- CHANGE #1: Import the new constant ---
from abcore16_defs import HARDWARE_DATA_MEM_SIZE_BYTES

try:
    from c_ply_compiler import compile_c_ssl_string_to_sal
except ImportError:
    print("ERROR: Could not import 'compile_c_ssl_string_to_sal' from 'c_ply_compiler.py'.")
    sys.exit(1)

try:
    from generate_mem_files import generate_mem_files
except ImportError:
    generate_mem_files = None


def run_toolchain_from_sal(
        sal_code_string,
        source_description="SAL Code",
        output_binary_file="program.bin",
        output_listing_file="program.asm",
        output_disassembled_file="program_disassembled.sal",
        output_sim_txt_file="sim_output.txt",
        # --- CHANGE #2: Update the signature to use the constant as a default ---
        sim_data_memory_size=HARDWARE_DATA_MEM_SIZE_BYTES,
        sim_stack_size=256,
        sim_program_memory_capacity=HARDWARE_DATA_MEM_SIZE_BYTES
):
    print(f"==============================================\n  STARTING TOOLCHAIN FOR PRE-COMPILED: {source_description}  \n==============================================")
    if not sal_code_string or not any(l.strip() and not l.strip().startswith(tuple([';', '//'])) for l in sal_code_string.split('\n')):
        print_toolchain_failure(source_description, "EMPTY SAL INPUT"); return False

    assembler = SimpleAssembler()
    print("\n--- ASSEMBLER: Assembling SAL Code ---")
    if not assembler.assemble_to_file(sal_code_string, output_binary_file, output_listing_file):
        print_toolchain_failure(source_description, "ASSEMBLY"); return False

    if generate_mem_files:
        print("\n--- FPGA MEMORY FILE GENERATOR ---")
        try:
            generate_mem_files(
                input_bin_file=output_binary_file,
                # --- CHANGE #3: Pass the constant to the generator ---
                memory_size=HARDWARE_DATA_MEM_SIZE_BYTES,
                memory_width=8
            )
        except Exception as e:
            print(f"FPGA GEN: An unexpected error occurred during .coe/.hex generation: {e}")
    else:
        print("\n--- FPGA MEMORY FILE GENERATOR (SKIPPED) ---")

    disassembler = SimpleDisassembler()
    print(f"\n--- DISASSEMBLER: Disassembling '{output_binary_file}' ---")
    try:
        with open(output_binary_file, "rb") as f: binary_content = f.read()
        if binary_content:
            disassembled_sal_output = disassembler.disassemble(binary_content)
            with open(output_disassembled_file, "w") as f_dis_out: f_dis_out.write(disassembled_sal_output if disassembled_sal_output else "")
            print(f"DISASSEMBLER: Output successfully written to '{output_disassembled_file}'")
            if disassembler.errors: [print(f"  - {err}") for err in disassembler.errors]
        else:
            print("DISASSEMBLER: Binary file is empty, skipping disassembly.")
    except Exception as e_dis:
        print(f"DISASSEMBLER: An error occurred during disassembly - {e_dis}"); traceback.print_exc()

    simulator = MicroprocessorSimulator(
        data_memory_size=sim_data_memory_size,
        stack_size=sim_stack_size,
        program_memory_capacity=sim_program_memory_capacity
    )
    print("\n--- SIMULATOR: Loading and Running Binary File ---")
    simulation_log = simulator.run_program(output_binary_file)
    try:
        file_content_parts = ["--- SIMULATOR: MMIO OUTPUT ---"]
        if simulator.mmio_output_lines: file_content_parts.append("\n".join(simulator.mmio_output_lines))
        else: file_content_parts.append("// No MMIO output was generated.")
        file_content_parts.extend(["\n", "--- SIMULATOR: Simulation Log ---", simulation_log if simulation_log else "// No simulation log generated."])
        with open(output_sim_txt_file, 'w') as f_out: f_out.write("\n".join(file_content_parts) + "\n")
        print(f"SIMULATOR: Full simulation output successfully written to '{output_sim_txt_file}'")
    except IOError as e: print(f"SIMULATOR: ERROR - Could not write simulation output to '{output_sim_txt_file}': {e}")

    print("\n--- SIMULATOR: Simulation Log (Console) ---");
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
        output_sim_txt_file="sim_output.txt",
        sim_data_memory_size=HARDWARE_DATA_MEM_SIZE_BYTES,
        sim_stack_size=256,
        sim_program_memory_capacity=HARDWARE_DATA_MEM_SIZE_BYTES
):
    print(f"==============================================\n  STARTING ORIGINAL SSL (.ab) TOOLCHAIN FOR: {source_description}  \n==============================================")
    compiler = SimpleTranslator()
    print("\n--- TRANSLATOR (simple_translator.py): Translating Original SSL ---")
    compiled_sal_string, compilation_had_errors = compiler.translate_program(ssl_ab_code)
    if compilation_had_errors: print_toolchain_failure(source_description, "TRANSLATION (Original SSL)"); return False
    if not compiled_sal_string or not any(line.strip() and not line.strip().startswith(tuple([';', '//'])) for line in compiled_sal_string.split('\n')):
        print_toolchain_failure(source_description, "EMPTY SAL (from Original SSL)"); return False
    return run_toolchain_from_sal(
        compiled_sal_string, f"Translated from {source_description}",
        output_binary_file, output_listing_file, output_disassembled_file,
        output_sim_txt_file, sim_data_memory_size, sim_stack_size, sim_program_memory_capacity
    )


def run_full_toolchain_from_c_ssl(
        source_ssl_filepath,
        source_description="C-like SSL (.ssl) Code",
        output_ply_sal_file="program_ply_generated.sal",
        output_binary_file="program.bin",
        output_listing_file="program.asm",
        output_disassembled_file="program_disassembled.sal",
        output_sim_txt_file="sim_output.txt",
        sim_data_memory_size=HARDWARE_DATA_MEM_SIZE_BYTES,
        sim_stack_size=256,
        sim_program_memory_capacity=HARDWARE_DATA_MEM_SIZE_BYTES
):
    print(f"==============================================\n  STARTING C-LIKE SSL (.ssl) TOOLCHAIN FOR: {source_description}  \n==============================================")
    print("\n--- PREPROCESSOR: Processing source file and #includes ---")
    preproc = Preprocessor(); preprocessed_code, preprocess_had_errors = preproc.process(source_ssl_filepath)
    if preprocess_had_errors:
        print("PREPROCESSOR: Encountered errors:"); [print(f"  - {err}") for err in preproc.errors]
        print_toolchain_failure(source_description, "PREPROCESSING"); return False
    try:
        base_name_for_outputs = os.path.splitext(os.path.basename(output_binary_file))[0]
        preprocessed_filename = os.path.join(os.path.dirname(output_binary_file), f"{base_name_for_outputs}.i")
        with open(preprocessed_filename, 'w') as f: f.write(preprocessed_code)
        print(f"PREPROCESSOR: Preprocessed code saved to '{preprocessed_filename}'")
    except IOError as e: print(f"PREPROCESSOR: Warning - Could not write preprocessed file: {e}")

    print("\n--- COMPILER (PLY-based via c_ply_compiler.py): Compiling C-like SSL ---")
    generated_sal_string, ply_compilation_had_errors = compile_c_ssl_string_to_sal(preprocessed_code)
    if ply_compilation_had_errors or generated_sal_string is None:
        print_toolchain_failure(source_description, "COMPILATION (C-like SSL with PLY)"); return False
    if not generated_sal_string.strip() or not any(line.strip() and not line.strip().startswith(tuple([';', '//'])) for line in generated_sal_string.split('\n')):
        print_toolchain_failure(source_description, "EMPTY SAL (from C-like SSL)"); return False
    print("\n--- COMPILER (PLY-based): Generated SAL successfully ---")
    try:
        with open(output_ply_sal_file, 'w') as f_sal: f_sal.write(generated_sal_string)
        print(f"PLY COMPILER: Generated SAL saved to '{output_ply_sal_file}'")
    except IOError as e: print(f"PLY COMPILER: Error writing generated SAL to '{output_ply_sal_file}': {e}")
    sal_for_assembler = generated_sal_string
    lines = [line.strip() for line in generated_sal_string.strip().split('\n') if line.strip() and not line.strip().startswith(tuple(['//', ';']))]
    if not lines or lines[-1].upper() != "HALT":
        sal_for_assembler = generated_sal_string.strip() + "\nHALT\n"
        print("(Appended HALT to PLY-generated SAL for assembler)")

    return run_toolchain_from_sal(
        sal_for_assembler, f"Compiled from {source_description} (via PLY)",
        output_binary_file, output_listing_file, output_disassembled_file,
        output_sim_txt_file, sim_data_memory_size, sim_stack_size, sim_program_memory_capacity
    )


def print_toolchain_failure(source_description, stage):
    print(f"==============================================\n       TOOLCHAIN FAILED ({stage.upper()}) FOR: {source_description}       \n==============================================")
def print_toolchain_success(source_description):
    print(f"\n==============================================\n       TOOLCHAIN COMPLETE FOR: {source_description}       \n==============================================")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="abCore16 Toolchain Orchestrator.", formatter_class=argparse.RawTextHelpFormatter)
    parser.add_argument("input_file", help="Input file to process.\n  .ssl, .ab, .sal, .asm")
    parser.add_argument("--sal-input", action="store_true", help="Force treatment of the input file as a pre-compiled SAL file.")
    args = parser.parse_args()
    source_file_to_process = args.input_file

    OUTPUT_DIR = "build"; os.makedirs(OUTPUT_DIR, exist_ok=True)
    base_filename = os.path.splitext(os.path.basename(source_file_to_process))[0]
    output_binary_file = os.path.join(OUTPUT_DIR, f"{base_filename}.bin")
    output_listing_file = os.path.join(OUTPUT_DIR, f"{base_filename}.asm")
    output_disassembled_file = os.path.join(OUTPUT_DIR, f"{base_filename}_disassembled.sal")
    output_sim_txt_file = os.path.join(OUTPUT_DIR, f"{base_filename}.txt")
    ply_generated_sal_intermediate_file = os.path.join(OUTPUT_DIR, f"{base_filename}_from_ply.sal")

    # --- CHANGE #4: Remove hardcoded constants, they are now handled by function defaults ---
    SIM_STACK_SIZE_WORDS = 256 # This can remain a configurable parameter

    if not os.path.exists(source_file_to_process): print(f"Error: Source file '{source_file_to_process}' not found."); sys.exit(1)
    with open(source_file_to_process, 'r') as f: file_content = f.read()
    if not file_content.strip(): print(f"Error: Input file '{source_file_to_process}' is empty."); sys.exit(1)

    file_ext = os.path.splitext(source_file_to_process)[1].lower()
    success = False
    if args.sal_input or file_ext in [".sal", ".asm"]:
        success = run_toolchain_from_sal(
            file_content, source_description=f"SAL/ASM File '{source_file_to_process}'",
            output_binary_file=output_binary_file, output_listing_file=output_listing_file,
            output_disassembled_file=output_disassembled_file, output_sim_txt_file=output_sim_txt_file,
            sim_stack_size=SIM_STACK_SIZE_WORDS
        )
    elif file_ext == ".ab":
        success = run_full_toolchain_from_original_ssl(
            file_content, source_description=f"Original SSL File '{source_file_to_process}'",
            output_binary_file=output_binary_file, output_listing_file=output_listing_file,
            output_disassembled_file=output_disassembled_file, output_sim_txt_file=output_sim_txt_file,
            sim_stack_size=SIM_STACK_SIZE_WORDS
        )
    elif file_ext == ".ssl":
        success = run_full_toolchain_from_c_ssl(
            source_file_to_process, source_description=f"C-like SSL File '{source_file_to_process}'",
            output_ply_sal_file=ply_generated_sal_intermediate_file,
            output_binary_file=output_binary_file, output_listing_file=output_listing_file,
            output_disassembled_file=output_disassembled_file, output_sim_txt_file=output_sim_txt_file,
            sim_stack_size=SIM_STACK_SIZE_WORDS
        )
    else:
        print(f"Error: Unknown file extension '{file_ext}'. Use .ab, .ssl, .sal, .asm, or --sal-input.")

    if not success: print(f"\nProcessing of '{source_file_to_process}' FAILED.")
        
