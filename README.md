# android_auto
Android系统机顶盒针对探针自动化部署和操作

1.**机顶盒连接**
  IP地址窗口填写机顶盒的IP，点击“连接”，就可通过adb命令连接 "adb connect ip"
  
2.**部署**
  部署是针对探针和脚本文件push到指定目录下完成的，具体如下：
  点击“部署”按钮，选择STBIQ.*apk、testagent、startstbagent.sh文件所在的文件夹，程序首先检查机顶盒/system/app/下是否存在STBIQ.*apk的文件，存在就删除，然后将新的apk文件push到/system/app/下；
  其次 testagent、startstbagent.sh文件会直接push到/system/bin/目录下，直接覆盖原文件，自动给testagent、startstbagent.sh文件赋权可执行权限，部署成功后自动弹窗提示"部署完成"。
  
3.##**重启机顶盒**
  adb 通过reboot对连接的盒子重启。
  
4.##**其他操作**
  **主要功能一**：从机顶盒内取日志，可以选择取整个路径的日志，还可以选择取单独的一个日志文件提取，
			探针日志路径为：/data/data/com.vixtel.stb.agent/files，files路径下有2个路径，log路径和crash路径；
			  log路径下为探针日志，
			  crash路径下为探针崩溃日志；
			日志提取页面包括：”全部提取机顶盒日志“和“提取部分日志”按钮；
			  全部提取机顶盒日志：提取/data/data/com.vixtel.stb.agent/files路径；
			  提取部分日志：点击后展示3个按钮：“提取log目录”、“选择log文件”、“提取crash目录”、“提取library或agent日志”
					“提取log目录”：提取/data/data/com.vixtel.stb.agent/files/log 目录
					“提取crash目录”：提取/data/data/com.vixtel.stb.agent/files/crash目录
					“选择log文件”：提取单个日志页面，有一个列表，列表展示/data/data/com.vixtel.stb.agent/files/log/下的文件；
									列信息包括：选择(复选框)、文件名称、日期、大小，
									页面底部有4个按钮：提取选中、全选、反选、返回
										提取选中：勾选复选框的文件，针对选择的文件提取；
										全选：全选所有文件；
										反选：根据已经选择的文件，反选所有没选择的文件；
										返回：返回上级页面；
					“提取library或agent日志”：日志路径在 /sdcard/;日志名称分别为：stbagent.log、stblibrary.log、stbsocketlibrary.log、testagent.log、testlibrary.log
						参考”选择log文件“页面功能
  **主要功能二**：有2个按钮，一个是”开启日志“，一个是“关闭日志”；
			页面有一个列表分别对应文件名称：
				appLog.log 、
				socketlibraryLogConfig.txt 、
				stbagentLogConfig.txt、
				stblibraryLogConfig.txt、
				testagentLogConfig.txt、
				testlibraryLogConfig.txt，
      日志开关文件已经内置到代码中，不在需要用户在本地查到，方便操作。
			第一列添加复选框，允许多选，勾选后，
			点击“开启日志”：将勾选的文件push到机顶盒内部 /data/local/vixtel/conf/ 路径下；
			点击“关闭日志”：将勾选的文件从机顶盒内部的 /data/local/vixtel/conf/ 路径下删除；
   
5.##**性能监测**
  性能监测页面存在3个按钮：启动性能监测、关闭性能监测、提取性能监测文件；
    程序路径下存放一个**top_Performance.sh**模板脚本。
		因每个机顶盒top命令查询展示的列信息位置不固定，程序自动在开启性能监测前查询top命令的列信息，修改top_Performance.sh脚本中CSV表头，根据最新的top获取到的CSV表头修改print中列位置取值。
		**启动性能监测**：先检测盒子内部是否存在top_Performance.sh脚本，并验证脚本文件的MD5值，如果文件存在变更，将修改后的top_Performance.sh push 到/system/bin/目录下，并赋值755；
					启动脚本："nohup /system/bin/top_Performance.sh > /dev/null 2>&1 & "，启动脚本后，/sdcard/路径下会生成2个文件，logfile.csv和performance.pid。
           logfile.csv：是存储的通过top命令获取的探针PID相关信息。
           performance.pid：是存储的脚本对应的PID，方便后续关闭性能监测使用。
					对应的操作需要有日志打印
		**关闭性能监测**：通过ps命令查询对应top_Performance.sh执行存储在performance.pid的pid,kill 掉pid进程；
		**提取性能监测文件**:将性能监测文件/sdcard/logfile.csv，通过pull命令提取到本地；
		**手动分析性能**：手动选择提出的logfile.csv文件，将文件内容根据进程名，按照%cpu和%mem进行折线图报表展示，就可以统计出探针性能占用。
				。
