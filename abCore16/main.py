# main.py
import os
import traceback
import sys  # Import the sys module for command-line arguments
from simple_compiler import SimpleCompilerLLM
from simple_assembler import SimpleAssembler
from simple_disassembler import SimpleDisassembler
from microprocessor_simulator import MicroprocessorSimulator


# ... (run_full_toolchain function remains the same) ...
def run_full_toolchain(ssl_code, source_description="SSL Code",
                       output_binary_file="program.bin",
                       output_listing_file="program.asm",
                       output_disassembled_file="program_disassembled.sal",
                       sim_data_memory_size=4096,
                       sim_stack_size=256,
                       sim_program_memory_capacity=65536
                       ):
    print("==============================================")
    print(f"      STARTING FULL TOOLCHAIN FOR: {source_description}      ")
    print("==============================================")
    # --- Step 1: Compilation (SSL to SAL) ---
    compiler = SimpleCompilerLLM()
    print("\n--- COMPILER: Compiling SSL Code ---")
    compiled_sal_string, compilation_had_errors = compiler.compile_program(ssl_code)
    if compilation_had_errors:
        print("\nCOMPILER: Compilation failed with errors (see compiler output for details).")
        print("Aborting toolchain.");
        print_toolchain_failure(source_description, "COMPILATION");
        return False
    if not compiled_sal_string or not any(
            line.strip() and not line.strip().startswith(";") for line in compiled_sal_string.split('\n')):
        print(
            "\nCOMPILER: Compilation resulted in no executable SAL instructions (SAL output was empty or comments/errors only).")
        print("Aborting toolchain.");
        print_toolchain_failure(source_description, "EMPTY SAL");
        return False
    print("\n--- COMPILER: Generated SAL Code (for reference) ---");
    print(compiled_sal_string)
    # --- Step 2: Assembly (SAL to Machine Code Binary & Listing) ---
    assembler = SimpleAssembler()
    print("\n--- ASSEMBLER: Assembling SAL Code ---")
    assembly_successful = assembler.assemble_to_file(compiled_sal_string, output_binary_file, output_listing_file)
    if not assembly_successful:
        print("\nASSEMBLER: Assembly failed (see assembler output for details).")
        print("Aborting toolchain.");
        print_toolchain_failure(source_description, "ASSEMBLY");
        return False
    # --- Step 2.5: Disassembly (Machine Code Binary back to SAL) ---
    disassembler = SimpleDisassembler()
    print(f"\n--- DISASSEMBLER: Disassembling '{output_binary_file}' ---")
    try:
        with open(output_binary_file, "rb") as f_bin_to_disas:
            binary_content = f_bin_to_disas.read()
        if binary_content:
            disassembled_sal_output = disassembler.disassemble(binary_content)
            with open(output_disassembled_file, "w") as f_dis_out:
                f_dis_out.write(disassembled_sal_output)
            print(f"DISASSEMBLER: Output successfully written to '{output_disassembled_file}'")
            if disassembler.errors:
                print("DISASSEMBLER: Encountered errors during disassembly (see .sal file for details):")
                for err in disassembler.errors: print(f"  - {err}")
        else:
            print("DISASSEMBLER: Binary file is empty, skipping disassembly.")
    except Exception as e_dis:
        print(f"DISASSEMBLER: An error occurred during disassembly - {e_dis}"); traceback.print_exc()

    # --- Step 3: Simulation (Machine Code Binary to Execution) ---
    simulator = MicroprocessorSimulator(data_memory_size=sim_data_memory_size, stack_size=sim_stack_size,
                                        program_memory_capacity=sim_program_memory_capacity)
    print("\n--- SIMULATOR: Loading and Running Binary File ---")
    simulation_log = simulator.run_program(output_binary_file)
    print("\n--- SIMULATOR: Simulation Log ---");
    print(simulation_log)
    print("\n--- SIMULATOR: Final Simulator Register States ---");
    simulator.print_final_state()
    print_toolchain_success(source_description);
    return True


def print_toolchain_failure(source_description, stage):
    print("==============================================")
    print(f"       FULL TOOLCHAIN FAILED ({stage}) FOR: {source_description}       ")
    print("==============================================")


def print_toolchain_success(source_description):
    print("\n==============================================")
    print(f"       FULL TOOLCHAIN COMPLETE FOR: {source_description}       ")
    print("==============================================")


if __name__ == "__main__":
    default_source_file = "myProg.ab"
    source_file_to_process = default_source_file

    if len(sys.argv) > 1:
        source_file_to_process = sys.argv[1]
        if not source_file_to_process.endswith(".ab"):
            print(f"Warning: Specified file '{source_file_to_process}' does not end with .ab. Proceeding anyway.")
        print(f"Processing user-specified file: {source_file_to_process}")
    else:
        print(f"No source file specified on command line. Using default: {default_source_file}")

    base_filename = os.path.splitext(source_file_to_process)[0]
    binary_output_filename = f"{base_filename}.bin"
    listing_output_filename = f"{base_filename}.asm"
    disassembled_output_filename = f"{base_filename}_disassembled.sal"

    SIM_DATA_MEMORY_SIZE = 4096
    SIM_STACK_SIZE_WORDS = 256
    SIM_PROG_MEM_CAPACITY_BYTES = 65536

    if os.path.exists(source_file_to_process):
        print(f"Found source file: {source_file_to_process}")
        try:
            with open(source_file_to_process, 'r') as f:
                ssl_code_from_file = f.read()

            success = run_full_toolchain(
                ssl_code_from_file,
                source_description=f"File '{source_file_to_process}'",
                output_binary_file=binary_output_filename,
                output_listing_file=listing_output_filename,
                output_disassembled_file=disassembled_output_filename,
                sim_data_memory_size=SIM_DATA_MEMORY_SIZE,
                sim_stack_size=SIM_STACK_SIZE_WORDS,
                sim_program_memory_capacity=SIM_PROG_MEM_CAPACITY_BYTES
            )
            if success:
                print(f"\nSuccessfully processed '{source_file_to_process}'.")
            else:
                print(f"\nProcessing of '{source_file_to_process}' encountered errors.")

        except Exception as e:
            print(f"An UNEXPECTED error occurred while processing file '{source_file_to_process}': {e}")
            traceback.print_exc()
    else:
        print(f"Error: Source file '{source_file_to_process}' not found.")
        if source_file_to_process == default_source_file:
            print("Please create 'myProg.ab' or specify a different file on the command line.")
