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
#include <dlfcn.h>
#include <errno.h>
#include <fcntl.h> // for open()
#include <pthread.h>
#include <signal.h>
#include <stdbool.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/ioctl.h>
#include <sys/mman.h>
#include <sys/syscall.h>
#include <unistd.h>

#include <link.h>
#include <stddef.h>
#include <time.h>

#include <linux/perf_event.h>

void __llvm_dump_mip_profile(void);
int __llvm_dump_mip_profile_with_filename(const char *Filename);

void *__llvm_mip_profile_begin(void);
void *__llvm_mip_profile_end(void);

void __llvm_mip_runtime_initialize(void);

typedef struct {
  int errno_value;
  unsigned long start;
  unsigned long end;
  size_t len;
} MProtectErrorInfo;

void CreateMprotectSuccessFile();
void CreateMprotectFailureWithInfo(const MProtectErrorInfo *errors, int count);
int RewriteCallback(struct dl_phdr_info *info, size_t size, void *data);
bool MakeCodePagesWriteable();

typedef struct {
  uint32_t fID;
  uint32_t Timestamp;
  int64_t OffsetToFunction;
  uint32_t DisabledFlag;
  uint32_t NumExitBlocks;
  uint32_t ExitBlockOffsetArray;
} ProfileData_t;

void EnableEntryInstrumentation(int64_t FunctionAddress,
                                const ProfileData_t *ProfileData);
void EnableExitInstrumentation(int64_t FunctionAddress,
                               const ProfileData_t *ProfileData);
void EnableAllInstrumentation();

// main function executed by the control thread
void *ControlThreadFunction();

// Runtime Config used by Blink
typedef struct {
  // Accumulates total samples collected (used for sample cap enforcement)
  uint64_t total_sample_count;
  // If true, enabling trace all function calls unconditionally
  bool pervasive;
  // Global cap on the total number of samples collected (0 = no cap)
  uint64_t max_samples;
  // Per-function sample budget before disabling tracing (n in the paper)
  uint64_t nsamples;
  // Time interval (in microseconds) to re-enable tracing (X in the paper)
  uint64_t sampling_interval;
  // Per-thread ring buffer size (number of 16-byte samples)
  uint64_t buffer_size;
  // PMU event ID to collect (matches Linux perf_event encoding)
  uint64_t PMU_event;
  uint64_t PMU_index;
  // Directory to write the configuration file and flushed trace buffers
  char output_dir[256];
  // Name of the instrumented shared library (required in dynamic mode)
  char lib[256];
  // If true, mode = dynamic, else mode = regular
  bool mode;
} BlinkConfigs;

void DumpBlinkConfigs(const char *path, const BlinkConfigs *c);
void LoadAndDumpBlinkConfigs(void);

#define MAX_DATA_SIZE 16384
#define MAX_NUM_FUN 2048
typedef struct {
  uint64_t source_location;
  uint64_t pmu_value;
} Data;

typedef struct {
  int size;
  int pmu_index;
  bool init;
  int dump_idx;
  int count[MAX_NUM_FUN];
  Data data[MAX_DATA_SIZE];
} PMUStats;

void InitPMUStats(PMUStats *stats);

void dump_data_array(PMUStats *stats, int size);
void init_perf_util();
void *__custom_instrumentation(ProfileData_t *ProfileData,
                               uint64_t CodeLocationID);
void *__custom_instrumentation_exit(ProfileData_t *ProfileData,
                                    uint64_t CodeLocationID);

#endif // MIP_MIPHELPER_H
