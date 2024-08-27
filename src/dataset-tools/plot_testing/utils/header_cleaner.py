import pandas as pd
import ujson as json
from typing import List


def get_descriptive_keys(header_group):
    headers = [json.loads(x) for x in header_group]
    first_elem = headers[0]
    first_keys = list(first_elem.keys())
    # first_keys = list(headers.keys())[0].keys()
    blacklist = []

    for val in headers:
        assert first_keys == list(val.keys()), 'ALL HEADER KEYS DO NOT MATCH'

    for key in first_keys:
        # is_static = always_matches(headers, lambda x: headers[0][key] == x[key])
        is_static = True
        for val in headers:
            if not first_elem[key] == val[key]:
                is_static = False
        # print(is_static)
        if is_static:
            blacklist.append(key)
    # print(blacklist)
    # print(set(first_keys) ^ set(blacklist))
    descriptive_keys = set(first_keys) - (set(blacklist) ^ {"__name__"})  # Keep descriptive keys and the name
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
            # print(f"Removing {bad_header}")
            del as_dict[bad_header]

        as_string = json.dumps(as_dict)
        new_cols.append(as_string)

    # MAKE DICT OF RENAMED COLUMNS, AND MODIFY THE DF
    cols_swaps = dict(zip(original_cols, new_cols))
    df.rename(columns=cols_swaps, inplace=True)

def minimize_keys(df, cols, descriptive_keys):
    # LOAD ORIGINAL COLUMN AS DICT, THEN NUKE THE REPETITIVE KEYS
    # FINALLY, CONVERT PRODUCT BACK TO STRING
    original_cols = cols
    keys = ["__name__"]
    num_cols = len(original_cols)
    if num_cols == 1:
        # Only one column -> we can simplify it by using __name__ only
        return [prettify_header(col, keys) for col in original_cols]
    col_dicts = [json.loads(col) for col in original_cols]
    lens_per_key = {}
    for key in (set(descriptive_keys) - {"__name__"}):
        vals = [col[key] for col in col_dicts]
        unique_cols_for_key = list(set(vals))
        lens_per_key[key] = len(unique_cols_for_key)

    # print(f"{col_dicts[0]['__name__']}")
    # print(f"Num_cols: {num_cols}, lens_per_key: {lens_per_key}")
    sorted_dict = dict(sorted(lens_per_key.items(), key=lambda item: item[1], reverse=True))

    # print(sorted_dict)

    for key in sorted_dict:
        keys.append(key)
        new_headers = [prettify_header(col, keys) for col in original_cols]
        # print(f"{num_cols}: {len(set(new_headers))}, {keys}")
        if len(set(new_headers)) == num_cols:
            if len(descriptive_keys) != len(keys):
                # print(f"Reduced from {len(descriptive_keys)} to {len(keys)}")
                pass
            return new_headers


def prettify_header(header: dict, keys: List[str]):
    if type(header) != dict:
        header = json.loads(header)
    keys = set(keys) - {'__name__'}
    prettified = f"{header['__name__']}"
    for key in keys:
        prettified += f"_{key}_{header[key]}"
    return prettified



def clean_up_headers(df: pd.DataFrame) -> pd.DataFrame:
    """
    Transforms dataframe headers into human-readable form.

    For example, given two json-type header strings, find the minimum amount of json keys that can be used
    to separate the two headers.

    Example:

    These two headers

    h1: "{name: worker1, pod: yolo, inference_time: x}"
    h2: "{name: worker1, pod: yolo, preprocessing_time: y}"

    would result in

    h1: "inference_time"
    h2: "preprocessing_time"

    :param df: DataFrame to clean
    :return: Cleaned DataFrame
    """

    # Group headers by feature name
    df = df.copy()
    grouped_by_name = {}
    for col in list(df.columns):
        try:
            header_dict = json.loads(col)
        except:
            print(f"Unable to read {col} as json")
            continue
        name = header_dict["__name__"]
        if name not in grouped_by_name:
            grouped_by_name[name] = []
        grouped_by_name[name].append(col)

    # Minimize headers for each group
    for feature_name, headers in grouped_by_name.items():
        try:
            descriptive_keys = get_descriptive_keys(headers)
            # print("Fine")
        except:
            print(f"Non-matching keys: {feature_name}")
            continue
        # remove_unnecessary_keys(df, headers, descriptive_keys)
        new_headers = minimize_keys(df, headers, descriptive_keys)
        cols_swaps = dict(zip(headers, new_headers))
        df.rename(columns=cols_swaps, inplace=True)
    return df


def clean_df(dataframe):
    #Count number of rows and cols in the original df
    print(f"Loaded {len(dataframe)} rows and {len(dataframe.columns)} columns")
    # Count the number of unique values in each column
    unique_counts = dataframe.nunique()
    # Find all static columns (columns with only one or two unique values)
    static_columns = unique_counts[unique_counts <= 2].index
    # Remove the static columns from the dataframe
    dataframe = dataframe.drop(static_columns, axis=1)
    print(f"Removing {len(static_columns)} static columns ({len(dataframe.columns)} remaining)")
    if len(dataframe.columns) < 100:
        # Only display if the df is small enough to not stall the IDE (thousands of columns really slows things down)
        dataframe.head()

    # changing the dataframe headers to a more human-readable format
    return clean_up_headers(dataframe)
    #%%

if __name__ == "__main__":
    path = "../../../data-intermediate/1706275648-8H-5S-SAMPLING/instances/worker1.feather"
    df = pd.read_feather(path)
    df2 = clean_up_headers(df)
    print(df.columns[0:3])
    print(df2.columns[0:3])


#%%
