#if defined(__aarch64__) || defined(__arm64__)
#include "../sanitizer_common/sanitizer_asm.h"

// The address of the raw profile symbol is expected to be in the x16 register.
#define PROFILE_REGISTER x16

    .text
    .p2align 2

.macro SAVE_STACK_FRAME
    // Allocate 0xF0 (240 bytes) and store x8 at the bottom
    str     x8, [sp, #-0xF0]!

    // Save paired registers, increasing addresses
    stp     x7,  x6,  [sp, #0x10]
    stp     x5,  x4,  [sp, #0x20]
    stp     x3,  x2,  [sp, #0x30]
    stp     x1,  x0,  [sp, #0x40]

    stp     x17, x16, [sp, #0x50]
    stp     x15, x14, [sp, #0x70]
    stp     x13, x12, [sp, #0x90]
    stp     x11, x10, [sp, #0xB0]
    stp     x9,  x8,  [sp, #0xD0]

    // Save frame pointer & link register
    stp     x29, x30, [sp, #0xE0]

    // Establish new frame pointer
    add     x29, sp, #0xE0

    // ----- CFI -----
    CFI_DEF_CFA(w29, 0x10)
    CFI_OFFSET(w30, -0x08)
    CFI_OFFSET(w29, -0x10)
.endm

.macro RESTORE_STACK_FRAME
    // Restore frame pointer and link register
    ldp     x29, x30, [sp, #0xE0]

    // Restore paired registers (reverse order)
    ldp     x9,  x8,  [sp, #0xD0]
    ldp     x11, x10, [sp, #0xB0]
    ldp     x13, x12, [sp, #0x90]
    ldp     x15, x14, [sp, #0x70]

    // Restore x16 and x17 (added pair)
    ldp     x17, x16, [sp, #0x50]

    // Restore baseline argument registers
    ldp     x1,  x0,  [sp, #0x40]
    ldp     x3,  x2,  [sp, #0x30]
    ldp     x5,  x4,  [sp, #0x20]
    ldp     x7,  x6,  [sp, #0x10]

    // Restore x8 (single register at bottom)
    ldr     x8,        [sp]

    // Deallocate frame (must match save)
    add     sp, sp, #0xF0
.endm

// Call the C instrumentation helper for function call counts. Expected to be
// called directly from the instrumented function.
    .global ASM_SYMBOL(__llvm_mip_call_counts_caller)
    ASM_TYPE_FUNCTION(ASM_SYMBOL(__llvm_mip_call_counts_caller))
ASM_SYMBOL(__llvm_mip_call_counts_caller):
    CFI_STARTPROC
    SAVE_STACK_FRAME
    mov     x0, PROFILE_REGISTER
    // void *Helper(uint64_t ProfileDataAddress)
    bl      ASM_SYMBOL(__llvm_mip_call_counts_instrumentation_helper)

    RESTORE_STACK_FRAME
    // Restore x29, x30 and return to the caller as if we were never called.
    mov     x16, x30
    ldp     x29, x30, [sp], #0x10
    ret     x16
    CFI_ENDPROC
    ASM_SIZE(__llvm_mip_call_counts_caller)


// Call the C instrumentation helper for dumping the data array
    .global ASM_SYMBOL(dump_data_array_helper)
    ASM_TYPE_FUNCTION(ASM_SYMBOL(dump_data_array_helper))
ASM_SYMBOL(dump_data_array_helper):
    CFI_STARTPROC
    SAVE_STACK_FRAME
    bl      ASM_SYMBOL(dump_data_array)

    RESTORE_STACK_FRAME
    // Restore x29, x30 and return to the caller as if we were never called.
    ret
    CFI_ENDPROC
    ASM_SIZE(dump_data_array_helper)

// Call the C instrumentation helper for dumping the data array
    .global ASM_SYMBOL(init_perf_util_helper)
    ASM_TYPE_FUNCTION(ASM_SYMBOL(init_perf_util_helper))
ASM_SYMBOL(init_perf_util_helper):
    CFI_STARTPROC
    SAVE_STACK_FRAME
    bl      ASM_SYMBOL(init_perf_util)

    RESTORE_STACK_FRAME
    // Restore x29, x30 and return to the caller as if we were never called.
    ret
    CFI_ENDPROC
    ASM_SIZE(init_perf_util_helper)

#endif // defined(__aarch64__) || defined(__arm64__)
