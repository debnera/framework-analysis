## Run_3 analysis

- QoS metrics missing for runs workers=3 and workers=5
  - Fixed bug with wrong dataset path in run 4
- Only one worker is consuming stuff
  - Others are not assigned to a kafka partition
  - Fixed by adjusting how many kafka partitions there are for the topic in run 4
  - Each partition can be assigned at most to one consumer
  - There should be one partition for each consumer
  - Too many partitions might cause imbalance between the consumers
- Throughput is not affected by number of workers
  - This relates directly to the kafka partitions bug