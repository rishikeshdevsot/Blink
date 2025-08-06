/*===- MIPHelper.c - Machine IR Profile Runtime Helper --------------------===*\
|*
|* Part of the LLVM Project, under the Apache License v2.0 with LLVM Exceptions.
|* See https://llvm.org/LICENSE.txt for license information.
|* SPDX-License-Identifier: Apache-2.0 WITH LLVM-exception
|*
\*===----------------------------------------------------------------------===*/

#include "MIPHelper.h"

// The global timestamp value. Effectively records the number of unique
// functions that have been called. A value of zero means instrumentation is
// disabled.
uint32_t __llvm_mip_global_timestamp = 1;

// A global flag that enables: 1) the control thread 2) allows the tracing
// function to run It is set when SIGUSR2 signal is sent to the process that
// needs tracing
uint32_t enable_global = 0;

// Signal Handler for SIGUSR2
void dumpProfileOnSignal(int signal) { __llvm_dump_mip_profile(); }

void __llvm_mip_runtime_initialize(void) {
  struct sigaction DumpProfile;
  DumpProfile.sa_flags = 0;
  DumpProfile.sa_handler = &dumpProfileOnSignal;
  sigaction(SIGUSR2, &DumpProfile, NULL);
}

void InitPMUStats(PMUStats *stats) { stats->size = 0; }

// zero‐initialized by default, but we override it here:
_Thread_local PMUStats stats = {.size = 0,
                                .pmu_index = 5, // use pmevcntr5_el0 as default
                                .init = 0};

void __llvm_dump_mip_profile(void) {
  InitPMUStats(&stats);
  enable_global = 1;

  configs.total_sample_count = 0;

  asm volatile("isb");
}

int __llvm_dump_mip_profile_with_filename(const char *Filename) {
  FILE *filep = fopen(Filename, "wb");
  if (!filep) {
    fprintf(stderr, "[MIPRuntime]: Failed to open %s: %s\n", Filename,
            strerror(errno));
    return -1;
  }

  const void *Data = __llvm_mip_profile_begin();
  size_t DataSize =
      (char *)__llvm_mip_profile_end() - (char *)__llvm_mip_profile_begin();
  size_t BytesWritten = fwrite(Data, 1, DataSize, filep);
  if (BytesWritten != DataSize) {
    fprintf(stderr, "[MIPRuntime]: Failed to write to %s: %s\n", Filename,
            strerror(errno));
    fclose(filep);
    return -1;
  }

  fclose(filep);
  return 0;
}

// Implements "Call Count" function instrumentation and returns the address of
// `ProfileData`.
// NOTE: This code is not thread-safe, but that is ok because absolute precision
//       of `CallCount` and `Timestamp` is not critical. 
void *
__llvm_mip_call_counts_instrumentation_helper(ProfileData_t *ProfileData) {
  if (__llvm_mip_global_timestamp) {
    if (ProfileData->CallCount == 0xFFFFFFFF) {
      // This function is called for the first time.
      ProfileData->CallCount = 1;
      ProfileData->Timestamp = __llvm_mip_global_timestamp;
      // Since the number of functions << 2^32, a saturating add is not
      // necessary.
      __llvm_mip_global_timestamp += 1;
    } else {
      // This is not the first time this function has been called.
      uint32_t NewCallCount = ProfileData->CallCount + 1;
      if (NewCallCount != 0xFFFFFFFF)
        ProfileData->CallCount = NewCallCount;
    }
  }
  return ProfileData;
}

// *NOTE*: The following functions are called using inlined assembly, be careful
// when performing any modifications to them

// Flush the thread local sample buffer to disk
void dump_data_array(Data *array, int size) {

  // 1) read thread ID from TPIDR_EL0
  uintptr_t tid;
  asm volatile("mrs %0, tpidr_el0" : "=r"(tid));

  // 2) create "<output_dir>"
  const char *subdir = "";
  size_t od_len = strlen(configs.output_dir);
  size_t sub_len = strlen(subdir);
  // +1 for '/', +1 for terminating '\0'
  size_t dir_buf = od_len + 1 + sub_len + 1;
  char dirpath[dir_buf];

  snprintf(dirpath, dir_buf, "%s/%s", configs.output_dir, subdir);

  // 3) build filename:  "<output_dir>/pmu/thread_0x<hex>.bin"
  const char *prefix = "thread_0x";
  const char *suffix = ".bin";
  // how many hex digits?
  size_t hex_digits = snprintf(NULL, 0, "%lx", tid);
  // dirpath + '/' + prefix + hex_digits + suffix + '\0'
  size_t fn_buf =
      strlen(dirpath) + 1 + strlen(prefix) + hex_digits + strlen(suffix) + 1;
  char filename[fn_buf];

  snprintf(filename, fn_buf, "%s/%s%lx%s", dirpath, prefix, tid, suffix);

  // 4) open+append & write
  FILE *fp = fopen(filename, "ab");
  if (fp) {
    size_t written = fwrite(array, sizeof(Data), size, fp);
    if (written != (size_t)size) {
      fprintf(stderr, "fwrite incomplete (%zu of %d)\n", written, size);
    }
    fclose(fp);
  }
}

static inline int perf_event_open_syscall(struct perf_event_attr *attr,
                                          pid_t pid, int cpu, int group_fd,
                                          unsigned long flags) {
  register long x8 asm("x8") = __NR_perf_event_open;
  register long x0 asm("x0") = (long)attr;
  register long x1 asm("x1") = pid;
  register long x2 asm("x2") = cpu;
  register long x3 asm("x3") = group_fd;
  register long x4 asm("x4") = flags;
  asm volatile("svc #0\n"
               : "+r"(x0)
               : "r"(x1), "r"(x2), "r"(x3), "r"(x4), "r"(x8)
               : "memory");
  return (int)x0;
}

// Initialize PMU counter
void init_perf_util() {
  struct perf_event_attr pe;
  memset(&pe, 0, sizeof(struct perf_event_attr));

  pe.type = PERF_TYPE_HARDWARE;
  pe.config = configs.PMU_event;
  pe.size = sizeof(struct perf_event_attr);

  // Enable counting for user-space only
  pe.exclude_kernel = 1; // Exclude kernel events
  pe.disabled = 1;       // Disable counter initially

  uint64_t before;
  asm volatile("mrs %0, pmcntenset_el0" : "=r"(before));

  int fd = perf_event_open_syscall(&pe, 0, -1, -1, 0);

  ioctl(fd, PERF_EVENT_IOC_RESET, 0);  // Reset the counter
  ioctl(fd, PERF_EVENT_IOC_ENABLE, 0); // Start counting immediately

  uint64_t after;
  asm volatile("mrs %0, pmcntenset_el0" : "=r"(after));

  uint64_t diff = before ^ after;
  if (diff == 0) {
    // use pmevcntr5_el0 as default
    stats.pmu_index = 5;
  } else {
    for (int bit = 0; bit < 8; ++bit) {
      if (diff & (1ULL << bit)) {
        stats.pmu_index = bit;
      }
    }
  }

  stats.init = 1;
}

// Blink's tracing function (instrumented at function entry)
// WARNING: Be careful modifying this code, it is tailored to only use registers
// x0,x1,x8-x16 to reduce overhead. Using any more registers without saving them
// can cause stack corruption or unexpected behaviour
void *__custom_instrumentation(ProfileData_t *ProfileData,
                               uint64_t CodeLocationID) {
  if (!enable_global) {
    return NULL;
  }

  // hoist emutls by caching thread local pointer in a register
  register PMUStats *local_stats asm("x16");

  asm volatile(
      // ─── compute &__emutls_v.stats into X16 ───────────────────
      "adrp    x0, __emutls_v.stats\n\t"
      "add     x0, x0, :lo12:__emutls_v.stats\n\t"

      // ─── save X0, X1, X8, X2, FP (X29) and LR (X30) ───────────
      "sub     sp, sp,    #48\n\t"        // allocate 48 bytes
      "stp     x3,   x2,   [sp, #0]\n\t"  // save X0 & X1
      "stp     x8,   x1,   [sp, #16]\n\t" // save X8 & X2
      "stp     x29,  x30,  [sp, #32]\n\t" // save FP & LR

      // ─── call the TLS helper ─────────────────────────────────
      "bl      __emutls_get_address\n\t"
      "mov     x16, x0\n\t" // capture return into X16

      // ─── restore FP, LR, and X8 ───────────────────────────────

      // ─── restore FP, LR, X8, X2, X0 & X1 ──────────────────────
      "ldp     x29,  x30,  [sp, #32]\n\t" // restore FP & LR
      "ldp     x8,   x1,   [sp, #16]\n\t" // restore X8 & X2
      "ldp     x3,   x2,   [sp, #0]\n\t"  // restore X0 & X1
      "add     sp,   sp,    #48\n\t"      // deallocate frame

      : "=r"(local_stats) // local_stats ← X16 - register clobbered
      :
      : "x0", "memory");

  if (!local_stats->init) {
    local_stats->init = 1;
    asm volatile("sub     sp, sp,    #48\n\t" // allocate space on stack for reg
                                              // who is not dead yet
                 "stp     x9,   x10,   [sp, #0]\n\t"
                 "stp     x11,   x12,   [sp, #16]\n\t"
                 "stp     x15,  x16,  [sp, #32]\n\t"

                 "stp x29, x30, [sp, #-16]!\n\t"
                 "bl init_perf_util_helper\n\t"
                 "ldp     x15,  x16,  [sp, #32]\n\t"
                 "ldp     x11,   x12,   [sp, #16]\n\t"
                 "ldp     x9,   x10,   [sp, #0]\n\t"
                 "add     sp,   sp,    #48\n\t");
  }

  configs.total_sample_count++;
  ProfileData->CallCount += 1;

  local_stats->data[local_stats->size].source_location = CodeLocationID;

  // access PMU counter
  int64_t value;
  // 5 captures perf_event set-up after emperical experiment on realworkload
  // asm volatile("isb");
  asm volatile("mrs %0, pmevcntr5_el0" : "=r"(value));
  // asm volatile("isb");
  local_stats->data[local_stats->size++].pmu_value = value;

  if (local_stats->size >= configs.buffer_size) {
    int size = local_stats->size;
    // Reset
    local_stats->size = 0;
    // dump_data_array(stats.data, stats.size);
    asm volatile("mov x0, %0\n\t"
                 "mov x1, %1\n\t"
                 "stp x29, x30, [sp, #-16]!\n\t"
                 "bl dump_data_array_helper\n\t"
                 :
                 : "r"(local_stats->data), "r"(size)
                 : "x0", "x1");
    return NULL;
  }

  return NULL;
}

// Blink's tracing function (instrumented at function exit)
// WARNING: Be careful modifying this code, it is tailored to only use registers
// x0,x1,x8-x16 to reduce overhead. Using any more registers without saving them
// can cause stack corruption or unexpected behaviour
void *__custom_instrumentation_exit(ProfileData_t *ProfileData,
                                    uint64_t CodeLocationID) {

  if (!enable_global) {
    return NULL;
  }

  int64_t value asm("x9");
  ;
  // 5 captures perf_event set-up after emperical experiment on realworkload
  // asm volatile("isb");
  asm volatile("mrs %0, pmevcntr5_el0" : "=r"(value));
  // asm volatile("isb");

  // hoist emutls by caching thread local pointer in a register
  register PMUStats *local_stats asm("x16");

  asm volatile(
      // ─── compute &__emutls_v.stats into X16 ───────────────────
      "adrp    x0, __emutls_v.stats\n\t"
      "add     x0, x0, :lo12:__emutls_v.stats\n\t"

      // ─── save X0, X1, X8, X2, FP (X29) and LR (X30) ───────────
      "sub     sp, sp,    #64\n\t"        // allocate 48 bytes
      "stp     x3,   x2,   [sp, #0]\n\t"  // save X0 & X1
      "stp     x8,   x1,   [sp, #16]\n\t" // save X8 & X2
      "stp     x29,  x30,  [sp, #32]\n\t" // save FP & LR
      "stp     x9,  x10,  [sp, #48]\n\t"  // save FP & LR

      // ─── call the TLS helper ─────────────────────────────────
      "bl      __emutls_get_address\n\t"
      "mov     x16, x0\n\t" // capture return into X16

      // ─── restore FP, LR, and X8 ───────────────────────────────

      // ─── restore FP, LR, X8, X2, X0 & X1 ──────────────────────
      "ldp     x9,  x10,  [sp, #48]\n\t"  // restore FP & LR
      "ldp     x29,  x30,  [sp, #32]\n\t" // restore FP & LR
      "ldp     x8,   x1,   [sp, #16]\n\t" // restore X8 & X2
      "ldp     x3,   x2,   [sp, #0]\n\t"  // restore X0 & X1
      "add     sp,   sp,    #64\n\t"      // deallocate frame

      : "=r"(local_stats) // local_stats ← X16 - register clobbered
      :
      : "x0", "memory");

  local_stats->data[local_stats->size].source_location = CodeLocationID;

  // access PMU counter
  local_stats->data[local_stats->size++].pmu_value = value;

  configs.total_sample_count++;
  ProfileData->CallCount += 1;

  if (local_stats->size >= configs.buffer_size) {
    int size = local_stats->size;
    // Reset
    local_stats->size = 0;
    // dump_data_array(stats.data, stats.size);
    asm volatile("mov x0, %0\n\t"
                 "mov x1, %1\n\t"
                 "stp x29, x30, [sp, #-16]!\n\t"
                 "bl dump_data_array_helper\n\t"
                 :
                 : "r"(local_stats->data), "r"(size)
                 : "x0", "x1");
    return NULL;
  }

  return NULL;
}

#ifdef __linux__
#define MIP_RAW_SECTION_BEGIN_SYMBOL MIP_CONCAT(__start_, MIP_RAW_SECTION)
#define MIP_RAW_SECTION_END_SYMBOL MIP_CONCAT(__stop_, MIP_RAW_SECTION)
extern char MIP_RAW_SECTION_BEGIN_SYMBOL;
extern char MIP_RAW_SECTION_END_SYMBOL;
#endif // __linux__

#ifdef __APPLE__
#define MIP_RAW_SECTION_BEGIN_SYMBOL __llvm_mip_raw_section_start
#define MIP_RAW_SECTION_END_SYMBOL __llvm_mip_raw_section_end
extern char MIP_RAW_SECTION_BEGIN_SYMBOL __asm(
    "section$start$__DATA$" MIP_RAW_SECTION_NAME);
extern char MIP_RAW_SECTION_END_SYMBOL __asm(
    "section$end$__DATA$" MIP_RAW_SECTION_NAME);
#endif // __APPLE__

#ifdef __OHOS__
#define MIP_RAW_SECTION_BEGIN_SYMBOL MIP_CONCAT(__start_, MIP_RAW_SECTION)
#define MIP_RAW_SECTION_END_SYMBOL MIP_CONCAT(__stop_, MIP_RAW_SECTION)
extern char MIP_RAW_SECTION_BEGIN_SYMBOL;
extern char MIP_RAW_SECTION_END_SYMBOL;
#endif // __OHOS__

void *__llvm_mip_profile_begin(void) { return &MIP_RAW_SECTION_BEGIN_SYMBOL; }

void *__llvm_mip_profile_end(void) { return &MIP_RAW_SECTION_END_SYMBOL; }
