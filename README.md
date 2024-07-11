# Scripts for processing datasets from our cluster

Mostly related to a "Framework"-paper.

Scripts are partially based on Johns work.

## Get example data:

Extract Prometheus data from a Kubernetes cluster using https://github.com/debnera/aalto-ensure-cluster

TODO:
- Add links to example datasets (google drive?)

## Process raw data into dataframes:

01_process_prometheus will create and save multiple dataframes from raw prometheus data

Outputs:
- `/intermediate/`
  - Intermediate dataframes are used to make processing faster and to reduce memory usage
    - full.df contains the unfiltered dataframe with all data
    - Intermediate files makes it possible to stop processing and continue later on
- In addition, the data is split per instance
  - e.g., each worker node has its own dataframe (i.e., `worker1.df`, `worker2.df`, ...)
  - Also data that is missing the name of the node has its own dataframe

02_process_yolo will create and save a dataframe from the yolo csv-files

## Use dataframes

After processing data to dataframes, the data can be handled in any desired way.