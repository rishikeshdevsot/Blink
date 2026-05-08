import argparse
import subprocess
import json
import glob
import os
import summarize_workload
import pprint
import pandas as pd
from pathlib import Path

# REPORT="/home/yWX1380092/CPU-test/Performance/TOP_APP_OH/Report_blink_cycle_final"
# REPORT="/home/yWX1380092/phone_data/result_blink_cycle"
# RESULT='./report_blink_single'
# RESULT='./report_blink_corrected'
# RESULT='./report_blink'

parser = argparse.ArgumentParser(
                    prog='process_workload',
                    description='processing hiperf/perf data',
)

parser.add_argument('reportdir')           # positional argument
parser.add_argument('--search', '-s', default="**/summary.csv")
parser.add_argument('--json', '-j', default="workload.json")
args = parser.parse_args()

REPORT = args.reportdir
REPORT_PATH = Path(REPORT)
RESULT = Path.cwd() / REPORT_PATH.name

SEARCH = args.search

PMU = 'pmu_blink'
RESULT.mkdir(exist_ok=True)



with open(args.json) as fd:
    conf = json.load(fd)

infos = []

active = conf['active']
for app, workloads in active.items():
    app_path = f"{REPORT}/{app}"
    for workload in workloads['workload']:
        workload_path = f"{app_path}/{workload}/{PMU}"
        # look for data.csv in the workload path
        print(workload_path + '/' + SEARCH)
        matches = glob.glob(os.path.join(workload_path, SEARCH), recursive=True)

        info = {
            'app': app,
            'workload': workload,
            'num_csv': len(matches),
            'combined_csv':  f'{RESULT}/{app}_{workload}.csv'
        }
        if len(matches) > 0:
            # print(workload_path, matches)
            infos.append(info)
            summarize_workload.combine_files(matches, info['combined_csv'])


dfs = []

for info in infos:
    df = pd.read_csv(info['combined_csv'])
    # df = df[['lib', 'Avg', 'Std%', 'Avg.Total', 'Num_Run_out_10']]
    df['app'] = f"{info['app']}"
    df['workload'] = f"{info['workload']}"
    dfs.append(df)



all_data = pd.concat(dfs)
with open(RESULT / "combined.csv", 'w') as fd:
        fd.write(all_data.to_csv(index=False))
print(all_data)
