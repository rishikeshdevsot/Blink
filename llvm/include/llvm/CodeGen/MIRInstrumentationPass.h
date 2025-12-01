//===-------------- MIRInstrumentationPass.h ------------------------------===//
//
// Part of the LLVM Project, under the Apache License v2.0 with LLVM Exceptions.
// See https://llvm.org/LICENSE.txt for license information.
// SPDX-License-Identifier: Apache-2.0 WITH LLVM-exception
//
//===----------------------------------------------------------------------===//

#ifndef LLVM_CODEGEN_MIRINSTRUMENTATIONPASS_H
#define LLVM_CODEGEN_MIRINSTRUMENTATIONPASS_H

#include "llvm/ADT/SmallVector.h"
#include "llvm/CodeGen/MachineFunctionPass.h"
#include "llvm/Support/CommandLine.h"
#include "llvm/Support/SpecialCaseList.h"
#include <sstream>

namespace llvm {

class MIRInstrumentation : public MachineFunctionPass {
public:
  static char ID;
  MIRInstrumentation() : MachineFunctionPass(ID) {}

  static cl::opt<bool> EnableMachineInstrumentation;
  static cl::opt<bool> EnableMachineFunctionCoverage;
  static cl::opt<bool> EnableMachineBasicBlockCoverage;
  static cl::opt<bool> EnableMachineBasicBlockInstrumentation;
  static cl::opt<bool> EnableMachineCallGraph;
  static cl::opt<bool> EnableMachineAtomicInstrumentation;
  static cl::opt<unsigned> MachineProfileRuntimeBufferSize;
  static cl::opt<unsigned> MachineProfileFunctionGroupCount;
  static cl::opt<unsigned> MachineProfileSelectedFunctionGroup;
  static cl::opt<unsigned> MachineProfileMinInstructionCount;
  static std::string FunctionSCLFilename;
  static cl::opt<std::string, true> FunctionSCLFilenameOption;
  static std::string LinkUnitName;
  static cl::opt<std::string, true> LinkUnitNameOption;
  static cl::opt<std::string> BlinkWhitelistFile;
  static cl::list<std::string> BlinkBlacklistFunctions;
  static cl::list<std::string> BlinkWhitelistFunctions;
  static cl::opt<std::string> BlinkMode;

  static cl::opt<bool> MIREntryOnly;

private:
  StringRef getPassName() const override {
    return "Add instrumentation code to machine functions.";
  }

  void getAnalysisUsage(AnalysisUsage &AU) const override {
    AU.setPreservesCFG();
    MachineFunctionPass::getAnalysisUsage(AU);
  }

  static std::atomic<unsigned> UniqueCodeLocationID;
  DenseMap<unsigned, SmallVector<std::string, 8>> MIRCodeLocationMapping;
  StringRef ModuleFileName;

  void addCodeInfoToMap(MachineFunction &MF, const DebugLoc &DL,
                        unsigned UniqueID);
  bool doInitialization(Module &M) override;
  bool doFinalization(Module &M) override;
  bool shouldInstrumentMachineFunction(const MachineFunction &MF) const;
  bool runOnMachineFunction(MachineFunction &MF) override;
  bool bbContainsPthreadExit(MachineBasicBlock &MBB);
  MachineInstr *bbContainsReturn(MachineBasicBlock &MBB);
  MachineInstr *bbContainsCall(MachineBasicBlock &MBB,
                               const TargetInstrInfo &TII);
  uint32_t getControlFlowGraphSignature(
      SmallVectorImpl<MachineBasicBlock *> &MBBs) const;
  void getMachineBasicBlocks(MachineFunction &MF,
                             SmallVectorImpl<MachineBasicBlock *> &MBBs) const;
  void runOnMachineBasicBlock(MachineBasicBlock &MBB, uint32_t BlockID);

  void printMIPCodeInfoMapping();
  std::string getMangledName(const Function *F) const;

  std::unique_ptr<SpecialCaseList> SCL;
};
} // namespace llvm

#endif // LLVM_CODEGEN_MIRINSTRUMENTATIONPASS_H
