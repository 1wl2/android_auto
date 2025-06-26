#!/system/bin/sh 
  
# 配置参数
target_path=$(echo "$1" | sed 's/"//g')    				# 需要监控的Android路径
threshold=$2                 	# 存储阈值
max_delete=$3                   # 每次最多删除文件数
log_file="/sdcard/cleanup.log"  # Android可访问的日志路径
max_log_size=5242880 			# 5MB
delete_path="/data/data/com.vixtel.stb.agent/files/log" #需要删除文件所在路径

echo "监控参数: $target_path $threshold% $max_delete" > /sdcard/cleanup.log

# 捕获退出信号，清理PID文件
cleanup() {
    rm -f /sdcard/cleanup.pid
    exit 0
}
trap cleanup EXIT

# 路径检查
if [ ! -d "$target_path" ]; then
    echo "Error: Target path not exist!" >&2
    exit 3
fi

# 获取存储使用率（适配Android df输出）
get_usage() {
    df_output=$(df $target_path | tail -n1)
    usage=$(echo "$df_output" | awk '{gsub(/%/,"",$(NF-1)); print $(NF-1)}')
    echo $usage
}

# 安全删除函数
delete_files() {
	find $delete_path -maxdepth 1 -type f -exec ls -1rt {} + | head -n $max_delete | while read file;do
        if rm -f "$file"; then
            log "Deleted: $file"
        else
            log "Failed to delete: $file"
        fi
    done
}

# 日志记录函数
log() {
    # 限制日志文件大小（5MB）
    max_log_size=5242880
    if [ -f "$log_file" ] && [ $(wc -c < "$log_file") -gt $max_log_size ]; then
        mv "$log_file" "$log_file.old"
    fi
    echo "$(date '+%Y-%m-%d %H:%M:%S') - $1" >> "$log_file"
}

# 主流程
log "===== Storage Cleaner Start ====="
(
    while true; do
      # 获取当前使用率
        current_usage=$(get_usage)
        if [ $current_usage -gt $threshold ]; then
        log "Over threshold! Start cleaning..."
            delete_files
        new_usage=$(get_usage)
        log "New Usage: $new_usage%"
        fi
        sleep 300  # 5分钟
    done
)&
echo $! > /sdcard/cleanup.pid
wait  # 等待后台进程结束


#通过 nohup /system/bin/cleanup.sh >/dev/null 2>&1 & 执行