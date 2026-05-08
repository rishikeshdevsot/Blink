import pandas as pd

dfs =  []
columns = {
    '': [],
    'num_sample': [],
    'nchildren': [],
    'call': [],
    'call.num_sample': []
}

for profile in 'base', 'custom':
    df = pd.read_csv(f'Report_mate70-blink-minh-{profile}-white-isb-sample_lock/Camera_large_picture_view.csv')
    df.set_index('fun', inplace=True)
    runs = []
    for i in range(11, 61):
        runs.append(f'{i}')
    new_columns = []
    for k in columns:
        if k != '':
            columns[k]  = list(map(lambda x: f'{k}.{x}', runs))
        else:
            columns[k]  = runs
        n_k = f'{profile}.{k}' if k !='' else f'{profile}'
        new_columns.append(n_k)
        df[n_k] = df[columns[k]].mean(axis=1)
    dfs.append((df[new_columns]))

final = pd.concat(dfs, axis=1)
final.to_csv('test.csv')
