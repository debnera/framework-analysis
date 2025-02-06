#%%
import os
import os.path

import ujson as json

from utils import utils

"""
00: Configuration and imports

NOTE: If using DataSpell, or similar IDE, you may need to increase the maximum allowed memory usage.
- Larger datasets will cause the IDE to completely freeze with the default limit of 4GB ram.

Results are minimized by removing all columns with static values.
- This means that some dataframes might have different columns than other dataframes.
"""

# This script will process all zips located at the input_path
# input_path = "../../data/raw_datasets/8.8_ajot"
# input_path = "/home/anton/Downloads/ov-ajo"
# input_path = "../../data/raw_datasets/ov_vs_pytorch"
# output_path = "../../data/processed/ov_vs_pytorch/prom"
input_path = "../../data_warehouse/warehouse_7b/snapshots/"
output_path = "../../data_warehouse/minimized_warehouse_7b/"

run_in_parallel = False  # parallel execution might cause running out of memory
max_parallel_workers = 10  #

zip_files_list = utils.list_zip_files(input_path)

print("List of zip files:")
for zip_file in zip_files_list:
    print(zip_file)
#%%
"""
01: Helper functions
"""

import json
import zipfile
import pandas as pd
import time
import utils.prometheus_processing as prom_util
from concurrent.futures import ProcessPoolExecutor

# Open the .7z file
def to_feather_sync(df: pd.DataFrame, path):
    # Save to feather as usual
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

def get_slices(zip_file, size_limit_mb):
    if zip_file.endswith(".zip"):
        with zipfile.ZipFile(zip_file, 'r') as zip_ref:
            items = zip_ref.namelist()
            json_files = [x for x in items if x.endswith('.json')]
            json_files_info = [(x, zip_ref.getinfo(x)) for x in json_files]
            json_files_info = sorted(json_files_info, key=lambda x: x[1].file_size, reverse=True)
    else:
        print(f"Cannot parse {zip_file}")

    total_file_size = sum(info.file_size for _, info in json_files_info)
    slice_limit = size_limit_mb * 1024 * 1024  # 100MB in bytes
    slices = []
    current_slice = []
    current_size = 0

    for file_name, file_info in json_files_info:
        if current_size + file_info.file_size <= slice_limit:
            current_slice.append(file_name)
            current_size += file_info.file_size
        else:
            slices.append(current_slice)
            current_slice = [file_name]
            current_size = file_info.file_size

    if current_slice:
        slices.append(current_slice)

    return slices

def parse_slice(zip_file, slice):
    values_container = {}
    index = 0
    with zipfile.ZipFile(zip_file, 'r') as zip_ref:
        for path in slice:
            size_in_megabytes = zip_ref.getinfo(path).file_size / (1024 * 1024)
            # print(f"\t{index}: {size_in_megabytes} MB, {path}")
            index += 1
            with zip_ref.open(path) as json_file:
                parse_metric(json_file, path, values_container)

    values_df = pd.DataFrame(values_container).apply(pd.to_numeric,
                                                     errors='ignore')  # Move to numeric if possible, cutting off 90% of size
    return values_df


def get_folders(zip_file, size_limit_mb):
    if zip_file.endswith(".zip"):
        with zipfile.ZipFile(zip_file, 'r') as zip_ref:
            items = zip_ref.namelist()
            json_files = [x for x in items if x.endswith('.json')]
            folders = {}
            for file in json_files:
                folder = os.path.dirname(file)
                if folder not in folders:
                    folders[folder] = []
                folders[folder].append(file)
    else:
        print(f"Cannot parse {zip_file}")

    return list(folders.values())


def parse_metric(data, path, values_container):
    json_data = json.load(data)
    # print(path)

    # LOOP THROUGH EACH SUB-METRIC
    try:
        for item in json_data['data']['result']:
            header = json.dumps(item['metric']) # Use a tuple of the metric dictionary's items
            values = dict(item['values'])

            # ADD HEADER KEY TO VALUES DICT
            if header not in values_container:
                values_container[header] = {}
            values_container[header].update(values)

    except KeyError as e:
        print(f"KeyError occurred while parsing JSON file '{path}': {e}")
    except ValueError as e:
        print(f"ValueError occurred while parsing JSON file '{path}': {e}")
    except Exception as e:
        print(f"An unexpected error occurred while parsing JSON file '{path}': {e}")


def process_zip(input_path, zip_relative_path, output_path2, process_intermediate_only):
    dfs = []
    print(f"Processing {zip_relative_path}")
    zip_name = zip_relative_path.replace(".zip", "")  # Remove file-extension for now
    full_output_path = f"{output_path2}/{zip_name}".replace(" ", "")  # Strip whitespace
    intermediate_folder_path = f"{full_output_path}/intermediate"
    full_intermediate_df_path = f"{intermediate_folder_path}/full.feather"  # Combined df from all intermediate files
    processed_folder_path = f"{full_output_path}/"
    start_time = time.time()
    if not os.path.exists(full_intermediate_df_path):
        max_slice_size_mb = 200
        # slices = get_slices(f"{input_path}/{zip_relative_path}", max_slice_size_mb)
        slices = get_folders(f"{input_path}/{zip_relative_path}", max_slice_size_mb)
        for i, slice in enumerate(slices):
            os.makedirs(intermediate_folder_path, exist_ok=True)
            output_path = intermediate_folder_path + f"/{i}.feather"
            if os.path.exists(output_path):
                if process_intermediate_only:
                    print(f"Skipping intermediate {output_path} because it already exists")
                    continue
                else:
                    values = pd.read_feather(output_path)
                    print(f"Got intermediate file from {output_path}")
            else:
                # print(f"Parsing slice {i} of {len(slices)}")
                values = parse_slice(
                    zip_file=f'{input_path}/{zip_relative_path}',
                    slice=slice,
                )
                # values = values.apply(pd.to_numeric, errors='coerce')
                # print("got vals")
                values.reset_index(drop=False, inplace=True, names=["timestamp"])  # Reset to default index (in case of old pandas/pyarrow version)
                # print("reset index")
                unique_counts = values.nunique()
                static_columns = unique_counts[unique_counts <= 2].index
                values.drop(static_columns, axis=1, inplace=True)
                # print("drop static")
                if len(values) == 0:
                    # Cannot save empty dataframes - nothing to do here
                    continue
                try:
                    # values.to_feather(output_path)
                    to_feather_sync(values, output_path)
                    # print("sync-write to file")
                except Exception as e:
                    print(e)
                # print(f"Saved intermediate {output_path}")
            if not process_intermediate_only:
                values.index = values["timestamp"]
                values.drop(columns=["timestamp"], inplace=True)
                dfs.append(values)

            # if not process_intermediate_only:
            #     if len(dfs) == 0:
            #         dfs = [values]
            #     else:
            #         df = pd.merge(dfs[0], values, how="outer")
            #         print(f"Current size in memory: {df.memory_usage(deep=True).sum() / (1024 * 1024):.2f} MB (rows: {len(df)}, columns: {len(df.columns)})")
            #         dfs = [df]
            """ Old style: (probably removes data)
            if not process_intermediate_only:
                dfs.append(values)
                if len(dfs) > 2:
                    # Try to minimize memory usage
                    df = pd.concat(dfs, axis=1)
                    print(df.columns[df.columns.duplicated()])
                    print(f"Current size in memory: {df.memory_usage(deep=True).sum() / (1024 * 1024):.2f} MB")
                    df = df.loc[:,
                         ~df.columns.duplicated()]  # TODO: Does removing duplicates remove information? Happens probably at zip-file slice boundaries
                    print(f"Current size in memory: {df.memory_usage(deep=True).sum() / (1024 * 1024):.2f} MB")
                    dfs = [df]
                # print("append to dfs")
            """
        if process_intermediate_only:
            return
        try:
            # df = dfs[0]
            # df.index = df["timestamp"]
            # df.drop(columns=["timestamp"], inplace=True)
            df = pd.concat(dfs, axis=1)

        except Exception as e:
            # This can happen if the zip did not contain any prometheus data (e.g., it contains yolo-data only)
            print(e)
            return
        df = df.loc[:,
             ~df.columns.duplicated()]  # TODO: Does removing duplicates remove information? Happens probably at zip-file slice boundaries
        df = df.reset_index(drop=False, inplace=False, names=["timestamp"])  # Reset to default index (in case of old pandas/pyarrow version)
        # df.to_feather(intermediate_folder_path + f"/full.feather")
        to_feather_sync(df, intermediate_folder_path + f"/full.feather")
        df.index = df["timestamp"]
        df.drop(columns=["timestamp"], inplace=True)

        # print(f"Saved full df to {intermediate_folder_path}/full.feather")
    else:
        print(f"Got cached full df from {full_intermediate_df_path}")
        df = pd.read_feather(full_intermediate_df_path)
        return #TODO: Debug only

    # df.index = df["timestamp"]  # Re-add index (in case of old pandas/pyarrow version)

    # Split df by instance
    sub_dfs = prom_util.sub_df_by_instance(df)

    # Minimize headers and save each instance as separate file
    for instance, sub_df in sub_dfs.items():
        df_minimized = sub_df.copy()
        # df_minimized.index = df_minimized["timestamp"] # 
        # df_minimized.drop("index", axis=1, inplace=True)

        # Group headers by name
        grouped_by_name = {}
        for col in list(df_minimized.columns):
            header_dict = json.loads(col)
            name = header_dict["__name__"]
            if name not in grouped_by_name:
                grouped_by_name[name] = {}
            grouped_by_name[name][col] = header_dict

        # Minimize headers
        for feature_name, headers in grouped_by_name.items():
            non_match_count = 0
            try:
                descriptive_keys = prom_util.get_descriptive_keys(headers)
            except:
                # print(f"Non-matching keys: {feature_name}")
                non_match_count += 1
                continue
            if non_match_count > 0:
                # TODO: Does this mean that information is removed from the resulting dataframe or just a debug print?
                print(f"Non-matching keys: {non_match_count}")
            prom_util.remove_unnecessary_keys(df_minimized, headers, descriptive_keys)

        # Save df
        path = f"{processed_folder_path}"
        os.makedirs(path, exist_ok=True)
        # df_minimized = df_minimized.sort_index()  # Make sure the dataframe is sorted by timestamp
        # df_minimized.index = df_minimized["index"]
        df_minimized = df_minimized.sort_index().reset_index(drop=False, inplace=False, names=["timestamp"])
        # print(df_minimized.index)
        # df_minimized.to_feather(path + f"/{instance}.feather")
        to_feather_sync(df_minimized, path + f"/{instance}.feather")



def main():
    """
    02: Process and save dataframes
    """
    zips = utils.list_zip_files(input_path)
    print(zips)



    """ First process all intermediate files one-by-one to save memory (otherwise multithreading might fill up memory) """
    if run_in_parallel:
        with ProcessPoolExecutor(max_parallel_workers) as executor:
            futures = [executor.submit(process_zip, input_path, zip_name_full, output_path, True) for zip_name_full in zips]
            for future in futures:
                try:
                    future.result()
                except Exception as e:
                    print(f"Exception raised in parallel processing: {e}")
    else:
        for zip_name_full in zips:
            try:
                process_zip(input_path, zip_name_full, output_path, process_intermediate_only=True)
            except Exception as e:
                print(f"Exception raised in sequential processing: {e}")

    """ Then read all intermediate files to memory and combine them into one big dataframe per zip file """
    for zip_name_full in zips:
        try:
            process_zip(input_path, zip_name_full, output_path, process_intermediate_only=False)
        except Exception as e:
            print(f"Exception raised in sequential processing: {e}")

#%%
def print_statistics():
    """
    03: Print some statistics from the resulting dataframes

    - Mostly for quick sanity checking of the results
    """
    import os
    import pandas as pd

    def count_feather_files(fpath):
        feather_files = []
        file_info = []
        for root, dirs, files in os.walk(fpath):
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

        for info in file_info:
            print("Size:", info[1] / 10**6, "mb", end="\t")
            print("Cols:", info[2], end="\t")
            print("Rows:", info[3], end="\t")
            print("File:", info[0].replace(fpath, ""))

    # Provide the path to the folder containing the feather files
    count_feather_files(output_path)
#%%
if __name__ == '__main__':
    main()
    print_statistics()