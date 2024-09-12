import os.path
import time
import zipfile
import pandas as pd
import ujson as json
import os


def get_descriptive_keys(header_group):
    headers = header_group
    first_elem = list(headers.values())[0]
    first_keys = list(first_elem.keys())
    # first_keys = list(headers.keys())[0].keys()
    blacklist = []

    for key, val in headers.items():
        assert first_keys == list(val.keys()), 'ALL HEADER KEYS DO NOT MATCH'

    for key in first_keys:
        # is_static = always_matches(headers, lambda x: headers[0][key] == x[key])
        is_static = True
        for _, val in headers.items():
            if not first_elem[key] == val[key]:
                is_static = False
        # print(is_static)
        if is_static:
            blacklist.append(key)
    # print(blacklist)
    # print(set(first_keys) ^ set(blacklist))
    descriptive_keys = set(first_keys) - (
            set(blacklist) ^ {"__name__"} ^ {"instance"})  # Keep descriptive keys and the name
    return descriptive_keys


def remove_unnecessary_keys(df, cols, descriptive_keys):
    # LOAD ORIGINAL COLUMN AS DICT, THEN NUKE THE REPETITIVE KEYS
    # FINALLY, CONVERT PRODUCT BACK TO STRING
    new_cols = []
    original_cols = cols
    for col in original_cols:
        as_dict = json.loads(col)
        repetitive_headers = set(as_dict.keys()) ^ descriptive_keys

        for bad_header in repetitive_headers:
            del as_dict[bad_header]

        as_string = json.dumps(as_dict)
        new_cols.append(as_string)

    # MAKE DICT OF RENAMED COLUMNS, AND MODIFY THE DF
    cols_swaps = dict(zip(original_cols, new_cols))
    df.rename(columns=cols_swaps, inplace=True)


def sub_df_by_instance(df):
    sub_df_cols = {}
    for col in df.columns:
        try:
            col_as_dict = json.loads(col)
        except Exception as e:
            print(e)
            print(f"Could not parse {col}")
            continue
        if "instance" not in col_as_dict:
            instance = "unknown"
        else:
            instance = col_as_dict["instance"]
        if instance not in sub_df_cols:
            sub_df_cols[instance] = []
        sub_df_cols[instance].append(col)
    sub_dfs = {instance: df[cols] for instance, cols in sub_df_cols.items()}
    return sub_dfs