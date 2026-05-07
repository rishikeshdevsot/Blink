# Building OpenHarmony Libraries

We are using OpenHarmony v5.0.0, which is similar to the closed-source version we used to collect the data.

### Sync the Source

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

### Install Dependencies

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

### Apply Required Patches

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

### Download Prebuilts

```bash
cd $BASE/oh/system
bash build/prebuilts_download.sh
```

### Point Prebuilts at Your Built Toolchain

Replace the prebuilt clang and libcxx-ndk with your freshly built toolchain:
> `$TOOLS` here refers to your Part 1 toolchain build root (e.g. `/home/ubuntu/tools`).

```bash
cd $BASE/oh/system/prebuilts/clang/ohos/linux-x86_64/

# Back up and replace libcxx-ndk
mv libcxx-ndk{,.bak}
tar xzf $TOOLS/packages/libcxx-ndk-dev-linux-x86_64.tar.gz

# Back up and replace llvm with your built toolchain
mv llvm llvm.bak
ln -s $TOOLS/out/install/linux-x86_64/clang-dev/ ./llvm
```


###  Force AArch64 Target

The rk3568 product config hardcodes target_cpu as arm (32-bit). Patch it to arm64 before building:
```bash
sed -i 's/"target_cpu": "arm"/"target_cpu": "arm64"/' \
    $BASE/oh/system/vendor/hihope/rk3568/config.json
```

# Verify
grep target_cpu $BASE/oh/system/vendor/hihope/rk3568/config.json

### Enable Patch
1. Disable compiler warnings:
```bash
sed -i 's/fatal_linker_warnings = true/fatal_linker_warnings = false/' \
    $BASE/oh/system/build/config/compiler/BUILD.gn
```

2. Add the flags to the linker when building render_service
```bash
cd $BASE/oh/system/foundation/graphic/graphic_2d
patch -p1 < $TOOLS/toolchain/llvm-project/patches/render_service_base_blink.patch
```
### Build the Library

```bash
cd $BASE/oh/system
# create a folder to hold to instrumentation location mappings
mkdir -p out/rk3568/MIPCodeInfo/
./build.sh --product-name rk3568 \
    --build-target foundation/graphic/graphic_2d/rosen/modules/render_service_base:librender_service_base \
    --no-prebuilt-sdk
```

Output will be at:

```
./out/rk3568/graphic/graphic_2d/librender_service_base.z.so
./out/rk3568/lib.unstripped/graphic/graphic_2d/librender_service_base.z.so
```
verify its 64-bit (aarch64) with `file`
remove `output`

