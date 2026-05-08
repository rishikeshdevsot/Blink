import argparse
import subprocess
import json
import glob
import os
from pathlib import Path
import summarize_workload
import pprint
import pandas as pd
# REPORT="/home/yWX1380092/CPU-test/Performance/TOP_APP_OH/Report_ohos5_perf_fixed"
# REPORT="/home/yWX1380092/CPU-test/Performance/TOP_APP_OH/Report_perf-minh-base_4001"
# REPORT="/home/yWX1380092/CPU-test/Performance/TOP_APP_OH/Report_ohos5_4000_user"
parser = argparse.ArgumentParser(
                    prog='process_workload',
                    description='processing hiperf/perf data',
)

parser.add_argument('reportdir')           # positional argument
parser.add_argument('--search', '-s', default="*data.csv")
parser.add_argument('--json', '-j', default="workload.json")
parser.add_argument('-n', type=int, default=10)

args = parser.parse_args()

REPORT = args.reportdir
REPORT_PATH = Path(REPORT)
RESULT = Path.cwd() / REPORT_PATH.name

RESULT.mkdir(exist_ok=True)

COMPONENT='render'
PMU = f'pmu_{COMPONENT}'
N=args.n
SEARCH=args.search

with open(args.json) as fd:
    conf = json.load(fd)

infos = []
active = conf['active']
for app, workloads in active.items():
    print(app)
    app_path = f"{REPORT}/{app}"
    for workload in workloads['workload']:
        workload_path = f"{app_path}/{workload}/{PMU}"
        csv_path = os.path.join(workload_path, SEARCH)
        print(csv_path)
        # print((csv_path))
        # look for data.csv in the workload path
        matches = glob.glob(csv_path)
        print(matches)
        info = {
            'app': app,
            'workload': workload,
            'num_csv': len(matches),
            'combined_csv':  f'{RESULT}/{app}_{workload}.csv'
        }
        if len(matches) > 0:
            infos.append(info)
            summarize_workload.combine_files(matches, info['combined_csv'])

dfs = []
selected_columns = ['fun', 'lib', 'Avg', 'StdDev%', 'Avg%_of_total', 'Num_Run_out_10']

selected_columns.extend(map(str, range(1, N + 1)))
# selected_columns.extend(map(str, range(1, 10 + 1)))
selected_columns.extend([f'num_sample.{i}' for i in range(1, N + 1)])

for info in infos:
    df = pd.read_csv(info['combined_csv'])
    actual_columns = []
    for c in selected_columns:
        if c in df.columns:
            actual_columns.append(c)
    # print(actual_columns)

    df = df[actual_columns]
    df['app'] = f"{info['app']}"
    df['workload'] = f"{info['workload']}"

    dfs.append(df)


all_data = pd.concat(dfs)
with open(RESULT / "combined.csv", 'w') as fd:
        fd.write(all_data.to_csv())


#--- parsing for json logs contains metadata

infos = []
for app, workloads in active.items():
    # print(app)
    app_path = f"{REPORT}/{app}"
    for workload in workloads['workload']:
        workload_path = f"{app_path}/{workload}/{PMU}"
        csv_path = os.path.join(workload_path, SEARCH + '.json')
        # print((csv_path))
        # look for data.csv in the workload path
        matches = glob.glob(csv_path)
        # print(matches)
        info = {
            'app': app,
            'workload': workload,
            'matches': matches,
            'combined_csv':  f'{RESULT}/{app}_{workload}_metadata.json'
        }
        if len(matches) > 0:
            infos.append(info)

# selected_columns = ['fun', 'lib', 'Avg', 'StdDev%', 'Avg%_of_total', 'Num_Run_out_10']

# selected_columns.extend(map(str, range(1, N + 1)))
# # selected_columns.extend(map(str, range(1, 10 + 1)))
# selected_columns.extend([f'num_sample.{i}' for i in range(1, N + 1)])
exit(0)

df_meta_total = None
for info in infos:
    df_meta = []
    matches = info['matches']
    metadata = []
    for m in matches:
        with open(m) as fd:
            data = json.load(fd)
            data['key'] = info['app'] + '/' + info['workload']
            # print(data['key'])
            metadata.append(data)
    df_meta = pd.DataFrame(metadata)
    if df_meta_total is None:
        df_meta_total = df_meta
    else:
        df_meta_total = pd.concat([df_meta_total, df_meta])
df_meta_total.to_csv(f'{RESULT}/combined_metadata.csv')
#     df = pd.read_csv(info['combined_csv'])
#     actual_columns = []
#     for c in selected_columns:
#         if c in df.columns:
#             actual_columns.append(c)
#     # print(actual_columns)

#     df = df[actual_columns]
#     df['app'] = f"{info['app']}"
#     df['workload'] = f"{info['workload']}"

#     dfs.append(df)


# all_data = pd.concat(dfs)
# with open(RESULT / "combined.csv", 'w') as fd:
#         fd.write(all_data.to_csv())

