| # | run | cfg | plusargs | cycles | beats | result | expected | verdict |
|---|-----|-----|----------|-------:|------:|--------|----------|---------|
| 1 | parallel_1 | main | `+PRIO=fixed +WAIT_MAX=3` | 540 | 493 | PASS | PASS | OK |
| 2 | parallel_2 | main | `+PRIO=fixed +WAIT_MAX=3` | 541 | 450 | PASS | PASS | OK |
| 3 | parallel_3 | main | `+PRIO=fixed +WAIT_MAX=3` | 507 | 422 | PASS | PASS | OK |
| 4 | parallel_4_busy20 | main | `+PRIO=equal +BUSY_PCT=20` | 498 | 432 | PASS | PASS | OK |
| 5 | parallel_5_busy20 | main | `+PRIO=equal +BUSY_PCT=20` | 501 | 380 | PASS | PASS | OK |
| 6 | parallel2_1 | main | `+PRIO=fixed` | 542 | 364 | PASS | PASS | OK |
| 7 | parallel2_2 | main | `+PRIO=fixed` | 548 | 280 | PASS | PASS | OK |
| 8 | contention_1 | main | `+PRIO=dynamic +WAIT_MAX=4` | 1635 | 524 | PASS | PASS | OK |
| 9 | contention_2 | main | `+PRIO=dynamic +WAIT_MAX=4` | 1211 | 380 | PASS | PASS | OK |
| 10 | contention_3 | main | `+PRIO=dynamic +WAIT_MAX=4` | 1261 | 395 | PASS | PASS | OK |
| 11 | contention_4 | main | `+PRIO=dynamic +WAIT_MAX=4` | 1183 | 375 | PASS | PASS | OK |
| 12 | contention_5 | main | `+PRIO=dynamic +WAIT_MAX=4` | 1455 | 463 | PASS | PASS | OK |
| 13 | contention_6 | main | `+PRIO=fixed +WAIT_MAX=2` | 1097 | 503 | PASS | PASS | OK |
| 14 | contention_7 | main | `+PRIO=fixed +WAIT_MAX=2` | 1008 | 453 | PASS | PASS | OK |
| 15 | contention_8 | main | `+PRIO=equal +WAIT_MAX=2` | 982 | 478 | PASS | PASS | OK |
| 16 | contention_9 | main | `+PRIO=equal +WAIT_MAX=2` | 903 | 420 | PASS | PASS | OK |
| 17 | rr_1 | main | `+PRIO=equal` | 494 | 167 | PASS | PASS | OK |
| 18 | rr_2 | main | `+PRIO=equal` | 417 | 138 | PASS | PASS | OK |
| 19 | rr_3 | main | `+PRIO=equal` | 435 | 148 | PASS | PASS | OK |
| 20 | rr_4 | main | `+PRIO=equal` | 417 | 140 | PASS | PASS | OK |
| 21 | rr_5 | main | `+PRIO=equal` | 426 | 143 | PASS | PASS | OK |
| 22 | lock_1 | main | `+PRIO=dynamic +WAIT_MAX=3` | 1157 | 423 | PASS | PASS | OK |
| 23 | lock_2 | main | `+PRIO=dynamic +WAIT_MAX=3` | 1296 | 485 | PASS | PASS | OK |
| 24 | lock_3 | main | `+PRIO=dynamic +WAIT_MAX=3` | 1215 | 454 | PASS | PASS | OK |
| 25 | lock_4 | main | `+PRIO=equal` | 1186 | 453 | PASS | PASS | OK |
| 26 | longburst_1 | main | `+PRIO=fixed` | 2011 | 754 | PASS | PASS | OK |
| 27 | longburst_2 | main | `+PRIO=fixed` | 1966 | 730 | PASS | PASS | OK |
| 28 | longburst_3 | main | `+PRIO=fixed` | 1940 | 729 | PASS | PASS | OK |
| 29 | burst_all_1 | main | `+PRIO=dynamic +WAIT_MAX=3` | 1113 | 582 | PASS | PASS | OK |
| 30 | burst_all_2 | main | `+PRIO=dynamic +WAIT_MAX=3` | 961 | 541 | PASS | PASS | OK |
| 31 | burst_all_3 | main | `+PRIO=dynamic +WAIT_MAX=3` | 962 | 536 | PASS | PASS | OK |
| 32 | rw_same_1 | main | `+PRIO=equal` | 246 | 60 | PASS | PASS | OK |
| 33 | rw_same_2 | main | `+PRIO=equal` | 250 | 60 | PASS | PASS | OK |
| 34 | rw_same_3 | main | `+PRIO=equal` | 245 | 60 | PASS | PASS | OK |
| 35 | error_1 | main | `+ERR_PCT=15 +WAIT_MAX=4` | 448 | 195 | PASS | PASS | OK |
| 36 | error_2 | main | `+ERR_PCT=15 +WAIT_MAX=4` | 422 | 202 | PASS | PASS | OK |
| 37 | error_3 | main | `+ERR_PCT=15 +WAIT_MAX=4` | 430 | 193 | PASS | PASS | OK |
| 38 | error_4_errcont | main | `+ERR_PCT=15 +ERR_CONTINUE` | 648 | 473 | PASS | PASS | OK |
| 39 | random_1 | main | `+PRIO=dynamic +WAIT_MAX=4 +ERR_PCT=5` | 720 | 366 | PASS | PASS | OK |
| 40 | random_2 | main | `+PRIO=dynamic +WAIT_MAX=4 +ERR_PCT=5` | 609 | 336 | PASS | PASS | OK |
| 41 | random_3 | main | `+PRIO=dynamic +WAIT_MAX=4 +ERR_PCT=5` | 652 | 345 | PASS | PASS | OK |
| 42 | random_4 | main | `+PRIO=dynamic +WAIT_MAX=4 +ERR_PCT=5` | 685 | 306 | PASS | PASS | OK |
| 43 | random_5 | main | `+PRIO=dynamic +WAIT_MAX=4 +ERR_PCT=5` | 746 | 351 | PASS | PASS | OK |
| 44 | longburst_11_resetmid | main | `+RESET_MID` | 1815 | 691 | PASS | PASS | OK |
| 45 | random_12_resetmid | main | `+PRIO=dynamic +RESET_MID` | 721 | 427 | PASS | PASS | OK |
| 46 | busy_1_nobusy | main | `+PRIO=equal +BUSY_PCT=0` | 1473 | 552 | PASS | PASS | OK |
| 47 | busy_2_nobusy | main | `+PRIO=equal +BUSY_PCT=0` | 1535 | 584 | PASS | PASS | OK |
| 48 | busy_3_nobusy | main | `+PRIO=equal +BUSY_PCT=0` | 1455 | 576 | PASS | PASS | OK |
| 49 | mask_1 | mask | `+PRIO=dynamic` | 645 | 435 | PASS | PASS | OK |
| 50 | mask_2 | mask | `+PRIO=dynamic` | 675 | 401 | PASS | PASS | OK |
| 51 | mask_3 | mask | `+PRIO=dynamic` | 677 | 348 | PASS | PASS | OK |
| 52 | busy_1_bug | main | `+PRIO=equal` | 1736 | 596 | FAIL | FAIL | OK |
| 53 | busy_2_bug | main | `+PRIO=equal` | 1693 | 564 | FAIL | FAIL | OK |
| 54 | busy_3_bug | main | `+PRIO=equal` | 1571 | 536 | FAIL | FAIL | OK |
| 55 | busy_1_fix | fix | `+PRIO=equal` | 1567 | 540 | PASS | PASS | OK |
| 56 | busy_2_fix | fix | `+PRIO=equal` | 1604 | 564 | PASS | PASS | OK |
| 57 | busy_3_fix | fix | `+PRIO=equal` | 1470 | 524 | PASS | PASS | OK |
| 58 | random_7_neg_1kb | main | `+NEG_1KB` | 874 | 504 | FAIL | FAIL | OK |
| 59 | random_7_inject_data | main | `+INJECT=data` | 853 | 498 | FAIL | FAIL | OK |
| 60 | error_7_inject_err1 | main | `+ERR_PCT=15 +INJECT=err1` | 368 | 168 | FAIL | FAIL | OK |

Sign-off runs: 51, passed 51; all runs as expected: True; wall time 50s; total cycles 57241, master beats 24690
