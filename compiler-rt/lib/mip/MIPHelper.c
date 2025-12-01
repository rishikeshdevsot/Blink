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

void print_regs(void) {
  uint64_t r1, r2, r3, r4, r5, r6, r7, r8, r9, r10, r11, r12, r13, r14, r15,
      r16, r17;

  asm volatile("mov %0, x1\n\t"
               "mov %1, x2\n\t"
               "mov %2, x3\n\t"
               "mov %3, x4\n\t"
               "mov %4, x5\n\t"
               "mov %5, x6\n\t"
               "mov %6, x7\n\t"
               "mov %7, x8\n\t"
               "mov %8, x9\n\t"
               "mov %9, x10\n\t"
               "mov %10, x11\n\t"
               "mov %11, x12\n\t"
               "mov %12, x13\n\t"
               "mov %13, x14\n\t"
               "mov %14, x15\n\t"
               "mov %15, x16\n\t"
               "mov %16, x17\n\t"
               : "=r"(r1), "=r"(r2), "=r"(r3), "=r"(r4), "=r"(r5), "=r"(r6),
                 "=r"(r7), "=r"(r8), "=r"(r9), "=r"(r10), "=r"(r11), "=r"(r12),
                 "=r"(r13), "=r"(r14), "=r"(r15), "=r"(r16), "=r"(r17)
               :
               :);

  printf("x1  = 0x%016llx\n", (unsigned long long)r1);
  printf("x2  = 0x%016llx\n", (unsigned long long)r2);
  printf("x3  = 0x%016llx\n", (unsigned long long)r3);
  printf("x4  = 0x%016llx\n", (unsigned long long)r4);
  printf("x5  = 0x%016llx\n", (unsigned long long)r5);
  printf("x6  = 0x%016llx\n", (unsigned long long)r6);
  printf("x7  = 0x%016llx\n", (unsigned long long)r7);
  printf("x8  = 0x%016llx\n", (unsigned long long)r8);
  printf("x9  = 0x%016llx\n", (unsigned long long)r9);
  printf("x10 = 0x%016llx\n", (unsigned long long)r10);
  printf("x11 = 0x%016llx\n", (unsigned long long)r11);
  printf("x12 = 0x%016llx\n", (unsigned long long)r12);
  printf("x13 = 0x%016llx\n", (unsigned long long)r13);
  printf("x14 = 0x%016llx\n", (unsigned long long)r14);
  printf("x15 = 0x%016llx\n", (unsigned long long)r15);
  printf("x16 = 0x%016llx\n", (unsigned long long)r16);
  printf("x17 = 0x%016llx\n", (unsigned long long)r17);
}

void set_regs(void) {
  asm volatile("mov x1,  #0x11\n\t"
               "mov x2,  #0x22\n\t"
               "mov x3,  #0x33\n\t"
               "mov x4,  #0x44\n\t"
               "mov x5,  #0x55\n\t"
               "mov x6,  #0x66\n\t"
               "mov x7,  #0x77\n\t"
               "mov x8,  #0x88\n\t"
               "mov x9,  #0x99\n\t"
               "mov x10, #0xAA\n\t"
               "mov x11, #0xBB\n\t"
               "mov x12, #0xCC\n\t"
               "mov x13, #0xDD\n\t"
               "mov x14, #0xEE\n\t"
               "mov x15, #0xFF\n\t"
               "mov x16, #0x1234\n\t"
               "mov x17, #0x5678\n\t"
               :
               :
               :);
}

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

void __llvm_mip_runtime_initialize(void) {
  struct sigaction DumpProfile;

  DumpProfile.sa_flags = 0;
  DumpProfile.sa_handler = &dumpProfileOnSignal;
  sigaction(SIGUSR2, &DumpProfile, NULL);

  // struct sigaction stopInstr;
  // stopInstr.sa_flags = 0;
  // stopInstr.sa_handler = &stopInstrumentation;
  // sigaction(SIGUSR1, &stopInstr, NULL);
}

void InitPMUStats(PMUStats *stats) { stats->size = 0; }

// zero‐initialized by default, but we override it here:
_Thread_local PMUStats stats = {.size = 0,
                                .pmu_index = 5, // use pmevcntr5_el0 as default
                                .init = 0,
                                .dump_idx = 0};

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
  if (false) {
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

  enable_global ^= 1;

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
void dump_data_array(PMUStats *stats, int size) {

  // 1) read thread ID from TPIDR_EL0
  // uintptr_t tid;
  // asm volatile("mrs %0, tpidr_el0" : "=r"(tid));
  // printf("dump called with size = %d\n", size);
  // if (size >= MAX_DATA_SIZE + 1) {
  // exit(0);
  // }
  // 2) create "<output_dir>"
  Data *array = stats->data;
  const char *subdir = "";
  size_t od_len = strlen(configs.output_dir);
  size_t sub_len = strlen(subdir);
  // +1 for '/', +1 for terminating '\0'
  size_t dir_buf = od_len + 1 + sub_len + 1;
  char dirpath[dir_buf];

  snprintf(dirpath, dir_buf, "%s/%s", configs.output_dir, subdir);

  // build filename:  "<dirpath>/<lib>_<tid>.bin"
  const char *suffix = ".bin";
  pid_t tid = syscall(SYS_gettid);
  size_t num_digits = snprintf(NULL, 0, "%d", tid);
  size_t dump_num_digits = snprintf(NULL, 0, "%d", stats->dump_idx);
  // dirpath + '/' + prefix + '_' + hex_digits + suffix + '\0'
  size_t fn_buf = strlen(dirpath) + 1 + strlen(configs.lib) + 1 + num_digits +
                  1 + dump_num_digits + strlen(suffix) + 1;
  char *filename = malloc(fn_buf * sizeof(char));

  snprintf(filename, fn_buf, "%s/%s_%d_%d%s", dirpath, configs.lib, tid,
           stats->dump_idx, suffix);
  stats->dump_idx++;

  // 4) open+append & write
  FILE *fp = fopen(filename, "ab");
  if (fp) {
    size_t written = fwrite(array, sizeof(Data), size, fp);
    if (written != (size_t)size) {
      fprintf(stderr, "fwrite incomplete (%zu of %d)\n", written, size);
    }
    fclose(fp);
  }
  free(filename);
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

  // uint64_t before;
  // asm volatile("mrs %0, pmcntenset_el0" : "=r"(before));

  int fd = perf_event_open_syscall(&pe, 0, -1, -1, 0);

  ioctl(fd, PERF_EVENT_IOC_RESET, 0);  // Reset the counter
  ioctl(fd, PERF_EVENT_IOC_ENABLE, 0); // Start counting immediately

  // uint64_t after;
  // asm volatile("mrs %0, pmcntenset_el0" : "=r"(after));

  // uint64_t diff = before ^ after;
  // if (diff == 0) {
  //     // use pmevcntr5_el0 as default
  stats.pmu_index = 5;
  // } else {
  //     for (int bit = 0; bit < 8; ++bit) {
  //         if (diff & (1ULL << bit)) {
  //           stats.pmu_index = bit;
  //         }
  //     }
  // }

  stats.init = 1;
}

// Blink's tracing function (instrumented at function entry)
// WARNING: Be careful modifying this code, it is tailored to only use registers
// x0,x1,x8-x16 to reduce overhead. Using any more registers without saving them
// can cause stack corruption or unexpected behaviour
void *__custom_instrumentation(ProfileData_t *ProfileData,
                               uint64_t CodeLocationID) {
  asm volatile("adrp  x16, enable_global\n"
               "ldr   w16, [x16, #:lo12:enable_global]\n"
               "cmp   w16, #0\n" // compare with zero
               "b.ne 1f\n"       // if enable_global != 0 → skip return
               "b 3f          \n"
               "1:");

  // hoist emutls by caching thread local pointer in a register
  register PMUStats *local_stats asm("x16");

  // set_regs();
  asm volatile(
      // ─── compute &__emutls_v.stats into X16 ───────────────────
      "adrp    x0, __emutls_v.stats\n\t"
      "add     x0, x0, :lo12:__emutls_v.stats\n\t"

      // ─── save X0, X1, X8, X2, FP (X29) and LR (X30) ───────────
      "sub     sp, sp,    #160   \n\t" // allocate 48 bytes
      // "stp     x2,  x3,  [sp, #16]\n\t"
      // "stp     x4,  x5,  [sp, #32]\n\t"
      // "stp     x6,  x7,  [sp, #48]\n\t"
      "stp     x8,  x9,  [sp, #64]\n\t"
      // "stp     x10, x11, [sp, #80]\n\t"
      // "stp     x12, x13, [sp, #96]\n\t"
      // "stp     x14, x15, [sp, #112]\n\t"
      "stp     x1, x17, [sp, #128]\n\t"
      "stp x29, x30,    [sp, #144]\n\t"

      // ─── call the TLS helper ─────────────────────────────────
      "bl      __emutls_get_address\n\t"
      // use x8 x0 x16 x17
      "mov     x16, x0\n\t" // capture return into X16

      // ─── restore FP, LR, and X8 ───────────────────────────────

      // ─── restore FP, LR, X8, X2, X0 & X1 ──────────────────────
      "ldp x29, x30,    [sp, #144]\n\t"
      "ldp     x1, x17,  [sp, #128]\n\t"
      // "ldp     x14, x15, [sp, #112]\n\t"
      // "ldp     x12, x13, [sp, #96]\n\t"
      // "ldp     x10, x11, [sp, #80]\n\t"
      "ldp     x8,  x9,  [sp, #64]\n\t"
      // "ldp     x6,  x7,  [sp, #48]\n\t"
      // "ldp     x4,  x5,  [sp, #32]\n\t"
      // "ldp     x2,  x3,  [sp, #16]\n\t"
      "add     sp, sp,        #160\n\t"

      : "=r"(local_stats) // local_stats ← X16 - register clobbered
      :
      : "memory");
  // print_regs();

  if (!local_stats->init) {
    local_stats->init = 1;

    // set_regs();
    asm volatile(
        // "sub     sp, sp,    #48\n\t"           // allocate space on stack for
        // reg who is not dead yet "stp     x9,   x10,   [sp, #0]\n\t" "stp x11,
        // x12,   [sp, #16]\n\t" "stp     x15,  x16,  [sp, #32]\n\t"

        "stp x29, x30, [sp, #-16]!\n\t"
        "bl init_perf_util_helper\n\t"
        "ldp x29, x30, [sp], #16\n\t"

        // "ldp     x15,  x16,  [sp, #32]\n\t"
        // "ldp     x11,   x12,   [sp, #16]\n\t"
        // "ldp     x9,   x10,   [sp, #0]\n\t"
        // "add     sp,   sp,    #48\n\t"
    );
    // print_regs();
  }

  // if (!configs.pervasive && ((ProfileData->CallCount >= configs.nsamples) ||
  // (ProfileData->DisabledFlag) || (configs.max_samples &&
  // configs.total_sample_count >= configs.max_samples))) {
  {
    register Data *data asm("x8") = &(local_stats->data[local_stats->size]);
    data->source_location = CodeLocationID;
    // access PMU counter
    register int64_t value asm("x0");
    asm volatile("isb \n\t"
                 // asm volatile(
                 "mrs %0, pmevcntr5_el0"
                 : "=r"(value));
    // ld x0 [data, 2]
    data->pmu_value = value;
  }

  {
    register int max_size asm("w0") = MAX_DATA_SIZE;
    asm volatile("ldr w1, [%0]  \n"
                 "add w1, w1, #1\n"
                 "cmp w1, %w1   \n"
                 "b.ge 2f       \n"
                 "str w1, [%0]  \n"
                 "b 3f          \n"
                 "2: \n"
                 "str wzr, [%0]  \n"
                 :
                 : "r"(&(local_stats->size)), "r"(max_size)
                 : "cc", "memory"

    );
  }

  // dump_data_array(stats.data, stats.size);
  // set_regs();
  asm volatile("mov x0, %0\n\t"
               //  "mov w1, %1"
               "stp x29, x30, [sp, #-16]!\n\t"
               "bl dump_data_array_helper\n\t"
               "ldp x29, x30, [sp], #16\n\t"
               :
               : "r"(local_stats)
               : "x0", "w1");
  // print_regs();
  asm volatile("3: \n");
  return NULL;
}
// Blink's tracing function (instrumented at function exit)
// WARNING: Be careful modifying this code, it is tailored to only use registers
// x0,x1,x8-x16 to reduce overhead. Using any more registers without saving them
// can cause stack corruption or unexpected behaviour
void *__custom_instrumentation_exit(ProfileData_t *ProfileData,
                                    uint64_t CodeLocationID) {
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
