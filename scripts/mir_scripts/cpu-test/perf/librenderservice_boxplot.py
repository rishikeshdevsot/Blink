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
import statsmodels.api as sm

parser = argparse.ArgumentParser(
    description="Generate comparative plots of Blink vs Perf cycle counts per function."
)
parser.add_argument('--perf', default="../perf/Report_ohos5_perf_fixed_user/combined.csv",
                    help="Path to perf combined.csv (default: %(default)s)")
parser.add_argument('--blink', default="../blink/Report_blink_cycle_user_final/combined.csv",
                    help="Path to blink combined.csv (default: %(default)s)")
parser.add_argument('--output', default="full_perf.png",
                    help="Output plot filename (default: %(default)s)")
args = parser.parse_args()

INPUT1 = args.perf
INPUT2 = args.blink
OUTPUT = args.output


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

    print(f"{inp}: {stats1['mean'].sum()}")
    print(f"{inp2}: {stats2['mean'].sum()}")

    # stats_self = load_data_and_get_stats(INPUT_SELF, LIB, is_num_sample)


    stats = pd.merge(stats1, stats2, how='outer', indicator=True,
                left_on=['fun', 'key',],
                right_on=['fun', 'key']
            )


    workloads = stats['key'].unique()
    fun_unique_per_key = []


    # # sum up the total PMU count
    # for w in workloads:
    #     d1 = stats1[(w == stats1['key'])]['mean'].sum()
    #     d2 = stats2[(w == stats2['key'])]['mean'].sum()
    #     print(w, d1, d2)
    # matching_status = stats.groupby(['key', '_merge']).size().unstack(fill_value=0)
    # print(matching_status)


    # look into the hit ratio when merged:
    # func_stats = pd.merge(stats1, stats2,
    #                      how='outer', indicator=True,
    #                      on=['fun'])

    # perf_funs = left_only['fun'].unique()
    # blink_funs = right_only['fun'].unique()
    
    # with open('fun_notblink_perf.csv', 'w') as fd:
    #     for f in perf_funs:
    #         fd.write(f'"{f}"\n')
    # with open('fun_blink_notperf.csv', 'w') as fd:
    #     for f in blink_funs:
    #         fd.write(f'"{f}"\n')
    ##############

    functions = stats['fun'].unique()
    function_map = {}
    for i,f in enumerate(functions):
        function_map[f] = i + 1
    stats['fun_key'] = stats['fun'].apply(lambda x: function_map[x])
    
    all_r_stat = []

    fig, axes = plt.subplots(3, len(workloads)//3, figsize=(15,12), sharey=True, sharex=True)
    axes_flat = [j  for i in axes for j in i]
    if is_histogram:
        
        for ax, w in zip(axes_flat, workloads):
            # print(ax, w)
            data = stats[(stats["key"] == w)]
            data = data[(data['_merge'] == 'both') & (True)]
            data.reset_index(inplace=True)

            # data = data[data['count'] >= 25]
            ax.hist(
            [data["count_x"], data["count_y"]],
            bins=np.arange(0, N+1) + 0.5,
            alpha=0.8,
            # label=["count_x", "count_y"],
            histtype='bar',
            rwidth=1  # controls how wide each group’s bars are
            )
            ax.set_title(w) 
       
    else:
        for i, (ax, w) in enumerate(zip(axes_flat, workloads)):
            print(ax, w)
            data = stats[(stats["key"] == w)]
            fun_data = {
                'perf': data[data['_merge'] == 'left_only']['fun'].unique(),
                'blink': data[data['_merge'] == 'right_only']['fun'].unique(),
                'both': data[data['_merge'] == 'both']['fun'].unique()
            }
            fun_df = pd.DataFrame({key: pd.Series(value) 
                                   for key, value in fun_data.items()})
            unique_funs = fun_df[['perf','blink', 'both']].count().to_dict()
            unique_funs['key'] = w
            fun_unique_per_key.append(unique_funs)

            # print(fun_df.count())
            data[data['_merge'] == 'left_only']\
                        .to_csv(f"{w.replace('/', '_')}_fun_unique_perf.csv")
            data[data['_merge'] == 'right_only']\
                        .to_csv(f"{w.replace('/', '_')}_fun_unique_blink.csv")
            data[data['_merge'] == 'both']\
                        .to_csv(f"{w.replace('/', '_')}_fun_unique_both.csv")
            
            # fun_df.to_csv(f"{w.replace('/', '_')}_fun_unique.csv")

            if top:
                # data = data.sort_values(by=['mean_y'], ascending=[False])
                # data = data.iloc[:top]
                self_data_sorted = stats_self[stats_self["key"] == w] \
                                    .sort_values(by=['mean'], ascending=[False])
                if top > 0:
                    self_data_sorted = self_data_sorted[:top]
                else:
                    self_data_sorted = self_data_sorted[top:]

                data = pd.merge(self_data_sorted['fun'], data, how='inner', on =['fun'])

            elif minh:
                known_functions = pd.read_csv('functions.csv')
                data = pd.merge(data, known_functions, how='inner', on=['fun'])
            print(w)
            data.reset_index(inplace=True)
            # data.to_csv(w.replace('/', '_') + '.csv')
            # print(w)
            # print(data[['mean_x', 'mean_y']].sum())

            # data = data[data['count'] >= 25]
            perf_error = data['std_x']
            blink_error = data['std_y']
            if show_stdev:
                ax.errorbar(
                    x=data['fun_key'], 
                    y=data["mean_y"],
                    yerr=blink_error, 
                    fmt='.',              # circle markers
                    capsize=2, 
                    markersize=2,
                    linestyle="none",     # no connecting lines
                    color="tab:orange"
                )
                ax.errorbar(
                    x=data['fun_key'], 
                    y=data["mean_x"],
                    yerr=perf_error, 
                    fmt='.',              # circle markers
                    capsize=2, 
                    markersize=2,
                    linestyle="none",     # no connecting lines
                    color="tab:blue"
                )
                ax.set_yscale('log')

            elif full_stdev:
                ax.errorbar(
                    x=data['fun_key'], 
                    y=100 * blink_error / data['mean_y'],
                    fmt='.',              # circle markers
                    markersize=5,
                    linestyle="none",     # no connecting lines
                    color="tab:orange"
                )
                ax.errorbar(
                    x=data['fun_key'], 
                    y=100 * perf_error / data['mean_x'], 
                    fmt='.',              # circle markers
                    markersize=5,
                    linestyle="none",     # no connecting lines
                    color="tab:blue"
                )
                ax.set_yscale('linear')

            elif xy:
                plt.gray()
                perf_count_sum = data['count_x'].sum()
                blink_count_sum = data['count_y'].sum()

                # data = data[(data['_merge'] == 'both') & (data['count_x'] == 10)]
                data = data[(data['_merge'] == 'both')]
                # data = data[(data['count_x'] == 10.0)]
                X = data['mean_x']
                X = sm.add_constant(X)
                Y = data['mean_y']
                model = sm.OLS(Y, X).fit()
                print(model.params)
                
                
                # m,b = np.polyfit(data['mean_x'], data['mean_y'], 1)
                # model = LinearRegression(fit_intercept=True).fit()
                
                r_stat = {
                    'key': w,
                    'slope': model.params.mean_x,
                    'intercept': model.params.const,
                    'r2': model.rsquared,
                    '#perf': data['sample_mean_x'].sum(),
                    '#blink': data['sample_mean_y'].sum(),
                }
                all_r_stat.append(r_stat)
                
                x_line = np.logspace(2, 10, 100)

                # pred = model.get_prediction(X)
                # pred_summary = pred.summary_frame(alpha=.99)

                # print(pred_summary[["mean_ci_lower", "mean_ci_upper"]])

                y_line = x_line
                
                ax.plot(
                    x_line, y_line,
                    label='perfect correlation (y=x)', color='red',
                    linestyle='--', linewidth=1, alpha=.6
                )

                # ax.fill_between(x_line, pred_summary["mean_ci_lower"], pred_summary["mean_ci_upper"],
                #  color="green", alpha=1, label="95% CI")
                norm_std_diff = (data['std_x'] - data['std_y']) / (0.5 * (data['mean_x'] + data['mean_y']))
                sc = ax.scatter(
                        data['mean_x'],
                        data['mean_y'],
                        # c = N - data["count_x"],
                        # c=(data['std_x'] - data['std_y']) / (0.5 * (data['mean_x'] + data['mean_y'])),
                        # c=np.maximum(-1 * norm_std_diff, 0), 
                        c=norm_std_diff,
                        s=2,
                        alpha=.8,
                        cmap="viridis",
                )
                cbar = plt.colorbar(sc, ax=ax)
                cbar.set_label('Norm. std diff')

                # print(data['count_x'])

                ax.plot(
                    x_line, r_stat['intercept'] + r_stat['slope'] * x_line,
                    'pink', label='fitted line',
                    linewidth=1
                )
                # ax.set_ylim(1e3)
                # ax.set_xlim(1e3)

                ax.set_yscale('log')
                ax.set_xscale('log')
            elif bland_altman:
                data = data[(data['_merge'] == 'both')]
                x = data['mean_x']
                y = data['mean_y']
                diff = np.log10(y) - np.log10(x)
                mean = (np.log10(y) + np.log10(x)) / 2
                bias = np.mean(diff)
                sd = np.std(diff)

                # Normal Bland–Altman, plotted on log axes
                ax.scatter(mean, diff, s=1, alpha=0.5)
                ax.axhline(bias, color='r', linestyle='--', label=f'Bias = {bias:.2f}')
                ax.axhline(bias + 1.96*sd, color='gray', linestyle='--', label='+1.96 SD')
                ax.axhline(bias - 1.96*sd, color='gray', linestyle='--', label='-1.96 SD')
                # print('bias =', bias)
                # print('lower = ', bias - 1.96*sd)
                # ax.set_xscale('symlog')
                # ax.set_yscale('symlog')
            else:
                ax.errorbar(
                    x=data['fun_key'], 
                    y=data["mean_y"], 
                    yerr=None,
                    fmt='.',              # circle markers
                    capsize=2, 
                    markersize=2,
                    linestyle="none",     # no connecting lines
                    color="tab:orange"
                )
                ax.errorbar(
                    x=data['fun_key'], 
                    y=data["mean_x"],
                    yerr=None,
                    fmt='.',              # circle markers
                    capsize=2, 
                    markersize=2,
                    linestyle="none",     # no connecting lines
                    color="tab:blue"
                )
                ax.set_yscale('log')

            if i == 0:
                handles, labels = ax.get_legend_handles_labels()
                fig.legend(handles, labels, loc='upper center', fontsize=14)
            # plt.ylim(, 5)

            ax.set_title(w) 
        # fig.tight_layout()
    # fig.ylabel("#cycle (millions)")
            data.to_csv(w.replace('/','_') + '_cycle.csv', index=False)    
                
    if is_num_sample:
        axes[0,0].set_ylabel("#sample")
        # axes[2,3].set_xlabel("function ID")
        fig.suptitle(f'{tool_name}: #samples and stdev per function (librender_base)')
        filename='numsample_function_merge.png'

    elif is_histogram:
        axes[0,0].set_ylabel("number of functions")
        # axes[2,3].set_xlabel("occurrence of a sampled function in 50 run")
        fig.suptitle(f'{tool_name}: Histogram showing the occurence of functions across runs in librender_base')
        filename='histogram_function_merge.png'
    elif full_stdev:
        axes[0,0].set_ylabel("% standard dev")
        top_label = "top" + str(top) + 'blink' if top else ""
        fig.suptitle(f'{tool_name}: % stdev per function (librender_base) {top_label}')
        filename=f'stdev_function_merge_{top_label}.png'
    elif xy:
        filename='xy_function_merge.png'
    else:
        axes[0,0].set_ylabel("#cycle")
        # axes[2,3].set_xlabel("function ID")
        top_label = "top" + str(top) + 'blink' if top else ""
        fig.suptitle(f'{tool_name}: #cycles and stdev per function (librender_base) {top_label}')
        filename=f'numcycle_function_merge_{top_label}.png'

    fig.savefig(filename, bbox_inches='tight')
    fig.savefig(filename[:-3] + 'pdf', format="pdf", bbox_inches='tight')
    fig.clf()


    # print("fun_unique_per_key")
    # print(fun_unique_per_key)

    r_stat_df = pd.DataFrame(all_r_stat)
    print(r_stat_df)

    plt.figure(figsize=(7,5))
    unique_fun_df = pd.DataFrame(fun_unique_per_key)

    x = np.arange(len(unique_fun_df['key']))
    width = 0.35  # bar width

    # Values
    blink = unique_fun_df['blink'] +  unique_fun_df['both']
    perf  = unique_fun_df['perf'] + unique_fun_df['both']

    # Denominator for percentages (sum of all categories per key)
    total = unique_fun_df[['blink', 'both', 'perf']].sum(axis=1)

    # Percentages
    blink_pct = blink / total * 100
    perf_pct  = perf / total * 100

    # plt.figure(figsize=(10, 5))

    # Bars
    plt.bar(x - width/2, blink, width - .05, label='Blink')
    plt.bar(x + width/2, perf,  width - .05, label='Hiperf')

# # Add percentage labels
    for i in range(len(x)):
        plt.text(x[i] - width/2, blink[i] + 0.01, f"{blink_pct[i]:.0f}%", 
                ha='center', va='bottom')
        plt.text(x[i] + width/2 + .125, perf[i]  + 0.01, f"{perf_pct[i]:.0f}%", 
                ha='center', va='bottom')

    # plt.bar(unique_fun_df['key'], unique_fun_df['blink'], label='Blink regular')
    # plt.bar(unique_fun_df['key'], unique_fun_df['both'], bottom=unique_fun_df['blink'], label='Both')
    # plt.bar(unique_fun_df['key'], unique_fun_df['perf'], bottom=unique_fun_df['both'] + unique_fun_df['blink'], label='Perf record')
    plt.xticks(x, unique_fun_df['key'])
    plt.xlabel('Workloads')
    plt.ylabel('# of functions')
    # plt.title('Function Category Counts per Iteration')
    # plt.xticks(x, [f'Run {i+1}' for i in x])
    plt.legend()
    plt.xticks(rotation=45)
    plt.tight_layout()
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

print(load_data_all_merge(INPUT1, False, False, INPUT2, xy=True))
# print(load_data_all_merge(INPUT1, False, False, INPUT2, bland_altman=False))

# print(load_data_all_merge(INPUT1, False, False, INPUT2, top=5))

# plot_per_lib(INPUT1, INPUT2, LIB)


sys.exit(0)
# print(df)
# print(df2)

# means = df.mean(axis=1)
# stds = df.std(axis=1)



print(df)
