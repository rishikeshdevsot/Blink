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
  uint32_t CallCount;       // Function Invocation counter
  uint32_t Timestamp;       // set to 0xffffffff
  int64_t OffsetToFunction; // PC relative offset to the function address
  uint32_t DisabledFlag;    // flag specifying if instrumentation is disabled
  uint32_t NumExitBlocks;   // Number of exit blocks in function
  uint32_t ExitBlockOffsetArray; // array containing offset from function entry
                                 // to exit instrumentations
} ProfileData_t;

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
  // Directory to write the configuration file and flushed trace buffers
  char output_dir[256];
  // Name of the instrumented shared library (required in dynamic mode)
  char lib[256];
} BlinkConfigs;

BlinkConfigs configs = {
    // clang-format off
    .total_sample_count = 0,
    .pervasive          = false,
    .max_samples        = 0,          // No global cap by default (pervasive
                                      // mode enabled unless --max-sample is
                                      // specified)
    .nsamples           = 10 * 2,     // Default: disable tracing after 10
                                      // samples per function
    .sampling_interval  = 400 * 1000, // Default: re-enable tracing after 400ms
    .buffer_size        = 10000,      // Default buffer size: 10,000 samples
                                      // per thread
    .PMU_event          = 0,          // Default PMU event
                                      // (e.g. PERF_COUNT_HW_CPU_CYCLES)
    .PMU_index          = 5,
    .output_dir         = "/data/local/tmp", // Default output location
    .lib                = "",         // Must be set explicitly for dynamic mode
    // clang-format on
};

#define MAX_DATA_SIZE 10000
typedef struct {
  uint64_t source_location;
  uint64_t pmu_value;
} Data;

typedef struct {
  Data data[MAX_DATA_SIZE];
  int size;
  int pmu_index;
  bool init;
} PMUStats;

void InitPMUStats(PMUStats *stats);

void dump_data_array(Data *array, int size);
void init_perf_util();
void *__custom_instrumentation(ProfileData_t *ProfileData,
                               uint64_t CodeLocationID);
void *__custom_instrumentation_exit(ProfileData_t *ProfileData,
                                    uint64_t CodeLocationID);

#endif // MIP_MIPHELPER_H
