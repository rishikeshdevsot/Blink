# Architecture detection
# ifeq ($(shell uname -m), x86_64)
#     ARCH_FLAGS = -DX86
# else ifeq ($(shell uname -m), aarch64)
#     ARCH_FLAGS = -DARM
# else
#     $(error Unsupported architecture)
# endif

# Compiler
CXX = /home/cWX1380091/llvm/out/llvm-install/bin/clang++

# Linker
LD = /home/cWX1380091/llvm/out/llvm-install/bin/ld.lld

# Compiler flags
CXXFLAGSHELLO = -O0 -g -Wall -Wextra $(ARCH_FLAGS) \
				-fuse-ld=$(LD) \
				--target=aarch64-linux-ohos \
				-fmachine-profile-generate \
				-Wl,-mllvm,-enable-machine-instrumentation \
				-Wl,-mllvm,-enable-machine-call-graph \
				-mllvm -enable-mir-custom \
				# -mllvm -mir-whitelist=_Z3fooi

CXXFLAGS = -O0 -g -Wall -Wextra $(ARCH_FLAGS) \
				-fuse-ld=$(LD) \
				--target=aarch64-linux-ohos \

# Output executables
TARGETS = configure-blink blink-pmu-detect


# Source files
SRC_pmu_access = configure-blink.cpp
SRC_inline_MIR_hello = blink-pmu-detect.cpp
MANUAL_MIR_SRC_hello = wait_mir.cpp
PERF_INTRUSIVE = perf_intrusiveness.cpp

# Build target
all: $(TARGETS)

# Build cycle_counter.out
configure-blink: $(SRC_pmu_access)
	$(CXX) $(CXXFLAGS) -o $@ $^

# Build hello.out
blink-pmu-detect.out: $(SRC_inline_MIR_hello)
	$(CXX) $(CXXFLAGS) -o $@ $^

# Build hello.out
wait_mir.out: $(MANUAL_MIR_SRC_hello)
	$(CXX) $(CXXFLAGS) -o $@ $^

# Build hello.out
perf_intrusive.out: $(PERF_INTRUSIVE)
	$(CXX) $(CXXFLAGS) -o $@ $^

# Clean target
clean:
	rm -f $(TARGETS)

# Run target for cycle_counter.out
run_cycle_counter: cycle_counter.out
	./cycle_counter.out

# Run target for hello.out
run_hello: hello.out
	./hello.out
