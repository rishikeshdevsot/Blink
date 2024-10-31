; RUN: llc < %s -enable-machine-call-graph -enable-machine-instrumentation -mtriple=arm64-linux -blink-mode=dynamic -stop-after=machine-ir-instrumentation | FileCheck %s --check-prefixes CHECK-MIR
; RUN: llc < %s -enable-machine-call-graph -enable-machine-instrumentation -mtriple=arm64-linux -blink-mode=dynamic | FileCheck %s --check-prefixes CHECK-ASM

define i32 @_Z3foov() #0 {
  ; MIR pass check
  ; CHECK-MIR: MIP_FUNCTION_INSTRUMENTATION_MARKER 0, 1
  ; Extry Instrumentation Transformation
  ; CHECK-MIR-NEXT: MIP_INSTRUMENTATION $x0, 1, &__custom_instrumentation, 0, 1

  ; Placeholder Transformation
  ; CHECK-MIR-NEXT: ORRWrs $wzr, $wzr, 0
  ; CHECK-MIR-NEXT: MIP_BASIC_BLOCK_COVERAGE_INSTRUMENTATION 218, 0

  ; Exit Instrumentation Transformation
  ; CHECK-MIR-NEXT: MIP_INSTRUMENTATION $x0, 2, &__custom_instrumentation, 1, 1
  ; CHECK-MIR: RET undef $lr, implicit killed $w0

  ; ASM code generation check:
  ; Entry Instrumentation Code Generation
  ; CHECK-ASM:      b    #56                             // MIP: Instrumentation
  ; CHECK-ASM-NEXT: stp  x0, x8, [sp, #-16]!
  ; CHECK-ASM-NEXT: str  x1, [sp, #-16]!
  ; CHECK-ASM-NEXT: mov  w1, #1
  ; CHECK-ASM-NEXT: movk w1, #0, lsl #16
  ; CHECK-ASM-NEXT: adrp x0, _Z3foov$RAW
  ; CHECK-ASM-NEXT: add  x0, x0, :lo12:_Z3foov$RAW
  ; CHECK-ASM-NEXT: adrp x16, __custom_instrumentation
  ; CHECK-ASM-NEXT: add  x16, x16, :lo12:__custom_instrumentation
  ; CHECK-ASM-NEXT: stp  x29, x30, [sp, #-16]!
  ; CHECK-ASM-NEXT: blr  x16
  ; CHECK-ASM-NEXT: ldp  x29, x30, [sp], #16
  ; CHECK-ASM-NEXT: ldr  x1, [sp], #16
  ; CHECK-ASM-NEXT: ldp  x0, x8, [sp], #16

  ; Placeholder Code Generation
  ; CHECK-ASM: mov  w0, wzr
  ; CHECK-ASM: b    #4

  ; Exit Instrumentation Code Generation
  ; CHECK-ASM:     b    #56                              // MIP: Instrumentation
  ; CHECK-ASM-NEXT:stp  x0, x8, [sp, #-16]!
  ; CHECK-ASM-NEXT:str  x1, [sp, #-16]!
  ; CHECK-ASM-NEXT:mov  w1, #2
  ; CHECK-ASM-NEXT:movk w1, #0, lsl #16
  ; CHECK-ASM-NEXT:adrp x0, _Z3foov$RAW
  ; CHECK-ASM-NEXT:add  x0, x0, :lo12:_Z3foov$RAW
  ; CHECK-ASM-NEXT:adrp x16, __custom_instrumentation_exit
  ; CHECK-ASM-NEXT:add  x16, x16, :lo12:__custom_instrumentation_exit
  ; CHECK-ASM-NEXT:stp  x29, x30, [sp, #-16]!
  ; CHECK-ASM-NEXT:blr  x16
  ; CHECK-ASM-NEXT:ldp  x29, x30, [sp], #16
  ; CHECK-ASM-NEXT:ldr  x1, [sp], #16
  ; CHECK-ASM-NEXT:ldp  x0, x8, [sp], #16
  ; CHECK-ASM-NEXT:ret

  ret i32 0
}
