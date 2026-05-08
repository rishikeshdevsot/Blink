#!/usr/bin/env python3
import sys
import re
import pandas as pd
from pathlib import Path

# filter(threshold)

N = 100

def combine_files(files, out):
    dfs = []
    data_columns = []

    df = None
    print(files, out)
    for i, f in enumerate(files):
        print(f)
        res = re.search(r'pmu_blink/(\d+)/.*/summary.*\.csv', f)
        if res:
            num = int(res.group(1))
            if num not in list(range(N + 1)):
                print(num)
                continue
        else:
            print("unable to extract the run# in filename")
            sys.exit(-1)

        df_old = pd.read_csv(f)
        print(df_old)
        df_new = df_old[['demangled', 'total_event_counts',
                         'count', 'nchildrens',
                         'total_callsite_event', 'total_callsite_n'
                       ]]
        # df_new.set_index('demangled')

        total_event_counts = f"{num}"
        count = f'num_sample.{num}'
        nchildren = f'nchildren.{num}'
        callsite = f'call.{num}'
        callsite_n = f'call.num_sample.{num}'

        df_new = df_new.rename(
            columns = {
                'total_event_counts': total_event_counts,
                'count': count,
                'demangled': 'fun',
                'nchildrens': nchildren,
                'total_callsite_event': callsite,
                'total_callsite_n': callsite_n,
            }
        )
        # print(df_new)
        df_long = pd.melt(df_new, id_vars=['fun'],
            var_name = f'samples',
            value_name='val')
        print(df_long)
        df_long = df_long.groupby(['fun', 'samples']).sum().reset_index()
        if df is None:
            df = df_long
        else:
            df = pd.concat([df, df_long], ignore_index=True)
        # print(df.columns)
        # print(df)
        data_columns.append((total_event_counts, count))
    # total_column, num_columns = list(zip(data_columns))
    # print()
    total_column, num_columns = zip(*data_columns)
    total_column = list(total_column)
    num_columns = list(num_columns)
    # df.reset_index(inplace=True)
    # print("======")
    # print(total_column)
    # dupes = df[df.duplicated(subset=['fun', 'samples'], keep=False)]
    # print()
    # df.to_csv('combined_before_pivot.csv')
    # print("=====")

    df = df.pivot(index="fun", columns="samples", values="val")
    df.to_csv('combined.csv')
    df['lib'] = '/system/lib64/librender_service_base.z.so'
    df['Avg'] = df[total_column].mean(axis=1)
    df['Std%'] = df[total_column].std(axis=1) * 100 / df['Avg']
    df['Avg.Total'] = df[num_columns].sum(axis=1)
    df['Num_Run_out_10'] = df[num_columns].count(axis=1)
    # print(total_column, num_columns)
    # print(df.head())
    df.to_csv(out)

    # grouped = all_data.groupby("lib", as_index=False)["period"].sum()

    # # Sort descending by total period
    # grouped = grouped.sort_values(by="period", ascending=False)

    return df

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(f"Usage: {sys.argv[0]} file1.csv file2.csv ... -o file.combined")
        sys.exit(1)


import argparse

def main():
    parser = argparse.ArgumentParser(
        description="Combine multiple CSV files for the same workload"
                    " into a single summary file"
    )
    parser.add_argument(
        "input_files",
        metavar="file",
        nargs="+",
        help="Input CSV files to combine"
    )
    parser.add_argument(
        "-o", "--output",
        required=True,
        help="Output combined file"
    )

    parser.add_argument(
        "-l", "--lib",
        nargs="*",
        help='Libraries to show (optional)'
    )
    args = parser.parse_args()

    print("Input files:", args.input_files)
    print("Output file:", args.output)

    result = combine_files(args.input_files, args.output)




if __name__ == "__main__":
    main()
