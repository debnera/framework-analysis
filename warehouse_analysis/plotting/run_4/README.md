# Run_4 analysis


## Next run ideas

- Auto-balancing for master
    - But how?
        - CPU usage might not get maxed out -> nothing to measure
        - Randomly increasing number of masters would work, but be inefficient
    - Also, multiple masters would need a divide-and-conquer strategy,
      where there are layers of masters, each layer having its own kafka topics
- Adjust feed-rate to account for max throughput saturation

## Energy consumption



## Throughput

### Throughput (Master):

Resolution 1000:
 min: 40 PCL/s at 1 worker
 mid: ~80 PCL/s at 2 workers
 max: ~100 PCL/s at 4 to 30 workers

Resolution 5000:
 min: 20 PCL/s at 1 worker
        35 PCL/s at 2
        55 PCL/s at 3
        70 PCL/s at 4
        ~80 PCL/s at 5 to 30

Resolution 10000:
    16 PCL/s at 1
    22 at 2
    34 at 3
    45 at 4
    55 at 5
    65 at 7
    ~80 at 8 to 30

Conclusion:
- Master saturates at 100 updates per second
- Decrease to 80 updates can be from 
  - workers saturating
  - OR workers consuming master resources
  - OR PCL feeder saturating


### Throughput (Workers):

Resolution 1000:
    min: 40 PCL/s at 1
    mid: roughly +40 PCL/s for each worker
    max: 1100 PCL/s at 30
    - No saturation at 30 workers

Resolution 5000:
    min: 18 PCL/s at 1
    mid: +18 PCL/s for each additional worker
    max: 400 PCL/s at 30
    - No saturation at 30 workers

Resolution 10000:
    min: 11
    mid: +11 per worker
    max: ~220 at 30 and ~200 at 20
    - Saturation seems to be really close at 30 workers

Conclusion:
- Workers produce way more updates than master can consume
- At resolutions 1k and 5k the number of workers does not saturate at 30 
- **This is a load balancing problem**

## Latencies

### Master latencies

- Stays below 30 ms, until master is staturated by too many updates from too many workers
- Less saturation at higher resolutions

### Worker latencies

- Worker latency stats are meaningless with burst-feeder
  - Would need to run with a feed-rate that does not saturate the workers 


