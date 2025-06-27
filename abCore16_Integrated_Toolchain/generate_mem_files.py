# June 22, 2025
# Reads a raw binary file (.bin) and generates two memory initialization files
# using the same base name as the input file:
# 1. A .coe file for Xilinx BRAM synthesis (8-bit width).
# 2. A .hex file for fast Verilog simulation ($readmemh).

import argparse
import os


def generate_mem_files(input_bin_file, memory_width=8, memory_size=8192):
    """
    Converts a raw binary file (.bin) into a Xilinx COE file and a Verilog HEX file.
    The output files will share the same base name as the input file.

    Args:
        input_bin_file (str): Path to the input .bin file.
        memory_width (int): The width of the BRAM in bits (e.g., 8).
        memory_size (int): The total desired size of the memory in bytes.
    """
    if memory_width != 8:
        raise ValueError("Memory width must be 8 for this script.")

    try:
        with open(input_bin_file, 'rb') as f_in:
            program_data = f_in.read()
    except FileNotFoundError:
        print(f"Error: Input file '{input_bin_file}' not found.")
        return

    if len(program_data) > memory_size:
        print(f"Error: Program size ({len(program_data)} bytes) exceeds specified memory size ({memory_size} bytes).")
        return

    # Determine the base name for the output files from the input file path
    output_base_name = os.path.splitext(input_bin_file)[0]

    # Define output file paths
    coe_file_path = output_base_name + ".coe"
    hex_file_path = output_base_name + ".hex"

    # --- 1. Generate .hex file (for behavioral simulation) ---
    # This file contains the raw program bytes, one per line, without padding.
    try:
        with open(hex_file_path, 'w') as f_hex:
            for byte_val in program_data:
                f_hex.write(f"{byte_val:02x}\n")
        print(f"Successfully generated Verilog simulation file: '{hex_file_path}'")
    except IOError as e:
        print(f"Error writing to file '{hex_file_path}': {e}")
        return

    # --- 2. Generate .coe file (for hardware synthesis) ---
    # This uses the exact padding logic from your original script.

    # --- PADDING LOGIC ---
    num_padding_bytes = memory_size - len(program_data)
    padded_data = program_data
    if num_padding_bytes > 0:
        # A NOP opcode of 0x00 is a perfect padding value.
        padding_bytes = bytes([0x00] * num_padding_bytes)
        padded_data += padding_bytes
        print(
            f"Info: Padded program with {num_padding_bytes} NOPs to reach total size of {memory_size} bytes for COE file.")

    # Generate the list of hex values for the COE file
    hex_values = [f"{byte_val:02x}" for byte_val in padded_data]

    # Write the COE file
    try:
        with open(coe_file_path, 'w') as f_out:
            f_out.write(f"; COE file generated from: {os.path.basename(input_bin_file)}\n")
            f_out.write(f"; Memory Size (depth): {memory_size}\n")
            f_out.write(f"; Memory Width: {memory_width}\n")
            f_out.write("MEMORY_INITIALIZATION_RADIX = 16;\n")
            f_out.write("MEMORY_INITIALIZATION_VECTOR =\n")

            if not hex_values:
                f_out.write("00;\n")
            else:
                # Write all values joined by a comma and newline for readability
                f_out.write(",\n".join(hex_values))
                f_out.write(";\n")  # Terminate with a semicolon

        print(f"Successfully generated Xilinx synthesis file: '{coe_file_path}'")

    except IOError as e:
        print(f"Error writing to file '{coe_file_path}': {e}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Convert a .bin file to .coe and .hex files using the same base name.",
        formatter_class=argparse.RawTextHelpFormatter
    )
    parser.add_argument("input_file", help="Input .bin file path.")
    parser.add_argument(
        "-s", "--size",
        type=int,
        default=8192,
        help="Total size of the memory in bytes for the COE file. \nDefault is 8192."
    )
    parser.add_argument(
        "-w", "--width",
        type=int,
        default=8,
        choices=[8],
        help="Memory width in bits. Currently only supports 8. \nDefault is 8."
    )

    args = parser.parse_args()

    # The main function now handles generating the output paths internally
    generate_mem_files(args.input_file, args.width, args.size)
