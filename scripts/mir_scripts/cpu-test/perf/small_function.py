import sys
import matplotlib
import re
import argparse
import pandas as pd
import matplotlib.pyplot as plt
import numpy as np
import seaborn as sns
# import scipy.stats as scipy_stats
# from sklearn.linear_model import LinearRegression
# import statsmodels.api as sm
from scipy import stats

parser = argparse.ArgumentParser(
    description="Generate small-function accuracy scatter plot (Fig. 4): measured vs ground-truth instruction counts."
)
parser.add_argument('--blink', default="../blink/Report_blink-minh-base-mate60_small_instr/Camera_large_picture_view.csv",
                    help="Blink (no ISB) per-workload CSV (default: %(default)s)")
parser.add_argument('--blink-isb', default="../blink/Report_blink-minh-base-mate60_small_isb_half_instr_tight2/Camera_large_picture_view.csv",
                    help="Blink (with ISB) per-workload CSV (default: %(default)s)")
parser.add_argument('--perf', default="../perf/Report_perf-minh-base-mate60-plain_instr/Camera_large_picture_view.csv",
                    help="Perf (default freq) per-workload CSV (default: %(default)s)")
parser.add_argument('--perf-20k', default="../perf/Report_perf-minh-base-mate60-plain_instr_20k/Camera_large_picture_view.csv",
                    help="Perf at 20kHz per-workload CSV (default: %(default)s)")
parser.add_argument('--ground-truth', default="final_demangled.csv",
                    help="Ground-truth instruction count CSV (default: %(default)s)")
parser.add_argument('--perf-combined', default="../perf/Report_ohos5_perf_fixed_user_self/combined.csv",
                    help="Perf combined.csv for boxplot functions (default: %(default)s)")
parser.add_argument('--blink-combined', default="../blink/Report_blink_cycle_user_final/combined.csv",
                    help="Blink combined.csv for boxplot functions (default: %(default)s)")
args = parser.parse_args()

CSV1 = args.blink
CSV2 = args.blink_isb
CSV3 = args.perf
CSV4 = args.perf_20k
GROUND_TRUTH = args.ground_truth



clone_pat = re.compile(r"\[clone \.llvm\.\d+\]")

INPUT1 = args.perf_combined
INPUT2 = args.blink_combined
LIB='/system/lib64/librender_service_base.z.so'

N = 9

def shorten(df, key='key'):
    keymap = {}
    # df[f'{key}_old'] = df[key]
    for k in df[key].unique():
        a, w = k.split('/')
        keymap[k] = a[0] + '/' + ''.join(s[0] for s in w.upper().split('_'))
    print(keymap)
    df.replace({key: keymap}, inplace=True)

def load_data_total(inp):
    og_df = pd.read_csv(inp)
    og_df = og_df[ (og_df['lib'] == 'totals') & (og_df['fun'] == 'Total')] 
    og_df['key'] = og_df['app'] + '/' + og_df['workload']
    selected_columns = \
        []
    selected_columns.extend(map(str, range(1, N + 1)))
    # for c in selected_columns:
    #     df[c] /= 1e6
    og_df.set_index(og_df['key'], inplace=True)

    df = og_df[selected_columns].copy()
    df.loc[:, selected_columns] = df[selected_columns]
    return df

def load_data_lib(inp, lib):
    og_df = pd.read_csv(inp)
    og_df = og_df[ (og_df['lib'] == lib) & (og_df['fun'] == 'Total') ]
    og_df['key'] = og_df['app'] + '/' + og_df['workload']
    selected_columns = \
        []
    selected_columns.extend(map(str, range(1, N + 1)))
    # for c in selected_columns:
    #     df[c] /= 1e6
    og_df.set_index(og_df['key'], inplace=True)

    df = og_df[selected_columns].copy()
    df.loc[:, selected_columns] = df[selected_columns]
    return df

def per_library(inp, lib):
    og_df = pd.read_csv(inp)
    columns = [f'{i}' for i in range(1, N + 1)]
    og_df = og_df[ (og_df['lib'] != 'totals') & (og_df['fun'] != 'Total')]
    
    #shorten workload name
    og_df['key'] = og_df.apply(lambda x: x['workload'][:5] + '...' + x['workload'][-5:], axis=1)
    
    df = og_df
    if 'lib' in og_df:
        df = og_df[ og_df['lib'] == lib ]

    long_df = df.melt(
        id_vars=['key', 'fun'],
        value_vars=columns,
        var_name="run",
        value_name="measurements"
    )
    stats = long_df.groupby(['key', 'run'])['measurements'] \
                .agg(["sum"]).reset_index()
    
    return stats


def plot_per_lib(inp1, inp2, lib):
    df1 = per_library(inp1, lib)
    df2 = per_library(inp2, lib)

    df1['method'] = 'perf'
    df2['method'] = 'blink'

    print(df1)
    print(df2)


    df = pd.concat([df1, df2])
    print(df)
    plt.figure(figsize=(20,16))
    sns.violinplot(
        data=df,
        x='key',
        y='sum',
        hue="method",
        split=True
    )
    # df_boxplot = \
    #     df.pivot(index="run", columns=["method", "key"], values='sum')
    # print(df_boxplot)
    # print(df_boxplot)
    # ax = df_boxplot.boxplot(by=['key'], title='librender')
    plt.xticks(rotation=45)
    plt.tight_layout()
    plt.savefig(f"wow.png")


def compute_perc_lib(inp, lib):
    df_total = load_data_total(inp)
    df_render = load_data_lib(inp, lib)
    df_merge = pd.merge(df_total, df_render, how='inner',
                        on=['key']
                        )
    columns_total = [f'{i}_x' for i in range(1, N + 1)]
    columns_lib = [f'{i}_y' for i in range(1, N + 1)]
    columns_lib_perc = list(range(1, N + 1))
    for i, c in enumerate(columns_lib_perc):
        df_merge[c] = df_merge[columns_lib[i]] * 100 / df_merge[columns_total[i]]
    # print(columns_lib_perc)
    # print(df_merge)
    return df_merge[columns_lib_perc].copy()

def load_metadata(inp, lib):
    df = pd.read_csv(inp)[['key', 'total_samples',
                           'total_periods',
                            f'{lib}.period', f'{lib}.sample']]
    shorten(df, 'key')
    df = df.groupby(['key']).mean().reset_index()
    df['avg_sample_period'] = df['total_periods'] / df['total_samples']
    print(df)
    return df

# INPUT1_METADATA = "../perf/Report_ohos5_perf_fixed_user/combined_metadata.csv"
# load_metadata(INPUT1_METADATA, LIB)
# sys.exit(0)
def load_data_and_get_stats(inp, lib, is_num_sample):
    og_df = pd.read_csv(inp)
    og_df['workload'] = og_df['workload'].astype(str)

    sample_columns = [f'num_sample.{i}' for i in range(1, N + 1)]
    columns = [f'{i}' for i in range(1, N + 1)]


    og_df = og_df[ (og_df['lib'] != 'totals') & (og_df['fun'] != 'Total')]
    og_df = og_df[ og_df['lib'] == lib]
    og_df['key'] = og_df['app'] + '/' + og_df['workload']
    shorten(og_df, 'key')

    
    # remove templating and random stuff
    og_df['fun'] = og_df['fun'].apply(clean_signature)
    
    og_df[columns] = og_df[columns].fillna(0)
    og_df['mean'] = og_df[columns].mean(axis=1)
    og_df['std'] = og_df[columns].std(axis=1)
    og_df['count'] = og_df[columns].astype(bool).sum(axis=1)
    og_df['sample_mean'] = og_df[sample_columns].mean(axis=1)
    og_df['sample_std'] = og_df[sample_columns].std(axis=1)


    # long_df = og_df.melt(
    #     id_vars=['key', 'fun'],
    #     value_vars=columns,
    #     var_name="run",
    #     value_name="perf"
    # )
    # long_df.to_csv("long_df.csv")
    # exit(0)
    # if not is_num_sample:
    #     long_df.loc[:, 'perf'] = long_df['perf'] / 1e6   
    # stats = long_df.groupby(['key', 'fun'])['perf'] \
                # .agg(["mean", "std", "count"]).reset_index()
        
    return og_df[["key", "fun", "mean", "std", "count", "sample_mean", "sample_std"]]

N = 100
dfs_csv = []
for f in [CSV1, CSV2, CSV3, CSV4]:
    df = pd.read_csv(f)
    df = df.fillna(0)

    column_data = {}
    for i in range(1, N + 1):
        # print(i)
        col = f'{i}'
        col_samples =f'num_sample.{i}'
        col_avg = f'avg.{i}'
        # column_data[col_avg] = df[col] / df[col_samples] 

    # new_df = pd.concat([df, pd.DataFrame(column_data)], axis=1)
    print(df)
    dfs_csv.append(df)

# drop the ones that blink isn't accurate on...
# holdon shouldn't I show it anyways
    
for i in range(1, N + 1):
    dfs_csv[1][f'{i}'] = dfs_csv[1][f'{i}']  -  dfs_csv[1][f'num_sample.{i}'] * 44

for i in range(1, N + 1):
    pass
    dfs_csv[0][f'{i}'] = dfs_csv[0][f'{i}']  -  dfs_csv[0][f'num_sample.{i}'] * 43
    # print(dfs_csv[0])
df_ground_truth = pd.read_csv(GROUND_TRUTH)
df_ground_truth.rename(
    columns={'name': 'fun'}, inplace=True
)
df_ground_truth.set_index('fun', inplace=True, drop=True)
df_ground_truth = df_ground_truth[['nins']]

def select_runtill(n, stats='mean', axis=1):

    # CSV1 = "../blink/Report_blink-minh-custom-mate60-white100/Camera_large_picture_view.csv"
    # CSV2 = "../blink/Report_blink-minh-base-mate60-white100/Camera_large_picture_view.csv"
    # CSV3 = "../perf/Report_perf-minh-custom-mate60/Camera_large_picture_view.csv"
    # CSV4 = "../perf/Report_perf-minh-base-mate60/Camera_large_picture_view.csv"
    

    # CSV5 = "../blink/Report_blink-minh-base-mate60-white100_first_news/Camera_large_picture_view.csv"
    # CSV6 = "../blink/Report_blink-minh-custom-mate60-white100_first_news/Camera_large_picture_view.csv"
 

 
    # print(columns)
    # exit(9)
    workloads = []
    out = None
    for f, df in zip([CSV1, CSV2, CSV3, CSV4], dfs_csv):
        name = re.search('/(Report_.*)/', f)
        name = name.group(1)            
        # df = pd.read_csv(f)

        # if 'perf' in name:
        if True:
            columns = ['fun']
            vals = [(f'{i}') for i in range(1, n+1)]
            samples = [f'num_sample.{i}' for i in range(1, n+1)]
        # else:
            # columns = ['fun', '6']
        # try:
        # print(df)
        for v,s in zip(vals, samples):
            # print(v,s)
            df[v] = df[v] / df[s]
        columns.extend(vals)
        df = df[columns]
        # except:
        # print(df.columns)
        # else:
        # print(df)
            # df = pd.read_csv(f)[['fun', '1']]

        df = df.set_index('fun', drop=True)
        df.to_csv(name + ".csv")

        df[name] = df.agg(stats, axis=1)
        if out is None:
            out = df[[name]]
        else:
            out = out.join(df[[name]], how='outer')

    # add the ground truth
    out = out.join(df_ground_truth, how='inner')
    # print(out['nins'].max())
    # print(out['nins'].mean())
    return out


num_runs = [100]
dfs = []
dfs_std = []
    # df_std = select_runtill(r + 1, 'std')
    # df["blink_pct"] = 100 * (df["Report_blink-minh-custom-mate60-white100_lpv"] \
    #                 - df["Report_blink-minh-base-mate60-white100_lpv"]) \
    #                 / df["Report_blink-minh-base-mate60-white100_lpv"]

    # df["perf_pct"]  = 100 * (df["Report_perf-minh-custom-mate60_lpv"] \
    #                 - df["Report_perf-minh-base-mate60_lpv"]) \
    #                 / df["Report_perf-minh-base-mate60_lpv"]
    # df_std["blink_pct"] = 100 * (df_std["Report_blink-minh-custom-mate60-white100_lpv"] \
    #                 - df_std["Report_blink-minh-base-mate60-white100_lpv"]) \
    #                 / df_std["Report_blink-minh-base-mate60-white100_lpv"]

    # df_std["perf_pct"]  = 100 * (df_std["Report_perf-minh-custom-mate60_lpv"] \
    #                 - df_std["Report_perf-minh-base-mate60_lpv"]) \
    #                 / df_std["Report_perf-minh-base-mate60_lpv"]
    # # df["blink_base_pct"] = 100 * (
    # #                         df['Report_blink-minh-base-mate60-white100_first_news']
    # #                       - df['Report_blink-minh-base-mate60-white100_lpv']
    # #                         ) / df['Report_blink-minh-base-mate60-white100_lpv']

    # # df["blink_custom_pct"] = 100 * (
    # #                         df['Report_blink-minh-custom-mate60-white100_first_news']
    # #                       - df['Report_blink-minh-custom-mate60-white100_lpv']
    # #                         ) / df['Report_blink-minh-custom-mate60-white100_lpv']

    # df["pct_diff"] = np.abs(df["blink_pct"] - df["perf_pct"])
    
    # df = df.sort_values(
    #     'Report_blink-minh-base-mate60-white100_lpv',
    #     ascending=False
    # )

selected_dfs = [
    select_runtill(100, 'mean')
]


# If you have a preselected list, filter to it:
# with open("selected_functions.txt") as f:
#     selected = [line.strip() for line in f]
# df = df[df["function"].isin(selected)]

# Compute differences
# df["blink_diff"] = df["blink_custom"] - df["blink_base"]
# df["perf_diff"]  = df["perf_custom"]  - df["perf_base"]

# # Scatter plot: Blink vs Perf difference
# plt.figure(figsize=(8,6))
# plt.scatter(df["blink_diff"], df["perf_diff"], alpha=0.7)
# # plt.axhline(0, color='gray', linestyle='--')
# # plt.axvline(0, color='gray', linestyle='--')
# plt.xlabel("Blink (custom - base)")
# plt.ylabel("Perf (custom - base)")
# plt.title("Custom - Base Difference: Blink vs Perf")
# plt.grid(True)
# plt.yscale('log')
# plt.savefig('top100.png')
# fig, ((ax1, ax2), (ax3,ax4)) = plt.subplots(2, 2, figsize=(7, 5), sharey=True)
fig, ax = plt.subplots(1, 1, figsize=(5, 3), sharey=True)

import scipy.stats as st
for r, ax, df in zip([num_runs[-1]], [ax], [selected_dfs[-1]]):
    df.to_csv("tmp_small.csv")
    vals = (df["Report_blink-minh-base-mate60_small_instr"] - df['nins']).dropna().values
    print(vals)
    mean = np.mean(vals)
    sem = st.sem(vals)
    l,h = st.norm.interval(0.95, loc=mean, scale=sem)
    print(mean)
    print(np.median(vals))
    print(l,h)
    print(len(vals))
    # print((df["Report_blink-minh-base-mate60_small_instr"] - df['nins']).median())

    # df = df.sort_values(by='Report_blink-minh-base-mate60_small_isb_half_instr_tight2', ascending=True)
    # x = np.arange(len(df))
    
    # ax.scatter(
    #     df["Report_blink-minh-base-mate60_small_isb_half_instr_tight2"],
    #     df["Report_perf-minh-base-mate60-plain_instr"],
    #     label="#Total Instr - Hiperf", marker='o', s=4
    # )
    ax.scatter(
        # df["Report_blink-minh-base-mate60_small_isb_half_instr_tight2"],
        df["nins"],
        df["Report_blink-minh-base-mate60_small_instr"], marker='o', s=4
        )
    x = df["nins"]
    ax.scatter(x, x, color='red',
            label="y=x: perfect correlation", linewidth=1)
    # ax.plot(x, df["Report_blink-minh-base-mate60_small_isb_half_instr_tight2"], label="Blink Isb", marker='s', markersize=2)
    # ax.plot(x, , label="Perf", marker='s', markersize=2)
    # ax.plot(x, df["Report_perf-minh-base-mate60-plain_instr_20k"], label="Perf_20k", marker='x', markersize=2)

    # ax.plot(x, df["nins"], label="Radare", marker='s', markersize=2)

    # ax.plot(x, df["blink_base_pct"], label="Blink (base vs base)", marker='^')
    # ax.plot(x, df["blink_custom_pct"], label="Blink (custom vs custom)", marker='x')
    # CSV1 = "../blink/Report_blink-minh-base-mate60_small_instr/Camera_large_picture_view.csv"
    # CSV2 = "../blink/Report_blink-minh-base-mate60_small_isb_half_instr_tight2/Camera_large_picture_view.csv"
    # CSV3 = "../perf/Report_perf-minh-base-mate60-plain_instr/Camera_large_picture_view.csv"

    # ax.set_title(f"#perf runs {r}", loc='center')
    # plt.axhline(0, color='gray', linestyle='--')
    if r == 1:
        ax.set_ylabel("% diff (c-b)/b") 

    ax.set_xlabel("Ground Truth")
    ax.set_ylabel("# Instructions")
    ax.grid(True, alpha=0.4)
    # ax.set_yscale('log')
    # ax.set_xscale('log')
    # ax.set_ylim(-50,50)
plt.legend()
plt.tight_layout()
plt.savefig('small_function.png')
plt.savefig('small_function.pdf', format='pdf')
plt.clf()
