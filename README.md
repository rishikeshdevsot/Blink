# Blink
Blink is a lightweight instrumentation framework that provides robust coverage for short-lived routines. It is built on top of [OpenHarmony's LLVM-based compiler toolchain](https://github.com/openharmony/third_party_llvm-project). 

Blink's changes to the upstream toolchain span commits `61ffacf3b822..4e9d65b005cc2`, touching the compiler-rt MIP runtime (`compiler-rt/lib/mip/`), the MIR instrumentation pass (`llvm/lib/CodeGen/MIRInstrumentationPass.cpp`), the AArch64 assembly printer (`llvm/lib/Target/AArch64/AArch64AsmPrinter.cpp`), the MIP section emitter (`llvm/lib/CodeGen/MIPSectionEmitter.cpp`), new target opcodes, and 7 lit tests under `llvm/test/CodeGen/AArch64/Blink/`. The remaining files in this repo (under `scripts/`, `example/`, `Docker/`, etc.) are supporting infrastructure for building and evaluating Blink.

The following sections describe how to build and use Blink.

## Getting Started
This section describes how to build Blink and compile a simple program with Blink's instrumentation.

### Build instructions:

<details>
<summary><strong>Docker build (recommended)</strong></summary>

A Dockerfile to automate building the toolchain ([Official build instructions](https://github.com/openharmony/third_party_llvm-project/blob/master/llvm-build/README.md)) is provided under [](Docker/). 

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

- The first `-v` mounts your Blink repository into the container. The entrypoint script will symlink it into place after `repo sync` completes.
- The second `-v` mounts the workspace directory where the toolchain pre-requisites will be checked out and built. `repo sync` will download the source tree here (the `llvm-toolchain.xml` manifest, which pulls repos like `toolchain/llvm-project`, `build`, `prebuilts`, etc.). The built binaries will be written to `/path/to/tools-output/out/llvm-install` on the host.
</details>

> [!NOTE]
> Blink only supports the AArch64 backend 

### Compiling an example program using Blink

After the Docker build completes, the toolchain is at `/path/to/tools-output/out/llvm-install` and the sysroot at `/path/to/tools-output/out/sysroot`.

Build the example program with Blink instrumentation:

```bash
cd blink_scripts/example
make LLVM_HOME=/path/to/tools-output/out/llvm-install \
     SYSROOT=/path/to/tools-output/out/sysroot/aarch64-linux-ohos
```

This produces an `example` binary (AArch64 ELF) with Blink's `__llvm_mipmap` and `__llvm_mipraw` sections embedded, and a `MIPCodeInfo/` directory with the instrumentation metadata CSV.


## Detailed Instructions
The official Blink user guide to compile an OpenHarmony library, deploy it on the phone, collect and process traces is [here](./Blink-User-Guide.md)

## Limitations
1. Running Blink compiled binaries requires Huawei Mate mobile phones that are unlocked and rooted. 
2. Blink compiled binaries have only been tested on OpenHarmony OS (v5.0.0) running on AArch64 architecture. In its current state, they cannot be run on other architectures. 

