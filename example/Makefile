LLVM_HOME?=/home/ubuntu/tools/out/llvm-install
SYSROOT?=$(LLVM_HOME)/../sysroot/aarch64-linux-ohos
CXX = $(LLVM_HOME)/bin/clang++
LD = $(LLVM_HOME)/bin/ld.lld

CXXFLAGSBLINK= -O0 -g -Wall -Wextra \
	           --target=aarch64-linux-ohos \
		   --sysroot=$(SYSROOT) \
		   -Wl,-Bsymbolic \
		   -fmachine-profile-generate \
		   -Wl,-mllvm,-enable-machine-instrumentation \
		   -Wl,-mllvm,-enable-machine-call-graph \
		   -Wl,-mllvm,--blink-mode=dynamic


all: example

example: example.cpp
	$(CXX) $(CXXFLAGSBLINK) -o $@ $^

clean:
		rm -f example
