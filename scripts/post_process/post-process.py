import csv
import glob
import argparse
import os
import re
import subprocess
import logging
from collections import defaultdict
from tqdm import tqdm

from pmu_filter import *
from statistics import median

from scipy import stats
import numpy as np

DEBUG = False

def demangle(name):
    result = subprocess.run(['c++filt', name], stdout=subprocess.PIPE, text=True)
    return result.stdout.strip()

def filter_outlier(durs):
    """
    DISABLED
    outliers can happen when sampling is enabled.
    if sampling is
        - disabled just before exit of a function X call #Y
        - enabled just before a function X call #Y+N
    then it could happen that there is no gap seen...
    <Y.ENTRY, #Y>
    (...) instrumentation paused
    <Y.EXIT, #Y+N>
    """
    zscores = np.abs(stats.zscore(durs))
    # print(zscores)
    result = []
    for z, d in zip(zscores, durs):
        if z < 3:
            result.append(d)
    # print(len(durs), len(result))
    # return result
    return durs

def validate(filtered_events):
    """
    Validates each filtered_events[path] = [(fid, name, val), ...] according to:
      0) Dumps the full filtered sequences to debug/<basename>.filtered_events.csv if DEBUG.
      1) Checks for any sample value ≤ 0; logs and dumps those to debug/invalid_samples.csv if DEBUG.
      2) Verifies that within each file the PMU values never decrease.
    Returns True if both checks pass, False otherwise.
    """
    ok = True

    # 0) Dump full filtered sequences for inspection
    if DEBUG:
        os.makedirs("debug", exist_ok=True)
        for path, seq in filtered_events.items():
            base = os.path.splitext(os.path.basename(path))[0]
            dump_path = os.path.join("debug", f"{base}.filtered_events.csv")
            with open(dump_path, "w", newline="") as csvfile:
                writer = csv.writer(csvfile)
                writer.writerow(["fid", "name", "val"])
                for fid, name, val in seq:
                    writer.writerow([fid, name, val])

    # 1) Check for invalid sample values (≤ 0)
    invalid_map = {}
    for path, seq in filtered_events.items():
        invalid = [(fid, name, val) for fid, name, val in seq if val <= 0]
        if invalid:
            print(f"ERROR: {len(invalid)} invalid sample(s) in {path} (≤ 0)")
            invalid_map[path] = invalid
            ok = False

    # 2) PMU‑stream monotonicity per file
    for path, seq in filtered_events.items():
        prev_val = None
        for idx, (_, _, val) in enumerate(seq):
            if prev_val is not None and val < prev_val:
                print(f"ERROR: non‑monotonic PMU stream in {path} at idx {idx}: {val} < {prev_val}")
                ok = False
                break
            prev_val = val

    print("✅ Validation passed" if ok else "❌ Validation failed")
    return ok



def prefilter_all(pmu_dir, id_map, valid_funcs):
    """
    Read each thread_*.csv, apply filter_glitches, and collect
    filtered_events[path] = [(fid,name,val), ...]
    """
    filtered_events = {}
    total_raw, total_filt = 0, 0
    pct = 0

    for path in tqdm(sorted(glob.glob(os.path.join(pmu_dir, "*.csv"))),
                     desc="Prefiltering glitches"):
        # load raw
        raw = []
        with open(path, newline="") as f:
            for row in csv.reader(f):
                if len(row) < 2 or not row[0].isdigit():
                    continue
                fid, val = int(row[0]), int(row[1])
                name = id_map.get(fid)[0]
                if name in valid_funcs:
                    raw.append((fid, name, val))

        # print(len(raw))
        # filtering

        raw_overlap = detect_and_apply_wrap(raw, window=10, wrap_max=0xFFFFFFFF)
        filt, r_cnt, f_cnt, _ = filter_glitches(raw_overlap, debug=DEBUG, src_path=path)

        filtered_events[path] = raw_overlap
        total_raw  += r_cnt
        total_filt += f_cnt

        if DEBUG and r_cnt:
            pct = f_cnt / r_cnt * 100
            print(f"[DEBUG] {os.path.basename(path)} filtered {f_cnt}/{r_cnt} ({pct:.1f}%)")

    if total_raw:
        pct = total_filt / total_raw * 100
        print(f"Overall filtered {total_filt}/{total_raw} ({pct:.1f}%)")

    # abort if over 60% of data are filtered
    # if pct > 60:
    #     return []

    return filtered_events


def filter_events(pmu_dir, mip_dir):
    """
    High‑level wrapper that:
      1) builds fid→func map
      2) prefilters all PMU files
    Returns filtered_events_map.
    """
    id_map, valid_funcs = build_id_map(mip_dir, DEBUG)
    filtered_events = prefilter_all(pmu_dir, id_map, valid_funcs)

    return filtered_events, id_map

def sort_by_seq(x):
    path = x[0]
    res = re.search(r'.*_(\d+)_(\d+).csv', path)
    seq = int(res.group(2))
    return seq

def combine_by_tid(events_map):
    tid_events_map = {}
    for path, filt in events_map.items():
        res = re.search(r'.*_(\d+)_(\d+).csv', path)
        tid = int(res.group(1))
        old_list = tid_events_map.get(tid, None)
        if not old_list:
            old_list = []
            tid_events_map[tid] = old_list
        old_list.append((path, filt))

    for tid, events in tid_events_map.items():
        events.sort(key=sort_by_seq)
        seq_last = re.search(r'.*_(\d+)_(\d+).csv', events[-1][0]).group(2)
        seq_last = int(seq_last)
        seq_start = re.search(r'.*_(\d+)_(\d+).csv', events[0][0]).group(2)
        seq_start = int(seq_start)
        # print('seq_last =', seq_last)
        # print('event_len = ', len(events))
        assert len(events) == (seq_last - seq_start + 1)

    return tid_events_map

# Algorithm for deriving event count for each function
def process_events(events_map, id_map, compute_self):
    """
    Stack-based self-time over prefiltered events_map:
      events_map[path] = [(fid,name,val),...]

    Robust pairing of entries and exits:
    - If an exit matches an entry not on top of the stack, discard intermediate frames.
    - Supports recursion/fault by resetting the top frame.

    Returns:
      durations:    dict func_name -> list of self-time durations
      event_counts: dict func_name -> total entry count
      last_exit:    dict func_name -> list of exit values
      leftover:     dict path -> leftover stack
    """
    durations    = defaultdict(list)
    event_counts = defaultdict(int)
    num_children = defaultdict(list)
    last_exit    = defaultdict(list)
    call_sites   = defaultdict(list)
    leftover     = {}
    failure = []

    # Precompute, for each function name, the minimal fid we consider as "entry"
    min_fid = {}
    for fid, name in id_map.items():
            if name not in min_fid or fid < min_fid[name]:
                min_fid[name] = fid

    total_count = 0
    pattern = r'.*_(\d+)_(\d+)\.csv'

    '''
    {'tid':
        [(path1, filt1), (path2, filt2), (path3, filt3)]  # sorted by seq
    }
    '''
    sorted_events_map = combine_by_tid(events_map)
    start_end_values = {}
    for tid, events in tqdm(sorted_events_map.items()):
        leftover[tid] = []
        consecutive_sucess = 0
        for path, filt in tqdm(events, desc="Processing events"):
            stack = leftover[tid]
            start_end_values[path] = [filt[0][2], filt[-1][2]]

            # for fid, name, val in tqdm(filt, desc=f"processing file path: {path}"):
            for i, (fid, name, val) in enumerate(filt):
                event_counts[name] += 1
                fail = False
                # print(path, fid, name, val, 'stack=', stack)
                # if fid is an entry put it on stack waiting
                _, expected_entry_fid, fid_type = id_map[fid]
                if fid_type == FIDType.ENTRY or \
                    fid_type == FIDType.CALL_ENTRY:
                    # print("push ", fid)
                    stack.append([fid, name, val, 0, 0])
                elif len(stack) == 0:
                    fail = True
                else:
                    found_matching = False
                    while not found_matching and len(stack) > 0:
                        popped = stack.pop()
                        popped_fid, popped_name, popped_val, popped_child_sum, popped_num_children = popped
                        if popped_fid == expected_entry_fid:
                            assert popped_fid != fid
                            assert popped_name == name
                            found_matching = True
                            total_dur = val - popped_val
                            self_time = total_dur - popped_child_sum
                            if fid_type == FIDType.CALL_EXIT:
                                call_sites[popped_name].append(self_time)
                                durations['callee'].append(self_time)
                            else: # fid_type == FIDType.CALL
                                durations[popped_name].append(self_time)
                            num_children[popped_name].append(popped_num_children)
                            last_exit[popped_name].append(popped_val)
                            if compute_self and len(stack) > 0:
                                # increase the popped_child_sum
                                stack[-1][3] += total_dur
                            # parent gets all the grandchildren + himself
                            if len(stack) > 0:
                                stack[-1][4] += popped_num_children + 1
                    if found_matching == False:
                        fail = True
                if fail:
                    print("FAIL!", fid, consecutive_sucess)
                    failure.append((path,i , fid, name, stack[:]))
                    consecutive_sucess = 0
                else:
                    consecutive_sucess += 1
            # print(f"failure, cumulative {len(failure)}" )
            # runtime checking: check exit > entry
            # if DEBUG and (total_dur <= 0 or self_time <= 0) :
            #     print(f"ERROR: function {name} in {path} executes for less than 0 event counts. total_dur = {total_dur}, self_time = {self_time}")
            #     stack.append(popped)
            #     continue

            # durations[popped_name].append(self_time)
            # last_exit[popped_name].append(popped_val)
            # # total_count += 1
            # if total_count % 100000 == 0:
                # print(total_count)
            # bubble up to parent
            # if stack:
                # stack[-1][3] += total_dur
            # continue



    return durations, call_sites, event_counts, last_exit, leftover, failure, num_children, start_end_values


def main():
    parser = argparse.ArgumentParser(description="Compute PMU self-time per function.")
    parser.add_argument("--mip_dir", default="MIPCodeInfo")
    parser.add_argument("--pmu_dir", default="pmu")
    parser.add_argument("--compute_self", action="store_true")
    parser.add_argument("--debug",  action="store_true")
    args = parser.parse_args()

    # set global DEBUG
    global DEBUG
    DEBUG = args.debug

    logging.basicConfig(level=logging.DEBUG if DEBUG else logging.INFO)

    # 1) Filtering
    events_map, id_map = filter_events(
        pmu_dir=args.pmu_dir,
        mip_dir=args.mip_dir
    )

    if events_map == []:
        print("Aborting due to not enough valid sample data, please rerun Blink to collect more data!")
        return

    # 2) Validation
    if not validate(events_map):
        print("Aborting due to validation failure.")
        return

    # 3) Self-time processing
    # print(events_map)
    durations, call_sites, evc, le, lo, failure, nchildren, start_end_values = \
        process_events(events_map, id_map, args.compute_self)

    # 4) Write outputs
    os.makedirs("data", exist_ok=True)
    with open("data/failure.csv", "w") as f:
        w = csv.writer(f)
        # w.writerow(['fid', ])
        for fail in failure:
            w.writerow(list(fail))

    with open("data/leftover.csv", "w") as f:
        w = csv.writer(f)
        for tid, stack in lo.items():
            for e in stack:
                o = [tid]
                o.extend(e)
                w.writerow(o)

    with open("data/output.csv","w") as f:
        w = csv.writer(f)
        for name, durs in durations.items():
            w.writerow([name] + durs)

    with open("data/summary.csv","w",) as f:
        w = csv.writer(f)
        w.writerow(["mangled","demangled","avg_event_counts","count","total_event_counts", "nchildrens", "total_callsite_event", "total_callsite_n"])
        for name, durs in durations.items():
            filtered_durs = filter_outlier(durs)
            cnt = len(filtered_durs)
            tot = sum(filtered_durs)
            med =  median(filtered_durs) if cnt else 0
            nchildrens_val = sum(nchildren.get(name, []))
            total_callsite_event = sum(call_sites.get(name, []))
            total_callsite_n = len(call_sites.get(name, []))
            w.writerow([name, demangle(name), f"{med:.2f}", str(cnt), str(tot),
                        str(nchildrens_val), str(total_callsite_event), str(total_callsite_n)])

    with open("data/nchildren.csv","w",) as f:
        w = csv.writer(f)
        w.writerow(["mangled","demangled","median","count","total_event_counts"])
        for name, nc in nchildren.items():
            cnt = len(nc)
            tot = sum(nc)
            med =  median(nc) if cnt else 0
            w.writerow([name, demangle(name), f"{med:.2f}", str(cnt), str(tot)])

    with open("data/summary_corrected.csv","w",) as f:
        w = csv.writer(f)
        w.writerow(["mangled","demangled","avg_event_counts","count","total_event_counts"])
        for name, durs in durations.items():
            cnt = len(durs)
            tot = sum(durs) - sum(nchildren[name]) * 10
            med =  median(durs) if cnt else 0
            w.writerow([name, demangle(name), f"{med:.2f}", str(cnt), str(tot)])

    overall = sum(sum(d) for d in durations.values())
    print(f"Overall pmu count across all functions: {overall}")
    overall_paired_event = sum((len(d)) for d in durations.values()) * 2
    print(f"Overall pair event across all functions: {overall_paired_event}")
    overall_unpaired_event = sum([len(d) for d in events_map.values()]) - overall_paired_event
    print(f"Overall unpaired events (after filtering): {overall_unpaired_event}")



    start_list, end_list = list(zip(*start_end_values.items()))


    with open("data/info.json","w") as f:
        json.dump(
            {
                "start_end_values": [min(start_list), max(end_list)],
                "overall_total_pmu": overall,
                "overall_paired_event": overall_paired_event,
                "overall_unpaired_event": overall_unpaired_event,
            },
            f
        )




if __name__ == "__main__":
    main()
