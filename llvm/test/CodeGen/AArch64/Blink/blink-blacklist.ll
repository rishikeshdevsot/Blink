q; RUN: llc < %s -enable-machine-instrumentation -enable-machine-call-graph -mtriple=arm64-linux -blink-mode=dynamic -blink-blacklist-functions=_Z3fooi | FileCheck %s --check-prefixes CHECK

@global = local_unnamed_addr global i32 4, align 4

; CHECK-LABEL: _Z3fooi:
; CHECK-NEXT: .cfi_startproc
; CHECK-NEXT: // %bb.0:
; CHECK-NEXT: mov  w0, #101
; CHECK-NEXT: ret
; CHECK-NEXT: .Lfunc_end0:
define i32 @_Z3fooi(i32) {
  ret i32 101
}

; CHECK-LABEL: _Z3gooi:
; CHECK-NEXT: .cfi_startproc
; CHECK-NEXT: // %bb.0:
; CHECK-NEXT: b    #56                             // MIP: Instrumentation
; CHECK-NEXT: stp  x0, x8, [sp, #-16]!
; CHECK-NEXT: str  x1, [sp, #-16]!
; CHECK-NEXT: mov  w1, #1
; CHECK-NEXT: movk w1, #0, lsl #16
; CHECK-NEXT: adrp x0, _Z3gooi$RAW
; CHECK-NEXT: add  x0, x0, :lo12:_Z3gooi$RAW
; CHECK-NEXT: adrp x16, __custom_instrumentation
; CHECK-NEXT: add  x16, x16, :lo12:__custom_instrumentation
; CHECK-NEXT: stp  x29, x30, [sp, #-16]!
; CHECK-NEXT: blr  x16
; CHECK-NEXT: ldp  x29, x30, [sp], #16
; CHECK-NEXT: ldr  x1, [sp], #16
; CHECK-NEXT: ldp  x0, x8, [sp], #16
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
