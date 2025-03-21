#%%
import multiprocessing
import os
import os.path
from functools import partial

import ujson as json
from typing import List, Tuple, Dict

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
input_path = "../../data_warehouse/warehouse_5b/snapshots/"
output_path = "../../data_warehouse/minimized_warehouse_5b/"
namespace_filter = "workload"  # Ignore all namespaces that do not have this string in it
use_column_filtering = False
run_in_parallel = True  # parallel execution might cause running out of memory
print_columns = False
max_parallel_workers = 20  #

zip_files_list = utils.list_zip_files(input_path)

print("List of zip files:")
for zip_file in zip_files_list:
    print(zip_file)

def parse_slice_to_dict(zip_file: str, slice: List[str], debug_prints=False) -> Dict[str, dict]:
    """
    From the given zip-file, parse a set (slice) of metrics into a dict.

    Dict format is expected to be a dict of dicts. Example:
        values_container[metric_header] = {timestamp: value}
    """
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
                a, b = parse_metrics_from_json(json_file, path, values_container)
                filtered_out += a
                no_namespace += b
        if debug_prints:
            print(f"\nFiltered out: {filtered_out}, no namespace: {no_namespace}")

    return values_container

def metrics_dict_to_dataframe(values_container: Dict[str, dict]) -> pd.DataFrame:
    """
    Create dataframes from dict one metric at a time.

    Dict format is expected to be a dict of dicts. Example:
        values_container[metric_header] = {timestamp: value}
    """
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
    return values_df


def parse_metrics_from_json(data: bytes, path: str, values_container: dict) -> Tuple[int, int]:
    """
    Parses

    Dict format is expected to be a dict of dicts. Example:
        values_container[metric_header] = {timestamp: value}
    """
    json_data = json.load(data)
    # print(path)

    # LOOP THROUGH EACH SUB-METRIC
    filtered_out = 0
    no_namespace = 0
    try:
        for item in json_data['data']['result']:
            header = json.dumps(item['metric']) # Use a tuple of the metric dictionary's items
            # Filter out if possible:
            if use_column_filtering:
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


def process_single_intermediate_slice(input_zip_path: str, intermediate_folder_path: str, slice_info: tuple
                                      ):
    """
    Process a single slice and save to intermediate file

    Args:
        input_zip_path (str): Path to the input zip file
        intermediate_folder_path (str): Path to save intermediate files
        i (int): Slice index
    """
    i, slice = slice_info
    output_path = os.path.join(intermediate_folder_path, f"{i}.feather")

    # Check if file already exists
    if os.path.exists(output_path):
        print(f"Skipping intermediate {i} because it already exists {output_path}")
        return

    try:
        # Process slice
        values_container = parse_slice_to_dict(input_zip_path, slice, debug_prints=False)
        values = metrics_dict_to_dataframe(values_container)

        # Preprocessing
        values.reset_index(drop=False, inplace=True, names=["timestamp"])
        unique_counts = values.nunique()
        static_columns = unique_counts[unique_counts <= 2].index
        values.drop(static_columns, axis=1, inplace=True)

        # Save to disk
        if len(values) > 0:
            dataframe_utils.to_feather_sync(values, output_path)
    except Exception as e:
        print(f"Error processing slice {i}: {e}")


def create_intermediate_files(input_zip_path: str, intermediate_folder_path: str):
    """
    Parallelize creation of intermediate files

    Args:
        input_zip_path (str): Path to the input zip file
        intermediate_folder_path (str): Path to save intermediate files
    """
    print(f"\nProcessing {input_zip_path}")
    os.makedirs(intermediate_folder_path, exist_ok=True)

    # Get slices
    slices = slice_utils.get_slices_by_folder(input_zip_path)

    # Determine number of workers
    max_workers = max_parallel_workers if run_in_parallel else 1

    # Prepare partial function with fixed arguments
    process_slice_func = partial(process_single_intermediate_slice, input_zip_path, intermediate_folder_path)

    # Use Pool for parallel processing
    with multiprocessing.Pool(processes=max_workers) as pool:
        pool.map(process_slice_func, enumerate(slices))


def get_intermediate_files(intermediate_folder_path: str) -> List[pd.DataFrame]:
    print(f"Merging intermediate files from {intermediate_folder_path}...")
    dfs = []
    feather_files = [file for file in os.listdir(intermediate_folder_path) if file.endswith('.feather')]
    for feather_file in feather_files:
        file_path = os.path.join(intermediate_folder_path, feather_file)
        df = pd.read_feather(file_path)

        # Preprocess, unsure if needed?
        df.index = df["timestamp"]
        df.drop(columns=["timestamp"], inplace=True)
        dfs.append(df)
    dataframe_utils.print_combined_size_dataframes(dfs)
    return dfs

def split_full_dataframe_by_instances(df, save_folder_path):
    print(f"Splitting full dataframe by instance (e.g., by worker node) {save_folder_path}...")
    df.index = df["timestamp"]
    df.drop(columns=["timestamp"], inplace=True)

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
        path = f"{save_folder_path}"
        os.makedirs(path, exist_ok=True)
        # df_minimized = df_minimized.sort_index()  # Make sure the dataframe is sorted by timestamp
        # df_minimized.index = df_minimized["index"]
        df_minimized = df_minimized.sort_index().reset_index(drop=False, inplace=False, names=["timestamp"])
        # print(df_minimized.index)
        # df_minimized.to_feather(path + f"/{instance}.feather")
        dataframe_utils.to_feather_sync(df_minimized, path + f"/{instance}.feather")


def process_zip(input_path: str, zip_relative_path: str, output_path: str, process_intermediate_only: bool) -> None:

    # Construct paths
    print(f"\nProcessing {zip_relative_path}")
    zip_name = zip_relative_path.replace(".zip", "")  # Remove file-extension for now
    zip_file_path = f"{input_path}/{zip_relative_path}"
    full_output_path = f"{output_path}/{zip_name}".replace(" ", "")  # Strip whitespace
    intermediate_folder_path = f"{full_output_path}/intermediate"

    # Check if we have already processed this zip
    full_intermediate_df_path = f"{intermediate_folder_path}/full.feather"  # Combined df from all intermediate files
    if os.path.exists(full_intermediate_df_path):
        print(f"Skipping previously processed zip {input_path} as full df already exists: {full_intermediate_df_path}")
        return

    # Process raw json files to separate dataframes
    if process_intermediate_only:
        create_intermediate_files(zip_file_path, intermediate_folder_path)
        return

    # Combine dataframes
    dfs = get_intermediate_files(intermediate_folder_path)
    try:
        df = pd.concat(dfs, axis=1)
    except Exception as e:
        # This can happen if the zip did not contain any prometheus data (e.g., it contains yolo-data only)
        print(e)
        return

    # Preprocess and save full feather
    df = df.loc[:,
         ~df.columns.duplicated()]  # TODO: Does removing duplicates remove information? Happens probably at zip-file slice boundaries
    df = df.reset_index(drop=False, inplace=False, names=["timestamp"])  # Reset to default index (in case of old pandas/pyarrow version)
    dataframe_utils.to_feather_sync(df, intermediate_folder_path + f"/full.feather")

    # Further process to separate files by instance (e.g., per each worker node)
    split_full_dataframe_by_instances(df, full_output_path)



def main() -> None:
    """
    02: Process and save dataframes
    """
    zips = utils.list_zip_files(input_path)
    print(zips)



    """ First process all intermediate files one-by-one to save memory (otherwise multithreading might fill up memory) """
    for zip_name_full in zips:
        try:
            process_zip(input_path, zip_name_full, output_path, process_intermediate_only=True)
        except Exception as e:
            print(f"Exception raised in sequential processing: {e}")
            import traceback
            traceback.print_exc()

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

