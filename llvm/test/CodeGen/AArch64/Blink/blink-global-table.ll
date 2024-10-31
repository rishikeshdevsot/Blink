; RUN: llc < %s -enable-machine-instrumentation -enable-machine-call-graph -mtriple=arm64-linux -blink-mode=dynamic | FileCheck %s --check-prefixes CHECK

; This test verifies that Blink’s machine-level instrumentation correctly generates
; per-function profiling global table in the `__llvm_mipraw` section, including:
; - proper alignment and structure layout,
; - accurate field per column,
; - and support for multiple function exits.

; ---------------------------------------------------------------------
; Test Case 1: Single-exit function (`_Z3fooi`)
; ---------------------------------------------------------------------

@global = local_unnamed_addr global i32 4, align 4

; CHECK-LABEL: _Z3fooi:
define i32 @_Z3fooi(i32) {
  ret i32 101
}

; ---------------------------------------------------------------------
; Test Case 2: Multi-exit function (`_Z3gooi`)
; This function has two return paths. We verify that Blink generates
; multiple block offsets in the RAW metadata table.
; ---------------------------------------------------------------------

; CHECK-LABEL: _Z3gooi:
define i32 @_Z3gooi(i1 %cond) {
entry:
  br i1 %cond, label %path1, label %path2

path1:
  %a = call i32 @unique1()
  ret i32 %a

path2:
  %b = call i32 @unique2()
  ret i32 %b
}

declare i32 @unique1() nounwind noinline
declare i32 @unique2() nounwind noinline

; Declaration of the struct that each mipraw section stores for each function:
;
; typedef struct {
;   uint32_t CallCount;
;   uint32_t Timestamp;
;   int64_t OffsetToFunction;
;   uint32_t DisabledFlag;
;   uint32_t NumExitBlocks;
;   uint32_t ExitBlockOffsetArray;
; } ProfileData_t;

; Check mipraw header exists
; CHECK-LABEL: .section  __llvm_mipraw,"aGwR",@progbits,__llvm_mipraw_header,comdat

; ---------------------------------------------------------------------
; Check RAW table for `_Z3fooi`
; ---------------------------------------------------------------------

; CHECK-LABEL: .section  __llvm_mipraw,"aGw",@progbits,"_Z3fooi$MIP"
; CHECK:       .p2align  6

; CHECK-LABEL: _Z3fooi$RAW:
; CHECK-NEXT:  [[FOO_REF:.*]]:

; Check if all field exists
; CHECK-NEXT:  .word  0x0
; CHECK-NEXT:  .word  0xffffffff
; CHECK-NEXT:  .xword _Z3fooi-[[FOO_REF]]                  // Function PC Offset
; CHECK-NEXT:  .word  0x1
; CHECK-NEXT:  .word  0x1
; CHECK-NEXT:  .word  .Lmip_exit_instrumentation0-_Z3fooi  // Block 0 Offset

; ---------------------------------------------------------------------
; Check RAW table for `_Z3gooi` (multi-exit function)
; ---------------------------------------------------------------------

; CHECK-LABEL:.section  __llvm_mipraw,"aGw",@progbits,"_Z3gooi$MIP"

; CHECK:       .p2align  6
; CHECK-LABEL: _Z3gooi$RAW:
; CHECK-NEXT:  [[GOO_REF:.*]]:

; Check if all field exists
; CHECK-NEXT:  .word  0x0
; CHECK-NEXT:  .word  0xffffffff
; CHECK-NEXT:  .xword _Z3gooi-[[GOO_REF]]                  // Function PC Offset
; CHECK-NEXT:  .word  0x1

; Number of exits should be 2
; CHECK-NEXT:  .word  0x2
; CHECK-NEXT:  .word  .Lmip_exit_instrumentation1-_Z3gooi  // Block 0 Offset
; CHECK-NEXT:  .word  .Lmip_exit_instrumentation2-_Z3gooi  // Block 1 Offset
