#!/bin/bash
set -euo pipefail

TOOLS_ROOT="${TOOLS_ROOT:-/home/builder/tools}"
BLINK_SOURCE="/home/builder/blink-source"
LLVM_PROJECT="${TOOLS_ROOT}/toolchain/llvm-project"

echo "=== Part 1: Building the Compiler (LLVM Toolchain) ==="
echo "TOOLS_ROOT:    ${TOOLS_ROOT}"
echo "Blink source:  ${BLINK_SOURCE}"
echo ""

# ── 1.2 Initialize the repository ──────────────────────────────────────────

# Check for a completed sync by looking for the toolchain directory.
# .repo alone isn't sufficient — a partial/failed sync leaves .repo behind.
if [ ! -d "${TOOLS_ROOT}/toolchain" ]; then
    echo ">>> Step 1.2: Initializing OpenHarmony repository..."
    cd "${TOOLS_ROOT}"
    repo init -u https://gitcode.com/OpenHarmony/manifest.git \
        -b master \
        -m llvm-toolchain.xml
    repo sync -c
    repo forall -c 'git lfs pull'
    echo "<<< Step 1.2: Repository initialized."
else
    echo ">>> Step 1.2: Repository already synced, skipping."
fi

# ── 1.3 Set up the project ─────────────────────────────────────────────────

echo ">>> Step 1.3: Setting up Blink as llvm-project..."

# Verify the mounted Blink directory exists
if [ ! -d "${BLINK_SOURCE}" ]; then
    echo "ERROR: Blink source directory not found at ${BLINK_SOURCE}"
    echo "Make sure you mount it: -v /path/to/Blink:${BLINK_SOURCE}"
    exit 1
fi

# If repo sync created llvm-project, back it up
if [ -d "${LLVM_PROJECT}" ] && [ ! -d "${LLVM_PROJECT}-old" ]; then
    mv "${LLVM_PROJECT}" "${LLVM_PROJECT}-old"
fi

# Ensure the parent directory exists
mkdir -p "$(dirname "${LLVM_PROJECT}")"

# Symlink the mounted Blink source into place
ln -sfn "${BLINK_SOURCE}" "${LLVM_PROJECT}"

echo "<<< Step 1.3: Blink symlinked to ${LLVM_PROJECT}"

# ── 1.4 Install prebuilt dependencies ──────────────────────────────────────

# env_prepare.sh downloads cmake, python3, build-tools, and clang prebuilts.
# Check for the cmake prebuilt as a proxy for "env_prepare completed successfully".
if [ ! -d "${TOOLS_ROOT}/prebuilts/cmake/linux-x86" ]; then
    echo ">>> Step 1.4: Installing prebuilt dependencies..."
    cd "${TOOLS_ROOT}"
    bash toolchain/llvm-project/llvm-build/env_prepare.sh
    echo "<<< Step 1.4: Prebuilts installed."
else
    echo ">>> Step 1.4: Prebuilts already present, skipping."
fi

# ── 1.5 Patch Python shebangs ──────────────────────────────────────────────────

echo ">>> Step 1.5: Patching Python shebangs to call python3..."
# Patch the build/ directory
find "${TOOLS_ROOT}/build" -name '*.py' 2>/dev/null | xargs -IOUT sed -i 's:#!/usr/bin/env python:#!/usr/bin/env python3:' OUT
find "${TOOLS_ROOT}/build" -name '*.py' 2>/dev/null | xargs -IOUT sed -i 's:#!/usr/bin/env python33:#!/usr/bin/env python3:' OUT
# Also ensure 'python' is available (musl build scripts use #!/usr/bin/env python)
if [ ! -e /usr/bin/python ]; then
    ln -sf /usr/bin/python3 /usr/bin/python
fi
echo "<<< Step 1.5: Python shebangs patched."

# ── 1.6 Build the toolchain ────────────────────────────────────────────────

echo ">>> Step 1.6: Building LLVM toolchain (AArch64 only)..."
echo "    This is the longest step — expect ~1 hour on 16+ cores."

cd "${TOOLS_ROOT}"
PATH="${TOOLS_ROOT}/prebuilts/python3/linux-x86/3.11.4/bin/:${TOOLS_ROOT}/prebuilts/build-tools/linux-x86/bin/:${PATH}" \
python3 ./toolchain/llvm-project/llvm-build/build.py \
    --host-build-projects clang,lld,clang-tools-extra,openmp \
    --no-build-riscv64 --no-build-mipsel --no-build-loongarch64 \
    --no-build-arm \
    --no-build lldb-server,windows \
    --compression-format gz

echo "<<< Step 1.6: Toolchain build complete."

# ── 1.7 Build musl libc for target architectures ────────────────────────────

# The main toolchain build only installs musl headers. The musl C library
# (libc.so, CRT objects, etc.) is needed for linking programs targeting
# aarch64-linux-ohos and x86_64-linux-ohos.
if [ ! -f "${TOOLS_ROOT}/out/sysroot/aarch64-linux-ohos/usr/lib/libc.so" ]; then
    echo ">>> Step 1.7: Building musl libc for target architectures..."
    cd "${TOOLS_ROOT}"
    PATH="${TOOLS_ROOT}/prebuilts/python3/linux-x86/3.11.4/bin/:${TOOLS_ROOT}/prebuilts/build-tools/linux-x86/bin/:${PATH}" \
    python3 ./toolchain/llvm-project/llvm-build/build.py \
        --build-only musl \
        --no-build-riscv64 --no-build-mipsel --no-build-loongarch64 \
        --no-build-arm
    echo "<<< Step 1.7: Musl libc built."
else
    echo ">>> Step 1.7: Musl libc already present, skipping."
fi

# ── 1.8 Install aarch64 target runtime libraries ────────────────────────────

# The build.py install step does not copy all runtime libraries needed for
# cross-compiling to aarch64-linux-ohos. We need:
#   - libc++ and libc++abi (C++ standard library)
#   - __config_site (libc++ target-specific configuration)
# These are available from the build output and prebuilts.
INSTALL_LIB="${TOOLS_ROOT}/out/llvm-install/lib/aarch64-linux-ohos"
INSTALL_INC="${TOOLS_ROOT}/out/llvm-install/include/aarch64-linux-ohos/c++/v1"
PREBUILT_LIB="${TOOLS_ROOT}/prebuilts/clang/ohos/linux-x86_64/clang-15.0.4/lib/aarch64-linux-ohos"
MUSL_OUT="${TOOLS_ROOT}/out/lib/libunwind-libcxxabi-libcxx-aarch64-linux-ohos"

if [ ! -f "${INSTALL_LIB}/libc++abi.a" ]; then
    echo ">>> Step 1.8: Installing aarch64 target runtime libraries..."
    mkdir -p "${INSTALL_LIB}"
    mkdir -p "${INSTALL_INC}"

    # libc++abi from the build output
    cp -v "${MUSL_OUT}/lib/aarch64-linux-ohos/libc++abi.a" "${INSTALL_LIB}/"

    # libc++ from prebuilts (the build doesn't produce aarch64 libc++)
    cp -v "${PREBUILT_LIB}/libc++.a" "${INSTALL_LIB}/"
    cp -v "${PREBUILT_LIB}/libc++.so" "${INSTALL_LIB}/"

    # __config_site for aarch64 C++ headers
    cp -v "${MUSL_OUT}/include/aarch64-linux-ohos/c++/v1/__config_site" "${INSTALL_INC}/"

    echo "<<< Step 1.8: Target runtime libraries installed."
else
    echo ">>> Step 1.8: Target runtime libraries already present, skipping."
fi

# ── Done ────────────────────────────────────────────────────────────────────

echo ""
echo "=== Build complete! ==="
echo "Toolchain output: ${TOOLS_ROOT}/out/llvm-install"
