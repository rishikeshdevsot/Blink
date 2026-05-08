import sys
import matplotlib
import re
import pandas as pd
import matplotlib.pyplot as plt
import numpy as np
import seaborn as sns
# import scipy.stats as scipy_stats
# from sklearn.linear_model import LinearRegression
import statsmodels.api as sm


clone_pat = re.compile(r"\[clone \.llvm\.\d+\]")



def strip_templates(sig: str) -> str:
    result = []
    depth = 0
    for c in sig:
        if c == '<':
            depth += 1
            if depth == 1:
                result.append('<')  # keep outer <>
        elif c == '>':
            if depth == 1:
                result.append('>')
            depth -= 1
        else:
            if depth == 0:
                result.append(c)
    return ''.join(result)


def clean_signature(sig):
    return sig
    # remove [clone .llvm...]
    sig = clone_pat.sub("", sig)
    sig = strip_templates(sig)
    # normalize whitespace
    sig = re.sub(r"\s+", " ", sig).strip()
    return sig

# Example: 8 workloads × 10 measurements
# Rows = workloads, Columns = Run1...Run10
# INPUT1='../perf/report_render_ohos_4000/combined.csv'

# INPUT1='../blink/report_blink/combined.csv'
INPUT1="../perf/Report_ohos5_perf_fixed_user/combined.csv"
# INPUT1='../blink/report_blink/combined.csv'
INPUT2='../blink/Report_blink_cycle_user_final/combined.csv'
# INPUT2='../perf/Report_ohos5_perf_fixed_user_f8000/combined.csv'
INPUT3='./Report_ohos5_perf_fixed_user_f8000/combined.csv'
INPUT4='./Report_ohos5_perf_fixed_user_f30k/combined.csv'
# INPUT3="../perf/report_render_ohos_fixed/combined.csv"
# INPUT1='../perf/report_render/combined.csv'
# INPUT_SELF="../perf/Report_ohos5_perf_fixed_user_self/combined.csv"

# INPUT1='./report_render_micro/combined.csv'

OUTPUT='full_perf.png'
LIB='/system/lib64/librender_service_base.z.so'

N = 10

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
    df_total = load_data_total(INPUT)
    df_render = load_data_lib(INPUT, lib)
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
    '''
    load metadata for perf
    '''
    df = pd.read_csv(inp)[['key', 'total_samples',
                           'total_periods',
                            f'{lib}.period', f'{lib}.sample']]
    shorten(df, 'key')
    df = df.groupby(['key']).mean().reset_index()
    df['avg_sample_period'] = df['total_periods'] / df['total_samples']


    blink_data = load_data_and_get_stats(INPUT2, LIB, True)
    blink_data = blink_data.groupby(['key'])[['mean', 'sample_mean']].sum()
    blink_data['avg_sample_period'] = blink_data['mean'] / blink_data['sample_mean']

    final = pd.merge(df, blink_data, on=['key'])
    final.to_csv('perf_blink_metadata.csv')
    return final


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


# INPUT1_METADATA = "../perf/Report_ohos5_perf_fixed_user/combined_metadata.csv"
# load_metadata(INPUT1_METADATA, LIB)

# sys.exit(0)


def load_data_all_func(inp, is_num_sample, is_histogram, inp2=None, tool_name="perf"):
    stats = load_data_and_get_stats(inp, is_num_sample)
    workloads = stats['key'].unique()
    functions = stats['fun'].unique()
    function_map = {}
    for i,f in enumerate(functions):
        function_map[f] = i + 1
    stats['fun_key'] = stats['fun'].apply(lambda x: function_map[x])

    fig, axes = plt.subplots(3, len(workloads)//3, figsize=(15,12), sharey=True)
    axes_flat = [j for i in axes for j in i]
    if is_histogram:

        for ax, w in zip(axes_flat, workloads):
            print(ax, w)
            data = stats[(stats["key"] == w)]
            data.reset_index(inplace=True)
            # data = data[data['count'] >= 25]
            ax.hist(
                data["count"],
                bins=np.arange(0,N+1) + 0.5, alpha=0.5
            )
            ax.set_title(w)


    else: # fig.tight_layout()
         for ax, w in zip(axes_flat, workloads):
            print(ax, w)
            data = stats[(stats["key"] == w)]
            data.reset_index(inplace=True)
            # data = data[data['count'] >= 25]
            ax.errorbar(
                x=data['fun_key'],
                y=data["mean"],
                yerr=data["std"],
                fmt='x',              # circle markers
                capsize=2,
                markersize=2,
                linestyle="none",     # no connecting lines
                color="tab:blue"
            )
            ax.set_yscale('log')

            ax.set_title(w)
        # fig.tight_layout()
    # fig.ylabel("#cycle (millions)")
    if is_num_sample:
        axes[0,0].set_ylabel("#sample")
        # axes[2,3].set_xlabel("function ID")
        fig.suptitle(f'{tool_name}: #samples and stdev per function (librender_base)')
        filename=f'{tool_name}_numsample_function.png'

    elif is_histogram:
        axes[0,0].set_ylabel("number of functions")
        # axes[2,3].set_xlabel("occurence of a sampled function in 50 run")
        fig.suptitle(f'{tool_name}: Histogram showing the occurence of functions across runs in librender_base')
        filename=f'{tool_name}_histogram_function.png'
    else:
        axes[0,0].set_ylabel("#cycle")
        # axes[2,3].set_xlabel("function ID")
        fig.suptitle(f'{tool_name}: #cycles and stdev per function (librender_base)')
        filename=f'{tool_name}_numcycle_function.png'

    fig.savefig(filename, bbox_inches='tight')




def load_data_all_merge(inp, is_num_sample, is_histogram,
                        inp2=None, tool_name='perf', top=None,
                        show_stdev=False, minh=False,
                        full_stdev=False, xy=False, bland_altman=False):
    stats1 = load_data_and_get_stats(inp, LIB, is_num_sample)
    stats2 = load_data_and_get_stats(inp2, LIB, is_num_sample)
    stats3 = load_data_and_get_stats(INPUT3, LIB, is_num_sample)
    stats4 = load_data_and_get_stats(INPUT4, LIB, is_num_sample)

    print(f"{inp}: {stats1['mean'].sum()}")
    print(f"{inp2}: {stats2['mean'].sum()}")
    # stats_self = load_data_and_get_stats(INPUT_SELF, LIB, is_num_sample)


    stats = pd.merge(stats1, stats2, how='outer',
                left_on=['fun', 'key',],
                right_on=['fun', 'key'],
                suffixes=['', '.blink']
            )
    stats = pd.merge(stats, stats3, how='outer',
                left_on=['fun', 'key',],
                right_on=['fun', 'key'],
                suffixes=['', '.perf8k']
            )
    stats = pd.merge(stats, stats4, how='outer',
                left_on=['fun', 'key',],
                right_on=['fun', 'key'],
                suffixes=['.perf4k', '.perf30k']

            )
    workloads = stats['key'].unique()
    stats.to_csv("tmp_converage.csv")
    print(workloads)
    print(stats)
    fun_unique_per_key = []


    # functions = stats['fun'].unique()
    # function_map = {}
    # for i,f in enumerate(functions):
    #     function_map[f] = i + 1
    # stats['fun_key'] = stats['fun'].apply(lambda x: function_map[x])

    fig, axes = plt.subplots(3, len(workloads)//3, figsize=(4,5), sharey=True, sharex=True)
    axes_flat = [j  for i in axes for j in i]
    if True:
        for i, (ax, w) in enumerate(zip(axes_flat, workloads)):
            print(ax, w)
            data = stats[(stats["key"] == w)]
            print
            fun_data = {
                # 'perf': data[data['sample'] == ]['fun'].unique(),
                'perf@f=4kHz': data['count.perf4k'].count(),
                'perf@f=8kHz': data['count.perf8k'].count(),
                'perf@f=30kHz': data['count.perf30k'].count(),
                'blink': data['count.blink'].count(),
                'total': data['fun'].count(),
            }
            # fun_df = pd.DataFrame({key: pd.Series(value)
            #                        for key, value in fun_data.items()})
            # unique_funs = fun_df[['perf','blink', 'both']].count().to_dict()
            fun_data['key'] = w
            fun_unique_per_key.append(fun_data)

    plt.figure(figsize=(6,5))
    unique_fun_df = pd.DataFrame(fun_unique_per_key)
    print(unique_fun_df)
    # sys.exit(0)

    x = np.arange(len(unique_fun_df['key']))
    width = 0.6  # bar width


    # Bars
    cols = list(unique_fun_df.columns)
    cols.remove('total')
    cols.remove('key')
    for label, loc in zip(cols, [x + width/4 * i for i in range(-2,2)]):
        plt.bar(loc, unique_fun_df[label], width/4, label=label)
    blink_pct = (unique_fun_df['blink']/unique_fun_df['total']).values

    print('blink', (unique_fun_df['blink']/unique_fun_df['total']).mean())
    print('4kHz', (unique_fun_df['perf@f=4kHz']/unique_fun_df['total']).mean())
    print('8kHz', (unique_fun_df['perf@f=8kHz']/unique_fun_df['total']).mean())
    print('30kHz', (unique_fun_df['perf@f=30kHz']/unique_fun_df['total']).mean())

    # print(blink_pct)
# # Add percentage labels
    for i in range(len(x)):
        # plt.scatter(x, unique_fun_df['total'],
                #  marker='_',
                #  label='combined # unique functions')
        plt.text(x[i] + width/3 , unique_fun_df['blink'].values[i] + 0.1,
                 f"{100 * blink_pct[i]:.0f}%",
                ha='center', va='bottom')
        # plt.text(x[i] + width/2 + .125, perf[i]  + 0.01, f"{perf_pct[i]:.0f}%",
        #         ha='center', va='bottom')

    # plt.bar(unique_fun_df['key'], unique_fun_df['blink'], label='Blink regular')
    # plt.bar(unique_fun_df['key'], unique_fun_df['both'], bottom=unique_fun_df['blink'], label='Both')
    # plt.bar(unique_fun_df['key'], unique_fun_df['perf'], bottom=unique_fun_df['both'] + unique_fun_df['blink'], label='Perf record')
    plt.xticks(x, unique_fun_df['key'])
    plt.xlabel('Workloads')
    plt.ylabel('# unique functions')
    # plt.title('Function Category Counts per Iteration')
    # plt.xticks(x, [f'Run {i+1}' for i in x])
    # plt.legend(
    #     loc='lower center',
    #     bbox_to_anchor=(0.05, 1.02),
    #     ncol=2,
    #     frameon=False
    # )
    plt.legend()
    plt.xticks(rotation=45)
    plt.tight_layout(pad=0.3)
    plt.savefig("unique_functions.png")
    plt.savefig('unique_functions.pdf')



    fig.clf()
    fig, axes = plt.subplots(3, len(workloads)//3, figsize=(15,12), sharey=True)
    axes_flat = [j for i in axes for j in i]

    for ax, w in zip(axes_flat, workloads):
        # print(ax, w)
        data = stats[(stats["key"] == w)]
        if top:
            data = data.sort_values(by=['mean_y'], ascending=[False])
            data = data.iloc[:top]
        elif minh:
            known_functions = pd.read_csv('functions.csv')
            data = pd.merge(data, known_functions, how='inner',
                            left_on=['fun'],
                            right_on=['fun']
            )
        data.reset_index(inplace=True)
        # data.to_csv(w.replace('/', '_') + '.csv')
        # print(w)
        # print(data[['mean_x', 'mean_y']].sum())
        ax.set_yscale('symlog')
        # ax.set_ylim(-100, 100)
        # data = data[data['count'] >= 25]
        perf_error = data['std_x']
        blink_error = data['std_y']
        # data["stddiff"] = data["std_x"] + data["std_y"]
        data["meandiff"] = data["mean_y"] - data["mean_x"]
        # data["meandiffp"] = data["meandiff"] / data['mean_x']
        # data["stddiffp"] = data["stddiff"] / data["meandiff"]

        # print(data['meandiff']/ data['mean_x'])
        ax.errorbar(
                x=data['fun_key'],
                y=100*data["meandiff"] / data["mean_x"],
                yerr=None,
                fmt='.',              # circle markers
                capsize=2,
                markersize=2,
                linestyle="none",     # no connecting lines
                color="tab:blue"
        )
    if top:
        label = f"_top_{top}_blink"
    else:
        label = ''
    if is_num_sample:
        measurement = "#samples"
    else:
        measurement = "cycle"

    fig.suptitle(f'%difference in {measurement} (blink-perf)/perf, {label}')
    fig.savefig(f"diff{label}_{measurement}.png", bbox_inches='tight')

def old():
    pass
    # unique_workloads = og_df['key'].unique()
    # print(unique_workloads)
    # count = pd.DataFrame()
    # avg = pd.DataFrame()
    # std_dev = pd.DataFrame()
    # for w in unique_workloads:
    #     df = og_df[ og_df['key'] == w ][columns].copy()
    #     df.reset_index(drop=True, inplace=True)
    #     print(df)
    #     count[w] = df.notna().sum(axis=1)
    #     avg[w] = df.avg(axis=1)
    #     std_dev[w] = df.std(axis=1) / avg[w]
    #     print(count)
    #     # print(count.T)
    # count.hist(figsize=(10, 6))
    #     # plt.ylabel("Number of Occurence")
    #     # plt.xlabel("number of time a function is sampled (out of 50)")
    #     # plt.title(f"Perf: Histogram of occurences for function in render_service_base.z.so N={N}")
    #     # plt.xticks(rotation=45)
    # plt.tight_layout() # Adjust layout to prevent labels from being cut off
    # plt.savefig(f"perf_occurence.png")
    # plt.clf()

    # avg = a
    # std_dev = pd.D
if False:
    df = load_data_total(INPUT)
    print(df)
    df.T.boxplot(figsize=(10, 10))
    plt.ylabel("# Cycle")
    plt.title(f"Perf: #Cycle Total N={N}")
    plt.xticks(rotation=90)
    plt.tight_layout() # Adjust layout to prevent labels from being cut off
    plt.savefig("total_cycle.png")
    plt.clf()

    df = load_data_lib(INPUT, LIB)
    df.T.boxplot(figsize=(10, 10))
    plt.ylabel("# Cycle)")
    plt.title(f"Perf: librender_service_base.so #Cycle N={N}")
    plt.xticks(rotation=90)
    plt.tight_layout() # Adjust layout to prevent labels from being cut off
    plt.savefig("librender_service_base.png")


    df = compute_perc_lib(INPUT, LIB)
    # print(df)
    plt.clf()
    df.T.boxplot(figsize=(10, 10))
    plt.ylabel("% of total cycle")
    plt.title(f"Perf: {LIB} as % of total cycle N={N}")
    plt.xticks(rotation=90)
    plt.tight_layout() # Adjust layout to prevent labels from being cut off
    plt.savefig("librender_service_base_perc.png")


# sys.exit(0)
# print(load_data_all_func(INPUT1, True, False, None, 'perf'))
# print(load_data_all_func(INPUT1, False, False, None, 'perf'))
# print(load_data_all_func(INPUT1, False, True, None, 'perf'))

# print(load_data_all_func(INPUT2, True, False, None, 'blink'))
# print(load_data_all_func(INPUT2, False, False, None, 'blink'))
# print(load_data_all_func(INPUT2, False, True, None, 'blink'))


# print(load_data_all_merge(INPUT1, False, False, INPUT2,  top=-100, show_stdev=True))
# print(load_data_all_merge(INPUT1, True, False, INPUT2, top=100, show_stdev=True))
# print(load_data_all_merge(INPUT1, False, False, INPUT2, minh=True, show_stdev=True))
# print(load_data_all_merge(INPUT1, False, True, INPUT2, xy=True))

# print(load_data_all_merge(INPUT1, False, False, INPUT2, xy=True))
print(load_data_all_merge(INPUT1, False, False, INPUT2, bland_altman=False))

# print(load_data_all_merge(INPUT1, False, False, INPUT2, top=5))

# plot_per_lib(INPUT1, INPUT2, LIB)


sys.exit(0)
# print(df)
# print(df2)

# means = df.mean(axis=1)
# stds = df.std(axis=1)



print(df)
