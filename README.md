# Blink
Blink is a lightweight instrumentation framework that provides robust coverage for short-lived routines. It is built on top of [OpenHarmony's LLVM-based compiler toolchain](https://github.com/openharmony/third_party_llvm-project). 

Blink's changes to the upstream toolchain span commits `61ffacf3b822..a4948380dc9f`, touching the compiler-rt MIP runtime (`compiler-rt/lib/mip/`), the MIR instrumentation pass (`llvm/lib/CodeGen/MIRInstrumentationPass.cpp`), the AArch64 assembly printer (`llvm/lib/Target/AArch64/AArch64AsmPrinter.cpp`), the MIP section emitter (`llvm/lib/CodeGen/MIPSectionEmitter.cpp`), new target opcodes, and 7 lit tests under `llvm/test/CodeGen/AArch64/Blink/`. The remaining files in this repo (under `scripts/`, `example/`, `Docker/`, etc.) are supporting infrastructure for building and evaluating Blink.

The following sections describe how to build and use Blink.

## Getting Started
This section describes how to build Blink and compile a simple program with Blink's instrumentation.

### Build instructions:

[This link](https://github.com/openharmony/third_party_llvm-project/blob/master/llvm-build/README.md) contains the toolchain's build instructions

> [!NOTE]
> Blink only supports the AArch64 backend 

<details>
<summary><strong>Docker build (recommended)</strong></summary>

A Dockerfile is provided that automates building the toolchain. The image contains only the build environment; the Blink source and output directories are volume-mounted at runtime.

**Requirements:** Internet access, 400 GB disk

**1. Build the image** (from inside the Blink repository):

```bash
docker build -t blink-llvm-toolchain -f Docker/Dockerfile.llvm-toolchain .
```

**2. Run the build:**

```bash
docker run --rm \
  -v /path/to/Blink:/home/builder/blink-source \
  -v /path/to/tools-output:/home/builder/tools \
  blink-llvm-toolchain
```

- The first `-v` mounts your Blink checkout into the container. The entrypoint script will symlink it into place after `repo sync` completes.
- The second `-v` mounts the workspace directory where the OpenHarmony toolchain will be checked out and built. `repo sync` will download the source tree here (the `llvm-toolchain.xml` manifest, which pulls repos like `toolchain/llvm-project`, `build`, `prebuilts`, etc.), and the built toolchain will be written to `/path/to/tools-output/out/llvm-install` on the host.
</details>


### Compiling an example program using Blink
TODO (YiFan)


## Detailed Instructions
This section describes how to run the scripts to replicate the results from "When Sampling Lies: Trustworthy Performance Profiling for Flat Workloads with
Blink (Operational Systems)".

[This link](https://gitee.com/openharmony/docs/blob/master/en/device-dev/subsystems/subsys-build-all.md) contains the english translated instructions for building an OpenHarmony components using the toolchain ([Original link](https://gitcode.com/openharmony/docs/blob/master/zh-cn/device-dev/subsystems/subsys-build-all.md)) 


## Limitations
1. Running Blink compiled binaries requires Huawei Mate mobile phones that are unlocked and rooted. 
2. Blink compiled binaries can only run on OpenHarmony OS running on AArch64 architecture. In its current state, it cannot be used on other architectures. (TODO: which OS versions does Blink work on) 

