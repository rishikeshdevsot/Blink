; REQUIRES: asserts
; RUN: llc -enable-machine-instrumentation -enable-machine-call-graph  -mtriple=arm64-linux --debug-only=machine-ir-instrumentation %s 2>&1  | FileCheck %s --check-prefixes CHECK

@global = local_unnamed_addr global i32 4, align 4

define i32 @_Z3fooi(i32) {
  ret i32 101
}

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

; ------------------------------------------------------------------------
; Check the compiler's stderr output for the expected instrumentation logs.
; Each line includes:
;   - a UniqueCodeID assigned to a specific function
;   - the SourceLocation (function name) associated with the encoding
;   - other fields regardling source location, such as line number and file number
; ------------------------------------------------------------------------

; Two IDs expected for _Z3fooi: entry and exit
; Three IDs expected for _Z3gooi: entry and two exits
; CHECK: UniqueCodeID: 2,SourceLocation: _Z3fooi,SourceLocation: ,SourceLocation: 0,
; CHECK: UniqueCodeID: 4,SourceLocation: _Z3gooi,SourceLocation: ,SourceLocation: 0,
; CHECK: UniqueCodeID: 1,SourceLocation: _Z3fooi,SourceLocation: ,SourceLocation: 0,
; CHECK: UniqueCodeID: 3,SourceLocation: _Z3gooi,SourceLocation: ,SourceLocation: 0,
; CHECK: UniqueCodeID: 5,SourceLocation: _Z3gooi,SourceLocation: ,SourceLocation: 0,
