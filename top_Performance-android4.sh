#!/system/bin/sh


LOGFILE="/sdcard/logfile.csv"
PID_FILE="/sdcard/performance.pid"
# LOGFILE3="/sdcard/Ethernet_port_traffic.csv"
INTERFACE="eth0"
VIXTEL_PATH="/data/local/vixtel"
# DISK_MONITORING="/sdcard/disk_monitoring.csv"
TARGET="stbagent|testagent|com.vixtel.stb.agent"


# 写入当前进程PID
echo $$ > "$PID_FILE"

# cleanup() {
    # rm -f "$PID_FILE"
# }
# trap cleanup EXIT	

set +e
trap "" HUP
trap "" TERM

echo "timestamp,total_cpu,user(%),system(%),idle(%),total_mem(kB),used_mem(kB),free_mem(kB),buffers(kB),pid,user,pr,ni,virt,res,shr,s,%cpu,%mem,time+,args" > "$LOGFILE"

while true; do
    ts=$(date '+%Y-%m-%d %H:%M:%S')

    # 获取top输出，限制行数避免阻塞
    TOP_OUTPUT=$(top -n 1 -d 1 | head -n 200)
	# printf "获取到的参数 TOP_OUTPUT：$TOP_OUTPUT \n"

    # 提取CPU信息
    cpu_line=$(echo "$TOP_OUTPUT" | grep -m 1 "User " | head -n 1)
    user_cpu=$(echo "$cpu_line" | awk '{print $2}' | tr -d '%,' )
    sys_cpu=$(echo "$cpu_line" | awk '{print $4}' | tr -d '%,' )
	# printf "获取到的参数 cpu_line：$cpu_line \n"
	# printf "获取到的参数 user_cpu：$user_cpu \n"
	# printf "获取到的参数 sys_cpu：$sys_cpu \n"
    
    # 处理空值
    user_cpu=${user_cpu:-0}
    sys_cpu=${sys_cpu:-0}
    
    total_cpu=$((user_cpu + sys_cpu))
    idle_cpu=$((100 - total_cpu))

    # 从/proc/meminfo获取内存信息
    total_mem=$(grep "MemTotal:" /proc/meminfo | awk '{print $2}')
    free_mem=$(grep "MemFree:" /proc/meminfo | awk '{print $2}')
    buffers=$(grep "Buffers:" /proc/meminfo | awk '{print $2}')
    cached=$(grep "^Cached:" /proc/meminfo | awk '{print $2}')
	# printf "获取到的参数 total_mem：$total_mem \n"
	# printf "获取到的参数 free_mem：$free_mem \n"
	# printf "获取到的参数 buffers：$buffers \n"
	# printf "获取到的参数 cached：$cached \n" 
	
    # 计算已使用内存
    used_mem=$((total_mem - free_mem - buffers - cached))
    if [ $used_mem -lt 0 ]; then
        used_mem=$((total_mem - free_mem))
		# printf "获取到的参数 used_mem：$used_mem  \n"
    fi
	# printf "获取到的参数 used_mem：$used_mem   \n"

    # 处理进程信息
    echo "$TOP_OUTPUT" | grep -E "$TARGET" | while read line; do
        # 跳过表头行
        if echo "$line" | grep -q "PID PR CPU%"; then
            continue
        fi
        
        # 提取基本字段
        pid=$(echo "$line" | awk '{print $1}')
        pr=$(echo "$line" | awk '{print $2}')
        cpu=$(echo "$line" | awk '{print $3}' | tr -d '%')
        s=$(echo "$line" | awk '{print $4}')
        thr=$(echo "$line" | awk '{print $5}')
        virt=$(echo "$line" | awk '{print $6}' | tr -d 'K')
        res=$(echo "$line" | awk '{print $7}' | tr -d 'K')
        pcy=$(echo "$line" | awk '{print $8}')
        uid=$(echo "$line" | awk '{print $9}')
		
		# printf "获取到的参数 pid：$pid   \n"
		# printf "获取到的参数 pr：$pr  \n"
        # printf "获取到的参数 s：$s  \n"
		# printf "获取到的参数 thr：$thr  \n"
		# printf "获取到的参数 virt：$virt  \n"
		# printf "获取到的参数 res：$res  \n"
		# printf "获取到的参数 pcy：$pcy  \n"
		# printf "获取到的参数 uid：$uid  \n"
		
		
        # 提取进程名和参数（处理从第10列开始的内容）
        # 获取从第10列到行尾的所有内容
        raw_args=$(echo "$line" | awk '{for(i=10;i<=NF;i++) printf $i" "; print ""}' | sed 's/ *$//')
        # printf "处理前获取到的参数 raw_args：$raw_args  \n"
		
        # 处理进程名提取
        args=""
        if [ -n "$raw_args" ]; then
            # 根据不同的进程名格式进行处理
            # 1. 包含com.vixtel.stb.agent的包名
            if echo "$raw_args" | grep -q "com.vixtel.stb.agent"; then
                # 提取包名部分
                if echo "$raw_args" | grep -q '/'; then
                    # 包含路径，提取最后一部分
                    args=$(echo "$raw_args" | awk -F'/' '{print $NF}' | awk '{print $1}')
					# printf "处理进程后获取到的参数args: $args  \n"
                else
                    # 直接是包名
                    args="$raw_args"
					# printf "处理进程后直接包名args: $args  \n"
                fi
            # 2. 包含testagent的路径
            elif echo "$raw_args" | grep -q "testagent"; then
                args="testagent"
            # 3. 包含stbagent的路径
            elif echo "$raw_args" | grep -q "stbagent"; then
                args="stbagent"
            # 4. 其他情况，尝试提取可执行文件名
            else
                # 如果包含路径，取最后一部分
                if echo "$raw_args" | grep -q '/'; then
                    args=$(echo "$raw_args" | awk -F'/' '{print $NF}')
					# printf "其他情况包含路径args：$args"
					
                else
                    args="$raw_args"
					# printf "其他情况args：$args"
                fi
            fi
        fi
        
        # 如果还是提取不到进程名，尝试proc获取
        if [ -z "$args" ]; then
            # 尝试从/proc/$pid/comm获取进程名
            if [ -r "/proc/$pid/comm" ]; then
                comm_name=$(cat /proc/$pid/comm 2>/dev/null | tr -d '\n')
                if [ -n "$comm_name" ]; then
                    args="$comm_name"
					# printf "proc获取args：$args \n"
                fi
            fi
        fi
        
        # 最终如果args还是为空，设置默认值
        if [ -z "$args" ]; then
            args="unknown"
        fi
        
        # 计算内存使用百分比
        if [ -n "$total_mem" ] && [ "$total_mem" -ne 0 ]; then
            mem_percent=$((res * 100 / total_mem))
        else
            mem_percent=0
        fi

        # 写入日志（Android 4.4不支持的字段用0填充）
        echo "$ts,$total_cpu,$user_cpu,$sys_cpu,$idle_cpu,$total_mem,$used_mem,$free_mem,$buffers,$pid,$uid,$pr,0,$virt,$res,0,$s,$cpu,$mem_percent,0,$args" >> "$LOGFILE"
    done

    # 网口流量监测
    # if [ -f "/proc/net/dev" ]; then
        # RX1=$(grep "$INTERFACE" /proc/net/dev | awk '{print $2}')
        # TX1=$(grep "$INTERFACE" /proc/net/dev | awk '{print $10}')
        # sleep 1
        # RX2=$(grep "$INTERFACE" /proc/net/dev | awk '{print $2}')
        # TX2=$(grep "$INTERFACE" /proc/net/dev | awk '{print $10}')
        
        # if [ -n "$RX1" ] && [ -n "$RX2" ] && [ -n "$TX1" ] && [ -n "$TX2" ]; then
            # RX_DIFF=$((RX2 - RX1))
            # TX_DIFF=$((TX2 - TX1))
            # RX_KB=$((RX_DIFF / 1024))
            # TX_KB=$((TX_DIFF / 1024))
            
            # echo "$(date '+%Y-%m-%d %H:%M:%S'),RX:${RX_KB}KB/s,TX:${TX_KB}KB/s" >> "$LOGFILE3"
        # fi
    # fi

    # # 磁盘占用监测
    # if [ -d "$VIXTEL_PATH" ]; then
        # disk_usage=$(du -sk "$VIXTEL_PATH" 2>/dev/null | awk '{print $1}')
        # echo "$ts,$disk_usage,$VIXTEL_PATH" >> "$DISK_MONITORING"
    # fi

    sleep 2
done