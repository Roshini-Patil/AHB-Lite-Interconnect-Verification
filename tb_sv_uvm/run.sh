#!/bin/bash
# usage: ./run.sh <vseq> <seed> [extra plusargs]      e.g.  ./run.sh contention 3 +PRIO=dynamic +WAIT_MAX=5
VSEQ=${1:-random}; SEED=${2:-1}; shift $(( $# < 2 ? $# : 2 ))
mkdir -p logs
xrun -64bit -sv -uvm -access +rwc -timescale 1ns/1ps -top tb_top \
     -f rtl.f -f tb.f \
     +UVM_TESTNAME=ahb_test +UVM_VERBOSITY=UVM_LOW +VSEQ=$VSEQ -svseed $SEED \
     -coverage all -covoverwrite -covworkdir cov_work -covtest ${VSEQ}_${SEED} \
     -l logs/${VSEQ}_${SEED}.log "$@"
echo "------ summary for ${VSEQ} seed ${SEED} ------"
grep -E "^UVM_(ERROR|FATAL) @|AHB_FAIL|AHB_RESULT|AHB_ARB_CHECKER|\*E," logs/${VSEQ}_${SEED}.log | head -20
