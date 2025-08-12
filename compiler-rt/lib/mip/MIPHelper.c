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
    .mode               = true        // Default is dynamic mode
    // clang-format on
};

void DumpBlinkConfigs(const char *path, const BlinkConfigs *c) {
  FILE *f = fopen(path, "w");
  if (!f) {
    fprintf(stderr, "Failed to open %s for writing: %s\n", path,
            strerror(errno));
    return;
  }
  fprintf(f,
          "output_dir          = %s\n"
          "lib                 = %s\n"
          "total_sample_count  = %lu\n"
          "max_samples         = %lu\n"
          "nsamples            = %lu\n"
          "sampling_interval   = %lu\n"
          "buffer_size         = %lu\n"
          "PMU_event           = %lu\n"
          "PMU_index           = %lu\n"
          "pervasive           = %d\n"
          "mode                = %d\n",
          c->output_dir, c->lib, c->total_sample_count, c->max_samples,
          c->nsamples, c->sampling_interval, c->buffer_size, c->PMU_event,
          c->PMU_index, c->pervasive, c->mode);
  fclose(f);
}

void LoadAndDumpBlinkConfigs(void) {
  const char *in_path = "/data/storage/el1/base/blink_configs.txt";
  const char *out_path = "/data/storage/el1/base/blink_configs_run.txt";
  FILE *in = fopen(in_path, "r");
  if (in) {
    char line[256];
    while (fgets(line, sizeof(line), in)) {
      // Trim leading whitespace
      char *p = line;
      while (*p == ' ' || *p == '\t')
        p++;

      // 1) output_dir is a string
      if (strncmp(p, "output_dir", 10) == 0) {
        char dirval[256];
        if (sscanf(p, "output_dir = %255s", dirval) == 1) {
          strncpy(configs.output_dir, dirval, sizeof(configs.output_dir) - 1);
          configs.output_dir[sizeof(configs.output_dir) - 1] = '\0';
        }
      } else if (strncmp(p, "lib", 3) == 0) {
        char libval[256];
        if (sscanf(p, "lib = %255s", libval) == 1) {
          strncpy(configs.lib, libval, sizeof(configs.lib) - 1);
          configs.lib[sizeof(configs.lib) - 1] = '\0';
        }
      }
      // 2) the rest are unsigned values
      else {
        char key[64];
        unsigned long val;
        if (sscanf(p, "%63[^= ] = %lu", key, &val) == 2) {
          if (strcmp(key, "PMU_index") == 0)
            configs.PMU_index = val;
          else if (strcmp(key, "max_samples") == 0)
            configs.max_samples = val;
          else if (strcmp(key, "nsamples") == 0)
            configs.nsamples = val;
          else if (strcmp(key, "sampling_interval") == 0)
            configs.sampling_interval = val;
          else if (strcmp(key, "buffer_size") == 0)
            configs.buffer_size = val;
          else if (strcmp(key, "PMU_event") == 0)
            configs.PMU_event = val;
          else if (strcmp(key, "pervasive") == 0)
            configs.pervasive = (bool)val;
          else if (strcmp(key, "mode") == 0)
            configs.mode = (bool)val;
        }
      }
    }
    fclose(in);
  }
  // write out the runtime-used values
  DumpBlinkConfigs(out_path, &configs);
}

// Created if mprotect call was succesful
void CreateMprotectSuccessFile() {
  int fd = open("/data/storage/el1/base/mprotect_success_new.txt",
                O_WRONLY | O_CREAT | O_TRUNC, 0644);
  if (fd >= 0) {
    close(fd);
  }
}

// Created if mprotect was unsuccesful, contains err code of failure
void CreateMprotectFailureWithInfo(const MProtectErrorInfo *errors, int count) {
  int fd = open("/data/storage/el1/base/mprotect_failure.txt",
                O_WRONLY | O_CREAT | O_TRUNC, 0644);
  if (fd < 0) {
    return;
  }

  for (int i = 0; i < count; ++i) {
    char buf[256];
    int len = snprintf(buf, sizeof(buf),
                       "errno[%d]=%d start=0x%lx end=0x%lx len=0x%lx\n", i,
                       errors[i].errno_value, errors[i].start, errors[i].end,
                       (unsigned long)errors[i].len);
    write(fd, buf, len);
  }

  close(fd);
}

void EnableEntryInstrumentation(int64_t FunctionAddress,
                                const ProfileData_t *ProfileData) {

  int64_t RewriteAddress = FunctionAddress;
  uintptr_t target_addr = (uintptr_t)RewriteAddress;

  *((uint32_t *)target_addr) = 0xD503201F; // encoding for noop
}

void EnableExitInstrumentation(int64_t FunctionAddress,
                               const ProfileData_t *ProfileData) {
  uint32_t NumExitBlocks = ProfileData->NumExitBlocks;
  if (NumExitBlocks == 0) {
    return;
  }
  const uint32_t *ExitBlockOffsetArray = &(ProfileData->ExitBlockOffsetArray);
  for (int i = 0; i < NumExitBlocks; i++) {
    int64_t RewriteAddress = FunctionAddress + ExitBlockOffsetArray[i];

    // Extra placehold instruction for exit instrumentation
    // that should be skipped
    RewriteAddress = RewriteAddress + 4;
    uintptr_t target_addr = (uintptr_t)RewriteAddress;

    *((uint32_t *)target_addr) = 0xD503201F; // encoding for noop
  }
}

// Calculates the value to skip to the next row in the global table -- next
// function
static uint32_t CalculateSkipValueForNextFunction(uint32_t NumExitBlocks) {
  // Each row is padded to a 64 byte boundary

  // sizeof(ProfileData_t) - 4 corresponds to the space occupied by the struct
  // minus the exit block address array NumExitBlocks*4 corresponds to the space
  // occupied by the array storing addresses of exit blocks
  uint32_t SkipValNextFunction =
      64 * ((NumExitBlocks * 4 + sizeof(ProfileData_t) - 4) / 64);
  if (((NumExitBlocks * 4 + sizeof(ProfileData_t) - 4) % 64) > 0)
    SkipValNextFunction += 64;
  return SkipValNextFunction;
}

void EnableAllInstrumentation() {
  const void *MIPRawSection = __llvm_mip_profile_begin();
  void *MIPDataIndexer =
      (void *)((int64_t)MIPRawSection + 64); // Skip the 64 byte MIPHeader

  // Iterate until the end of the MIP profile section
  while (((int64_t)MIPDataIndexer) < ((int64_t)__llvm_mip_profile_end())) {

    // 0x50494DFB is the magic number that the MIP header starts with
    // Assumption: It's unlikely call count for a function will have this exact
    // value
    // TODO: Make this check more robust
    if (*((int32_t *)MIPDataIndexer) == 0x50494DFB) {
      MIPDataIndexer +=
          64; // Skip any additional MIP headers present post linking
      continue;
    }

    ProfileData_t *ProfileData = (ProfileData_t *)(MIPDataIndexer);
    uint32_t SkipValNextFunction =
        CalculateSkipValueForNextFunction(ProfileData->NumExitBlocks);
    if (!ProfileData->DisabledFlag) {
      MIPDataIndexer += SkipValNextFunction; // Move to the next function
      continue;
    }

    int64_t FunctionAddress =
        (int64_t)MIPDataIndexer + ProfileData->OffsetToFunction;

    EnableEntryInstrumentation(FunctionAddress, ProfileData);
    EnableExitInstrumentation(FunctionAddress, ProfileData);

    // Reset invocation count
    ProfileData->CallCount = 0;

    ProfileData->DisabledFlag = 0;
    MIPDataIndexer += SkipValNextFunction; // Move to the next function
  }
  asm volatile("isb");
}

void *ControlThreadFunction();

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

// Callback function call over all the loaded libaries by dl_iterate_phdr
int RewriteCallback(struct dl_phdr_info *info, size_t size, void *data) {
  const char *libname = (const char *)data;
  long page_size = sysconf(_SC_PAGESIZE);

  if (strstr(info->dlpi_name, libname)) {
    ElfW(Addr) start = info->dlpi_addr;
    ElfW(Addr) end = 0;

    // Find the end address by iterating over all the segments
    // Update the start address if not same as info->dlpi_addr
    for (int i = 0; i < info->dlpi_phnum; i++) {
      const ElfW(Phdr) *phdr = &info->dlpi_phdr[i];
      if (phdr->p_type == PT_LOAD) {
        ElfW(Addr) seg_start = info->dlpi_addr + phdr->p_vaddr;
        ElfW(Addr) seg_end = seg_start + phdr->p_memsz;

        if (seg_start < start)
          start = seg_start;
        if (seg_end > end)
          end = seg_end;
      }
    }

    // Page align the start and end
    unsigned long AlignedStart = start & ~(page_size - 1);
    unsigned long AlignedEnd = (end + page_size - 1) & ~(page_size - 1);
    if (mprotect((void *)AlignedStart, AlignedEnd - AlignedStart,
                 PROT_READ | PROT_WRITE | PROT_EXEC) == 0) {
      CreateMprotectSuccessFile();
    } else {
      MProtectErrorInfo err;
      err.errno_value = errno;
      err.start = AlignedStart;
      err.end = AlignedEnd;
      err.len = AlignedEnd - AlignedStart;
      CreateMprotectFailureWithInfo(&err, 1);
    }

    // Found library, stop iteration
    return 1;
  }
  // Keep iterating
  return 0;
}

// Returns true is successful, false if not
bool MakeCodePagesWriteable() {
  const char *target_lib = configs.lib;
  if (strlen(target_lib) == 0) {
    // if user fails to specify the rewriting library, we must not set the
    // enable_global flag as it will cause a segfault.
    return false;
  }

  dl_iterate_phdr(RewriteCallback, (void *)target_lib);
  // TODO: What if user passes an erroneous library name?
  return true;
}

void __llvm_dump_mip_profile(void) {
  LoadAndDumpBlinkConfigs();
  InitPMUStats(&stats);
  if (configs.mode) {
    // do nothing if lib is not provided/supported in dynamic mode
    if (!MakeCodePagesWriteable()) {
      return;
    } else {
      // here we are in dynamic mode with a rewritable library, initiating
      // control thread for turning the instrumentation on
      pthread_t ControlThread;
      pthread_create(&ControlThread, NULL, ControlThreadFunction, NULL);
    }
  } else {
    // if we are in regular mode, always turn on the instrumentation without
    // triggering any disabling mechanism
    configs.pervasive = 1;
  }

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

void *ControlThreadFunction() {
  while (!enable_global) {
    sleep(1);
  }
  while (enable_global) {
    if (configs.max_samples &&
        configs.total_sample_count >= configs.max_samples) {
      return NULL;
    }
    EnableAllInstrumentation();
    usleep(configs.sampling_interval);
  }
  return NULL;
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

  if (!configs.pervasive &&
      ((ProfileData->CallCount >= configs.nsamples) ||
       (ProfileData->DisabledFlag) ||
       (configs.max_samples &&
        configs.total_sample_count >= configs.max_samples))) {
    void *return_address;
    asm volatile("mov %0, lr" : "=r"(return_address));

    uintptr_t target_addr = (uintptr_t)return_address - 44;
    uint32_t *inst_ptr = (uint32_t *)target_addr;
    // Self-disable instrumentation
    *inst_ptr = 0x1400000E; // b +14 instructions
    ProfileData->DisabledFlag = 1;
    // asm volatile("isb");
  } else {

    configs.total_sample_count++;
    ProfileData->CallCount += 1;

    local_stats->data[local_stats->size].source_location = CodeLocationID;

    // access PMU counter
    int64_t value;
    // 5 captures perf_event set-up after emperical experiment on realworkload
    // asm volatile("isb");
    switch (configs.PMU_index) {
    case 0:
      asm volatile("mrs %0, pmevcntr0_el0" : "=r"(value));
      break;
    case 1:
      asm volatile("mrs %0, pmevcntr1_el0" : "=r"(value));
      break;
    case 2:
      asm volatile("mrs %0, pmevcntr2_el0" : "=r"(value));
      break;
    case 3:
      asm volatile("mrs %0, pmevcntr3_el0" : "=r"(value));
      break;
    case 4:
      asm volatile("mrs %0, pmevcntr4_el0" : "=r"(value));
      break;
    case 5:
      asm volatile("mrs %0, pmevcntr5_el0" : "=r"(value));
      break;
    }
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
  // 5 captures perf_event set-up after emperical experiment on realworkload
  // asm volatile("isb");
  switch (configs.PMU_index) {
  case 0:
    asm volatile("mrs %0, pmevcntr0_el0" : "=r"(value));
    break;
  case 1:
    asm volatile("mrs %0, pmevcntr1_el0" : "=r"(value));
    break;
  case 2:
    asm volatile("mrs %0, pmevcntr2_el0" : "=r"(value));
    break;
  case 3:
    asm volatile("mrs %0, pmevcntr3_el0" : "=r"(value));
    break;
  case 4:
    asm volatile("mrs %0, pmevcntr4_el0" : "=r"(value));
    break;
  case 5:
    asm volatile("mrs %0, pmevcntr5_el0" : "=r"(value));
    break;
  }
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

  if (!configs.pervasive &&
      ((ProfileData->CallCount >= configs.nsamples) ||
       (ProfileData->DisabledFlag) ||
       (configs.max_samples &&
        configs.total_sample_count >= configs.max_samples))) {
    void *return_address;
    asm volatile("mov %0, lr" : "=r"(return_address));

    uintptr_t target_addr = (uintptr_t)return_address - 44;
    uint32_t *inst_ptr = (uint32_t *)target_addr;
    // Self-disable instrumentation
    *inst_ptr = 0x1400000E; // b +14 instructions
    ProfileData->DisabledFlag = 1;
    // asm volatile("isb");
  } else {
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
