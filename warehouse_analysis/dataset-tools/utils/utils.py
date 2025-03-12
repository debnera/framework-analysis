import os
import sys

import pandas as pd
import psutil


def list_zip_files(directory_path):
    zip_files = []
    for root, dirs, files in os.walk(directory_path):
        for file in files:
            if file.lower().endswith(".zip"):
                full_path = os.path.join(root, file)
                relative_path = os.path.relpath(full_path, directory_path)
                zip_files.append(relative_path)
    return zip_files




def check_ram():
    # Check OS memory usage
    memory_info = psutil.virtual_memory()
    if memory_info.percent > 80:
        user_input = input(f"Memory usage is at {memory_info.percent}%. Do you want to continue? (yes/no): ")
        if user_input.lower() != "yes":
            print("Aborting due to high memory usage.")
            sys.exit(1)