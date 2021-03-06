#!/bin/bash

MINING=(
    mining_2t_nicehash
    mining_4t_nicehash
    mining_gpu_nicehash_equihash_1070_60p
    mining_gpu_nicehash_equihash_1080ti_85p
    mining_gpu_nicehash_equihash_1080ti_100p
    browsing
    netflix
    social-network
    youtube
)

TRAFFIC=(
    browsing
    netflix
    social-network
    youtube
)

for i in ${!MINING[@]}; do
    for j in ${!TRAFFIC[@]}; do
        printf "\n\e[38;5;220m Generating ${MINING[$i]}_${TRAFFIC[$j]}.dat... \n\e[0m";
        python3 generate_merge_datasets.py -i datasets/${MINING[$i]}.dat datasets/${TRAFFIC[$j]}.dat -o merge-datasets/${MINING[$i]}_${TRAFFIC[$j]}.dat
    done
done
