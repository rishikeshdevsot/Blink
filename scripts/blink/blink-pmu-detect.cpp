#include <stdio.h>
#include <stdlib.h>
#include <unistd.h>
#include <signal.h>
#include <pthread.h>
#include <sched.h>
#include <string.h>
#include <stdint.h>
#include <iostream>
#include <unistd.h>
#include <fcntl.h>
#include <sys/ioctl.h>
#include <linux/perf_event.h>
#include <sys/syscall.h>
#include <cstring>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>
#include <inttypes.h>
#include <sys/mman.h>
#include <sys/ioctl.h>
#include <sys/syscall.h>
#include <linux/perf_event.h>
#include <asm/unistd.h>
#include <time.h>
#include <errno.h>

#define NUM_INTERLEAVING_THREADS 1

// maintainer only
// #define DEBUG

#ifdef DEBUG
#define DBG(fmt, ...) printf(fmt, ##__VA_ARGS__)
#else
#define DBG(...) do {} while (0)
#endif

int perf_cs_fd = -1;
int fd2[NUM_INTERLEAVING_THREADS];
int fd3[NUM_INTERLEAVING_THREADS];

static uint32_t g_event_code = 0x0008;
static const char *g_event_name = "INST_RETIRED";
static int num_cores_global = 0;

#define NUM_EVENT_COUNTERS 31  // ARMv8 PMU: counters 0–30 (31 is PMCCNTR_EL0)

// Simple growable array for samples per counter
typedef struct {
    uint64_t *samples;
    size_t    count;
    size_t    cap;
} series_t;

static series_t g_counter_series[NUM_EVENT_COUNTERS];

static void series_append(series_t *s, uint64_t v) {
    if (s->count == s->cap) {
        size_t ncap = s->cap ? (s->cap * 2) : 64;
        uint64_t *n = (uint64_t*)realloc(s->samples, ncap * sizeof(uint64_t));
        if (!n) {
            // Allocation failure — keep going but drop this sample.
            return;
        }
        s->samples = n;
        s->cap = ncap;
    }
    s->samples[s->count++] = v;
}

static void series_free(series_t *s) {
    free(s->samples);
    s->samples = nullptr;
    s->count = s->cap = 0;
}

// Simple stderr progress bar (doesn't depend on DEBUG)
static void progress_bar(size_t current, size_t total, const char *label) {
    if (total == 0) return;
    if (current > total) current = total;

    const int width = 40;  // bar width
    double ratio = (double)current / (double)total;
    int filled = (int)(ratio * width + 0.5);

    static const char *FULL = "########################################";
    static const char *EMPTY = "........................................";

    fprintf(stderr, "\r[%.*s%.*s] %3d%%  %s",
            filled, FULL, width - filled, EMPTY,
            (int)(ratio * 100.0 + 0.5), label ? label : "");
    fflush(stderr);

    if (current == total) {
        fprintf(stderr, "\n");
        fflush(stderr);
    }
}

// Read a system register
#define READ_SYSREG(REG, VAL) asm volatile("mrs %0, " #REG : "=r"(VAL))

// Write to PMSELR_EL0 (to select event counter index)
static inline void write_pmselr_el0(uint32_t idx) {
    asm volatile("msr pmselr_el0, %0\n isb" :: "r"(idx));
}

// Read PMXEVCNTR_EL0 (selected event counter)
static inline uint64_t read_pmxevcntr_el0(void) {
    uint64_t val;
    asm volatile("mrs %0, pmxevcntr_el0" : "=r"(val));
    return val;
}

// Collect values for ALL event counters (0..NUM_EVENT_COUNTERS-1)
// Record into g_counter_series and print in DEBUG mode.
void collect_all_pmu_counters(void) {
    int core_after = sched_getcpu();  // returns the current core ID
    DBG("init [Core %d]\n", core_after);

    uint64_t pmcr, pmcntenset, pmuserenr, pmccntr;
    READ_SYSREG(pmcr_el0, pmcr);
    READ_SYSREG(pmcntenset_el0, pmcntenset);
    READ_SYSREG(pmuserenr_el0, pmuserenr);
    READ_SYSREG(pmccntr_el0, pmccntr);

    DBG("PMCR_EL0        = 0x%016lx\n", pmcr);
    DBG("PMCNTENSET_EL0  = 0x%016lx\n", pmcntenset);
    DBG("PMUSERENR_EL0   = 0x%016lx\n", pmuserenr);
    DBG("PMCCNTR_EL0     = %lu\n", pmccntr);

    for (uint32_t i = 0; i < NUM_EVENT_COUNTERS; ++i) {
        write_pmselr_el0(i);
        uint64_t val = read_pmxevcntr_el0();
        series_append(&g_counter_series[i], val);
        DBG("  PMEVCNTR[%2u] = %lu%s\n", i, val,
            ((pmcntenset >> i) & 1) ? " (enabled)" : "");
    }
}

static int
perf_event_open_c(struct perf_event_attr *attr,
                  pid_t pid, int cpu, int group_fd, unsigned long flags)
{
    return syscall(__NR_perf_event_open, attr, pid, cpu, group_fd, flags);
}

/**
 * perf_sample_cycles()  -- unchanged (kept for reference)
 */
void perf_sample_cycles(uint64_t sample_period) {
    struct perf_event_attr pe;
    int fd;
    size_t page_size = sysconf(_SC_PAGESIZE);
    const int data_pages = 8;

    memset(&pe, 0, sizeof(pe));
    pe.type           = PERF_TYPE_HARDWARE;
    pe.config         = PERF_COUNT_HW_CPU_CYCLES;
    pe.size           = sizeof(pe);
    pe.sample_period  = sample_period;
    pe.sample_type    = PERF_SAMPLE_IP | PERF_SAMPLE_TID | PERF_SAMPLE_TIME;
    pe.disabled       = 1;
    pe.exclude_kernel = 1;
    pe.exclude_hv     = 1;
    pe.wakeup_events  = 1;

    fd = perf_event_open_c(&pe, 0, -1, -1, 0);
    if (fd < 0) {
        DBG("perf_event_open: %s\n", strerror(errno));
        return;
    }

    void *ring = mmap(NULL, page_size * (1 + data_pages),
                      PROT_READ | PROT_WRITE, MAP_SHARED, fd, 0);
    if (ring == MAP_FAILED) {
        DBG("mmap: %s\n", strerror(errno));
        close(fd);
        return;
    }

    ioctl(fd, PERF_EVENT_IOC_RESET, 0);
    ioctl(fd, PERF_EVENT_IOC_ENABLE, 0);

    // workload(); // omitted

    // Parsing omitted.
    // munmap(ring, page_size * (1 + data_pages));
    // close(fd);
}

inline void perf_inst_retired_fd_init(int thread_id) {
    struct perf_event_attr pe{};
    memset(&pe, 0, sizeof(struct perf_event_attr));

    pe.type   = PERF_TYPE_HARDWARE;
    pe.config = PERF_COUNT_HW_CACHE_MISSES;
    pe.size   = sizeof(struct perf_event_attr);
    pe.exclude_kernel = 1;
    pe.disabled       = 1;

    fd3[thread_id] = syscall(__NR_perf_event_open, &pe, 0, -1, -1, 0);
    if (fd3[thread_id] == -1) {
        DBG("perf_event_open failed\n");
        return;
    }

    ioctl(fd3[thread_id], PERF_EVENT_IOC_RESET, 0);
    ioctl(fd3[thread_id], PERF_EVENT_IOC_ENABLE, 0);
    return;
}

static inline int
perf_event_open_syscall(struct perf_event_attr *attr, pid_t pid,
                        int cpu, int group_fd, unsigned long flags)
{
    register long x8 asm("x8") = __NR_perf_event_open;
    register long x0 asm("x0") = (long)attr;
    register long x1 asm("x1") = pid;
    register long x2 asm("x2") = cpu;
    register long x3 asm("x3") = group_fd;
    register long x4 asm("x4") = flags;
    asm volatile(
        "svc #0\n"
        : "+r"(x0)
        : "r"(x1), "r"(x2), "r"(x3), "r"(x4), "r"(x8)
        : "memory");
    return (int)x0;
}

inline void perf_cpu_cycle_fd_init(int thread_id) {
    struct perf_event_attr pe;
    memset(&pe, 0, sizeof(struct perf_event_attr));

    pe.type = PERF_TYPE_HARDWARE;
    pe.config = PERF_COUNT_HW_CPU_CYCLES;
    pe.size = sizeof(struct perf_event_attr);
    pe.exclude_kernel = 1;
    pe.disabled = 1;
    pe.pinned = 1;

    // uint64_t before;
    // asm volatile("mrs %0, pmcntenset_el0" : "=r"(before));
    // DBG("pmcntenset_el0 before perf is: 0x%08llx\n", (unsigned long long)before);

    int fd = perf_event_open_syscall(&pe, 0, -1, -1, 0);

    ioctl(fd, PERF_EVENT_IOC_RESET, 0);
    ioctl(fd, PERF_EVENT_IOC_ENABLE, 0);

    // uint64_t after;
    // asm volatile("mrs %0, pmcntenset_el0" : "=r"(after));
    // DBG("pmcntenset_el0 after  perf is: 0x%08llx\n", (unsigned long long)after);

    // uint64_t diff = before ^ after;
    // if (diff == 0) {
    //     DBG("No PMU-enable bits changed in indices 0–7.\n");
    // } else {
    //     for (int bit = 0; bit < 8; ++bit) {
    //         if (diff & (1ULL << bit)) {
    //             DBG("  ▶ bit %d changed\n", bit);
    //         }
    //     }
    // }

    // (void)thread_id;
    return;
}

#define PMU_PMCR_E    (1UL << 0)
static inline uint64_t read_pmcr_el0(void) {
    uint64_t v;
    asm volatile("mrs %0, pmcr_el0" : "=r"(v));
    return v;
}
static inline void write_pmcr_el0(uint64_t v) {
    asm volatile("msr pmcr_el0, %0" :: "r"(v) : "memory");
    asm volatile("isb");
}

void enable_vpmu_in_guest(void) {
    uint64_t v = read_pmcr_el0();
    v |= PMU_PMCR_E;
    write_pmcr_el0(v);
}

void disable_pmccntr_el0();

void configure_pmu_for_event(int counter_id, uint32_t event_code, int core_id) {
    (void)event_code;

    uint32_t range_per_core = UINT32_MAX / (num_cores_global ? num_cores_global : 1);
    uint32_t base_value = core_id * range_per_core;

    uint64_t pmcr;
    asm volatile("mrs %0, PMCR_EL0" : "=r"(pmcr));
    pmcr &= ~1; // disable all
    asm volatile("msr PMCR_EL0, %0" :: "r"(pmcr));
    asm volatile("isb");
    asm volatile("msr pmovsclr_el0, %0" :: "r"((uint64_t)0xFFFFFFFF));

    uint64_t pmuserenr_el0;
    asm volatile("mrs %0, pmuserenr_el0" : "=r"(pmuserenr_el0));
    DBG("pmuserenr_el0 is: %lx\n", pmuserenr_el0);

    uint32_t readback = 0;

    if (counter_id == 0) {
        asm volatile("msr pmevtyper0_el0, %0" :: "r"((uint64_t)core_id));
        asm volatile("msr pmevcntr0_el0, %0"  :: "r"((uint64_t)base_value));
        asm volatile("mrs %0, PMCCNTR_EL0" : "=r"(readback));
    } else {
        asm volatile("msr pmevtyper1_el0, %0" :: "r"((uint64_t)core_id));
        asm volatile("msr pmevcntr1_el0, %0"  :: "r"((uint64_t)base_value));
    }

    asm volatile("msr pmcntenset_el0, %0" :: "r"((uint64_t)0xf0));
    uint64_t pmcntenset_el0;
    asm volatile("mrs %0, pmcntenset_el0" : "=r"(pmcntenset_el0));
    DBG("pmcntenset_el0 is: %lx\n", pmcntenset_el0);

    DBG("[Core %d] PMU configured: event=%s (0x%X), counter=%d\n",
        core_id, g_event_name, g_event_code, readback);
}

void* thread_func(void* arg) {
    int core_id = *(int*)arg;
    cpu_set_t cpuset;
    CPU_ZERO(&cpuset);
    CPU_SET(core_id, &cpuset);
    if (sched_setaffinity(0, sizeof(cpuset), &cpuset) != 0) {
        perror("sched_setaffinity");
        pthread_exit(NULL);
    }
    sched_yield();
    configure_pmu_for_event(0, g_event_code, core_id);
    pthread_exit(NULL);
}

void disable_pmccntr_el0() {
    asm volatile(
        "mov x0, #(1 << 31)\n"
        "msr pmcntenclr_el0, x0\n"
        "isb\n"
        :::"x0", "memory"
    );
}

pthread_mutex_t lock;

void* thread_func2(void* arg) {
    int thread_id = *(int*)arg;
    free(arg);
    perf_cpu_cycle_fd_init(thread_id);

    const int total_rounds = 20;
    for (int i = 0; i < total_rounds; i++) {
        // update progress *before* sampling this round
        progress_bar(i, total_rounds, "Detecting PMU...");

        pthread_mutex_lock(&lock);

        DBG("printing thread id: %d\n", thread_id);
        collect_all_pmu_counters();

        int core_id = sched_getcpu();
        cpu_set_t cpuset;
        CPU_ZERO(&cpuset);
        int new_core_id = (num_cores_global > 0)
                          ? ((core_id + 1) % num_cores_global)
                          : core_id;
        CPU_SET(new_core_id, &cpuset);
        if (sched_setaffinity(0, sizeof(cpuset), &cpuset) != 0) {
            perror("sched_setaffinity");
            pthread_mutex_unlock(&lock);
            pthread_exit(NULL);
        }
        sched_yield();

        collect_all_pmu_counters();

        DBG("\n");
        pthread_mutex_unlock(&lock);

        // update progress *after* sampling this round
        progress_bar(i + 1, total_rounds, "Detecting PMU...");

        sleep(1);
    }

    DBG("first thread finished\n");
    pthread_exit(NULL);
}


// Check if a series is monotonically increasing (non-decreasing with at least one increase)
static bool is_monotonic_increasing(const series_t *s) {
    if (s->count < 2) return false;
    bool any_increase = false;
    for (size_t i = 1; i < s->count; ++i) {
        if (s->samples[i] < s->samples[i - 1]) return false;
        if (s->samples[i] > s->samples[i - 1]) any_increase = true;
    }
    return any_increase;
}

static void print_final_summary(void) {
    // Build list of monotonic counters
    int candidates[NUM_EVENT_COUNTERS];
    int n = 0;
    for (int i = 0; i < NUM_EVENT_COUNTERS; ++i) {
        if (is_monotonic_increasing(&g_counter_series[i])) {
            candidates[n++] = i;
        }
    }

#ifndef DEBUG
    // Non-debug mode: only final message
#endif

    if (n == 0) {
        printf("[RESULT] Unable to determine a monotonically increasing counter. "
               "No counter showed a clear increasing trend across migrations.\n");
    } else if (n == 1) {
        printf("[RESULT] Counter PMEVCNTR%d_EL0 appears monotonically increasing. "
               "Recommend using index %d.\n", candidates[0], candidates[0]);
    } else {
        printf("[RESULT] Multiple counters appear monotonically increasing: ");
        for (int i = 0; i < n; ++i) {
            printf("%sPMEVCNTR%d_EL0", (i ? ", " : ""), candidates[i]);
        }
        printf(". You may choose one of these indices.\n");
    }

#ifdef DEBUG
    // In debug mode, also print brief per-counter stats.
    for (int i = 0; i < NUM_EVENT_COUNTERS; ++i) {
        if (g_counter_series[i].count) {
            uint64_t first = g_counter_series[i].samples[0];
            uint64_t last  = g_counter_series[i].samples[g_counter_series[i].count - 1];
            DBG("PMEVCNTR[%02d]: samples=%zu first=%" PRIu64 " last=%" PRIu64 " %s\n",
                i, g_counter_series[i].count, first, last,
                is_monotonic_increasing(&g_counter_series[i]) ? "(mono↑)" : "");
        }
    }
#endif
}

int main(int argc, char *argv[]) {

    if (pthread_mutex_init(&lock, NULL) != 0) {
        printf("mutex init failed\n");
        return 1;
    }

    num_cores_global = sysconf(_SC_NPROCESSORS_ONLN);

    // Phase 1: per-core PMU setup (as in your original code)
    pthread_t threads[num_cores_global];
    int core_ids[num_cores_global];
    for (int i = 0; i < num_cores_global; i++) {
        core_ids[i] = i;
        pthread_create(&threads[i], NULL, thread_func, &core_ids[i]);
    }
    for (int i = 0; i < num_cores_global; i++) {
        pthread_join(threads[i], NULL);
    }

    DBG("Configuration complete.\n");

    // Phase 2: spawn a thread that migrates and collects samples repeatedly
    pthread_t threads2[NUM_INTERLEAVING_THREADS];
    for (int i = 0; i < NUM_INTERLEAVING_THREADS; i++) {
        int *id_ptr = (int *)malloc(sizeof *id_ptr);
        *id_ptr = i;
        pthread_create(&threads2[i], NULL, thread_func2, id_ptr);
    }
    for (int i = 0; i < NUM_INTERLEAVING_THREADS; i++) {
        pthread_join(threads2[i], NULL);
    }

    // Final summary (only message shown in non-DEBUG builds)
    print_final_summary();

    // Cleanup
    for (int i = 0; i < NUM_EVENT_COUNTERS; ++i) {
        series_free(&g_counter_series[i]);
    }
    pthread_mutex_destroy(&lock);
    return 0;
}
