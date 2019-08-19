Sample functions
================

Sampler which counts the number of times we find ourselves in a particular function. 
Outputs a list of functions with their counts.
	
	Usage: 
	  usample <start_bbcount> <end_bbcount> <bbcount_interval> 
	  Parameters:
		start_bbcount: Time, given as a bbcount to start sampling.
		end_bbcount: Last time that may be sampled.
		bbcount_interval: How often to take a sample, in number of basic blocks.

	  E.g. 1 1000 1 
	  means sample every basic block from 1 to 1000. 
