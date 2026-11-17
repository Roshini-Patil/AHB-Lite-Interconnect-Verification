#!/bin/bash
# runs every test with 5 seeds, prints a PASS/FAIL table
mkdir -p logs; : > regress_summary.txt
for t in parallel contention rr lock longburst burst_all rw_same random; do
  for s in 1 2 3 4 5; do
    ./run.sh $t $s +PRIO=dynamic +WAIT_MAX=4 > /dev/null 2>&1
    r=$(grep -h "AHB_RESULT" logs/${t}_${s}.log | tail -1)
    f=$(grep -cE "AHB_FAIL|^UVM_(ERROR|FATAL) @" logs/${t}_${s}.log)
    echo "$t seed=$s : ${r:-NO RESULT (compile/sim crashed)}  fail_lines=$f" | tee -a regress_summary.txt
  done
done
# error tests need the interconnect-error allowance and slave errors
for s in 1 2 3; do ./run.sh error $s +ERR_PCT=15 +WAIT_MAX=4 +ALLOW_IC_ERR > /dev/null 2>&1
  echo "error seed=$s : $(grep -h AHB_RESULT logs/error_${s}.log | tail -1)" | tee -a regress_summary.txt; done
./run.sh longburst 1 +RESET_MID > /dev/null 2>&1; echo "reset_mid : $(grep -h AHB_RESULT logs/longburst_1.log | tail -1)" | tee -a regress_summary.txt
