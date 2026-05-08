#!/usr/bin/env python3
import sys
import re
import pandas as pd
import statistics
from pathlib import Path
import argparse



def combine_files(files, out):

    # print("combine_files", files, out)
    periods = []
    keys = ['fun', 'lib']
    df = None
    for i, f in enumerate(files):
        # print(f)
        # res = re.search(r'pmu_.*_(\d+)\.data.*\.csv', f)
        res = re.search(r"(?:[a-z/_]+)(\d+)(?:[a-z._/]*)data.*\.csv", f)

        # for lse
        # res = re.search(r'pmu_render/perf(\d+)\.data.*\.csv', f)

        if res:
            periods.append(res.group(1))
            num = int(res.group(1))
            periods.append(f'num_sample.{num}')
        else:
            print("unable to extract the run# in filename")
            sys.exit(-1)

        df_new = pd.read_csv(f)

        df_new = df_new.rename(columns={
                                'period': str(num),
                                'num_sample': f'num_sample.{num}'
                            })

        if i == 0:
            df = df_new
            # print(df)
        else:
            # print(df)
            # print(df_new.columns)
            # print(df.columns)
            df = pd.merge(
                left=df,
                right=df_new,
                how='outer',
                on=['fun', 'lib']
            )
        # print(df.tail())

    # all_data = pd.concat(dfs, axis=1)

    # print(df)
    # print(df[periods])
    sums = df[periods].sum(axis=0).tolist()
    sums_avg = statistics.mean(sums)
    # print('sums: list')
    # print(sums)
    row_total = ['', 'totals']
    # print(tmp)
    row_total.extend(sums)
    row_total_index = len(df.index)
    df.loc[row_total_index] = row_total





    # fun1, lib1, 1 2 3 4 5 6 7 8 9 10
    # fun2, lib1, 1 2 3 4 5 6 7 8 9 10
    # -----------------
    aggregation_functions = {}
    for p in periods:
        aggregation_functions[p] = 'sum'

    # print(df.head())
    aggregate_cols = periods[:]
    aggregate_cols.append('lib')
    df_per_library = df[aggregate_cols] \
                      .groupby('lib', as_index=False) \
                      .aggregate(aggregation_functions)
    df_per_library['fun'] = 'Total'

    df = pd.concat([df, df_per_library])

    df[keys] = df[keys].fillna('')
    # df[periods] = df[periods].fillna(0)



    df['Avg'] = df[periods].mean(axis=1)
    df['StdDev%'] = df[periods].std(axis=1) / df['Avg'] * 100
    df['Avg%_of_total'] = (df['Avg'] * 100) /sums_avg
    df['Num_Run_out_10'] = df[periods].count(axis=1)

    # Fix me:
    filtered_df = df
    # print(filtered_df)
    # filtered_df = df[df['lib'] == "/system/lib64/librender_service_base.z.so"]

    # print(tmp)

    # grouped_columns = periods[]
    # grouped = filtered_df \
    #             .groupby("lib", as_index=False)[periods].sum()
    # grouped.to_csv(out + '.grouped.csv')


    #add total
    # filtered_df.loc[len(filtered_df.index)] = df.loc[row_total_index]
    # filtered_df = df
    filtered_df.to_csv(out, index=False)
    print(filtered_df.columns)

    # # Sort descending by total period
    # grouped = grouped.sort_values(by="period", ascending=False)

    return filtered_df

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(f"Usage: {sys.argv[0]} file1.csv file2.csv ... -o file.combined")
        sys.exit(1)


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

    # print("Input files:", args.input_files)
    # print("Output file:", args.output)

    result = combine_files(args.input_files, args.output)




if __name__ == "__main__":
    main()
