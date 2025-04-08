import sys
import os
import re
import time
import tempfile
import hashlib
import subprocess
from PyQt6.QtCore import Qt, QDateTime
from PyQt6.QtWidgets import (QVBoxLayout, QFileDialog, QLabel, QDialog, QMessageBox, QTableWidget, QTableWidgetItem,
                             QHeaderView, QCheckBox,
                             QAbstractItemView, QDialogButtonBox, QProgressDialog, QApplication, QPushButton,QWidget, QHBoxLayout,QLineEdit, QTextEdit, )


class LogFileSelector(QDialog):
    """日志文件选择对话框"""

    def __init__(self, parent_widget=None, log_type="log", custom_path=None, specific_files=None):
        super().__init__(parent_widget)
        self.parent_widget = parent_widget  # 使用新变量名保存父对象
        self.log_type = log_type
        self.custom_path = custom_path  # 新增自定义路径
        self.specific_files = specific_files  # 特定文件列表

        # 动态设置窗口标题
        title = f"选择{log_type}日志文件" if not specific_files else "选择library/agent日志"
        self.setWindowTitle(title)

        # 创建界面组件
        self.table = QTableWidget()
        self.table.setColumnCount(4)
        self.table.setHorizontalHeaderLabels(["选择", "文件名", "修改时间", "大小"])
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)

        # 按钮组
        self.btn_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Cancel |
                                        QDialogButtonBox.StandardButton.Ok)  # 添加标准按钮
        self.btn_box.button(QDialogButtonBox.StandardButton.Ok).setText("提取选中")
        self.btn_box.addButton("全选", QDialogButtonBox.ButtonRole.ActionRole).clicked.connect(self.select_all)
        self.btn_box.addButton("反选", QDialogButtonBox.ButtonRole.ActionRole).clicked.connect(self.invert_selection)
        # 绑定标准按钮信号
        self.btn_box.accepted.connect(self.extract_selected)
        self.btn_box.rejected.connect(self.reject)  # 新增关闭逻辑
        # 布局
        layout = QVBoxLayout()
        layout.addWidget(self.table)
        layout.addWidget(self.btn_box)
        self.setLayout(layout)

        self.load_file_list()
        self.base_path = custom_path if custom_path else f"/data/data/com.vixtel.stb.agent/files/{log_type}"  # 新增基础路径属性

    def load_file_list(self):
        """改进后的文件加载方法,记录文件加载过程"""
        self.parent_widget.log(f"开始加载{self.log_type}日志列表...")

        if self.specific_files:
            # 特殊处理预定义文件列表
            self.handle_specific_files()
            return

        cmd = (
            f'shell "su -c \'ls -l /data/data/com.vixtel.stb.agent/files/{self.log_type}\'"'
            if self.parent_widget.is_root_required()  # 使用新变量名
            else f'shell ls -l /data/data/com.vixtel.stb.agent/files/{self.log_type}'
        )
        output = self.parent_widget.run_adb(
            f'-s {self.parent_widget.ip_input.text()} {cmd}'
        )
        self.parse_file_list(output)
        self.parent_widget.log(f"找到{self.table.rowCount()}个日志文件")

    def handle_specific_files(self):
        """处理预定义文件列表"""
        self.table.setRowCount(0)

        ip = self.parent_widget.ip_input.text()
        device_path = self.custom_path + "/"

        # 一次性查询所有文件
        file_list = " ".join([f'"{device_path}{f}"' for f in self.specific_files])
        cmd = f'shell ls -l {file_list}'
        output = self.parent_widget.run_adb(f'-s {ip} {cmd}')

        # 添加调试日志
        print(f"ADB命令输出：\n{output}")  # 调试用

        # 解析完整输出
        self.parse_file_list(output)

    def parse_file_list(self, raw_output):
        """使用增强正则表达式解析"""
        self.table.setRowCount(0)

        # 增强正则表达式（兼容带路径的文件名）
        ls_pattern = re.compile(
            r'^([-rwxdlsStT]{10,12})\s+\d+\s+\S+\s+\S+\s+(\d+)\s+'
            r'(\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}|'
            r'\w{3}\s+\d{1,2}\s+\d{2}:\d{2}|'
            r'\w{3}\s+\d{1,2}\s+\d{4})\s+(.+)$'
        )

        for line in raw_output.split('\n'):
            line = line.strip()
            if not line or line.startswith('total'):
                continue

            match = ls_pattern.match(line)
            if not match:
                continue

            perm, size, date_str, full_path = match.groups()  # 获取完整路径
            filename = os.path.basename(full_path)  # 提取纯文件名

            # 仅过滤目录
            if perm.startswith('d'):
                continue

            # 添加行到表格（显示纯文件名）
            row = self.table.rowCount()
            self.table.insertRow(row)

            # 复选框
            check = QCheckBox()
            self.table.setCellWidget(row, 0, check)

            # 文件名列
            self.table.setItem(row, 1, QTableWidgetItem(filename))

            # 处理日期格式
            try:
                if '-' in date_str:  # 2023-08-15格式
                    modify_time = QDateTime.fromString(date_str, "yyyy-MM-dd HH:mm")
                else:  # Aug 15 14:22格式
                    current_year = QDateTime.currentDateTime().date().year()
                    modify_time = QDateTime.fromString(f"{current_year} {date_str}", "yyyy MMM dd HH:mm")
            except Exception as e:
                print(f"时间解析失败：{date_str} - {str(e)}")
                modify_time = QDateTime()

            # 修改时间
            time_label = QLabel()
            if modify_time.isValid():
                time_label.setText(modify_time.toString("yyyy-MM-dd HH:mm"))
            else:
                time_label.setText(date_str)
            self.table.setCellWidget(row, 2, time_label)

            # 文件大小
            size_item = QTableWidgetItem(self.format_size(size))
            size_item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            self.table.setItem(row, 3, size_item)

    def format_size(self, bytes_str):
        """格式化文件大小"""
        try:
            size = int(bytes_str)
            if size >= 1024 * 1024:
                return f"{size / 1024 / 1024:.1f} MB"
            elif size >= 1024:
                return f"{size / 1024:.1f} KB"
            return f"{size} B"
        except:
            return bytes_str

    def get_selected_files(self):
        """获取选中的文件列表"""
        selected = []
        for row in range(self.table.rowCount()):
            if self.table.cellWidget(row, 0).isChecked():
                filename = self.table.item(row, 1).text()
                selected.append(filename)
        return selected

    def select_all(self):
        """全选/取消全选"""
        current_state = not all(
            self.table.cellWidget(row, 0).isChecked()
            for row in range(self.table.rowCount())
        )

        for row in range(self.table.rowCount()):
            self.table.cellWidget(row, 0).setChecked(current_state)

    def invert_selection(self):
        """反选"""
        for row in range(self.table.rowCount()):
            check = self.table.cellWidget(row, 0)
            check.setChecked(not check.isChecked())

    def extract_selected(self):
        """增强日志记录的提取方法,记录文件提取详情"""
        files = self.get_selected_files()
        if not files:
            self.parent_widget.log("提取取消：未选择文件")
            QMessageBox.warning(self, "警告", "请先选择要提取的文件")
            return

        dest_dir = QFileDialog.getExistingDirectory(self, "选择保存目录")
        if not dest_dir:
            self.parent_widget.log("提取取消：未选择保存目录")
            return

        self.parent_widget.log(f"开始提取{len(files)}个文件到：{dest_dir}")

        ip = self.parent_widget.ip_input.text()
        success_count = 0
        failed_files = []

        # 显示进度对话框
        progress = QProgressDialog("文件提取中...", "取消", 0, len(files), self)
        progress.setWindowModality(Qt.WindowModality.WindowModal)

        for index, filename in enumerate(files):
            # 修正源路径生成逻辑
            src_path = f"{self.base_path}/{filename}"  # 使用统一基础路径

            # 特殊处理sdcard路径（无嵌套目录）
            if self.base_path == "/sdcard":
                src_path = f"{self.base_path}/{filename}"

            dest_path = os.path.join(dest_dir, filename)

            # 执行adb pull命令
            cmd = f'-s {ip} pull "{src_path}" "{dest_dir}"'
            output = self.parent_widget.run_adb(cmd)

            # 验证结果
            if os.path.exists(dest_path) and os.path.getsize(dest_path) > 0:
                success_count += 1
            else:
                failed_files.append(filename)

        progress.close()
        # 显示详细结果
        result_msg = f"成功提取 {success_count}/{len(files)} 个文件\n"
        if failed_files:
            result_msg += f"失败文件：\n" + "\n".join(failed_files[:3]) + ("\n..." if len(failed_files) > 3 else "")
        QMessageBox.information(self, "提取结果", result_msg)
        self.accept()


class LogExtractDialog(QDialog):
    """日志提取对话框"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("日志提取")
        self.setFixedSize(300, 150)

        layout = QVBoxLayout()

        # 全部提取按钮
        btn_full = QPushButton("全部提取探针日志", self)
        btn_full.clicked.connect(self.extract_full_logs)
        layout.addWidget(btn_full)

        # 部分提取按钮
        btn_partial = QPushButton("提取部分日志", self)
        btn_partial.clicked.connect(self.show_partial_options)
        layout.addWidget(btn_partial)

        self.setLayout(layout)

    def extract_full_logs(self):
        """提取完整日志"""
        dest_dir = QFileDialog.getExistingDirectory(self, "选择保存目录")
        if dest_dir:
            cmd = "pull /data/data/com.vixtel.stb.agent/files"
            output = self.parent().run_adb(f'-s {self.parent().ip_input.text()} {cmd} "{dest_dir}"')
            QMessageBox.information(self, "完成", "完整日志提取完成！")

    def show_partial_options(self):
        sub_dialog = QDialog(self)
        sub_dialog.setWindowTitle("选择日志类型")
        sub_dialog.setFixedSize(300, 250)  # 增加高度

        layout = QVBoxLayout()

        btn_log = QPushButton("提取log目录", sub_dialog)
        btn_log.clicked.connect(lambda: self.extract_partial("log"))

        btn_log_detail = QPushButton("选择log文件", sub_dialog)
        btn_log_detail.clicked.connect(
            lambda: LogFileSelector(parent_widget=self.parent(), log_type="log").exec()  # 传递正确的参数
        )
        # 提取crash目录
        btn_crash = QPushButton("提取crash目录", sub_dialog)
        btn_crash.clicked.connect(lambda: self.extract_partial("crash"))

        # 新增library/agent日志按钮
        btn_library_agent = QPushButton("提取library/agent日志", sub_dialog)
        btn_library_agent.clicked.connect(self.show_library_agent_selector)

        layout.addWidget(btn_log)
        layout.addWidget(btn_log_detail)
        layout.addWidget(btn_crash)
        layout.addWidget(btn_library_agent)
        sub_dialog.setLayout(layout)
        sub_dialog.exec()

    def extract_partial(self, log_type):
        """提取指定类型日志"""
        dest_dir = QFileDialog.getExistingDirectory(self, "选择保存目录")
        if dest_dir:
            cmd = f"pull /data/data/com.vixtel.stb.agent/files/{log_type}"
            output = self.parent().run_adb(f'-s {self.parent().ip_input.text()} {cmd} "{dest_dir}"')
            QMessageBox.information(self, "完成", f"{log_type}日志提取完成！")

    def show_library_agent_selector(self):
        """显示library/agent日志选择器"""
        log_files = [
            "stbagent.log", "stblibrary.log",
            "stbsocketlibrary.log", "testagent.log",
            "testlibrary.log"
        ]
        LogFileSelector(
            parent_widget=self.parent(),
            log_type="sdcard",  # 使用特殊标识
            custom_path="/sdcard",  # 明确指定自定义路径
            specific_files=log_files
        ).exec()


class STBTool(QWidget):
    def __init__(self):
        super().__init__()
        self.adb_timeout = 50  # 可配置的超时时间
        self.setWindowTitle("机顶盒管理工具")
        self.resize(800, 600)

        # 输入框和按钮
        self.ip_input = QLineEdit(self)
        self.ip_input.setPlaceholderText("请输入机顶盒IP地址")
        self.connect_btn = QPushButton("连接", self)
        self.deploy_btn = QPushButton("部署", self)
        self.other_ops_btn = QPushButton("其他操作", self)
        self.reboot_btn = QPushButton("重启机顶盒", self)
        self.monitor_btn = QPushButton("性能监测", self)

        # ADB 命令输入框
        self.adb_command_input = QLineEdit(self)
        self.adb_command_input.setPlaceholderText("输入ADB命令")
        self.run_adb_btn = QPushButton("执行", self)

        # 日志窗口
        self.log_output = QTextEdit(self)
        self.log_output.setReadOnly(True)

        # 布局
        top_layout = QHBoxLayout()
        top_layout.addWidget(QLabel("IP地址:"))
        top_layout.addWidget(self.ip_input)
        top_layout.addWidget(self.connect_btn)
        top_layout.addWidget(self.deploy_btn)
        top_layout.addWidget(self.other_ops_btn)
        top_layout.addWidget(self.reboot_btn)
        top_layout.addWidget(self.monitor_btn)

        adb_layout = QHBoxLayout()
        adb_layout.addWidget(self.adb_command_input)
        adb_layout.addWidget(self.run_adb_btn)

        main_layout = QVBoxLayout()
        main_layout.addLayout(top_layout)
        main_layout.addLayout(adb_layout)
        main_layout.addWidget(self.log_output)

        self.setLayout(main_layout)

        # 绑定事件
        self.connect_btn.clicked.connect(self.connect_stb)
        self.deploy_btn.clicked.connect(self.deploy_files)
        self.other_ops_btn.clicked.connect(self.other_operations)
        self.reboot_btn.clicked.connect(self.reboot_stb)
        self.run_adb_btn.clicked.connect(self.run_adb_command)
        self.monitor_btn.clicked.connect(self.show_performance_monitor)

    def log(self, message, command=False):
        """增强日志方法，实时刷新界面"""
        prefix = "[CMD] " if command else ""
        self.log_output.append(f"{prefix}{message}")
        QApplication.processEvents()  # 强制刷新界面

    def run_adb_command(self):
        """执行自定义 ADB 命令"""
        command = self.adb_command_input.text().strip()
        if command:
            output = self.run_adb(command)
            self.log(f"> {command}\n{output}")

    def run_adb(self, command):
        """改进的ADB命令执行方法（使用打包的ADB）"""
        # 获取ADB路径
        if getattr(sys, 'frozen', False):  # 打包后环境
            base_dir = sys._MEIPASS
        else:  # 开发环境
            base_dir = os.path.dirname(os.path.abspath(__file__))

        adb_path = os.path.join(base_dir, "platform-tools", "adb.exe")
        full_cmd = f'"{adb_path}" {command}'  # 使用绝对路径
        self.log(f"执行命令: {full_cmd}", command=True)

        try:
            process = subprocess.Popen(
                full_cmd,
                shell=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                encoding='utf-8',
                bufsize=1
            )

            stdout_lines = []
            start_time = time.time()
            timeout = 20

            while True:
                if time.time() - start_time > timeout:
                    process.kill()
                    self.log("命令执行超时")
                    return "Timeout Error"

                # 实时读取输出
                output = process.stdout.readline()
                if output:
                    stripped_output = output.strip()
                    stdout_lines.append(stripped_output)
                    self.log(f"实时输出: {stripped_output}")

                return_code = process.poll()
                if return_code is not None:
                    break
                time.sleep(0.1)

            # 获取剩余输出
            remaining_out, err = process.communicate()
            if remaining_out:
                remaining_lines = remaining_out.splitlines()
                stdout_lines.extend(remaining_lines)
                for line in remaining_lines:
                    self.log(f"实时输出: {line.strip()}")

            # 仅在有内容时记录完整输出
            full_output = '\n'.join(stdout_lines)
            if full_output.strip():  # 关键修改：检查输出是否非空
                self.log(f"完整输出:\n{full_output}")

            return full_output if return_code == 0 else f"Error: {full_output}"

        except Exception as e:
            self.log(f"执行异常: {str(e)}")
            return str(e)

    def connect_stb(self):
        """增强连接日志"""
        ip = self.ip_input.text().strip()
        if not ip:
            self.log("连接失败：未输入IP地址")
            QMessageBox.warning(self, "警告", "请输入IP地址")
            return

        self.log(f"尝试连接机顶盒：{ip}")
        output = self.run_adb(f"connect {ip}")

        if "connected" in output.lower():
            self.log(f"连接成功：{ip}")
        else:
            self.log(f"连接失败：{output}")

    def deploy_files(self):
        """增强部署日志"""
        self.log("开始部署流程")
        folder = QFileDialog.getExistingDirectory(self, "选择部署文件夹")
        if not folder:
            self.log("部署取消：未选择文件夹")
            return

        self.log(f"选择的部署文件夹: {folder}")
        if folder:
            # 部署startstbagent.sh
            sh_path = os.path.join(folder, 'startstbagent.sh')
            if os.path.exists(sh_path):
                self.log("部署startstbagent.sh...")
                output = self.run_adb(f'push "{sh_path}" /system/bin/')
                self.run_adb("shell chmod 755 /system/bin/startstbagent.sh")
            else:
                self.log("未找到startstbagent.sh文件", command=True)

            # 部署testagent
            sh_path = os.path.join(folder, 'testagent')
            if os.path.exists(sh_path):
                self.log("部署testagent...")
                output = self.run_adb(f'push "{sh_path}" /system/bin/')
                self.run_adb("shell chmod 755 /system/bin/testagent")
            else:
                self.log("未找到testagent文件", command=True)

            # 处理 STBIQ APK
            apk_files = [f for f in os.listdir(folder) if f.startswith("STBIQ") and f.endswith(".apk")]
            if apk_files:
                apk_path = os.path.join(folder, apk_files[0])
                if os.path.exists(sh_path):
                    self.log("部署STBIQ APK...")
                    self.run_adb("shell rm -rf /system/app/STBIQ*.apk")  # 删除旧版本
                    self.run_adb(f'push "{apk_path}" /system/app/')
                else:
                    self.log("未找到STBIQ APK文件", command=True)

            self.log("部署完成")

    def reboot_stb(self):
        """重启机顶盒"""
        self.run_adb("reboot")
        self.log("机顶盒已重启")

    def other_operations(self):
        """其他操作功能主界面"""
        self.log("执行其他操作")
        dialog = QDialog(self)
        dialog.setWindowTitle("其他操作")
        dialog.setFixedSize(300, 150)

        layout = QVBoxLayout()

        # 日志提取按钮
        btn_extract = QPushButton("日志提取", dialog)
        btn_extract.clicked.connect(lambda: LogExtractDialog(self).exec())
        layout.addWidget(btn_extract)

        # 日志开关按钮
        btn_switch = QPushButton("日志开关配置", dialog)
        btn_switch.clicked.connect(self.log_switch)
        layout.addWidget(btn_switch)

        dialog.setLayout(layout)
        dialog.exec()

    def log_switch(self):
        """日志开关配置"""
        LogSwitchDialog(self).exec()

    def is_root_required(self):
        """检测是否需要root权限"""
        output = self.run_adb(f'-s {self.ip_input.text()} shell ls /data/data/com.vixtel.stb.agent/files')
        return "Permission denied" in output

    def show_performance_monitor(self):
        """显示性能监测对话框"""
        PerformanceMonitorDialog(self).exec()

    def get_top_headers(self):
        """获取当前设备的top命令列信息（仅取前10行）"""
        output = self.run_adb(f'-s {self.ip_input.text()} shell "top -b -n 1 | head -n 10"')  # 关键修改
        if "Error" in output:
            return None

        # 解析列头
        headers_line = ""
        for line in output.split('\n'):
            if "PID" in line and "USER" in line:  # 匹配列头特征行
                headers_line = line
                break

        if not headers_line:
            return None

        # 清理特殊字符并分割列
        headers = headers_line.strip().replace("%", "").split()
        return {header: idx for idx, header in enumerate(headers)}


class LogSwitchDialog(QDialog):
    """日志开关配置对话框"""

    FILE_CONFIG = {
        "appLog.log": "1",
        "socketlibraryLogConfig.txt": "{\"logLevelType\":\"TRACE\"}",
        "stbagentLogConfig.txt": "{\"logLevelType\":\"TRACE\"}",
        "stblibraryLogConfig.txt": "{\"logLevelType\":\"TRACE\"}",
        "testagentLogConfig.txt": "{\"logLevelType\":\"TRACE\"}",
        "testlibraryLogConfig.txt": "{\"logLevelType\":\"TRACE\"}"
    }

    def __init__(self, parent=None):
        super().__init__(parent)
        self.parent = parent
        self.setWindowTitle("日志开关配置")
        self.setFixedSize(400, 400)

        layout = QVBoxLayout()

        # 按钮布局
        btn_layout = QHBoxLayout()
        self.btn_enable = QPushButton("开启日志")
        self.btn_disable = QPushButton("关闭日志")
        btn_layout.addWidget(self.btn_enable)
        btn_layout.addWidget(self.btn_disable)

        # 文件列表
        self.table = QTableWidget()
        self.table.setColumnCount(2)
        self.table.setHorizontalHeaderLabels(["选择", "配置文件"])
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.table.setRowCount(len(self.FILE_CONFIG))

        for row, (filename, _) in enumerate(self.FILE_CONFIG.items()):
            # 复选框
            checkbox = QCheckBox()
            self.table.setCellWidget(row, 0, checkbox)
            # 文件名
            self.table.setItem(row, 1, QTableWidgetItem(filename))

        # 添加组件
        layout.addLayout(btn_layout)
        layout.addWidget(self.table)
        self.setLayout(layout)

        # 绑定事件
        self.btn_enable.clicked.connect(lambda: self.handle_files(enable=True))
        self.btn_disable.clicked.connect(lambda: self.handle_files(enable=False))

    def get_selected_files(self):
        """获取选中的文件列表"""
        selected = []
        for row in range(self.table.rowCount()):
            if self.table.cellWidget(row, 0).isChecked():
                selected.append(self.table.item(row, 1).text())
        return selected

    def handle_files(self, enable=True):
        """处理文件操作"""
        files = self.get_selected_files()
        if not files:
            QMessageBox.warning(self, "警告", "请至少选择一个配置文件")
            return

        if enable:
            self.push_files(files)
        else:
            self.delete_files(files)

    def push_files(self, files):
        """推送配置文件到设备"""
        device_path = "/data/local/vixtel/conf/"
        success = 0

        with tempfile.TemporaryDirectory() as tmpdir:
            for filename in files:
                try:
                    # 生成临时文件
                    content = self.FILE_CONFIG[filename]
                    tmp_path = os.path.join(tmpdir, filename)
                    with open(tmp_path, "w", encoding="utf-8") as f:
                        f.write(content)

                    # 执行push命令
                    cmd = f'-s {self.parent.ip_input.text()} push "{tmp_path}" "{device_path}{filename}"'
                    output = self.parent.run_adb(cmd)

                    if "error" in output.lower():
                        raise RuntimeError(output)
                    success += 1
                except Exception as e:
                    self.parent.log(f"推送失败 {filename}: {str(e)}")

        QMessageBox.information(self, "完成",
                                f"成功推送 {success}/{len(files)} 个文件")

    def delete_files(self, files):
        """删除设备上的配置文件"""
        device_path = "/data/local/vixtel/conf/"
        success = 0

        for filename in files:
            try:
                cmd = f'-s {self.parent.ip_input.text()} shell rm "{device_path}{filename}"'
                output = self.parent.run_adb(cmd)

                if "No such file" in output:
                    raise FileNotFoundError(output)
                success += 1
            except Exception as e:
                self.parent.log(f"删除失败 {filename}: {str(e)}")

        QMessageBox.information(self, "完成",
                                f"成功删除 {success}/{len(files)} 个文件")


class PerformanceMonitorDialog(QDialog):
    """性能监测对话框"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.parent = parent
        self.setWindowTitle("性能监测")
        self.setFixedSize(300, 200)

        layout = QVBoxLayout()

        self.btn_start = QPushButton("启动性能监测")
        self.btn_stop = QPushButton("关闭性能监测")
        self.btn_extract = QPushButton("提取监测文件")

        layout.addWidget(self.btn_start)
        layout.addWidget(self.btn_stop)
        layout.addWidget(self.btn_extract)

        self.setLayout(layout)

        # 绑定事件
        self.btn_start.clicked.connect(self.start_monitoring)
        self.btn_stop.clicked.connect(self.stop_monitoring)
        self.btn_extract.clicked.connect(self.extract_logs)

    def start_monitoring(self):
        """启动性能监测"""
        # 生成动态脚本
        headers = self.parent.get_top_headers()
        if not headers:
            QMessageBox.warning(self, "错误", "无法获取top命令列信息")
            return

        # 生成脚本内容
        script_content = self.generate_script(headers)
        current_md5 = self.get_remote_md5()
        new_md5 = hashlib.md5(script_content.encode()).hexdigest()

        # 检查并更新脚本
        if current_md5 != new_md5:
            self.parent.log("检测到脚本变更，正在更新...")
            with tempfile.NamedTemporaryFile(delete=False) as tmp:
                tmp.write(script_content.encode())
                tmp_path = tmp.name

            self.parent.run_adb(f'-s {self.parent.ip_input.text()} push "{tmp_path}" /system/bin/top_Performance.sh')
            self.parent.run_adb(f'-s {self.parent.ip_input.text()} shell chmod 755 /system/bin/top_Performance.sh')
            os.unlink(tmp_path)

        # 启动脚本 使用exec替换当前进程 添加输出重定向
        output = self.parent.run_adb(
            f'-s {self.parent.ip_input.text()} shell "nohup /system/bin/top_Performance.sh > /dev/null 2>&1 &"'
        )

        # 等待PID文件生成（最多尝试3次，每次间隔1秒）
        max_retries = 3
        pid = None
        for _ in range(max_retries):
            output = self.parent.run_adb(
                f'-s {self.parent.ip_input.text()} shell "cat /sdcard/performance.pid 2>/dev/null"'
            )
            if output.strip().isdigit():
                pid = output.strip()
                break
            time.sleep(1)

        if pid:
            self.current_pid = pid
            self.parent.log(f"性能监测已启动，进程PID: {pid}")
            QMessageBox.information(self, "成功", f"性能监测已启动（PID: {pid}）")
        else:
            self.parent.log("启动失败：未找到PID文件或内容无效")
            QMessageBox.warning(self, "错误", "启动监测失败，请检查设备日志")

    def stop_monitoring(self):
        """停止性能监测（使用PID文件中的进程ID）"""
        if not hasattr(self, 'current_pid') or not self.current_pid:
            QMessageBox.warning(self, "警告", "未找到运行中的监测进程")
            return

        # 验证进程是否存在
        check_output = self.parent.run_adb(
            f'-s {self.parent.ip_input.text()} shell "ps -p {self.current_pid}"'
        )
        if "No such process" in check_output:
            self.parent.log(f"进程已终止（PID: {self.current_pid}）")
            QMessageBox.information(self, "提示", "进程已终止")
            return

        # 终止进程
        output = self.parent.run_adb(
            f'-s {self.parent.ip_input.text()} shell "kill {self.current_pid}"'
        )
        if "error" not in output.lower():
            self.parent.log(f"已停止监测进程（PID: {self.current_pid}）")
            QMessageBox.information(self, "成功", "已停止性能监测")
        else:
            self.parent.log(f"终止进程失败（PID: {self.current_pid}）")
            QMessageBox.warning(self, "错误", "终止进程失败")

    def extract_logs(self):
        """提取日志文件"""
        dest_dir = QFileDialog.getExistingDirectory(self, "选择保存目录")
        if dest_dir:
            self.parent.run_adb(f'-s {self.parent.ip_input.text()} pull /sdcard/logfile.csv "{dest_dir}"')
            self.parent.log(f"监测日志已保存至: {dest_dir}")
            QMessageBox.information(self, "完成", "日志提取完成")

    def generate_script(self, headers):
        """生成动态脚本"""
        column_mapping = {
            'PID': '$1',
            'USER': '$2',
            'PR': '$3',
            'NI': '$4',
            'VIRT': '$5',
            'RES': '$6',
            'SHR': '$7',
            'S': '$8',
            '%CPU': '$9',
            '%MEM': '$10',
            'TIME+': '$11',
            'COMMAND': '$12'
        }

        # 构建awk打印语句
        awk_print = []
        for header in ['timestamp', 'PID', 'USER', 'PR', 'NI', 'VIRT', 'RES', 'SHR', 'S', '%CPU', '%MEM', 'TIME+',
                       'COMMAND']:
            if header == 'timestamp':
                awk_print.append('ts')
            else:
                awk_print.append(column_mapping.get(header, '""'))

        # 从top_Performance.sh读取模板并替换（使用UTF-8编码）
        with open('top_Performance.sh', 'r', encoding='utf-8') as f:  # 关键修改点
            script = f.read()

        script = script.replace(
            'echo "timestamp,pid,user,pr,ni,virt,res,shr,s,%cpu,%mem,time+,args" > "$LOGFILE"',
            f'echo "timestamp,{",".join(column_mapping.keys())}" > "$LOGFILE"'
        )
        script = script.replace(
            'print ts, $1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12',
            f'print {", ".join(awk_print)}'
        )
        return script

    def get_remote_md5(self):
        """获取设备端文件的MD5"""
        output = self.parent.run_adb(
            f'-s {self.parent.ip_input.text()} shell "md5sum /system/bin/top_Performance.sh 2>/dev/null"')
        return output.split()[0] if output else ""


if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = STBTool()
    window.show()
    sys.exit(app.exec())
