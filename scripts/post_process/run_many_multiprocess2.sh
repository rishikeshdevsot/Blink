# report=/home/yWX1380092/CPU-test/Performance/TOP_APP_OH/Report_ohos5_blink
# report=/home/yWX1380092/phone_data/result_blink
# report=/home/yWX1380092/phone_data/result_blink_instr_lsb
report=$1
MIP=$2
OLD=$3 # backward compatible
N=${N:=10}
process() {
    w=$1
    for i in $(seq 1 $N)
        do
            echo $i
            rm ./pmu/*
            dir=""

            if [ $OLD = 'true' ]
            then
                cp $dir/*.bin ./pmu/
                dir=$w/pmu_blink/$i/base
            else
                cd ./pmu
                    tar -xvzf  $w/pmu_blink/$i/blink_logs.tar.gz
                    mv data/storage/el1/base/* ./
                cd -
                dir=$w/pmu_blink/$i/data/storage/el1/base/
                mkdir -p $dir
            fi


            python3 parser.py
            # python3 post-process.py --compute_self
            
            # cp ./data/summary.csv $dir/summary_single.csv
            # cp ./data/info.json $dir/info_single.json

            python3 post-process.py --compute_self
            
            cp ./data/summary.csv $dir/summary.csv
            cp ./data/summary_corrected.csv $dir/summary_corrected.csv
            cp ./data/info.json $dir/info.json
            cp ./data/leftover.csv $dir/leftover.csv
            cp ./data/output.csv $dir/output.csv
            cp ./data/failure.csv $dir/failure.csv
            # sleep 10
        done
}
ID=$(uuidgen -r)
echo $ID
APPS=$(find $report -maxdepth 1 -mindepth 1 -type d)
for app in $APPS
do
    workloads=$(find $app -maxdepth 1 -mindepth 1 -type d)
    for w in $workloads
    do 
        echo $w
        workdir=${ID}/$(basename $app)/$(basename $w)
        # rm  $workdir
        mkdir -p $workdir
        cp -r ${MIP} $workdir/MIPCodeInfo
        cp *.py $workdir
        cp *.sh $workdir
        mkdir -p $workdir/pmu
        mkdir -p $workdir/data
        cd $workdir
        if [ $3 = "--parallel" ]
        then 
            process $w &
        else
            process $w
        fi
        cd -
    done
done


