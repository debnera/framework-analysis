# Run_7b analysis

- Add HPA for master and workers
    - Also add logging for hpa statistics
- One long run for each resolution, instead of one run per worker count 

Fixes run 7
- Fix number of kafka partitions (1 partition for 40 workers will not do any good)