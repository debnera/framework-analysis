#%%
import os
import os.path

import ujson as json
from typing import List

from utils import utils, dataframe_utils, slice_utils

import zipfile
import pandas as pd
import time
import utils.prometheus_processing as prom_util
from concurrent.futures import ProcessPoolExecutor

"""
00: Configuration and imports

NOTE: If using DataSpell, or similar IDE, you may need to increase the maximum allowed memory usage.
- Larger datasets will cause the IDE to completely freeze with the default limit of 4GB ram.

Results are minimized by removing all columns with static values.
- This means that some dataframes might have different columns than other dataframes.
"""

# This script will process all zips located at the input_path
input_path = "../../data_warehouse/warehouse_6b/snapshots/"
output_path = "../../data_warehouse/minimized_warehouse_6bbb/"
namespace_filter = "workload"  # Ignore all namespaces that do not have this string in it
run_in_parallel = True  # parallel execution might cause running out of memory
print_columns = False
max_parallel_workers = 10  #

zip_files_list = utils.list_zip_files(input_path)

print("List of zip files:")
for zip_file in zip_files_list:
    print(zip_file)


def parse_slice(zip_file: str, slice: List[str], debug_prints=False) -> pd.DataFrame:
    values_container = {}
    index = 0

    # Parse metrics from json files to a dict
    with zipfile.ZipFile(zip_file, 'r') as zip_ref:
        if debug_prints:
            total_size = sum(zip_ref.getinfo(path).file_size for path in slice) / (1024 * 1024)  # Convert to MB
            parent_folder = os.path.dirname(slice[0])  # Get the parent directory of the first file
            print(f"Processing {parent_folder} (size: {total_size:.2f} MB, files {len(slice)})")
        filtered_out = 0
        no_namespace = 0
        for path in slice:
            print(f" {index}", end="")
            index += 1
            with zip_ref.open(path) as json_file:
                a, b = parse_metric(json_file, path, values_container)
                filtered_out += a
                no_namespace += b
        if debug_prints:
            print(f"\nFiltered out: {filtered_out}, no namespace: {no_namespace}")

    # Create dataframes from dict one metric at a time (NOTE: creating a df in one pass caused issues?)
    dfs = []
    for key, item in values_container.items():

        df = pd.DataFrame({key: item})
        df = df.apply(dataframe_utils.safe_to_numeric)  # Move to numeric if possible (reduces size)
        if print_columns:
            mem_usage_MB = df.memory_usage(deep=True).sum() / (1024 * 1024)
            num_values = len(item)
            print(f"n={num_values}, MB={mem_usage_MB:.2f}, col={key}")
        dfs.append(df)

    # Move to numeric if possible (reduces size)
    values_df = pd.DataFrame(values_container).apply(dataframe_utils.safe_to_numeric)

    if debug_prints:
        print("")
        print(f"values_df after cut size: {values_df.memory_usage(deep=True).sum() / (1024 * 1024):.2f} MB "
              f"(rows: {len(values_df)}, columns: {len(values_df.columns)})")
    return values_df





def parse_metric(data: bytes, path: str, values_container: dict) -> tuple[int, int]:
    json_data = json.load(data)
    # print(path)

    # LOOP THROUGH EACH SUB-METRIC
    filtered_out = 0
    no_namespace = 0
    try:
        for item in json_data['data']['result']:
            header = json.dumps(item['metric']) # Use a tuple of the metric dictionary's items
            # Filter out if possible:
            if "namespace" in item["metric"]:
                if namespace_filter not in item["metric"]["namespace"]:
                    filtered_out += 1
                    continue
            else:
                no_namespace += 1

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
    return filtered_out, no_namespace





def process_zip(
        input_path: str, zip_relative_path: str, output_path2: str, process_intermediate_only: bool
) -> None:
    dfs = []
    print(f"Processing {zip_relative_path}")
    zip_name = zip_relative_path.replace(".zip", "")  # Remove file-extension for now
    full_output_path = f"{output_path2}/{zip_name}".replace(" ", "")  # Strip whitespace
    intermediate_folder_path = f"{full_output_path}/intermediate"
    full_intermediate_df_path = f"{intermediate_folder_path}/full.feather"  # Combined df from all intermediate files
    processed_folder_path = f"{full_output_path}/"
    start_time = time.time()
    if not os.path.exists(full_intermediate_df_path):
        slices = slice_utils.get_slices_by_folder(f"{input_path}/{zip_relative_path}")
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
                    dataframe_utils.to_feather_sync(values, output_path)
                except Exception as e:
                    print(e)
                # print(f"Saved intermediate {output_path}")
            if not process_intermediate_only:
                values.index = values["timestamp"]
                values.drop(columns=["timestamp"], inplace=True)
                dfs.append(values)
                dataframe_utils.print_combined_size_dataframes(dfs)

        if process_intermediate_only:
            return
        try:
            df = pd.concat(dfs, axis=1)

        except Exception as e:
            # This can happen if the zip did not contain any prometheus data (e.g., it contains yolo-data only)
            print(e)
            return
        df = df.loc[:,
             ~df.columns.duplicated()]  # TODO: Does removing duplicates remove information? Happens probably at zip-file slice boundaries
        df = df.reset_index(drop=False, inplace=False, names=["timestamp"])  # Reset to default index (in case of old pandas/pyarrow version)
        # df.to_feather(intermediate_folder_path + f"/full.feather")
        dataframe_utils.to_feather_sync(df, intermediate_folder_path + f"/full.feather")
        df.index = df["timestamp"]
        df.drop(columns=["timestamp"], inplace=True)

    else:
        print(f"Got cached full df from {full_intermediate_df_path}")
        df = pd.read_feather(full_intermediate_df_path)

    # Split df by instance
    sub_dfs = prom_util.sub_df_by_instance(df)

    # Minimize headers and save each instance as separate file
    for instance, sub_df in sub_dfs.items():
        df_minimized = sub_df.copy()

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
        dataframe_utils.to_feather_sync(df_minimized, path + f"/{instance}.feather")


def main() -> None:
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
if __name__ == '__main__':
    main()
    dataframe_utils.print_feather_file_stats(output_path)

