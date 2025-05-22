#!/system/bin/sh 
  
LOGFILE="/sdcard/logfile.csv"
PID_FILE="/sdcard/performance.pid"  # 新增PID文件路径

touch "$LOGFILE"

# 定义多个监控进程（用 | 分隔，支持正则表达式）
TARGET_PROCESSES="stbagent|testagent|com.vixtel.stb.agent"

# 写入当前进程PID
echo $$ > "$PID_FILE"

# 退出时清理PID文件
cleanup() {
    rm -f "$PID_FILE"
}
trap cleanup EXIT

# 新CSV表头（含系统指标）
echo "timestamp,total_cpu(%),user(%),system(%),idle(%),total_mem(kB),used_mem(kB),free_mem(kB),buffers(kB),pid,user,pr,ni,virt,res,shr,s,%cpu,%mem,time+,args" > "$LOGFILE"

while true; do
    timestamp=$(date +'%Y-%m-%d %H:%M:%S')
    top_output=$(top -b -n 1)
    
    # ---------- 解析CPU指标 ----------
    cpu_line=$(echo "$top_output" | grep -m 1 -E "^[0-9]+%cpu")
    user_cpu=$(echo "$cpu_line" | awk '{print $2}' | tr -d '%user')
    sys_cpu=$(echo "$cpu_line" | awk '{print $4}' | tr -d '%sys')
    idle_cpu=$(echo "$cpu_line" | awk '{print $5}' | tr -d '%idle')
    total_cpu=$(awk "BEGIN {print $user_cpu + $sys_cpu}")
    
    # ---------- 解析内存指标 ----------
    mem_line=$(echo "$top_output" | grep -m 1 "^Mem")
    total_mem=$(echo "$mem_line" | awk '{print $2}' | tr -d 'k')    # 2025232
    used_mem=$(echo "$mem_line" | awk '{print $4}' | tr -d 'k')     # 1554496
    free_mem=$(echo "$mem_line" | awk '{print $6}' | tr -d 'k')     # 470736
    buffers=$(echo "$mem_line" | awk '{print $8}' | tr -d 'k')      # 57260
    
    # ---------- 解析进程数据 ----------
    echo "$top_output" | grep -Ew "$TARGET_PROCESSES" | \
    awk -v ts="$timestamp" \
        -v tc="$total_cpu" \
        -v uc="$user_cpu" \
        -v sc="$sys_cpu" \
        -v ic="$idle_cpu" \
        -v tm="$total_mem" \
        -v um="$used_mem" \
        -v fm="$free_mem" \
        -v bf="$buffers" '
    BEGIN {OFS=","}
    {
        # 清理进程数据中的%符号
        gsub(/%/, "", $9)  # %CPU
        gsub(/%/, "", $10) # %MEM
        print ts, tc, uc, sc, ic, tm, um, fm, bf, $1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12
    }' >> "$LOGFILE"
    
    sleep 3
done