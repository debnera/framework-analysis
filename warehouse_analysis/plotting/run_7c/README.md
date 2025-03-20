# Run_7c analysis

- Add HPA for master and workers
  - Also add logging for hpa statistics
- One long run for each resolution, instead of one run per worker count

Changes from run_7b:
- Use linearly increasing workloads (instead of shuffled)
- Add time between workloads to maker the cycles visually more clear
- Automate use of hpa_logger