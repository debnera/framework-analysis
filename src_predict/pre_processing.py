import json
import os
from typing import List

import pandas as pd

def find_subfolders_with_file(root_folder: str, filename: str) -> List[str]:
    result = []
    for root, dirs, files in os.walk(root_folder):
        if filename in files:
            result.append(root)
    return result

def try_load_json(column_json: str):
    try:
        return json.loads(column_json)
    except json.JSONDecodeError:
        return None

def rename_workers(column_json: str):
    # Affects key-pairs: "instance":"worker1"
    #
    # Rename instances (worker1,worker2,worker3,worker4,worker5) -> "worker"
    for i in range(1,6):
        column_json = column_json.replace("worker" + str(i), "worker")
    return column_json

def filter_namespaces(column_json: str):
    # Filter out key-pairs such as: "container_namespace":"kube-system"
    json_obj = try_load_json(column_json)
    # Accept all columns that cannot be parsed as json
    if json_obj is None:
        return True
    # Accept all columns that do not have a namespace
    if "container_namespace" not in json_obj:
        return True
    # If the column has namespace, accept only the "workloadb" namespace
    container_namespace: str = json_obj["container_namespace"]
    if container_namespace == "workloadb":  # All YOLO workload applications run under the "workloadb" namespace
        return True
    # Filter out all other namespaces
    return False

def filter_go_specific(column_json: str):
    # Filter out columns related to go-language garbage collection (e.g., go_memstats_last_gc_time_seconds)
    json_obj = try_load_json(column_json)
    # Accept all columns that cannot be parsed as json
    if json_obj is None:
        return True
    # Accept all columns, except go specific columns
    column_name: str = json_obj["__name__"]
    if not column_name.startswith("go_"):
        return True
    # Filter out all other namespaces
    return False

def filter_process_specific(column_json: str):
    # Filter out columns about kepler_process_*, since they have very specific process ids and container ids.
    # These processes are also included in the kepler_container.
    json_obj = try_load_json(column_json)
    # Accept all columns that cannot be parsed as json
    if json_obj is None:
        return True
    # Accept all columns, except process specific columns
    column_name: str = json_obj["__name__"]
    if not column_name.startswith("kepler_process_"):
        return True
    # Filter out all other namespaces
    return False

def filter_durations(column_json: str):
    # Filter out columns like:
    # - go_gc_duration_seconds_count
    # - go_gc_duration_seconds_sum
    # - node_scrape_collector_duration_seconds
    # - scrape_duration_seconds
    # - go_gc_duration_seconds

    json_obj = try_load_json(column_json)
    # Accept all columns that cannot be parsed as json
    if json_obj is None:
        return True
    # Accept all columns, columns with "duration"
    column_name: str = json_obj["__name__"]
    if "_duration_" not in column_name:
        return True
    # Filter out all other namespaces
    return False

def rename_container_columns(column_json: str):
    """
    Removes "container_id" and "pod_name" from the column JSON string.

    Example: {"__name__":"kepler_container_cpu_instructions_total","container_id":"e4f3637bcbcb4fa1db77b269c7a1eec025fce7bb982e38b4ba668804f371b90f","container_name":"yolo-consumer","container_namespace":"workloadb","instance":"worker","pod_name":"yolo-consumer-64478765c9-k5bvh"}
    """
    json_obj = try_load_json(column_json)
    # Do nothing if the column cannot be parsed as json
    if json_obj is None:
        return column_json

    # Remove "container_id" and "pod_name" key-value pairs
    json_obj.pop("container_id", None)
    json_obj.pop("pod_name", None)

    # Return the JSON object as a string
    return json.dumps(json_obj)

"""
Convert monontonically increasing cols to rates (e.g., total joules to joules per unit of time)
"""
def get_counters(df):
    return [col for col in df.columns if df[col].is_monotonic_increasing]

def convert_to_rates(df, counters):
    rate_dataframes = []
    for counter in counters:
        json_obj = try_load_json(counter)
        if json_obj is None:
            continue
        name = json_obj["__name__"]
        new_name = name + "_rate"
        new_name = new_name.replace("_total_", "_")  # Some counters have "total" in their name
        json_obj["__name__"] = new_name
        new_column = json.dumps(json_obj)
        rate_dataframes.append(df[counter].diff().rename(new_column))

    # Combine the existing dataframe with the new rate dataframes
    df = pd.concat([df] + rate_dataframes, axis=1)
    return df
