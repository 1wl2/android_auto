#!/system/bin/sh

LOGFILE="/sdcard/logfile.csv"
PID_FILE="/sdcard/performance.pid"  # 新增PID文件路径
LOGFILE3="/sdcard/Ethernet_port_traffic.csv"
INTERFACE="eth0"
VIXTEL_PATH="/data/local/vixtel"
DISK_MONITORING="/sdcard/disk_monitoring.csv"
TARGET="stbagent|testagent|com.vixtel.stb.agent"


# 写入当前进程PID
echo $$ > "$PID_FILE"

# 退出时清理PID文件
cleanup() {
    rm -f "$PID_FILE"
}
trap cleanup EXIT


echo "timestamp,total_cpu,user(%),system(%),idle(%),total_mem(kB),used_mem(kB),free_mem(kB),buffers(kB),pid,user,pr,ni,virt,res,shr,s,%cpu,%mem,time+,args" > "$LOGFILE"

parse_cpu_line() {
    echo "$1" | awk '
    {
        cpu=0; user=0; sys=0; idle=0;
        for(i=1;i<=NF;i++){
            if($i ~ /cpu$/)  {gsub("%cpu","",$i);  cpu=$i}
            if($i ~ /user$/) {gsub("%user","",$i); user=$i}
            if($i ~ /sys$/)  {gsub("%sys","",$i);  sys=$i}
            if($i ~ /idle$/) {gsub("%idle","",$i); idle=$i}
        }
        print cpu,user,sys,idle
    }'
}

while true; do
    ts=$(date '+%Y-%m-%d %H:%M:%S')

    RAW=$(top -n 1 -b 2>/dev/null | sed 's/\[[^]]*\]//g')

    # CPU
    cpu_line=$(echo "$RAW" | grep -m 1 "%cpu")

    cpu_values=$(parse_cpu_line "$cpu_line")
    total_cpu=$(echo "$cpu_values" | awk '{print $1}')
    user_cpu=$(echo "$cpu_values" | awk '{print $2}')
    sys_cpu=$(echo "$cpu_values" | awk '{print $3}')
    idle_cpu=$(echo "$cpu_values" | awk '{print $4}')

    # MEM
    mem_line=$(echo "$RAW" | grep -m 1 "Mem:")
    total_mem=$(echo $mem_line | awk '{print $2}' | tr -d 'K')
    used_mem=$(echo $mem_line | awk '{print $4}' | tr -d 'K')
    free_mem=$(echo $mem_line | awk '{print $6}' | tr -d 'K')
    buffers=$(echo $mem_line | awk '{print $8}' | tr -d 'K')

    # PROCESS
    echo "$RAW" | grep -E "$TARGET" | while read line; do

        col_count=$(echo "$line" | awk '{print NF}')
        if [ "$col_count" -lt 12 ]; then
            continue
        fi	

        pid=$(echo "$line" | awk '{print $1}')
        user=$(echo "$line" | awk '{print $2}')
        pr=$(echo "$line" | awk '{print $3}')
        ni=$(echo "$line" | awk '{print $4}')
        virt=$(echo "$line" | awk '{print $5}')
        res=$(echo "$line" | awk '{print $6}')
        shr=$(echo "$line" | awk '{print $7}')
        s=$(echo "$line" | awk '{print $8}')
        cpu=$(echo "$line" | awk '{print $9}')
        mem=$(echo "$line" | awk '{print $10}')
        timeplus=$(echo "$line" | awk '{print $11}')
		
        # 仅保留进程名，不带路径/参数
		raw_args=$(echo "$line" | awk '{print $12}')
		args=$(echo "$raw_args" | awk -F'/' '{print $NF}')

        echo "$ts,$total_cpu,$user_cpu,$sys_cpu,$idle_cpu,$total_mem,$used_mem,$free_mem,$buffers,$pid,$user,$pr,$ni,$virt,$res,$shr,$s,$cpu,$mem,$timeplus,$args" >> "$LOGFILE"
    done
	
	# 网口流量
	RX1=$(cat /proc/net/dev | grep $INTERFACE | awk '{print $2}')
    TX1=$(cat /proc/net/dev | grep $INTERFACE | awk '{print $10}')
    sleep 1
    RX2=$(cat /proc/net/dev | grep $INTERFACE | awk '{print $2}')
    TX2=$(cat /proc/net/dev | grep $INTERFACE | awk '{print $10}')

    RX_DIFF=$((RX2 - RX1))
    TX_DIFF=$((TX2 - TX1))
    RX_KB=$((RX_DIFF / 1024))
    TX_KB=$((TX_DIFF / 1024))

    echo "$(date "+%Y-%m-%d %H:%M:%S"), RX:, ${RX_KB}, KB/s, TX:, ${TX_KB}, KB/s" >> "$LOGFILE3"
	
	
	
	# 探针磁盘占用监测
	dd=$(du -sk $VIXTEL_PATH 2>/dev/null | awk '{print $1 "," $2}')
	echo "$ts,${dd}" >> $DISK_MONITORING
	
    sleep 2
done


# 后台执行： nohup /system/bin/top_Performance.sh > /dev/null 2>&1 &