# Utility functions for the post-process script
import os
import logging
from collections import defaultdict
from enum import Enum
import csv
import sys
import glob
import json
import subprocess

logger = logging.getLogger(__name__)


class FIDType(Enum):
    UNKNOWN = -1
    ENTRY = 0
    EXIT = 1
    CALL_ENTRY = 2
    CALL_EXIT = 3

def demangle(name):

    out = subprocess.check_output(["c++filt", name], stderr=subprocess.DEVNULL)
    return out.decode("utf-8", errors="ignore").strip()


def build_id_map(mip_dir, debug):
    """
    Scan all *.csv in mip_dir, return:
      id_map:      dict mapping fid -> function name
      valid_funcs: set of function names that have at least one entry and one exit (i.e. ≥2 IDs) statically
    
    Note, this valid_funcs does not ensure there will always be an entry-exit pair at runtime

    Additionally, any functions that fail this criterion are logged to
    debug/missing_entry_or_exit_funcs.txt, with a header count and one name per line.
    """
    id_map   = {}
    func_ids = defaultdict(set)
    # Gather all IDs per function
    for fn in glob.glob(os.path.join(mip_dir, "*.csv")):
        with open(fn, newline="") as f:
            for row in csv.reader(f):
                if len(row) >= 2 and row[0].isdigit():
                    # print(row)
                    fid, name, entryID = int(row[0]), row[1], int(row[4])
                    old_name = id_map.get(fid)
                    if old_name:
                        print("Error: found duplicate entry from MIPInfo")
                        print(f"{fid}, {name}")
                        print(f"{fid}, {old_name}")
                        sys.exit(1)
                    id_map[fid] = (name, entryID, FIDType.UNKNOWN)
                    func_ids[name].add(fid)
    
    for name, fids in func_ids.items():
        entire_function_entry = min(fids)
        #iterate through all the exit
        for fid in fids:
            entryID = id_map[fid][1]
            if entryID == 0:
                continue
            if entryID == entire_function_entry:
                id_map[fid] = (name, entryID, FIDType.EXIT)
                id_map[entryID] = (name, 0, FIDType.ENTRY)
            else:
                id_map[fid] = (name, entryID, FIDType.CALL_EXIT)
                id_map[entryID] = (name, 0, FIDType.CALL_ENTRY)
    # UNKNOWN = '<unknown callee>'
    # if not id_map.get(0, None):    
    #     id_map[0] = UNKNOWN
    #     func_ids[UNKNOWN].add(0)
    # if not id_map.get(1, None):
    #     id_map[1] = UNKNOWN
    #     func_ids[UNKNOWN].add(1)
    # Functions missing either entry or exit will have fewer than 2 distinct IDs
    invalid_funcs = [content[0] for fid, content in id_map.items() if content[2] == FIDType.UNKNOWN]
    valid_funcs   = {content[0] for fid, content in id_map.items() if content[2] != FIDType.UNKNOWN}

    # Ensure debug directory exists and write out the invalid list
    if debug:
        os.makedirs("debug", exist_ok=True)
        out_path = os.path.join("debug", "missing_entry_or_exit_funcs.txt")
        with open(out_path, "w") as outf:
            outf.write(f"Number of functions missing entry or exit: {len(invalid_funcs)} out of {len(func_ids)}\n")
            outf.write(f"Invalid function ratio is {len(invalid_funcs) / len(func_ids) * 100 :.2f} %\n")
            for name in sorted(invalid_funcs):
                outf.write(f"{name}\n")

        id_map_json = os.path.join("debug", "id_map.json")
        with open(id_map_json, 'w') as fd:
            json.dump(id_map, fd,
                sort_keys=True, indent=4)
    return id_map, valid_funcs


def detect_and_apply_wrap(
    events,
    window: int = 10,
    wrap_max: int = 0xFFFFFFFF
):
    """
    Detect 32‑bit counter wrap‑around in a sequence of PMU events since hardware PMU counter is using 32-bits unsigned number to count
    and extend all subsequent values by wrap_max.

    TODO: support multiple wrap arounds

    Args:
      events: List of (fid, name, raw_val) tuples.
      window: Number of strictly‑increasing samples to confirm a wrap.
      wrap_max: Maximum counter value before wrap (2^32‑1).

    Returns:
      List of (fid, name, ext_val) with wrap applied.
    """
    raw_vals = [val for (_, _, val) in events]
    n = len(raw_vals)
    wrap_idx = None

    # scan for a wrap point at i
    for i in range(window, n - window):
        prev = raw_vals[i - window : i]
        curr = raw_vals[i]
        nxt  = raw_vals[i : i + window]

        # conditions:
        # 1) prev is strictly increasing
        # 2) prev[-1] near wrap_max (e.g. > 90%)
        # 3) curr small (e.g. < 10%)
        # 4) nxt is strictly increasing
        if (prev[-1] > wrap_max * 0.9 and
            curr      < wrap_max * 0.1 and
            all(prev[j] < prev[j+1] for j in range(window - 1)) and
            all(nxt[j] < nxt[j+1]     for j in range(window - 1))):
            wrap_idx = i
            logging.debug(
                f"PMU wrap detected at idx={i}: "
                f"{prev[-1]} → {curr}"
            )
            break

    # if no wrap, return original
    if wrap_idx is None:
        return [(fid, name, val) for fid, name, val in events]

    # apply wrap_max to all values from wrap_idx onward
    extended = []
    for idx, (fid, name, val) in enumerate(events):
        ext = val + wrap_max if idx >= wrap_idx else val
        extended.append((fid, name, ext))
    return extended


def filter_glitches(
    events,
    debug=False,
    src_path=None,
    debug_dir="debug",
    recovery_window=10,
    pct_threshold=0.1
):
    """
    Drop readings that break monotonic increase or jump > pct_threshold;
    only recover once you see a value back within [last_good, last_good*(1+pct)]
    AND it’s followed by recovery_window strictly increasing in-range samples.
    """

    raw_count      = len(events)
    filtered_count = 0
    segments       = []

    if raw_count == 0:
        return [], 0, 0, []

    # 1) seed with first reading
    filtered      = []
    last_good_idx = 0
    last_good_val = events[0][2]
    last_good_fid = events[0][0]

    i, n = 0, raw_count
    while i < n:
        fid, name, val = events[i]
        lower = last_good_val
        upper = last_good_val * (1 + pct_threshold)

        # 2) normal accept?
        if lower <= val <= upper:
            filtered.append((fid, name, val))
            last_good_idx = i
            last_good_val = val
            last_good_fid = fid
            i += 1
            continue
        elif val > upper:
            # may be the thread is running but instrumentation are all disabled
            # check next recovery_window for strict monotonical increasing
            prev = val
            ok   = True
            for j in range(i+1, i+recovery_window):
                vj = events[j][2]
                if vj <= prev:
                    ok = False
                    break
                prev = vj
            if ok:
                filtered.append((fid, name, val))
                last_good_idx = i
                last_good_val = val
                last_good_fid = fid
                i += 1
                continue

        # 3) glitch detected
        logger.debug(f"Glitch at idx={i}, fid={fid}, val={val}, last_good=(idx={last_good_idx},fid={last_good_fid},val={last_good_val})")

        bad_list = []
        # drop until valid recovery
        while i < n:
            fid2, name2, val2 = events[i]
            lower = last_good_val
            upper = last_good_val * (1 + pct_threshold)

            if not (lower <= val2 <= upper):
                # still out‑of‑range
                bad_list.append((i, fid2, val2))
                filtered_count += 1
                i += 1
                continue

            # possible recovery candidate
            #logger.debug(f"  recovery candidate idx={i}, val={val2}")

            # not enough left to confirm?
            if n - i < recovery_window:
                logger.debug(f"Recovered at idx={i}, fid={fid2}, val={val2}, dropped {len(bad_list)}")
                bad_list.extend((j, events[j][0], events[j][2]) for j in range(i, n))
                filtered_count += (n - i)
                i = n
                break

            # check next recovery_window for strict increase & in‑range
            prev = val2
            ok   = True
            for j in range(i+1, i+recovery_window):
                vj = events[j][2]
                if vj <= prev or vj < lower or vj > upper:
                    ok = False
                    break
                prev = vj

            if ok:
                # confirmed recovery
                segments.append((
                    last_good_idx,
                    last_good_fid,
                    last_good_val,
                    bad_list,
                    i,
                    fid2,
                    val2
                ))
                if debug:
                    print(f"[DEBUG] recovered at idx={i}, fid={fid2}, val={val2}, dropped {len(bad_list)}")
                filtered.append((fid2, name2, val2))
                last_good_idx = i
                last_good_val = val2
                last_good_fid = fid2
                # bad_list already counted
                i += 1
                break
            else:
                # false recovery → drop this too
                bad_list.append((i, fid2, val2))
                filtered_count += 1
                if debug:
                    print(f"[DEBUG] false recovery idx={i}, fid={fid2}, val={val2}")
                i += 1

    # 4) dump per-file logs
    if debug and segments and src_path:
        os.makedirs(debug_dir, exist_ok=True)
        base = os.path.basename(src_path)
        with open(os.path.join(debug_dir, f"{base}_glitches.log"), "w") as df:
            for idx, (lg_i, lg_f, lg_v, bad, rec_i, rec_f, rec_v) in enumerate(segments, 1):
                df.write(f"Segment {idx}:\n")
                df.write(f"  last_good:       (idx={lg_i}, fid={lg_f}, val={lg_v})\n")
                df.write(f"  bad_values:      {bad}\n")
                df.write(f"  first_recovered: (idx={rec_i}, fid={rec_f}, val={rec_v})\n\n")


    return filtered, raw_count, filtered_count, segments