import os
from typing import List

import pandas as pd

def print_feather_file_stats(folder_path, print_limit=20):
    """
    Print some statistics from the resulting dataframes

    - Mostly for quick sanity checking of the results
    """
    import os
    import pandas as pd


    feather_files = []
    file_info = []
    for root, dirs, files in os.walk(folder_path):
        for file in files:
            if file.endswith(".feather"):
                file_path = os.path.join(root, file)
                feather_files.append(file_path)

    for file_path in feather_files:
        try:
            df = pd.read_feather(file_path)
            file_size = os.path.getsize(file_path)
            file_info.append((file_path, file_size, len(df.columns), len(df)))
        except pd.errors.EmptyDataError:
            file_info.append((file_path, 0, 0, 0))
        except Exception as e:
            file_info.append((file_path, -1, -1, -1))

    file_info.sort(key=lambda x: x[1], reverse=True)  # Sort based on file size in descending order

    for i, info in enumerate(file_info):
        print("Size:", info[1] / 10**6, "mb", end="\t")
        print("Cols:", info[2], end="\t")
        print("Rows:", info[3], end="\t")
        print("File:", info[0].replace(folder_path, ""))
        if i >= print_limit:
            print(f"Printed only the first {print_limit} of {len(file_info)} files.")
            break


def to_feather_sync(df: pd.DataFrame, path):
    """ Save feather file to disk synchronously as an attempt to avoid memory issues. """
    if len(df) == 0:
        print(f"Cannot save empty dataframe! {path}")
        return
    path = path.replace(":", "-")  # Saving with names like 10.192.33.1:3000 fail because of the port number
    memory_size = df.memory_usage(deep=True).sum() / (1024 * 1024)  # Convert bytes to MB
    df.to_feather(path)
    print(f"Saved {path} (df size in memory: {memory_size:.2f} MB, rows: {len(df)}, columns: {len(df.columns)})")
    # Force OS to write the file to disk (multithreaded writing seems to fully fill memory without this)
    with open (path, "rb+") as f:
        os.fsync(f.fileno())
    # print(f"Verified that {path} is saved on disk.")


def safe_to_numeric(series):
    """ Wraps to_numeric() in a try-except block, because the ignore errors parameter is deprecated in pandas. """
    try:
        return pd.to_numeric(series)
    except (ValueError, TypeError):
        return series

def print_combined_size_dataframes(dfs: List[pd.DataFrame]) -> None:
    total_size = sum(df.memory_usage(deep=True).sum() for df in dfs)  # Get size in bytes
    total_size_mb = total_size / (1024 * 1024)  # Convert to MB
    print(f"Combined size of DataFrames: {total_size_mb:.2f} MB")