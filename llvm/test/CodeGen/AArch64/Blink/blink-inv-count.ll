; RUN: llc < %s -enable-machine-instrumentation -enable-machine-call-graph  -mtriple=arm64-linux -blink-mode=dynamic | FileCheck %s --check-prefixes CHECK

@global = local_unnamed_addr global i32 4, align 4

; CHECK-LABEL: _Z3fooi:
define i32 @_Z3fooi(i32) {
  ret i32 101
}

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

; Declaration of the struct that each mipraw section stores for each function
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

; Check invocation count field exists for foo
; CHECK-LABEL:.section  __llvm_mipraw,"aGw",@progbits,"_Z3fooi$MIP"
; CHECK:       .p2align  6

; CHECK-LABEL: _Z3fooi$RAW:
; CHECK-NEXT:  [[FOO_REF:.*]]:

; Check if the CallCount field exists
; CHECK-NEXT:  .word  0x0

; Check invocation count field exists for goo
; CHECK-LABEL:.section  __llvm_mipraw,"aGw",@progbits,"_Z3gooi$MIP"

; CHECK:       .p2align  6
; CHECK-LABEL: _Z3gooi$RAW:
; CHECK-NEXT:  [[GOO_REF:.*]]:

; Check if the CallCount field exists
; CHECK-NEXT:  .word  0x0
