//===-------------- MIRInstrumentationPass.cpp ----------------------------===//
//
// Part of the LLVM Project, under the Apache License v2.0 with LLVM Exceptions.
// See https://llvm.org/LICENSE.txt for license information.
// SPDX-License-Identifier: Apache-2.0 WITH LLVM-exception
//
//===----------------------------------------------------------------------===//

#define DEBUG_TYPE "machine-ir-instrumentation"

#include "llvm/CodeGen/MIRInstrumentationPass.h"
#include "llvm/ADT/Statistic.h"
#include "llvm/CodeGen/MachineInstrBuilder.h"
#include "llvm/CodeGen/TargetInstrInfo.h"
#include "llvm/IR/Mangler.h"
#include "llvm/InitializePasses.h"
#include "llvm/Support/VirtualFileSystem.h"
#include "llvm/Target/TargetMachine.h"

using namespace llvm;

STATISTIC(NumInstrumented, "Number of machine functions instrumented");
STATISTIC(NumBlocksInstrumented, "Number of machine basic blocks instrumented");

char MIRInstrumentation::ID;
char &llvm::MIRInstrumentationID = MIRInstrumentation::ID;
INITIALIZE_PASS(MIRInstrumentation, DEBUG_TYPE,
                "Add instrumentation code to machine functions.", false, false)

cl::opt<bool> MIRInstrumentation::EnableMachineInstrumentation(
    "enable-machine-instrumentation", cl::init(false), cl::ZeroOrMore,
    cl::desc("Instrument machine ir"));
cl::opt<bool> MIRInstrumentation::EnableMachineFunctionCoverage(
    "enable-machine-function-coverage", cl::init(false), cl::ZeroOrMore,
    cl::desc("Instrument machine ir to profile function coverage only."));
cl::opt<bool> MIRInstrumentation::EnableMachineBasicBlockCoverage(
    "enable-machine-block-coverage", cl::init(false), cl::ZeroOrMore,
    cl::desc("Instrument machine ir to profile machine basic blocks."));

cl::opt<bool> MIRInstrumentation::EnableMachineBasicBlockInstrumentation(
    "enable-machine-block-instrumentation", cl::init(false), cl::ZeroOrMore,
    cl::desc("Instrument basic blocks in machine IR"));

cl::opt<bool> MIRInstrumentation::EnableMachineCallGraph(
    "enable-machine-call-graph", cl::init(false), cl::ZeroOrMore,
    cl::desc("Instrument machine ir to profile the dynamic call graph."));

cl::opt<bool> MIRInstrumentation::EnableMachineAtomicInstrumentation(
    "enable-machine-atomic-instrumentation", cl::init(false), cl::ZeroOrMore,
    cl::desc("MIR instrumentations will be atomic"));

cl::opt<bool> MIRInstrumentation::MIREntryOnly(
    "mir-entry-only", cl::init(false), cl::ZeroOrMore,
    cl::desc("Instrument entry blocks of functions only"));

cl::list<std::string> MIRInstrumentation::BlinkWhitelistFunctions(
    "blink-whitelist-functions",
    llvm::cl::desc("List of mangled function names to instrument"),
    llvm::cl::CommaSeparated, llvm::cl::ZeroOrMore,
    llvm::cl::value_desc("func1,func2,..."));

cl::list<std::string> MIRInstrumentation::BlinkBlacklistFunctions(
    "blink-blacklist-functions",
    llvm::cl::desc("List of mangled function names to instrument"),
    llvm::cl::CommaSeparated, llvm::cl::ZeroOrMore,
    llvm::cl::value_desc("func1,func2,..."));

cl::opt<std::string> MIRInstrumentation::BlinkMode(
    "blink-mode", cl::init("regular"),
    cl::desc("Used to specify Blink's mode of operation. Two options can be "
             "specified - `regular` or `dynamic`"));

cl::opt<unsigned> MIRInstrumentation::MachineProfileRuntimeBufferSize(
    "machine-profile-runtime-buffer", cl::init(0), cl::ZeroOrMore,
    cl::value_desc("RuntimeBufferSize"),
    cl::desc("Allocate a buffer of <RuntimeBufferSize> bytes to hold machine "
             "function call samples."));
cl::opt<unsigned> MIRInstrumentation::MachineProfileFunctionGroupCount(
    "machine-profile-function-group-count", cl::init(1), cl::ZeroOrMore,
    cl::value_desc("N"),
    cl::desc(
        "Partition the machine functions into <N> groups and instrument the "
        "group specified by -machine-profile-selected-function-group."));
cl::opt<unsigned> MIRInstrumentation::MachineProfileSelectedFunctionGroup(
    "machine-profile-selected-function-group", cl::init(0), cl::ZeroOrMore,
    cl::value_desc("i"),
    cl::desc("Instrument group <i>. Must be in the range [0, "
             "-fmachine-profile-function-group-count)."));
cl::opt<unsigned> MIRInstrumentation::MachineProfileMinInstructionCount(
    "machine-profile-min-instruction-count", cl::init(0), cl::ZeroOrMore,
    cl::value_desc("N"),
    cl::desc("Do not instrument machine function that have fewer than <N> "
             "machine instructions."));

// A unique ID for each instrumentation point
// Defined atomic because the execution of this pass is multi-threaded
std::atomic<unsigned> MIRInstrumentation::UniqueCodeLocationID(0);
std::string MIRInstrumentation::FunctionSCLFilename;
cl::opt<std::string, true> FunctionSCLFilenameOption(
    "machine-profile-special-case-list",
    cl::location(MIRInstrumentation::FunctionSCLFilename), cl::init(""),
    cl::ZeroOrMore, cl::value_desc("scl.txt"),
    cl::desc("Allow or block functions from being instrumented based on "
             "<scl.txt>."));

std::string MIRInstrumentation::LinkUnitName;
cl::opt<std::string, true> MIRInstrumentation::LinkUnitNameOption(
    "link-unit-name", cl::location(MIRInstrumentation::LinkUnitName),
    cl::init(""), cl::ZeroOrMore, cl::value_desc("LinkUnitName"),
    cl::desc("Use <LinkUnitName> to identify this link unit"));

bool MIRInstrumentation::doInitialization(Module &M) {
  auto &Ctx = M.getContext();
  if (EnableMachineInstrumentation) {
    ModuleFileName = M.getSourceFileName();
    if (EnableMachineFunctionCoverage == EnableMachineCallGraph)
      Ctx.emitError("Exactly one of -" + Twine(EnableMachineCallGraph.ArgStr) +
                    " or -" + Twine(EnableMachineFunctionCoverage.ArgStr) +
                    " must be provided when using -" +
                    Twine(EnableMachineInstrumentation.ArgStr) + ".");

    if (EnableMachineFunctionCoverage && MachineProfileRuntimeBufferSize)
      Ctx.emitError("Cannot set -" +
                    Twine(MachineProfileRuntimeBufferSize.ArgStr) + " when -" +
                    Twine(EnableMachineFunctionCoverage.ArgStr) +
                    " is provided.");
    if (EnableMachineBasicBlockCoverage)
      Ctx.emitError(Twine(EnableMachineBasicBlockCoverage.ArgStr) +
                    " is not supported.");
    if (MachineProfileRuntimeBufferSize)
      Ctx.emitError("-" + Twine(MachineProfileRuntimeBufferSize.ArgStr) +
                    " is not yet implemented.");

    if (!FunctionSCLFilename.empty())
      SCL = SpecialCaseList::createOrDie({FunctionSCLFilename},
                                         *vfs::getRealFileSystem());
  }
  return false;
}

bool MIRInstrumentation::doFinalization(Module &M) {
  printMIPCodeInfoMapping();
  MIRCodeLocationMapping.clear();
  return true;
}

void MIRInstrumentation::addCodeInfoToMap(MachineFunction &MF,
                                          const DebugLoc &DL,
                                          unsigned UniqueCodeID) {
  SmallVector<std::string, 8> CodeInfo;
  StringRef FunctionName = MF.getName();
  unsigned LineNumber = 0;
  StringRef FileName("");
  if (DL && DL.get()) {
    LineNumber = DL.getLine();
  }
  if (const DILocation *DIL = DL.get()) {
    FileName = DL.get()->getFilename();
  }
  CodeInfo.push_back(FunctionName.str());
  CodeInfo.push_back(FileName.str());
  CodeInfo.push_back(std::to_string(LineNumber));
  MIRCodeLocationMapping[UniqueCodeID] = CodeInfo;
}

void MIRInstrumentation::printMIPCodeInfoMapping() {
  std::error_code EC;
  raw_fd_ostream OutFile("./MIPCodeInfo/MIPCodeInfo-" +
                             std::to_string(hash_value(ModuleFileName)) +
                             ".csv",
                         EC, llvm::sys::fs::OF_None);
  if (EC) {
    errs() << "Failed to open file: ./MIPCodeInfo/MIPCodeInfo-"
           << std::to_string(hash_value(ModuleFileName)) << ".csv" << "\n";
  }
  for (const auto &pair : MIRCodeLocationMapping) {
    if (!EC)
      OutFile << pair.first << ",";
    LLVM_DEBUG(dbgs() << "UniqueCodeID: " << pair.first << ",");
    for (auto item : pair.second) {
      if (!EC)
        OutFile << item << ",";
      LLVM_DEBUG(dbgs() << "SourceLocation: " << item << ",");
    }
    if (!EC)
      OutFile << "\n";
    LLVM_DEBUG(dbgs() << "\n");
  }
  if (!EC)
    OutFile.close();
}

bool MIRInstrumentation::bbContainsPthreadExit(MachineBasicBlock &MBB) {
  for (auto &MBBI : MBB) {
    if (!MBBI.isCall())
      continue;

    for (auto &MO : MBBI.operands()) {
      if (!MO.isGlobal())
        continue;
      const GlobalValue *GV = MO.getGlobal();
      if (const Function *F = dyn_cast<Function>(GV))
        return (F->getName() == "pthread_exit");
    }
  }
  return false;
}

MachineInstr *MIRInstrumentation::bbContainsReturn(MachineBasicBlock &MBB) {
  for (auto &MBBI : MBB) {
    if (MBBI.isReturn())
      return (&MBBI);
  }
  return nullptr;
}

bool MIRInstrumentation::runOnMachineFunction(MachineFunction &MF) {
  if (!shouldInstrumentMachineFunction(MF))
    return false;

  SmallVector<MachineBasicBlock *, 4> MBBs;
  getMachineBasicBlocks(MF, MBBs);
  if (MBBs.empty()) {
    LLVM_DEBUG(dbgs() << MF.getName() << " has zero non-debug blocks");
    return false;
  }

  LLVM_DEBUG(dbgs() << "Blink: Instrumenting MIR of " << MF.getName());

  auto &EntryBlock = *MBBs[0];
  const auto &TII = *MF.getSubtarget().getInstrInfo();
  auto MBBI = EntryBlock.begin();
  const auto &DL = MBBI->getDebugLoc();

  // Count number of exit basic blocks in this function
  // A basic block containing the return instruction is treated as an exit basic
  // block
  unsigned ExitBasicBlockCount = 0;
  if (!MIREntryOnly) {
    for (uint32_t BlockID = 0; BlockID < MBBs.size(); BlockID++) {
      auto &MBB = *MBBs[BlockID];
      MachineInstr *RetInstr = bbContainsReturn(MBB);
      if (RetInstr) {
        ExitBasicBlockCount++;
      }
    }
  }

  // Add an MIR instrumentation to mark this function for instrumentation
  BuildMI(EntryBlock, MBBI, DL,
          TII.get(TargetOpcode::MIP_FUNCTION_INSTRUMENTATION_MARKER))
      .addImm(getControlFlowGraphSignature(MBBs))
      .addImm(ExitBasicBlockCount);
  ++NumInstrumented;

  if (EnableMachineCallGraph) {

    unsigned UniqueCodeID = ++UniqueCodeLocationID;

    // Instrument entry
    BuildMI(EntryBlock, MBBI, DL,
            TII.get(TargetOpcode::MIP_INSTRUMENTATION))
        .addReg(TII.getTemporaryMachineProfileRegister(EntryBlock))
        .addImm(UniqueCodeID)
        .addExternalSymbol(
            "__custom_instrumentation") // Name of tracing function
        .addImm(
            0) // Flag to specify whether instrumentation is for an exit block
        .addImm(BlinkMode == "dynamic");

    addCodeInfoToMap(MF, DL, UniqueCodeID);

    if (!MIREntryOnly) {
      unsigned ExitBlockID = 0;
      for (uint32_t BlockID = 0; BlockID < MBBs.size(); BlockID++) {
        auto &MBB = *MBBs[BlockID];
        // Exit Basic Block
        MachineInstr *RetInstr = bbContainsReturn(MBB);
        if (RetInstr) {
          auto MBBIReturn = RetInstr;
          const auto &DLReturn = MBBIReturn->getDebugLoc();

          unsigned UniqueCodeID = ++UniqueCodeLocationID;

          // This instruction is used to track exit block offset from function
          // start This offset is stored in a global table in a row
          // corresponding to this function At runtime, this table is read and
          // the offset is used to figure out where the instrumented
          // instructions at exit are located to perform binary rewriting.
          BuildMI(
              MBB, MBBIReturn, DLReturn,
              TII.get(TargetOpcode::MIP_BASIC_BLOCK_COVERAGE_INSTRUMENTATION))
              .addImm(TII.getTemporaryMachineProfileRegister(MBB))
              .addImm(ExitBlockID);
          ExitBlockID++;

          // Instrument Exit
          BuildMI(MBB, MBBIReturn, DLReturn,
                  TII.get(TargetOpcode::MIP_INSTRUMENTATION))
              .addReg(TII.getTemporaryMachineProfileRegister(MBB))
              .addImm(UniqueCodeID)
              .addExternalSymbol(
                  "__custom_instrumentation") // Name of tracing function
              .addImm(1) // Flag to specify whether instrumentation is for an
                         // exit block
              .addImm(BlinkMode == "dynamic");
          addCodeInfoToMap(MF, DLReturn, UniqueCodeID);
        }
      }
    }
  } else {
    llvm_unreachable(
        "Expected function coverage or call graph instrumentation.");
  }
  return true;
}

void MIRInstrumentation::runOnMachineBasicBlock(MachineBasicBlock &MBB,
                                                uint32_t BlockID) {
  const auto &MF = *MBB.getParent();
  const auto &TII = *MF.getSubtarget().getInstrInfo();
  auto MBBI = MBB.begin();
  const auto &DL = MBBI->getDebugLoc();

  if (EnableMachineBasicBlockCoverage)
    BuildMI(MBB, MBBI, DL,
            TII.get(TargetOpcode::MIP_BASIC_BLOCK_COVERAGE_INSTRUMENTATION))
        .addReg(TII.getTemporaryMachineProfileRegister(MBB))
        .addImm(BlockID);
  else if (EnableMachineBasicBlockInstrumentation)
    BuildMI(MBB, MBBI, DL,
            TII.get(TargetOpcode::MIP_BASIC_BLOCK_INSTRUMENTATION))
        .addReg(TII.getTemporaryMachineProfileRegister(MBB))
        .addImm(BlockID)
        .addImm(EnableMachineAtomicInstrumentation);
  else
    llvm_unreachable("Basic Block Instrumentation type not specified");
  ++NumBlocksInstrumented;
}

static bool isInList(const llvm::cl::list<std::string> &list,
                     const std::string &functionName) {
  return std::find(list.begin(), list.end(), functionName) != list.end();
}

bool MIRInstrumentation::shouldInstrumentMachineFunction(
    const MachineFunction &MF) const {
  auto &F = MF.getFunction();
  auto Name = MF.getName();

  if (MF.empty() || Name.empty())
    return false;

  if (Name.startswith("OUTLINED_FUNCTION_"))
    return false;

  if (F.getCallingConv() == CallingConv::CXX_FAST_TLS)
    return false;

  if (F.hasFnAttribute(Attribute::Naked))
    return false;

  if (MF.getInstructionCount() < MachineProfileMinInstructionCount)
    return false;

  if (MachineProfileFunctionGroupCount > 1) {
    unsigned Group = MD5Hash(Name) % MachineProfileFunctionGroupCount;
    if (Group != MachineProfileSelectedFunctionGroup)
      return false;
  }

  if (SCL) {
    if (SCL->inSection("mip", "fun", Name, "block"))
      return false;
  }

  // If a function is both whitelisted and blacklisted,
  // it will not be instrumented, i.e., blacklist takes priority
  if (!BlinkBlacklistFunctions.empty()) {
    if (isInList(BlinkBlacklistFunctions, Name.str()))
      return false;
  }

  if (!BlinkWhitelistFunctions.empty()) {
    if (!isInList(BlinkWhitelistFunctions, Name.str()))
      return false;
  }

  return true;
}

void MIRInstrumentation::getMachineBasicBlocks(
    MachineFunction &MF, SmallVectorImpl<MachineBasicBlock *> &MBBs) const {
  auto ShouldSkipBlock = [](const MachineBasicBlock &MBB) {
    return MBB.empty() || MBB.getFirstNonDebugInstr() == MBB.end();
  };

  for (auto &MBB : MF) {
    if (!ShouldSkipBlock(MBB))
      MBBs.push_back(&MBB);
  }
}

uint32_t MIRInstrumentation::getControlFlowGraphSignature(
    SmallVectorImpl<MachineBasicBlock *> &MBBs) const {
  if (MBBs.size() <= 1)
    return 0;

  DenseMap<const MachineBasicBlock *, uint32_t> BlockToID;
  uint32_t ID = 0;
  for (auto *MBB : MBBs)
    BlockToID[MBB] = ID++;

  std::string AdjacencyList;
  raw_string_ostream OS(AdjacencyList);
  for (auto *MBB : MBBs) {
    OS << "{";
    for (auto *Succ : MBB->successors())
      OS << BlockToID[Succ] << ";";
    OS << "}";
  }

  return MD5Hash(OS.str());
}
