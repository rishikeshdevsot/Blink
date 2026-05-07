# OpenHarmony Build Guide

This guide covers building the LLVM toolchain and OpenHarmony libraries (e.g. `librender_service_base.z.so`).
It uses the existing build instructions in `/llvm-build/README.md` as a reference.

---

## Recommended Build Machine

- **OS**: Ubuntu 22.04 or 24.04 x86_64 — avoid 26.04 (Python 3.13 breaks builds)
- **RAM**: 32 GB minimum, 64 GB recommended
- **Disk**: 400 GB SSD (gp3 on AWS)
- **CPU**: 16+ cores (c7i.4xlarge or better on AWS)
- **Note**: Do NOT use `t3` instances — burstable CPU throttles badly on long builds

---

## Part 1: Building the Compiler (LLVM Toolchain)

### 1.1 Install System Dependencies

```bash
sudo apt install -y \
  build-essential \
  swig \
  python3-dev \
  libedit-dev \
  libncurses5-dev \
  binutils-dev \
  gcc-multilib \
  abigail-tools \
  elfutils \
  pkg-config \
  autoconf \
  autoconf-archive \
  git-lfs \
  clang \
  lld \
  cmake \
  ninja-build
```

### 1.2 Initialize the Repository

`$PWD` refers to the root build directory, e.g. `/home/ubuntu/tools`.
All instructions start from `$PWD`.

```bash
repo init -u https://gitcode.com/OpenHarmony/manifest.git \
    -b master \
    -m llvm-toolchain.xml
repo sync -c
repo forall -c 'git lfs pull'
```

> Takes approximately 30 min depending on connection speed.

### 1.3 Set Up the Project

Rename the current project `Blink` (a fork of LLVM) to `llvm-project` and place it
under the following directory (create directories if necessary). If the directory
already exists, rename the old one to `llvm-project-old`.

```bash
# target location
$PWD/toolchain/llvm-project
```

### 1.4 Install Prebuilt Dependencies

```bash
bash toolchain/llvm-project/llvm-build/env_prepare.sh
```

> Installs prebuilts into `prebuilts/`

### 1.5 Patch Python Scripts to call Python3 only

```bash
find $PWD/build -name '*.py' | xargs -IOUT sed -i 's:#!/usr/bin/env python:#!/usr/bin/env python3:' OUT
find $PWD/build -name '*.py' | xargs -IOUT sed -i 's:#!/usr/bin/env python33:#!/usr/bin/env python3:' OUT
```

### 1.6 Build the Toolchain

Builds clang and the toolchain targeting AArch64 only (~1 hour):

```bash
PATH=$PWD/prebuilts/python3/linux-x86/3.11.4/bin/:$PWD/prebuilts/build-tools/linux-x86/bin/:$PATH \
python3 ./toolchain/llvm-project/llvm-build/build.py \
    --host-build-projects clang,lld,clang-tools-extra,openmp \
    --no-build-riscv64 --no-build-mipsel --no-build-loongarch64 \
    --no-build-arm \
    --no-build lldb-server,windows \
    --compression-format gz
```

Built toolchain will be at `$PWD/out/llvm-install`.

### 1.7 Rebuilding

- Add `--no-build=libs` if changes are made only to the compiler or compiler-rt
- Add `--skip-package` to skip tarball creation

### 1.8 Testing

Under this repo `Blink` in `blink_script/example`, there is an example you can build for `ohos-aarch64`
to verify the toolchain works. Make sure to update `LLVM_HOME` in the `Makefile`
to point to your built toolchain at `$PWD/out/llvm-install`.

---

## Part 2: Building OpenHarmony Libraries

We are using OpenHarmony v5.0.0, which is similar to the closed-source version we used to collect the data.

### 2.1 Sync the Source

```bash
export BASE=~  # set this to your preferred root directory
mkdir -p $BASE/oh/system
cd $BASE/oh/system

repo init -u https://gitee.com/openharmony/manifest \
    -b refs/tags/OpenHarmony-v5.0.0-Release \
    --no-repo-verify

repo sync -c
repo forall -c 'git lfs pull'
```

### 2.2 Install Dependencies

```bash
sudo apt install -y \
  build-essential \
  git git-lfs \
  curl wget unzip zip \
  openjdk-17-jdk \
  ruby ruby-dev \
  python3 python3-pip python3-setuptools \
  gcc g++ make cmake ninja-build \
  libssl-dev libxml2-dev libz-dev libc6-dev \
  lib32ncurses-dev lib32z1-dev \
  libgl1-mesa-dev libelf-dev \
  ccache bc bison flex m4 perl gperf \
  genext2fs device-tree-compiler \
  mtd-utils e2fsprogs dosfstools \
  binutils xsltproc \
  x11proto-core-dev libx11-dev \
  apt-utils rsync cpio tzdata locales
```

### 2.3 Apply Required Patches

**Ruby OpenStruct fix** (Ruby 3.2+ removed OpenStruct from stdlib):

```bash
sudo gem install ostruct

grep -r "OpenStruct" $BASE/oh/system/arkcompiler/runtime_core/ --include="*.rb" -l | \
    xargs -I{} sed -i '2s/^/require "ostruct"\n/' {}
```

**HDF core missing cstdint include**:

```bash
sed -i '1s/^/#include <cstdint>\n/' \
    $BASE/oh/system/drivers/hdf_core/framework/tools/hdi-gen/util/options.cpp
```

### 2.4 Download Prebuilts

```bash
cd $BASE/oh/system
bash build/prebuilts_download.sh
```

### 2.5 Point Prebuilts at Your Built Toolchain

Replace the prebuilt clang and libcxx-ndk with your freshly built toolchain:

```bash
cd $BASE/oh/system/prebuilts/clang/ohos/linux-x86_64/

# Back up and replace libcxx-ndk
mv libcxx-ndk{,.bak}
tar xzf $PWD/packages/libcxx-ndk-dev-linux-x86_64.tar.gz

# Back up and replace llvm with your built toolchain
mv llvm llvm.bak
ln -s $PWD/out/install/linux-x86_64/clang-dev/ ./llvm
```

> `$PWD` here refers to your Part 1 toolchain build root (e.g. `/home/ubuntu/tools`).

### 2.6 Build the Library

```bash
cd $BASE/oh/system

./build.sh --product-name rk3568 \
    --build-target foundation/graphic/graphic_2d/rosen/modules/render_service_base:librender_service_base \
    --no-prebuilt-sdk \
    --gn-args "target_cpu=\"arm64\""

```

Output will be at:

```
./out/rk3568/graphic/graphic_2d/librender_service_base.z.so
./out/rk3568/lib.unstripped/graphic/graphic_2d/librender_service_base.z.so
```
