import argparse
import re
import sys
import json
from collections import defaultdict

LINE_RE = re.compile(
    r"""
    ^\s*
    (?P<task>.+?)-(?P<pid>\d+)\s+      # TASK-PID
    \(\s*(?P<tgid>\d+)\)\s+             # TGID
    \[(?P<cpu>\d+)\]\s+                 # CPU
    [\.]+?\s+                           # flags (ignored for now)
    (?P<timestamp>\d+\.\d+):\s+         # TIMESTAMP
    (?P<event>\w+):\s*                  # FUNCTION / event
    (?P<details>.*)                     # rest
    $
    """,
    re.VERBOSE,
)

RECEIVE_VSYNC="ReceiveVsync name:"

def parse_line(line):
    m = LINE_RE.match(line)
    if not m:
        return None
    return m.groupdict()

def populate(app_frame_events, app_vsyncs, parsed, app_internal):
    if parsed['details'].startswith('S') or \
        parsed['details'].startswith('F'):
       return

    if parsed['details'].startswith('B'):
        app_frame_events.append(parsed)
    elif parsed['details'].startswith('E'):
        if len(app_frame_events) == 0:
            print("warning: tracing with end but not begin")
            return
        start = app_frame_events.pop()
        end = parsed
        if 'ArkUIPerfMonitor' in start['details']:
            res = re.search(r'(\{.*\})', start['details'])
            data = json.loads(res.group(1).replace("'", "\""))
            if data['layout'] == 0 and data['render'] == 0:
                pass
                #app_internal['skip'] = True
                #print("SKIP")
        if 'OnVsyncEvent now' in start['details']:
            app_internal['end_time'] = end['timestamp']

        if RECEIVE_VSYNC in start['details']:
            #print("###", start['details'])
            start['end'] = app_internal['end_time']
            if not app_internal['skip']:
                app_vsyncs.append(start)
            app_internal['skip'] = False
            app_internal['end_time'] = 'NaN'

        #print(float(end['timestamp']) - float(start['timestamp']))
    else:
        pass
        #print("events should start with B or E")
        #print(parsed)

def find_nearest_after(av, rvs):
    av_end = float(av['end'])
    for rv in rvs:
        rv_start = float(rv['timestamp'])
        if rv_start >= av_end:
            return rv
    return None

def process_trace(file):
    app_frame_events = []
    app_vsyncs = []
    app_internal = {
        'skip' : False,
        'end_time': 'NaN',
    }
    render_frame_events = []
    render_vsyncs = []
    render_internal = {
        'skip' : False,
        'end_time': 'NaN',
    }
    skip = False
    end_time = ""
    fd = open(file, 'r')
    for line in fd:
        line = line.rstrip()
        if not line or line.startswith("#"):
            continue

        parsed = parse_line(line)
        if parsed is None:
            print(f"UNPARSED: {line}")
        else:
            if parsed['task'] == 'wei.hmos.photos':
                if parsed['event'] == 'tracing_mark_write':
                    # print(parsed)
                    if RECEIVE_VSYNC in parsed['details']:
                        app_frame_events = []
                    populate(app_frame_events, app_vsyncs, parsed, app_internal)

            if parsed['task'] == 'render_service':
                if parsed['event'] == 'tracing_mark_write':
                    populate(render_frame_events, render_vsyncs, parsed, render_internal)

    fd.close()

    # print(render_frame_events)
    stats = defaultdict(int)

    consecutive_jank = 0
    is_jank = False
    for av in app_vsyncs:
        is_jank = False
        # print(av)
        # print(av)
        res = re.search(r'expectedEnd: (\d+)', av['details'])
        expected_end = float(res.group(1))
        #print(av, av['end'], expected_end)
        if float(av['end']) * 1e9 > expected_end:
            is_jank = True
        else:
            rv = find_nearest_after(av, render_vsyncs)
            if rv is None:
                continue
            av_id = re.search(r'vsyncId: (\d+)', av['details']).group(1)
            rv_id = re.search(r'vsyncId: (\d+)', rv['details']).group(1)
            expected_end = float(re.search(r'expectedEnd: (\d+)', av['details']).group(1))
            if float(rv['end']) * 1e9 > expected_end:
                is_jank = True
        # if tracing_mark_write: B|6478|H:ReceiveVsync dataCount:
        #    print(parsed)

        if is_jank:
            consecutive_jank += 1
        else:
            stats[consecutive_jank] += 1
            consecutive_jank = 0

    if is_jank:
        stats[consecutive_jank] += 1

    return stats
import pandas as pd

def main():
    parser = argparse.ArgumentParser(
        description="Print the contents of one or more files"
    )

    # Accept one or more file paths
    parser.add_argument(
        "files",
        nargs="+",
        help="Files to print"
    )

    args = parser.parse_args()

    rows = {}
    for f in args.files:
        print(f)
        num = int(re.search(r'_(\d+)\.htrace', f).group(1))
        # print(num)
        # if num not in range(1, 11):
        #     print("skipping anything > 10")
        #     continue
        stats = process_trace(f)
        print(stats)
        if len(stats) > 0:
            rows[num] = (stats)
            df = pd.DataFrame(rows)
        print(df)

    df.fillna(0, inplace=True)
    df.loc['total'] = df.mul(df.index, axis=0).sum() + df.loc[0]

    print(df.mean(axis=1))
    print(df.std(axis=1))
    df.to_csv('jank.csv')

if __name__ == "__main__":
    main()
