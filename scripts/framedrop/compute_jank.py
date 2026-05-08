import sqlite3
import plot_dependencies
import logging
import sys
import subprocess

# Configure the logging
logging.basicConfig(filename='app.log', level=logging.INFO)
logging.getLogger().addHandler(logging.StreamHandler())

# Create a logger
logger = logging.getLogger(__name__)
# creating file path
# dbfile = 'open_global_search_interface_com.ohos.sceneboard_5.db'
dbfile = sys.argv[1]
# Create a SQL connection to our SQLite database
con = sqlite3.connect(dbfile)

# creating cursor
c = con.cursor()

thread_name = "IPC_4_2676"
ts = 252662454000


def itid2tid(itid):
    if itid == 0xDEADBEEF:
        return 0xDEADBEEF
    res=c.execute(f"SELECT tid FROM thread where itid={itid}")
    tid, = res.fetchone()
    return tid
def tid2itid(tid):
    if tid == 0xDEADBEEF:
        return 0xDEADBEEF
    res=c.execute(f"SELECT itid FROM thread where tid={tid}")
    itid, = res.fetchone()
    return itid

# reading all table names
table_list = [a for a in c.execute("SELECT * FROM sqlite_master WHERE type = 'table'")]
# x=c.execute("SELECT * FROM sqlite_master where type='table'")
# [print(i) for i in table_list]

for t in table_list:
    # print(t)
    # print(t[1])
    res = c.execute(f"SELECT * FROM {t[1]}")
    first = res.fetchone()
    # if first is not None:
        # print(t)
        # for row in res.fetchmany(10):
            # print(row)



def get_itid(tname):
    res=c.execute(f"SELECT itid FROM thread where name=\"{tname}\"")
    itid, = res.fetchone()
    return itid

# exit(0)
# res = c.execute(f"SELECT vsync, ts, dur, type_desc FROM frame_slice WHERE itid = {tid2itid(43785)} ")
# res = c.execute(f"SELECT * FROM frame_slice WHERE itid = {tid2itid(58659)} ")

# out = res.fetchall()
# ('table', 'frame_slice', 'frame_slice', 4111, 'CREATE TABLE frame_slice(\n
# id INT,\n  ts INT,\n  vsync INT,\n  ipid INT,\n  itid INT,\n
# callstack_id INT,\n  dur INT,\n  src TEXT,\n  dst INT,\n  type INT,\n  type_desc TEXT,\n  flag INT,\n  depth INT,\n  frame_no INT\n)')
# print(out)
# actual = filter(out,)
# exit(1)

# Fill this up
# FRAME_START = int(sys.argv[1])
# FRAME_DUR = int(sys.argv[2])
# THREAD_NAME = sys.argv[3]
# OUT_NAME = sys.argv[4]


def get_tid(itid):
    res=c.execute(f"SELECT name, tid FROM thread where itid=\"{itid}\"")
    name,tid = res.fetchone()
    return name, tid

def get_pid(itid):
    res=c.execute(f"SELECT ipid FROM thread where itid=\"{itid}\"")
    ipid, = res.fetchone()
    res=c.execute(f"SELECT name, pid FROM process where ipid=\"{ipid}\"")
    name, pid = res.fetchone()
    return name, pid

def find_slice(ts, itid, before=True):
    operator = ('>=', 'ASC')
    if before:
        operator = ('<=', 'DESC')

    res = c.execute(f"SELECT id, ts, dur, cpu, itid FROM sched_slice \
                     where itid={itid} AND ts{operator[0]}{ts} ORDER BY ts {operator[1]}")
    return res.fetchone()
'''
('table', 'process', 'process', 2, 'CREATE TABLE process(\n  id INT,\n  ipid INT,\n  pid INT,\n  name TEXT,\n  start_ts INT,\n  switch_count INT,\n  thread_count INT,\n  slice_count INT,\n  mem_count INT\n)')
('table', 'thread', 'thread', 3, 'CREATE TABLE thread(\n  id INT,\n  itid INT,\n  tid INT,\n  name TEXT,\n  start_ts INT,\n  end_ts INT,\n  ipid INT,\n  is_main_thread INT,\n  switch_count INT\n)')
('table', 'sched_slice', 'sched_slice', 544, 'CREATE TABLE sched_slice(\n  id INT,\n  ts INT,\n  dur INT,\n  ts_end INT,\n  cpu INT,\n  itid INT,\n  ipid INT,\n  end_state TEXT,\n  priority INT,\n  arg_setid INT\n)')
('table', 'instant', 'instant', 383, 'CREATE TABLE instant(\n  ts INT,\n  name TEXT,\n  ref INT,\n  wakeup_from INT,\n  ref_type TEXT,\n  value REAL\n)')
('table', 'callstack', 'callstack', 1292, 'CREATE TABLE callstack(\n  id INT,\n  ts INT,\n  dur INT,\n  callid INT,\n  cat TEXT,\n  name TEXT,\n  depth INT,\n  cookie INT,\n  colorIndex INT,\n  parent_id INT,\n  argsetid INT,\n  chainId TEXT,\n  spanId TEXT,\n  parentSpanId TEXT,\n  flag TEXT\n)')]

'''
def insert_data(res, m, s):
    itid=s[4]
    slice_id = s[0]
    tid = itid2tid(itid)
    if res.get(tid) is None:
        res[tid] = []
    if s[1:4] not in res[tid]:
        res[tid].append(s[1:4])
        if m.get(slice_id, None) != None:
            m[slice_id] = None
        return True
    return False

def stacktrace(itid, start, end):
    x = c.execute(f"SELECT ts, dur, callid, name, depth  FROM callstack WHERE callid = {itid} AND ts <= {end} AND ts >= {start}")
    for y in x.fetchall():
        print(y[0], itid2tid(y[2]), y[3], y[4])

def wakeup_by(ts, itid):
    res = c.execute(f"SELECT ts, wakeup_from FROM instant where ts<={ts} AND ref={itid} ORDER BY ts DESC")
    wakeup = res.fetchone()
    return wakeup
def get_wakeup_list(ts, dur, itid):
    ''' get the threads our program wake up
        returns the ts where our wakeup happens'''
    # print("log:", ts, ts+dur)
    res = c.execute(f"SELECT ts, ref, wakeup_from FROM instant where ts<={ts + dur} \
                    AND ts>={ts} AND wakeup_from={itid}")
    wakeup_list = list(res.fetchall())
    print(wakeup_list)
    return wakeup_list

def look_for_start(slice_map):
    for k in slice_map:
        v = slice_map[k]
        if v is None:
            continue
        res = get_wakeup_list(v[1], v[2], v[3])
        print(f'{v[0]}: {len(res)}')

def check_preemption(ts, itid, before=True):
    operator = ('>', '', )
    if before:
        operator = ('<', 'DESC')
    res = c.execute(f"SELECT id, ts, dur, cpu, itid, end_state FROM sched_slice \
                      WHERE ts{operator[0]}{ts} AND itid={itid} ORDER BY ts {operator[1]}")
    s = res.fetchone()
    if s is None:
        return s
    # print(s[5])
    if s[5] == "R+":
        return s[:5]
    return None

def check_curr_preemption(id):
    res = c.execute(f"SELECT id, ts, dur, cpu, itid, end_state FROM sched_slice \
                      WHERE id={id}")
    s = res.fetchone()
    if s is None:
        raise Exception("id not found!")
    # print(s[5])
    if s[5] == "R+":
        return True
    return False

def main():

    itid = get_itid("wei.hmos.photos")
    res = c.execute(f"SELECT vsync, ts, dur, type_desc FROM frame_slice WHERE itid = {itid} ")
    # res = c.execute(f"SELECT * FROM frame_slice WHERE itid = {tid2itid(58659)} ")

    out = res.fetchall()
    # print(out)
    expect = {}
    actual = {}
    for f in out:
        if f[3] == 'expect':
            expect[f[0]] = (f[1], f[2])
        else:
            actual[f[0]] = (f[1], f[2])
    # print(expect)
    # print(actual)
    merge_actual = {}
    for key, value in actual.items():
        if expect.get(key) is not None:
            merge_actual[key]  = {
                'actual': value,
                'expect': expect.get(key)
            }
    # print(merge_actual)
    frame_numbers_s = list(merge_actual.keys())
    frame_numbers_s.sort()
    # print((frame_numbers_s))
    last_frameno = 0
    consec_jank = 0
    results = [0] * 100
    reason = {}
    bad_frames = {}
    good_frames = {}
    script = "/home/yWX1380092/projects/critical_path/chenxing_workload/parse_hitrace.py"
    for f in frame_numbers_s:
        data = merge_actual[f]
        if data is None:
            last_frameno = f
            continue

        actual_end_time = data['actual'][0] + data['actual'][1]
        expected_deadline = data['expect'][0] + data['expect'][1]
        if actual_end_time > expected_deadline:
            # if last_frameno == 0 or f == last_frameno + 1:
                reason[f] = ''
                if data['actual'][1] > data['expect'][1]:
                    reason[f] = "longer duration;"
                    bad_frames[f] = data['actual']
                else:
                    reason[f] = "delayed start;"
                consec_jank += 1
                # print(f, consec_jank)
        else:
            results[consec_jank] += 1
            consec_jank = 0
            good_frames[f] = data['actual']
        last_frameno = f

    if consec_jank > 0:
        results[consec_jank] += 1
    for i in results:
        print(i, end=',')
    print()
    # print(reason)

    sys.exit(0)
    # print(good_frames)
    # print(bad_frames)
    good_regions = split_regions(good_frames, itid)
    bad_regions = split_regions(bad_frames, itid)
    tid = itid2tid(itid)
    swipes = ['r1', 'l1', 'r2', 'l2', 'r3']
    for f,v in good_regions.items():
        print(f)
        for swipe in swipes:
            for i,r in enumerate(v):
                unique_id = f'./results/{f}_{swipe}_{i}'
                perf_dumpfile = \
                    f"/home/yWX1380092/projects/critical_path/chenxing_workload/hiperf_new_logs1/photos{swipe}.perf2.dump"
                result = subprocess.run([f'python3 {script} {r[0]} {r[1]} {tid} {perf_dumpfile} > {unique_id}'], shell=True)

            # python3 parse_hitrace.py $tstart $tend $tid $file > $output

    # ('table', 'frame_slice', 'frame_slice', 4111, 'CREATE TABLE frame_slice(\n
    # id INT,\n  ts INT,\n  vsync INT,\n  ipid INT,\n  itid INT,\n
    # callstack_id INT,\n  dur INT,\n  src TEXT,\n  dst INT,\n  type INT,\n  type_desc TEXT,\n  flag INT,\n  depth INT,\n  frame_no INT\n)')
    # print
    # (out)
    # actual = filter(out,)
    # exit(1)

def split_regions(frames, itid):
    # ('table', 'callstack', 'callstack', 13295, '
    # CREATE TABLE callstack(\n  id INT,\n  ts INT,\n  dur INT,\n  callid INT,\n  cat TEXT,\n  name TEXT,
    # \n  depth INT,\n  cookie INT,\n  colorIndex INT,\n  parent_id INT,\n  argsetid INT,\n
    # chainId TEXT,\n  spanId TEXT,\n  parentSpanId TEXT,\n  flag TEXT\n)')
    res = c.execute(f"SELECT * FROM callstack where name='H:FlushDirtyNodeUpdate' AND callid={itid}")
    regions = {}
    search_result = res.fetchall()
    for f, v in frames.items():
        # print(f, v)
        frame_start = v[0]
        frame_end = v[1] + frame_start
        for call in search_result:
            call_start = call[1]
            call_end = call_start + call[2]
            if (call_start >= frame_start and call_end <= frame_end):
                # print(f, frame_start, frame_end, call_start, call_end)
                region1 = (frame_start, call_start)
                region2 = (call_start, call_end)
                region3 = (call_end, frame_end)
                regions[f] = [region1, region2, region3]
                break
    # print(regions)
    return regions
# print(get_itid("wei.hmos.photos"))


def generate_data(name, sched_slices, slice_map):
    plot_data = {
        "data": {},
        "dependency": [],
        "t_names": {},
    }
    output = plot_data["data"]
    dependency = plot_data["dependency"]
    translation = plot_data['t_names']

    # sched_slices = [s]
    count = 0
    while (len(sched_slices)!= 0):
        sched_slice = sched_slices.pop()
        count += 1
        # if count > 10000:
        #     break
        itid = sched_slice[4]
        tid = itid2tid(itid)
        dur = sched_slice[2]
        ts = sched_slice[1]
        slice_id = sched_slice[0]
        logger.info(f"{sched_slice}, {tid}, {check_curr_preemption(slice_id)}")

        if itid == 0:
            continue

        if insert_data(output, slice_map, sched_slice) == False:
            continue
        if tid == 0:
            continue


        preemption_before = check_preemption(ts, itid, before=True)
        is_curr_preemption = check_curr_preemption(slice_id)
        if preemption_before:
            logger.info(f"preempt before: {preemption_before}")
            sched_slices.append(preemption_before)
        if is_curr_preemption:
            preemption_after = check_preemption(ts, itid, before=False)
            if preemption_after:
                logger.info(f"preempt after: {preemption_after}")
                sched_slices.append(preemption_after)

        if not preemption_before:
            # continue # disabled
            wakeup = wakeup_by(ts, itid)
            if wakeup is None:
                continue
            wakeup_ts, wakeup_itid = wakeup
            if wakeup_itid == 0:
                continue
            print(ts, itid2tid(itid),  ' wakeup by =>', wakeup_ts, itid2tid(wakeup_itid))
            wakeup_rel = (wakeup_ts, itid2tid(wakeup_itid), ts, itid2tid(itid))
            #temp workaround for really f
            # if (ts - wakeup_ts) >  200000:
            #     continue
            next_slice = find_slice(wakeup_ts, wakeup_itid)
            if next_slice is None:
                continue
            dependency.append(wakeup_rel)
            sched_slices.append(next_slice)
        # print(f"next_slice {next_slice}")

        waking = get_wakeup_list(ts, dur, itid)
        for w in waking:
            n = find_slice(w[0], w[1], before=False)
            # print("hi")
            if n is not None:
                print(itid2tid(itid), 'wake up', itid2tid(n[4]))
                dep = (w[0], itid2tid(itid), n[1], itid2tid(n[4]))
                print(dep[2] - dep[0])
                dependency.append(dep)
                sched_slices.append(n)
    print(output)
    for k in output:
        t_name, tid = get_tid(tid2itid(k))
        p_name, pid = get_pid(tid2itid(k))
        translation[k] = f"{t_name}({tid}):{p_name}({pid})"
    # print(translation)
    # print(dependency)
    # plot_dependencies.plot(name, output, dependency, translation)
    translation[0xDEADBEEF] = "RENDER"
    # insert_data(output, slice_map,(0xDEADBEEF, 383211447417550, 15086458, 0, 0xDEADBEEF))
    insert_data(output, slice_map,(0xDEADBEEF, FRAME_START, FRAME_DUR, 0, 0xDEADBEEF))
    # 383212.141828488s    Duration
    # 16ms 918μs 229ns
    # id, ts, dur, cpu, itid
    return plot_data

main()
