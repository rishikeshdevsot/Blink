# artifact instructions
this guide uses the existing build instructions  `/llvm-build/README.md`
## Building the compiler

required dependencies (assuming on ubuntu)
```
build-essential
swig
python3-dev
libedit-dev \
libncurses5-dev \
binutils-dev \
gcc-multilib abigail-tools elfutils pkg-config autoconf autoconf-archive \
```

`$PWD` refers be the root build directory, for example `/home/ubuntu/tool`

rename the current project `Blink` (a fork of llvm) to `llvm-project`
and put in under the following directory (create directories if necessary)

```
# llvm-project is the current project
$PWD/toolchain/llvm-project
```


initialize the rest of the dependencies (about 1h of downloading)
```
repo init -u https://gitcode.com/OpenHarmony/manifest.git -b master -m llvm-toolchain.xml
repo sync -c 
repo forall -c 'git lfs pull'
```


Patch all python3 scripts in build to call python3
```
find $PWD/build -name '*.py' | xargs -IOUT sed -i 's:#!/usr/bin/env python:#!/usr/bin/env python3:' OUT
find $PWD/build -name '*.py' | xargs -IOUT sed -i 's:#!/usr/bin/env python33:#!/usr/bin/env python3:' OUT
```

build clang and the toolchain for arm (about 2h)
```
PATH=$PWD/prebuilts/python3/linux-x86/3.11.4/bin/:$PWD/prebuilts/build-tools/linux-x86/bin/:$PATH \
python3 ./toolchain/llvm-project/llvm-build/build.py \
    --host-build-projects clang,lld,clang-tools-extra,openmp \
    --no-build-riscv64 --no-build-mipsel --no-build-loongarch64 \
    --no-build-arm \
    --no-build lldb-server,windows \
    --no-build
    --skip-package \
```

built toolchain will be in `$PWD/out/llvm-install`

under the `Blink` in `./example`, there is an `example` you can build for ohos-aarch64 to check if the toolchain works.
make sure to overwrite the `LLVM_HOME` in the `Makefile` to point to your built toolchain

## Building librender (or any library for OHOS)
