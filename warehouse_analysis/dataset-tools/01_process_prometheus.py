#%%
import os
import os.path
import traceback
import zipfile
import time
import utils.prometheus_processing as prom_util
from concurrent.futures import ProcessPoolExecutor
from utils import utils, dataframe_utils, slice_utils

import ujson as json

import pandas as pd
from typing import Dict, Any, List



"""
00: Configuration and imports

NOTE: If using DataSpell, or similar IDE, you may need to increase the maximum allowed memory usage.
- Larger datasets will cause the IDE to completely freeze with the default limit of 4GB ram.

Results are minimized by removing all columns with static values.
- This means that some dataframes might have different columns than other dataframes.
"""


input_path = "../../data_warehouse/warehouse_6b/snapshots/"
output_path = "../../data_warehouse/minimized_warehouse_6b/"

run_in_parallel = True  # parallel execution might cause running out of memory
max_parallel_workers = 5  #

zip_files_list = utils.list_zip_files(input_path)

print("List of zip files:")
for zip_file in zip_files_list:
    print(zip_file)

def parse_slice(zip_file: str, slice: List[str]) -> pd.DataFrame:
    values_container = {}
    index = 0
    with zipfile.ZipFile(zip_file, 'r') as zip_ref:
        for path in slice:
            size_in_megabytes = zip_ref.getinfo(path).file_size / (1024 * 1024)
            # print(f"\t{index}: {size_in_megabytes} MB, {path}")
            index += 1
            with zip_ref.open(path) as json_file:
                parse_metric(json_file, path, values_container)

    values_df = pd.DataFrame(values_container).apply(dataframe_utils.safe_to_numeric)  # Move to numeric if possible
    return values_df

def parse_metric(data: Any, path: str, values_container: Dict[str, Dict[str, Any]]) -> None:
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


from typing import Any


def process_zip(input_path: str, zip_relative_path: str, output_path2: str, process_intermediate_only: bool) -> None:
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
        slices = slice_utils.get_slices_by_file_size(f"{input_path}/{zip_relative_path}", max_slice_size_mb)
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
                    dataframe_utils.to_feather_sync(values, output_path)
                    # print("sync-write to file")
                except Exception as e:
                    print(e)
                # print(f"Saved intermediate {output_path}")
            values.index = values["timestamp"]
            values.drop(columns=["timestamp"], inplace=True)
            dfs.append(values)
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

        # print(f"Saved full df to {intermediate_folder_path}/full.feather")
    else:
        print(f"Got cached full df from {full_intermediate_df_path}")
        df = pd.read_feather(full_intermediate_df_path)
        return #TODO: Debug only

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
        df_minimized = df_minimized.sort_index().reset_index(drop=False, inplace=False, names=["timestamp"])
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
                    traceback.print_exc()
    else:
        for zip_name_full in zips:
            try:
                process_zip(input_path, zip_name_full, output_path, process_intermediate_only=True)
            except Exception as e:
                print(f"Exception raised in sequential processing: {e}")
                traceback.print_exc()

    """ Then read all intermediate files to memory and combine them into one big dataframe per zip file """
    for zip_name_full in zips:
        try:
            process_zip(input_path, zip_name_full, output_path, process_intermediate_only=False)
        except Exception as e:
            print(f"Exception raised in sequential processing: {e}")
            traceback.print_exc()

#%%
if __name__ == '__main__':
    main()
    dataframe_utils.print_feather_file_stats(output_path)
