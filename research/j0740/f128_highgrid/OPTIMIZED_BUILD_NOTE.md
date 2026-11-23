# F128 3001x6001 optimized retry

The upstream makefile defaults to an unoptimized `-g3 -Wall` build. The retry workflow overrides `MY_OWN` to `-O3` for the 3001x6001 native RNS build. Inputs remain pinned by SHA; calls are capped at 1200 seconds and five per density. This is a diagnostic mesh check only.
