# Sample functions

Sampler which counts the number of times we find ourselves in a particular function. 
Outputs a list of functions with their counts.
```
Usage:
  usample <start_bbcount> <end_bbcount> <bbcount_interval> [<filename>]
  Parameters:
    start_bbcount: Time, given as a basic block count to start sampling.
    end_bbcount: Last time that may be sampled.
    bbcount_interval: How often to take a sample, in basic block count.
    filename: A file to output the sampled stacks to.

  E.g. 1 1000 1
  means sample every basic block count from 1 to 1000.
```

## Generating flame graphs

The output from this tool can be used directly to generate [flame graphs](https://www.brendangregg.com/flamegraphs.html).
These graphs provide a visual indication of the busiest areas of your program.
Generally, around 1,000 samples will produce a useful flame graph. You may
wish to limit the sampling to a specific range, for example after start up has
completed.

To generate a flame graph:
 - clone the [flame graph repository](https://github.com/brendangregg/FlameGraph)

 - run the `usample` script. In this case we first query the recorded time
 range within UDB:
```
> info time
Current time is: 1 (in recorded range; [1 - 140,988,372])
```
To get around 1,000 samples we wish to sample every 141,000 bbcounts, so we
run `usample` with:
```
> usample 1 140988372 141000 /tmp/stacks.data
```

 - in the shell run `flamegraph.pl` on the generated call stack data:
```
$ flamegraph.pl /tmp/stacks.data > /tmp/stacks.svg
```

You can then view the generated SVG file in your browser. Clicking on a block
will allow you to zoom in to see more detail. You can also search for function
names with regular expressions.

Run `flamegraph.ph --help` to see more options for controlling the output.

These flame graphs show the proportion of basic blocks that run in a particular
call stack. This is related to execution time, but is *not* identical. Not all
basic blocks take the same amount of time to run. In addition, this doesn't
show time spent in different processes, in particular time spent in system
calls.
