#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <errno.h>
#include <getopt.h>
#include <stdint.h>
#include <signal.h>
#include <sys/stat.h>
#include <unistd.h>

// Event table entry
typedef struct {
    const char *name;
    uint32_t code;
    const char *type;
    const char *desc;
} event_t;

static const event_t event_table[] = {
    {"CPU_CYCLES",          0, "Architectural", "Total cycles (PERF_COUNT_HW_CPU_CYCLES)"},
    {"INST_RETIRED",        1, "Architectural", "Instructions retired (PERF_COUNT_HW_INSTRUCTIONS)"},
    {"CACHE_REFERENCES",    2, "Architectural", "Cache references (PERF_COUNT_HW_CACHE_REFERENCES)"},
    {"CACHE_MISSES",        3, "Architectural", "Cache misses (PERF_COUNT_HW_CACHE_MISSES)"},
    {"BRANCH_INSTRUCTIONS", 4, "Architectural", "Branch instructions (PERF_COUNT_HW_BRANCH_INSTRUCTIONS)"},
    {"BRANCH_MISSES",       5, "Architectural", "Branch misses (PERF_COUNT_HW_BRANCH_MISSES)"},
    {"BUS_CYCLES",          6, "Architectural", "Bus cycles (PERF_COUNT_HW_BUS_CYCLES)"},
    {"STALL_FRONTEND",      7, "Architectural", "Stalled cycles frontend (PERF_COUNT_HW_STALLED_CYCLES_FRONTEND)"},
    {"STALL_BACKEND",       8, "Architectural", "Stalled cycles backend (PERF_COUNT_HW_STALLED_CYCLES_BACKEND)"},
    {"REF_CPU_CYCLES",      9, "Architectural", "Reference CPU cycles (PERF_COUNT_HW_REF_CPU_CYCLES)"},
};
static const size_t event_table_size = sizeof(event_table) / sizeof(event_table[0]);

typedef struct {
    unsigned long total_sample_count;
    unsigned long max_samples;
    unsigned long nsamples;
    unsigned long sampling_interval;
    unsigned long buffer_size;
    unsigned long PMU_event;
    unsigned long PMU_index;
    int pervasive;
    char output_dir[256];
    int pid;
    uint32_t event_code;
    char event_name[64];
    char lib_name[128];
    char bundle_name[256];
    int is_dynamic_mode; // 1 = dynamic, 0 = regular
} BlinkConfigs;

static BlinkConfigs configs = {
    .total_sample_count = 0,
    .max_samples = 0,
    .nsamples = 20,
    .sampling_interval = 400000,
    .buffer_size = 10000,
    .PMU_event = 1,
    .PMU_index = 5,
    .pervasive = 0,
    .output_dir = "/data/storage/el1/base",
    .pid = 0,
    .event_code = 0,
    .event_name = "CPU_CYCLES",
    .lib_name = "",
    .bundle_name = "",
    .is_dynamic_mode = 0
};

void print_event_table(void);
static void dump_configs(const char *path, const BlinkConfigs *c);

int mkdir_recursive(const char *dir) {
    char tmp[512];
    snprintf(tmp, sizeof(tmp), "%s", dir);
    size_t len = strlen(tmp);
    if (len == 0) return -1;
    if (tmp[len - 1] == '/') tmp[len - 1] = '\0';
    for (char *p = tmp + 1; *p; p++) {
        if (*p == '/') {
            *p = '\0';
            if (mkdir(tmp, 0777) != 0 && errno != EEXIST) return -1;
            chmod(tmp, 0777);
            *p = '/';
        }
    }
    if (mkdir(tmp, 0777) != 0 && errno != EEXIST) return -1;
    chmod(tmp, 0777);
    return 0;
}

static void print_usage(const char *prog) {
    printf("Usage: %s --pid <pid> --event <event_name> --mode <dynamic|regular> [options]\n\n", prog);
    printf("Mandatory arguments:\n");
    printf("  --pid <pid>               PID of the process to be traced by Blink\n");
    printf("  --event <event_name>      Performance event name (e.g. CPU_CYCLES)\n");
    printf("  --mode <dynamic|regular>  Specify if library was compiled in dynamic or regular mode\n");
    printf("  --lib <library>           Name of instrumented library (required in dynamic mode)\n");
    printf("  --bundle <name>           App bundle name, or \"\" for non-app processes (required in instrumenting app)\n\n");
    printf("Optional arguments:\n");
    printf("  --pmu-index <n>           PMU register index to use (e.g. 5 for PMEVCNTR5_EL0)\n");
    printf("  --output-dir <dir>        Output directory (default: %s)\n", configs.output_dir);
    printf("  --buffer-size <n>         Thread-local buffer size (default: %lu)\n", configs.buffer_size);
    printf("  --nsamples <n>            Samples per function before disabling (default: %lu)\n", configs.nsamples);
    printf("  --sampling-interval <us>  Re-enable interval (default: %lu)\n", configs.sampling_interval);
    printf("  --max-sample <n>          Max total samples (default: %lu = no cap)\n", configs.max_samples);
    printf("  --pervasive               Trace all invocations (disable sampling)\n");
    printf("  --list                    List supported events\n");
    printf("  -h, --help                Show this help\n");
}

void find_event(const char *name) {
    for (size_t i = 0; i < event_table_size; i++) {
        if (strcmp(name, event_table[i].name) == 0) {
            configs.event_code = event_table[i].code;
            strncpy(configs.event_name, name, sizeof(configs.event_name) - 1);
            return;
        }
    }
    fprintf(stderr, "Unknown event: %s\n", name);
    print_event_table();
    exit(1);
}

void send_signal_to_process(int pid) {
    if (kill(pid, SIGUSR2) == -1) {
        perror("Failed to send signal");
        exit(1);
    }
    printf("Signal sent to process %d to trigger Blink\n", pid);
}

int main(int argc, char *argv[]) {
    static struct option long_opts[] = {
        {"pid", required_argument, NULL, 'p'},
        {"event", required_argument, NULL, 'e'},
        {"bundle", required_argument, NULL, 'a'},
        {"lib", required_argument, NULL, 'L'},
        {"output-dir", required_argument, NULL, 'o'},
        {"buffer-size", required_argument, NULL, 'b'},
        {"nsamples", required_argument, NULL, 'n'},
        {"sampling-interval", required_argument, NULL, 'i'},
        {"max-sample", required_argument, NULL, 'm'},
        {"pervasive", no_argument, NULL, 'v'},
        {"mode", required_argument, NULL, 'M'},
        {"list", no_argument, NULL, 'l'},
        {"help", no_argument, NULL, 'h'},
        {"pmu-index", required_argument, NULL, 'x'},
        {NULL, 0, NULL, 0}
    };

    int opt;
    while ((opt = getopt_long(argc, argv, "p:e:a:L:o:b:n:i:m:M:vlhx:", long_opts, NULL)) != -1) {
        switch (opt) {
            case 'p': configs.pid = atoi(optarg); break;
            case 'e': find_event(optarg); break;
            case 'a': strncpy(configs.bundle_name, optarg, sizeof(configs.bundle_name) - 1); break;
            case 'L': strncpy(configs.lib_name, optarg, sizeof(configs.lib_name) - 1); break;
            case 'o': strncpy(configs.output_dir, optarg, sizeof(configs.output_dir) - 1); break;
            case 'b': configs.buffer_size = strtoul(optarg, NULL, 10); break;
            case 'n': configs.nsamples = strtoul(optarg, NULL, 10); break;
            case 'i': configs.sampling_interval = strtoul(optarg, NULL, 10); break;
            case 'm': configs.max_samples = strtoul(optarg, NULL, 10); break;
            case 'v': configs.pervasive = 1; break;
            case 'M':
                if (strcmp(optarg, "dynamic") == 0) configs.is_dynamic_mode = 1;
                else if (strcmp(optarg, "regular") == 0) configs.is_dynamic_mode = 0;
                else {
                    fprintf(stderr, "Invalid mode: %s. Must be 'dynamic' or 'regular'.\n", optarg);
                    return 1;
                }
                break;
            case 'l': print_event_table(); return 0;
            case 'h': print_usage(argv[0]); return 0;
            case 'x':
                configs.PMU_index = atoi(optarg);
                break;
            default: print_usage(argv[0]); return 1;
        }
    }

    if (configs.pid <= 0 || configs.event_name[0] == '\0' || (configs.is_dynamic_mode != 0 && configs.is_dynamic_mode != 1)) {
        fprintf(stderr, "Error: --pid, --event, and --mode are required\n");
        print_usage(argv[0]);
        return 1;
    }

    char path[512];
    char dir_path[512];
    if (strcmp(configs.bundle_name, "") != 0){
    	snprintf(path, sizeof(path), "/data/app/el1/100/base/%s/blink_configs.txt", configs.bundle_name);
        snprintf(dir_path, sizeof(path), "/data/app/el1/100/base/%s", configs.bundle_name);
    }else{
	    snprintf(path, sizeof(path), "%s/blink_configs.txt", "/data/storage/el1/base");
        snprintf(dir_path, sizeof(path), "/data/app/el1/100/base");
    }
    // create all directories for the path /data/storage/el1/base/ if they do not exist
    if (mkdir_recursive(dir_path) != 0) {
        fprintf(stderr, "Error: failed to create output subdirectory: %s (%s)\n",
                path, strerror(errno));
        return 1;
    }

    dump_configs(path, &configs);
    send_signal_to_process(configs.pid);
    printf("Wrote Blink configuration to %s\n", path);
    return 0;

}

void print_event_table(void) {
    printf("%-20s %-10s\n", "Event Name", "Code");
    for (size_t i = 0; i < event_table_size; i++) {
        printf("%-20s 0x%04X\n", event_table[i].name, event_table[i].code);
    }
}

static void dump_configs(const char *path, const BlinkConfigs *c) {
    FILE *f = fopen(path, "w");
    if (!f) {
        fprintf(stderr, "Error writing to %s: %s\n", path, strerror(errno));
        return;
    }
    fprintf(f,
        "pid                 = %d\n"
        "event_code          = 0x%04X\n"
        "event_name          = %s\n"
        "lib                 = %s\n"
        "output_dir          = %s\n"
        "total_sample_count  = %lu\n"
        "max_samples         = %lu\n"
        "nsamples            = %lu\n"
        "sampling_interval   = %lu\n"
        "buffer_size         = %lu\n"
        "PMU_event           = %lu\n"
        "PMU_index           = %lu\n"
        "pervasive           = %d\n"
        "mode                = %d\n",
        c->pid,
        c->event_code,
        c->event_name,
        c->lib_name,
        c->output_dir,
        c->total_sample_count,
        c->max_samples,
        c->nsamples,
        c->sampling_interval,
        c->buffer_size,
        c->PMU_event,
        c->PMU_index,
        c->pervasive,
        c->is_dynamic_mode
    );
    fclose(f);
}
