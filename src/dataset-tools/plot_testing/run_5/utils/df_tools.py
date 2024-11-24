from typing import Tuple

import pandas as pd
import copy
import difflib

from .header_cleaner import clean_up_headers

"""
Functions related to handling training data and worker-related dataframes
"""

def get_dfs(path, minimize_headers=False) -> Tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """
    Reads a worker dataframe, converts 'total joules' to 'joules per second' and returns three dataframes.

    Output dataframes include
    - df without static columns (but includes monotonic values)
    - df with only monotonic values
        (This is useless, unless you transform these counters to rates, e.g., total joules to joules per second)
    - df without monotonic values (These values can be used for training as such)

    :param path: path to the worker dataframe
    :param minimize_headers: If true, uses header_cleaner to convert headers to a human-readable form
    :return df_without_static, df_monotonic, df_non_monotonic
    """
    df = pd.read_feather(path)
    if minimize_headers:
        df = clean_up_headers(df)

    # Fix start time to start from 0 instead of unix time
    start_time = df.index[0]
    df.index -= start_time

    # Interpret measurement interval in seconds
    measurement_interval = df.index[1] - df.index[0]

    # Find the best candidate for the power column
    target_word = 'kepler_node_package_joules_total_dynamic'
    closest_matches = difflib.get_close_matches(target_word, df.columns)
    print(f"The closest matches to '{target_word}' are: {closest_matches}")
    power_col = closest_matches[0]
    df["watts"] = df[power_col].diff() / measurement_interval
    df["watts"] = df["watts"].shift(-1)
    df = df.dropna(subset=['watts'])

    # Drop all rows with nans
    df = df.dropna(axis="index", how="all")  # Drop completely empty rows
    df = df.dropna(axis="columns", thresh=len(df.index)//2)  # Drop cols that are mostly empty

    # Find and drop all columns that have static values.
    static_columns = [column for column in df.columns if df[column].nunique() == 1]
    #pprint(f"The following columns have static values: {static_columns}")
    df.drop(columns=static_columns, inplace=True)

    # Find all monotonically increasing columns.
    # - These values might be accumulative and needs additional processing to be useful. (delta over time)
    # - Some of these values as simple timers (thus useless)
    # - For example, joules are shown as a cumulative sum since the start of the experiment.
    #  -- To get the energy consumption at given time, we need to compute the delta between consecutive rows
    monotonic_columns = [column for column in df.columns if df[column].is_monotonic_increasing]

    # Display the resulting list of columns.
    # pprint(f"The following columns are monotonically increasing: {monotonic_columns}")
    # print(len(monotonic_columns))
    df_monotonic = df[monotonic_columns]
    non_monotonic_columns = set(df.columns) - set(monotonic_columns)
    non_monotonic_columns = list(non_monotonic_columns)
    df_non_monotonic = df[non_monotonic_columns]
    return df, df_monotonic, df_non_monotonic


def get_non_monotonic(path, minimize_headers=False):
    return get_dfs(path, minimize_headers)[2]


class DatasetManager:
    """
    Can be used to slice a set of worker dataframes (e.g., worker1 to worker5) in different ways for training

    - Split to train and test by timestamp (e.g., first 6 hours is train data, final hour is test data)
    - Split to train and test randomly by given percentage (e.g., 80% train data, 20% test data,)
    """

    def __init__(self, data: dict[str: list[pd.DataFrame]]):
        """ Expected format is ["data1": [w0,w1,w2,...], "data2": [w0,w1,w2,...]]"""
        self.data = copy.deepcopy(data)

    def extract_datasets_by_timestamp(self, datasets: dict[str: list[int]], cutoff_timestamp):
        # Fetch and concat desired datasets as a single dataframe
        # e.g. datasets = {"data1": (1,2,3)} gets workers 2,3,4 from dataset named "data1"
        #
        # Splits to train and test sets by given cutoff_timestamp
        train_data = []
        test_data = []
        for name, worker_indices in datasets.items():
            for i in worker_indices:
                x = self.data[name][i].copy()
                x_train = x[x.index <= cutoff_timestamp]
                x_test = x[x.index > cutoff_timestamp]
                train_data.append(x_train)
                test_data.append(x_test)
        return pd.concat(train_data, ignore_index=True), pd.concat(test_data, ignore_index=True)

    def extract_datasets(self, datasets: dict[str: list[int]]):
        # Fetch and concat desired datasets as a single dataframe
        # e.g. datasets = {"data1": (1,2,3)} gets workers 2,3,4 from dataset named "data1"
        new_data = []
        for name, worker_indices in datasets.items():
            [new_data.append(self.data[name][i].copy()) for i in worker_indices]
        return pd.concat(new_data, ignore_index=True)

    def extract_percentage_wise(self, datasets, test_percentage, random_state) -> tuple[pd.DataFrame, pd.DataFrame]:
        # Fetch and concat desired datasets as a single dataframe
        # e.g. datasets = {"data1": (1,2,3)} gets workers 2,3,4 from dataset named "data1"
        #
        # Also splits the resulting dataframe to test and train sets according to given percentage
        full_df = self.extract_datasets(datasets)
        test_df = full_df.sample(frac=test_percentage, random_state=random_state)
        train_df = full_df.drop(test_df.index)
        return train_df, test_df

def get_training_columns(df, num_features, target_col):
    correlations = df.corrwith(df[target_col])
    best_col_candidates = correlations.nlargest(num_features+1).index.tolist()
    input_cols = list(set(best_col_candidates) - set([target_col]))
    assert correlations.isna().sum() < 5
    return input_cols



if __name__ == "__main__":
    # results = [get_dfs(f"../../../data_processed/worker{i+1}.feather") for i in range(5)]
    results = get_dfs(f"../../../data-intermediate/1706275648-8H-5S-SAMPLING/instances/worker5.feather", minimize_headers=True)
    print(results)
    print(list(("watts" in df.columns for df in results)))

#%%

#%%
