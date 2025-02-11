import numpy as np
import os
import pandas as pd
from utils.header_cleaner import *
from functools import lru_cache
from collections import namedtuple
import plotly.express as px
import difflib
from typing import List, NamedTuple

"""
------------------------------------------------
Functions for finding files from folders
------------------------------------------------
"""


def find_subfolders_with_file(root_folder: str, filename: str) -> List[str]:
    result = []
    for root, dirs, files in os.walk(root_folder):
        if filename in files:
            result.append(root)
    return result



"""
----------------------------------------------------------------
Functions for reading and cleaning feather files (with caching)
----------------------------------------------------------------
"""

def get_cleaned_df(file_path: str) -> pd.DataFrame:
    return get_cleaned_df2(file_path).copy()

def read_feather_cached(file_path: str) -> pd.DataFrame:
    return read_feather_cached2(file_path).copy()

@lru_cache(maxsize=None)
def get_cleaned_df2(file_path: str) -> pd.DataFrame:
    return clean_df(read_feather_cached(file_path))

@lru_cache(maxsize=None)
def read_feather_cached2(file_path: str) -> pd.DataFrame:
    return pd.read_feather(file_path)


"""
--------------------------------------------------------------------------------
Functions for translating model names and filepaths to human readable format
--------------------------------------------------------------------------------
"""

def unify_model_names(model_name: str) -> str:
    # Make naming conventions consistent across yolo versions
    model_name = model_name.replace("yolov", "yolo")
    model_name = model_name.replace("9t", "9n").replace("9c", "9l").replace("9e", "9x") # Yolov9 has different model names
    return model_name

def sort_by_model_size_then_version(df: pd.DataFrame) -> pd.DataFrame:
    """
    Sorts model by
        1. model size
        2. yolo version
    Input: DataFrame for sorting
    Output: Sorted DataFrame
    """
    return df.sort_index(key=lambda x: x.map(_sort_key_size_version))

def _sort_key_size_version(label: str):
    """
    Sorts model by
        1. model size
        2. yolo version
    """
    import re
    label = unify_model_names(label)
    match = re.match(r"yolo(\d+)([nsmxl])", label)
    if match:
        version_number = int(match.group(1))
        variation = match.group(2)
        variation_order = {'n': 1, 's': 2, 'm': 3, 'l': 4, 'x': 5}
        # Sort first by variation, then by version_number
        return 100 * variation_order[variation] + version_number
    else:
        return 0

class ModelInfo(NamedTuple):
    timestamp: str
    model: str  # Makes model names consistent across yolo versions (e.g., yolov9t -> yolo9n)
    model_raw: str  # Gives the raw name with differing naming schemes (e.g., yolov9t or yolo11n)
    resolution: int

class WarehouseInfo(NamedTuple):
    timestamp: str
    num_vehicles: int  # Number of vehicles / worker nodes processing point clouds
    resolution: int  # Number of point in each point cloud

def path_to_workers_and_pcl_size(path: str) -> WarehouseInfo:
    """
    Run_5 specific naming.
    Example: '1735649744_(3.1000)' -> timestamp_model_resolution
    """
    timestamp, application_specs = path.split("_")
    application_specs = application_specs.replace("(", "").replace(")", "")
    workers, resolution = application_specs.split(".")
    return WarehouseInfo(timestamp, int(workers), int(resolution))


def path_to_name_and_resolution(path: str) -> ModelInfo:
    """
    Run_5 specific naming.
    Example: '1730280141_yolov9e_1280' -> timestamp_model_resolution
    """
    timestamp, model_raw, resolution = path.split("_")
    resolution = int(resolution)
    model = unify_model_names(model_raw)
    return ModelInfo(timestamp, model, model_raw, resolution)


# %%
def get_number_of_images(model_path: str) -> int:
    """
    This method is specific to run_5 configuration
    Run_5 is split to small, medium and large model-resolution combinations

    Input: model name (or file_path)
    Output: number of images used for the model

    Small: 30k images
    Medium: 10k images
    Large: 1k images
    """
    import re
    model_info = path_to_name_and_resolution(model_path)
    model_name = model_info.model
    resolution = model_info.resolution

    # Make naming conventions consistent across yolo versions
    label = unify_model_names(model_name)

    # Use regex to find the model type
    match = re.match(r"yolo(\d+)([nsmxl])", label)
    num_images = -99
    if match:
        version_number = int(match.group(1))
        variation = match.group(2)
        is_large_model = variation in ["m", "l", "x"]
        is_large_resolution = int(resolution) == 1280
        if is_large_model and is_large_resolution:
            num_images = 1000
        elif is_large_model or is_large_resolution:
            num_images = 10000
        else:
            num_images = 30000
    else:
        print("ERROR: unknown model")
        print(model_name)
    print(f"{model_name}, {resolution}: {num_images} images")
    return num_images
