# android_auto

Android系统机顶盒针对探针自动化部署和操作
![img_1.png](img_1.png)

## **机顶盒连接**
IP地址窗口填写机顶盒的IP，点击“连接”，就可通过adb命令连接 `adb connect ip`

## **部署**
部署是针对探针和脚本文件push到指定目录下完成的，具体如下：
  - 点击“整体体部署”按钮，选择`STBIQ.*apk`、`testagent`、`startstbagent.sh`文件所在的文件夹，程序首先检查机顶盒`/system/app/`下是否存在`STBIQ.*apk`的文件，存在就删除，然后将新的apk文件push到`/system/app/`下；
  - 其次 `testagent`、`startstbagent.sh`文件会直接push到`/system/bin/`目录下，直接覆盖原文件，自动给`testagent`、`startstbagent.sh`文件赋权可执行权限，部署成功后自动弹窗提示"部署完成"。
  - 点击"单文件部署"按钮：
    - 选择需要部署的apk文件，程序会检查机顶盒`/system/app/`下是否存在`STBIQ.*apk`的文件，存在就删除，然后将新的apk文件push到`/system/app/`下，并自动给apk文件赋权可执行权限，部署成功后自动弹窗提示"部署完成"。
    - 选择testagent文件，点击"单文件部署"按钮，选择testagent文件，程序会检查机顶盒`/system/bin/`下是否存在`testagent`文件，存在就删除，然后将新的文件push到`/system/bin/`下，并自动给文件赋权可执行权限，部署成功后自动弹窗提示"部署完成"。
    - 选择`startstbagent.sh`文件，点击"单文件部署"按钮，选择`startstbagent.sh`文件，程序会检查机顶盒`/system/bin/`下是否存在`startstbagent.sh`文件，存在就删除，然后将新的文件push到`/system/bin/`下，并自动给文件赋权可执行权限，部署成功后自动弹窗提示"部署完成"。

## **重启机顶盒**
adb 通过`reboot`对连接的盒子重启。

## **其他操作**
### **主要功能一**
- 从机顶盒内取日志，可以选择取整个路径的日志，还可以选择取单独的一个日志文件提取。
- 探针日志路径为：`/data/data/com.vixtel.stb.agent/files`，`files`路径下有2个路径，`log`路径和`crash`路径；
  - `log`路径下为探针日志
  - `crash`路径下为探针崩溃日志

日志提取页面包括：
- **“全部提取机顶盒日志”** 和 **“提取部分日志”** 按钮；
  - **全部提取机顶盒日志**：提取`/data/data/com.vixtel.stb.agent/files`路径；
  - **提取部分日志**：点击后展示3个按钮：
    - **“提取log目录”**：提取`/data/data/com.vixtel.stb.agent/files/log` 目录
    - **“提取crash目录”**：提取`/data/data/com.vixtel.stb.agent/files/crash`目录
    - **“选择log文件”**：
      - 提取单个日志页面，有一个列表，列表展示`/data/data/com.vixtel.stb.agent/files/log/`下的文件；
      - 列信息包括：选择(复选框)、文件名称、日期、大小，
      - 页面底部有4个按钮：
        - **提取选中**：勾选复选框的文件，针对选择的文件提取；
        - **全选**：全选所有文件；
        - **反选**：根据已经选择的文件，反选所有没选择的文件；
        - **返回**：返回上级页面；
    - **“提取library或agent日志”**：日志路径在 `/sdcard/`; 日志名称分别为：`stbagent.log`、`stblibrary.log`、`stbsocketlibrary.log`、`testagent.log`、`testlibrary.log`
      - 参考"选择log文件"页面功能

### **主要功能二**
- 有2个按钮：**“开启日志”** 和 **“关闭日志”**；
- 页面有一个列表分别对应文件名称：
  - `appLog.log`
  - `socketlibraryLogConfig.txt`
  - `stbagentLogConfig.txt`
  - `stblibraryLogConfig.txt`
  - `testagentLogConfig.txt`
  - `testlibraryLogConfig.txt`

日志开关文件已经内置到代码中，不再需要用户在本地查找，方便操作。
- 第一列添加复选框，允许多选，勾选后：
  - **点击“开启日志”**：将勾选的文件push到机顶盒内部 `/data/local/vixtel/conf/` 路径下；
  - **点击“关闭日志”**：将勾选的文件从机顶盒内部的 `/data/local/vixtel/conf/` 路径下删除；

## **性能监测**
性能监测页面存在3个按钮：
**启动性能监测**、**关闭性能监测**、**提取性能监测文件**，程序路径下存放一个`top_Performance.sh`(`top_Performance-android4.sh`为android4设备单独编写的脚本)脚本。
- 因每个机顶盒`top`命令查询展示的列信息位置不固定，程序自动在开启性能监测前查询`top`命令的列信息，修改`top_Performance.sh`脚本中CSV表头，根据最新的`top`获取到的CSV表头修改`print`中列位置取值。
- **启动性能监测**：
  - 先检测盒子内部是否存在`top_Performance.sh`脚本，并验证脚本文件的MD5值，如果文件存在变更，将修改后的`top_Performance.sh` push 到`/system/bin/`目录下，并赋值755；
  - 启动脚本：`nohup /system/bin/top_Performance.sh > /dev/null 2>&1 & `，启动脚本后，`/sdcard/`路径下会生成2个文件，`logfile.csv` 和 `performance.pid`。
  - `logfile.csv`：存储的通过`top`命令获取的探针PID相关信息。
  - `performance.pid`：存储的脚本对应的PID，方便后续关闭性能监测使用。
  - 对应的操作需要有日志打印。

- **关闭性能监测**：
  - 通过`ps`命令查询对应`top_Performance.sh`执行存储在`performance.pid`的`pid`，`kill`掉`pid`进程；

- **提取性能监测文件**:
  - 将性能监测文件`/sdcard/logfile.csv`，通过`pull`命令提取到本地；

  - **手动分析性能**:
    - 手动选择提出的`logfile.csv`文件，将文件内容根据进程名，按照`%cpu`和`%mem`进行折线图报表展示，就可以统计出探针性能占用。
  
  

## **存储空间监测**
 测试过程中Android机顶盒经常由于日志过大占用导致存储空间不足影响机顶盒使用。存储空间监测最要是监测机顶盒内部空间大小，进行对探针路径/data/data/com.vixtel.stb.agent/files/log/日志下的文件清除功能；
 存储空间监测主要包括 **启动监测**、**停止监测** 和`cleanup.sh`监测模板脚本。

- **启动监测**：
  - 启动监测前程序允许用户输入监测的路径、存储阈值、最大删除数，不输出的情况下，默认监测路径为：/data/,存储阈值： 80%，最大删除数：5；
  - 启动监测时，自动去检查/system/bin/目录下是否存在cleanup.sh脚本，不存在就push进去，并赋权755可执行权限。如果存在脚本，检查MD5值是否跟最新的脚本一致，不一致重新更新并赋权脚本文件。
  - 监测和删除的功能已经再cleanup.sh脚本中实现，只需要运行时将传递给脚本参数；
  - 脚本执行监测时，在/sdcard/路径下生成cleanup.pid和cleanup.log文件，cleanup.pid内容为脚本运行的pid, cleanup.log为删除日志操作记录；

- **停止监测**：
   - 通过`ps`命令查询对应存储在cleanup.pid`的`pid`是否存在，kill掉`pid`进程；


## **性能分析**
 对通过性能监测功能生成的监测数据进行折线图展示

- 单图/多图模式：切换模式对应的是展示的进程（内存占用、CPU使用率、内存使用率）信息要不要拆分显示；
- 全选进程：选中所有的进程名；
- 清除选择：将选中的进程名取消选中；
- 程序进程选择：默认全部选中，可以点击选中和取消，可支持筛选；
- 图例：PID和进程名拼接形成的示例，可进行点击，支持显示和隐藏对应的PID折线图；
- 多图模式下，可以对（内存占用、CPU使用率、内存使用率）选择显示隐藏；


## **接口比对分析**
  对软探针的周期、收视和告警上报接口字段和数据跟接口文档比对

- 基础文件：软探针的各个接口的字段都在`软探针接口字段.xlsx`中
- 通过选择软探针的日志文件，进行跟基础文件进行比对，将上报的值添加在字段之后，如果字段没上报自动处理为：指标未上报，字段上报为0，自动处理为：有字段上报为0