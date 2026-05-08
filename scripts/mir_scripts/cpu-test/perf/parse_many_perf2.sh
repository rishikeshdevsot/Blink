# REPORT=~/phone_data/result_record_instr2_freq/
# REPORT=/home/yWX1380092/CPU-test/Performance/TOP_APP_OH/Report_perf
# REPORT=~/phone_data/result_record_instr2_freq/
REPORT=$1
# binary_cache=$2
render_service=$2
# "/home/yWX1380092/export/binary_cache_minh"
old_binary_cache="/home/yWX1380092/export/binary_cache_rishi"
cp $render_service $old_binary_cache//system/lib64/librender_service_base.z.so

binary_cache="/home/yWX1380092/export/binary_cache_$(basename $render_service)"
cp -r $old_binary_cache $binary_cache

event=hw-instructions
event=hw-cpu-cycles

gen_csv()
{   
    w=$1
    for data in $(find $w/pmu_render  -name '*.data')
    do
        # if [ ! -e $data.single.csv ]
        # then
            echo  $data
            python3 parse_perf.py $data -e $event -o $data.single.csv  \
                -s  $binary_cache || exit 1
            python3 parse_perf.py $data  -e $event --fullstack -o $data.csv  \
                -s  $binary_cache || exit 1
        # fi
    done
}

for APP in $(find $REPORT -mindepth 1 -maxdepth 1 -type d)
do
    workloads=$(find $APP -mindepth 1 -maxdepth 1 -type d)
    
    for w in $workloads
    do
        echo $w
        # for data in $(find $w/pmu_app  -name '*.data')
        # do
        #     echo  $data
        #     python3 parse_perf.py $data -o $data.csv -s /data/local/tmp/binary_cache || exit 0
        # done

        # for data in $(find $w/pmu_render  -name '*.data')
        # do
        #     echo  $data
        #     python3 parse_perf.py $data -o $data.single.csv -f -s  /data/local/tmp/binary_cache  || exit 1
        # done
        #if [ "$3" = "--parallel" ]
        #then
        #    gen_csv $w &
        #else
            gen_csv $w
        #fi
    done

done
