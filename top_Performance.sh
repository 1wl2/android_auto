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

# 生成CSV表头（仅首次运行）
echo "timestamp,pid,user,pr,ni,virt,res,shr,s,%cpu,%mem,time+,args" > "$LOGFILE"

while true; do
    timestamp=$(date +'%Y-%m-%d %H:%M:%S')
    {
        # 使用扩展正则匹配多个进程
        top -b -n 1 2>/dev/null |
          grep -Ew "${TARGET_PROCESSES}" |  # -E 启用正则，-w 全词匹配
          grep -v "grep" |                 # 排除自身
          awk -v ts="${timestamp}" '
            BEGIN {OFS=","}
            {
              gsub(/%/, "")  # 移除CPU/MEM的百分号
              print ts, $1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12
            }'
    } >> "$LOGFILE" 2>&1
    sleep 3
done

