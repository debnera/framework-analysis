import os
import zipfile
from typing import List


"""
Prometheus metrics are stored in a set of folders, where each folder contains a number of JSON files.
Each JSON file contains multiple metrics from a range of timestamps.
Care needs to be taken when merging the slices, 
so that no metrics are lost for any of the timestamps.

These utils functions help with splitting the JSON files into slices.
Each slice is a list of json file paths.
Too large slices can cause memory issues and problems when creating dataframes from the data.
"""



def get_slices_by_folder(zip_file: str) -> List[List[str]]:
    """
    Retrieve JSON files from a given zip file and split them into slices where each slice
    adheres to a specified size limit in megabytes (MB).


    Parameters
    ----------
    zip_file : str
        Path to the zip file to be processed. Must end with the `.zip` extension.

    Returns
    -------
    List[List[str]]
        A list of slices, where each slice is a list of file names.
        Each slice contains JSON file names from the zip.
    """
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

def get_slices_by_file_size(zip_file: str, size_limit_mb: int) -> List[List[str]]:
    """
        Retrieve JSON files from a given zip file and split them into slices where each slice
        adheres to a specified size limit in megabytes (MB).

        NOTE: This way of slicing can cause issues when merging the slices to a dataframe,
              because a single metric can be split across multiple slices.

        Parameters
        ----------
        zip_file : str
            Path to the zip file to be processed. Must end with the `.zip` extension.
        size_limit_mb : int
            Maximum allowable size in megabytes for any given slice of JSON files.

        Returns
        -------
        List[List[str]]
            A list of slices, where each slice is a list of file names. Each slice contains
            JSON file names from the zip, and the combined file sizes for the slice are
            within the specified size limit.
    """
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
            # Continue current slice
            current_slice.append(file_name)
            current_size += file_info.file_size
        else:
            # Start the next slice
            slices.append(current_slice)
            current_slice = [file_name]
            current_size = file_info.file_size

    if current_slice:
        # Make sure the final slice is added to the list
        slices.append(current_slice)

    return slices
