/*===- MIPHelper.h - Machine IR Profile Runtime Helper --------------------===*\
|*
|* Part of the LLVM Project, under the Apache License v2.0 with LLVM Exceptions.
|* See https://llvm.org/LICENSE.txt for license information.
|* SPDX-License-Identifier: Apache-2.0 WITH LLVM-exception
|*
\*===----------------------------------------------------------------------===*/

#ifndef MIP_MIPHELPER_H
#define MIP_MIPHELPER_H

#include "mip/MIPData.inc"

void __llvm_dump_mip_profile(void);
int __llvm_dump_mip_profile_with_filename(const char *Filename);

void *__llvm_mip_profile_begin(void);
void *__llvm_mip_profile_end(void);

void __llvm_mip_runtime_initialize(void);

typedef struct {
  uint32_t CallCount;       // Function Invocation counter
  uint32_t Timestamp;       // set to 0xffffffff
  int64_t OffsetToFunction; // PC relative offset to the function address
  uint32_t DisabledFlag;    // flag specifying if instrumentation is disabled
  uint32_t NumExitBlocks;   // Number of exit blocks in function
  uint32_t ExitBlockOffsetArray; // array containing offset from function entry
                                 // to exit instrumentations
} ProfileData_t;

#endif // MIP_MIPHELPER_H
