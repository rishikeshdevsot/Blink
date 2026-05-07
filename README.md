# Blink
Blink is a lightweight instrumentation framework that provides robust coverage for short-lived routines. It is built on top of [OpenHarmony's LLVM-based compiler toolchain](https://github.com/openharmony/third_party_llvm-project) with 3 additional components: an LLVM IR pass, a Machine IR pass and a compiler-rt plugin. This repo contains these components on top the toolchain. 

TODO (Rishi): Add filenames and line numbers corresponding to the changes so evaluators know what to look for. 

The following sections describe how to build and use Blink.

## Getting Started
This section describes how to build Blink and use it to compile a simple program.

### Build instructions: 

[This link](https://github.com/openharmony/third_party_llvm-project/blob/master/llvm-build/README.md) contains the toolchain's build instructions

> [!NOTE]
> Blink only supports the AArch64 backend so follow the instructions for ["Build process of AArch64 toolchain"](https://github.com/openharmony/third_party_llvm-project/tree/master/llvm-build#build-process-of-aarch64-toolchain)   

### Compiling an example program using Blink
TODO (YiFan)


## Detailed Instructions
This section describes how to run the scripts to replicate the results from "When Sampling Lies: Trustworthy Performance Profiling for Flat Workloads with
Blink (Operational Systems)".

[This link](https://gitee.com/openharmony/docs/blob/master/en/device-dev/subsystems/subsys-build-all.md) contains the english translated instructions for building an OpenHarmony components using the toolchain ([Original link](https://gitcode.com/openharmony/docs/blob/master/zh-cn/device-dev/subsystems/subsys-build-all.md)) 


## Limitations
1. Running Blink compiled binaries requires Huawei Mate mobile phones that are unlocked and rooted. 
2. Blink compiled binaries can only run on OpenHarmony OS running on AArch64 architecture. In its current state, it cannot be used on other architectures. (TODO: which OS versions does Blink work on) 

