# abCore16_dev

abCore16 Project & Toolchain
The abCore16 project provides a complete Python-based ecosystem for a custom 16-bit microprocessor. It includes 
a comprehensive toolchain enabling users to write programs in either a simple, direct Simple Source Language (SSL) 
or a more expressive C-like SSL.  This high-level code is then processed through a compiler (either a direct 
SSL-to-SAL translator or a more advanced PLY-based compiler for C-like SSL) into Simple Assembly Language (SAL). 
The SAL code is subsequently assembled into 16-bit binary machine code. The toolchain also features a disassembler 
for verification and a detailed microprocessor simulator to execute the machine code, offering a full cycle from 
high-level programming to simulated hardware execution for learning and experimentation with 16-bit computing 
concepts.

This project allows users to write programs using 16-bit data and addressing capabilities, see them translated 
through various stages of abstraction, and ultimately observe their execution on a simulated 16-bit CPU 
architecture. The primary goal is to demystify computer architecture, 16-bit instruction set design, language 
translation processes (compilation and assembly), and the fundamental principles of CPU operation. Conceptual 
SystemVerilog code is also provided as a blueprint for potential hardware implementation of the 16-bit abCore16 
on an FPGA.

Project Development Process: abCore16 with Google AI Studio (Gemini 2.5 Pro)
The development of the abCore16 microprocessor toolchain and simulator was an iterative and collaborative process, 
leveraging the capabilities of Google AI Studio and the Gemini 2.5 Pro model. The process can be characterized by 
a series of prompts, code generation, testing, feedback, and refinement cycles.
