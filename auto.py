import sys
import os
import re
import time
import tempfile
import hashlib
import subprocess
import pandas as pd
import matplotlib.pyplot as plt
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.backends.backend_qtagg import NavigationToolbar2QT as NavigationToolbar
from matplotlib.figure import Figure
from PyQt6.QtCore import Qt, QDateTime, QThread, pyqtSignal
from PyQt6.QtWidgets import (QVBoxLayout, QFileDialog, QLabel, QDialog, QMessageBox, QTableWidget, QTableWidgetItem,
                             QHeaderView, QCheckBox, QAbstractItemView, QDialogButtonBox, QProgressDialog,
                             QApplication, QPushButton, QWidget, QHBoxLayout, QLineEdit, QTextEdit,
                             QListWidget, QListWidgetItem, QSplitter, QFrame)
from PyQt6.QtCore import Qt

# ✅ 防止中文乱码
import matplotlib
matplotlib.rcParams['font.sans-serif'] = ['SimHei']  # 支持中文，如“内存占用(MB)”
matplotlib.rcParams['axes.unicode_minus'] = False


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
            r'^([-rwxdlsStT]{10,12})\s+'  # 权限
            r'\d+\s+'  # 硬链接数
            r'\S+\s+'  # 所有者
            r'\S+\s+'  # 组
            r'(\d+)\s+'  # 文件大小（允许长数字）
            r'('  # 日期部分
            r'\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}|'  # 格式1: 2025-05-20 11:43
            r'\w{3}\s+\d{1,2}\s+\d{2}:\d{2}|'  # 格式2: Apr 27 10:38
            r'\w{3}\s+\d{1,2}\s+\d{4}'  # 格式3: Aug 15 2025
            r')\s+'
            r'(.+)$'  # 路径（贪婪匹配到行末）
        )

        for line in raw_output.split('\n'):
            line = line.strip()
            if not line:
                continue

            # 过滤错误行（如 "Error: ..."）
            if line.lower().startswith('error:'):
                print(f"[WARNING] 忽略错误行: {line}")
                continue

            # 跳过 "total ..." 行
            if line.startswith('total'):
                continue

            match = ls_pattern.match(line)
            if not match:
                print(f"[ERROR] 未匹配的行: {line}")  # 输出未匹配的完整行
                continue

            # 提取字段
            perm, size, date_str, full_path = match.groups()
            filename = os.path.basename(full_path.strip())  # 确保路径无前后空格

            # 调试日志
            print(f"[DEBUG] 匹配成功: {line}")
            print(f"[DEBUG] 分组结果: perm={perm}, size={size}, date={date_str}, path={full_path}")
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
        self.other_ops_btn = QPushButton("日志操作", self)
        self.reboot_btn = QPushButton("重启机顶盒", self)
        self.monitor_btn = QPushButton("性能监测", self)
        self.storage_btn = QPushButton("存储空间监测", self)
        self.analysis_btn = QPushButton("性能分析功能", self)


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
        top_layout.addWidget(self.storage_btn)
        top_layout.addWidget(self.analysis_btn)

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
        self.storage_btn.clicked.connect(self.show_storage_monitor)
        self.analysis_btn.clicked.connect(self.show_performance_analysis)

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

            return full_output
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
        dialog.setWindowTitle("日志操作")
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
        """动态解析列头（修复 S 列识别问题）"""
        # 执行命令获取输出
        output = self.run_adb(
            f'-s {self.ip_input.text()} shell "top -b -n 1 | grep -E \'PID|ARGS|COMMAND\' | grep -vE \'grep|sh -c\'"'
        )

        # 处理编码问题
        try:
            cleaned_output = output.encode('latin-1').decode('utf-8', errors='ignore')
        except:
            cleaned_output = output

        # 匹配列头行
        header_line = None
        for line in cleaned_output.split('\n'):
            line = line.strip()
            if re.search(r'\bPID\b.*\bARGS\b', line, re.IGNORECASE):
                header_line = line
                break

        if not header_line:
            self.log("列头匹配失败")
            return None

        # 关键修复：分离 S 和 %CPU
        cleaned_header = re.sub(r'(\bS)\[%CPU\]', r'\1 %CPU', header_line)  # S[%CPU] -> S %CPU
        cleaned_header = re.sub(r'\s{2,}', ' ', cleaned_header)

        # 精准分割列名
        columns = re.findall(r'\b\w+\+?\b|\%?\w+', cleaned_header)
        columns = [col.upper().replace('%', '') for col in columns]

        # 列名标准化映射
        key_mappings = {
            'PID': ['PID'],
            'USER': ['USER', 'UID'],
            'PR': ['PR', 'PRI'],
            'NI': ['NI', 'NICE'],
            'VIRT': ['VIRT', 'VSZ'],
            'RES': ['RES', 'RSS'],
            'SHR': ['SHR'],
            'S': ['S', 'STAT'],  # 确保匹配 S 列
            'CPU': ['CPU', '%CPU'],  # 映射清洗后的 CPU 列
            'MEM': ['MEM', '%MEM'],
            'TIME+': ['TIME+', 'TIME'],
            'COMMAND': ['ARGS', 'COMMAND']
        }

        # 构建列映射
        final_headers = {}
        for std_name, variants in key_mappings.items():
            for var in variants:
                if var in columns:
                    final_headers[std_name] = columns.index(var)
                    break
            else:
                self.log(f"缺失关键列: {std_name}")
                return None

        self.log(f"列头解析结果: {final_headers}")
        return final_headers

    def show_storage_monitor(self):
        """显示存储空间监测对话框"""
        StorageMonitorDialog(self).exec()

    def show_performance_analysis(self):
        file_path, _ = QFileDialog.getOpenFileName(self, "选择性能监测文件", "", "CSV Files (*.csv);;All Files (*)")
        if file_path:
            try:
                dialog = PerformanceAnalysisDialogV2(file_path, self)
                dialog.exec()
            except Exception as e:
                QMessageBox.critical(self, "错误", f"无法分析文件: {str(e)}")
                self.log(f"性能分析错误: {str(e)}")

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
        """启动监控（增加版本校验）"""
        # 检查设备是否支持新脚本
        android_version = self.parent.run_adb(
            f'-s {self.parent.ip_input.text()} shell "getprop ro.build.version.release"'
        )
        if float(android_version) < 8.0:
            QMessageBox.warning(
                self, "兼容性警告",
                "Android 8.0以下设备可能不支持新版监控脚本"
            )
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
        """提取监测文件（兼容新旧版本日志格式）"""
        dest_dir = QFileDialog.getExistingDirectory(self, "选择保存目录")
        if not dest_dir:
            return

        # 提取日志文件
        self.parent.run_adb(
            f'-s {self.parent.ip_input.text()} pull /sdcard/logfile.csv "{dest_dir}"'
        )

        # 校验文件完整性
        log_path = os.path.join(dest_dir, "logfile.csv")
        if os.path.exists(log_path):
            with open(log_path, 'r') as f:
                header = f.readline().strip()
                if "total_cpu" in header:
                    self.parent.log("成功提取新版监测日志")
                else:
                    self.parent.log("警告：日志格式可能不兼容")

            QMessageBox.information(self, "完成", "日志提取成功")
        else:
            QMessageBox.warning(self, "错误", "未找到日志文件")

    def generate_script(self, headers):
        """生成动态脚本（确保系统指标解析正确）"""
        # 读取模板文件（注意编码处理）
        try:
            with open('top_Performance.sh', 'r', encoding='utf-8') as f:
                script = f.read()
        except UnicodeDecodeError:
            with open('top_Performance.sh', 'r', encoding='gbk') as f:
                script = f.read()

        # 替换系统指标解析逻辑
        cpu_parser = '''
        # 解析 CPU 使用率
        cpu_line=$(echo "$top_output" | grep -m 1 "%Cpu(s)")
        user_cpu=$(echo "$cpu_line" | awk '{print $2}' | tr -d '%%us,')
        sys_cpu=$(echo "$cpu_line" | awk '{print $4}' | tr -d '%%sy,')
        idle_cpu=$(echo "$cpu_line" | awk '{print $8}' | tr -d '%%id,')
        total_cpu=$(echo "scale=1; $user_cpu + $sys_cpu" | bc)
        '''

        mem_parser = '''
        # 解析内存信息
        mem_line=$(echo "$top_output" | grep -m 1 "^Mem")
        total_mem=$(echo "$mem_line" | awk '{print $4}' | tr -d 'k')
        used_mem=$(echo "$mem_line" | awk '{print $8}' | tr -d 'k')
        free_mem=$(echo "$mem_line" | awk '{print $10}' | tr -d 'k')
        buffers=$(echo "$mem_line" | awk '{print $12}' | tr -d 'k')
        '''

        script = script.replace('# ========== 解析系统级指标 ==========', cpu_parser + mem_parser)

        return script

    def get_remote_md5(self):
        """获取设备端文件的MD5"""
        output = self.parent.run_adb(
            f'-s {self.parent.ip_input.text()} shell "md5sum /system/bin/top_Performance.sh 2>/dev/null"')
        return output.split()[0] if output else ""


# 存储监测对话框类
class StorageMonitorDialog(QDialog):
    """存储空间监测对话框"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.parent = parent
        self.setWindowTitle("存储空间监测")
        self.setFixedSize(400, 300)
        self.script_name = "cleanup.sh"
        self.pid_file = "/sdcard/cleanup.pid"
        # 初始化时直接读取PID文件
        self.current_pid = self._read_pid_from_device()
        self.is_running = self._check_pid_active()

        layout = QVBoxLayout()

        # 路径输入
        self.path_input = QLineEdit("/data")
        path_layout = QHBoxLayout()
        path_layout.addWidget(QLabel("监控路径:"))
        path_layout.addWidget(self.path_input)

        # 阈值输入
        self.threshold_input = QLineEdit("80")
        threshold_layout = QHBoxLayout()
        threshold_layout.addWidget(QLabel("存储阈值(%):"))
        threshold_layout.addWidget(self.threshold_input)

        # 删除数量
        self.delete_input = QLineEdit("5")
        delete_layout = QHBoxLayout()
        delete_layout.addWidget(QLabel("最大删除数:"))
        delete_layout.addWidget(self.delete_input)

        # 按钮组
        btn_layout = QHBoxLayout()
        self.btn_start = QPushButton("启动监测")
        self.btn_stop = QPushButton("停止监测")
        btn_layout.addWidget(self.btn_start)
        btn_layout.addWidget(self.btn_stop)

        # 添加组件
        layout.addLayout(path_layout)
        layout.addLayout(threshold_layout)
        layout.addLayout(delete_layout)
        layout.addLayout(btn_layout)
        self.setLayout(layout)

        # 绑定事件
        self.btn_start.clicked.connect(self.start_monitoring)
        self.btn_stop.clicked.connect(self.stop_monitoring)

    def validate_inputs(self):
        """验证输入参数"""
        try:
            path = self.path_input.text().strip()
            threshold = int(self.threshold_input.text())
            max_delete = int(self.delete_input.text())

            if not path.startswith("/"):
                raise ValueError("路径必须以/开头")
            if not 1 <= threshold <= 99:
                raise ValueError("阈值需在1-99之间")
            if max_delete < 1:
                raise ValueError("删除数量至少为1")
            return True
        except ValueError as e:
            QMessageBox.warning(self, "输入错误", str(e))
            return False

    def start_monitoring(self):
        """启动存储监测"""
        if not self.validate_inputs():
            return

        # 检查本地脚本
        local_script = os.path.join(os.path.dirname(__file__), self.script_name)
        if not os.path.exists(local_script):
            QMessageBox.critical(self, "错误", f"未找到本地脚本: {self.script_name}")
            return

        # 上传并更新脚本
        remote_path = f"/system/bin/{self.script_name}"
        current_md5 = self.get_remote_md5(remote_path)
        new_md5 = self.calculate_md5(local_script)

        if current_md5 != new_md5:
            self.parent.log("更新监测脚本...")
            output = self.parent.run_adb(
                f'-s {self.parent.ip_input.text()} push "{local_script}" {remote_path}')
            self.parent.run_adb(
                f'-s {self.parent.ip_input.text()} shell chmod 755 {remote_path}')

        # 构建命令参数
        params = (
            f'"{self.path_input.text().strip()}" '  # 路径加引号防止空格问题
            f'{self.threshold_input.text().strip()} '
            f'{self.delete_input.text().strip()}'
        )

        # 启动脚本前删除旧的PID文件
        self.parent.run_adb(f'-s {self.parent.ip_input.text()} shell "rm {self.pid_file} 2>/dev/null"')

        # 启动脚本并获取PID
        cmd = f'shell "sh -c \'nohup {remote_path} {params} >/dev/null 2>&1 & echo $! > {self.pid_file}\'"'
        output = self.parent.run_adb(f'-s {self.parent.ip_input.text()} {cmd}')

        # 直接读取设备PID文件
        self.current_pid = self._read_pid_from_device()
        if self.current_pid:
            QMessageBox.information(self, "成功", f"监测已启动（PID: {self.current_pid}）")
        else:
            QMessageBox.warning(self, "错误", "启动监测失败")

    def stop_monitoring(self):
        """直接从设备读取PID并终止进程"""
        # 实时读取PID文件
        current_pid = self._read_pid_from_device()
        if not current_pid:
            QMessageBox.warning(self, "警告", "未找到运行中的监测进程")
            return

        try:
            # 终止进程树
            cmd = (
                f'shell "'
                f'for pid in $(ps -o pid --ppid {current_pid} 2>/dev/null | tail -n +2); do '
                f'  kill -9 $pid 2>/dev/null; '
                f'done; '
                f'kill -9 {current_pid} 2>/dev/null; '
                f'rm {self.pid_file} 2>/dev/null"'
            )
            output = self.parent.run_adb(f'-s {self.parent.ip_input.text()} {cmd}')

            # 验证终止结果
            check_cmd = f'shell "ps | grep -w {current_pid} | grep -v grep"'
            if not self.parent.run_adb(check_cmd):
                QMessageBox.information(self, "成功", "进程已终止")
            else:
                raise RuntimeError("进程残留")
        except Exception as e:
            QMessageBox.critical(self, "错误", f"终止失败: {str(e)}")

    def get_remote_md5(self, remote_path):
        """获取设备端文件的MD5"""
        output = self.parent.run_adb(
            f'-s {self.parent.ip_input.text()} shell "md5sum {remote_path} 2>/dev/null"')
        return output.split()[0] if output else ""

    def calculate_md5(self, file_path):
        """计算本地文件MD5"""
        hash_md5 = hashlib.md5()
        with open(file_path, "rb") as f:
            for chunk in iter(lambda: f.read(4096), b""):
                hash_md5.update(chunk)
        return hash_md5.hexdigest()

    def _read_pid_from_device(self):
        """从设备读取PID文件内容"""
        output = self.parent.run_adb(
            f'-s {self.parent.ip_input.text()} shell "cat {self.pid_file} 2>/dev/null"'
        ).strip()
        return output if output.isdigit() else None

    def _check_pid_active(self):
        """检查PID是否有效"""
        if not self.current_pid:
            return False
        output = self.parent.run_adb(
            f'-s {self.parent.ip_input.text()} shell "ps | grep -w {self.current_pid} | grep -v grep"'
        )
        return bool(output.strip())


class PerformanceAnalysisDialogV2(QDialog):
    def __init__(self, file_path, parent=None):
        super().__init__(parent)
        self.setWindowTitle("性能分析")
        self.resize(1200, 800)
        self.setSizeGripEnabled(True)
        self.setWindowFlags(self.windowFlags() | Qt.WindowType.WindowMinMaxButtonsHint)

        self.file_path = file_path
        self.data = None
        self.process_data = {}
        self.args_to_pids = {}
        self.unique_names = []
        self.visible_pids = set()
        self.is_multi_plot = True

        # 初始加载数据（使用线程避免界面卡死）
        self.load_thread = LoadDataThread(file_path)
        self.load_thread.data_loaded.connect(self.on_data_loaded)
        self.load_thread.start()

        # 主布局
        layout = QVBoxLayout(self)

        # 添加图例开关按钮
        switch_layout = QHBoxLayout()
        self.multi_plot_btn = QPushButton("切换到单图模式")
        self.multi_plot_btn.setCheckable(True)
        self.multi_plot_btn.setChecked(False)
        self.multi_plot_btn.clicked.connect(self.toggle_plot_mode)
        switch_layout.addWidget(self.multi_plot_btn)

        # 添加全选/清除按钮
        self.select_all_btn = QPushButton("全选进程")
        self.select_all_btn.clicked.connect(self.select_all_processes)
        self.clear_btn = QPushButton("清除选择")
        self.clear_btn.clicked.connect(self.clear_selection)
        switch_layout.addWidget(self.select_all_btn)
        switch_layout.addWidget(self.clear_btn)
        switch_layout.addStretch()
        layout.addLayout(switch_layout)

        # 分割视图
        splitter = QSplitter(Qt.Orientation.Horizontal)

        # 左侧面板（进程选择）
        left_panel = QWidget()
        left_layout = QVBoxLayout(left_panel)
        left_layout.addWidget(QLabel("选择进程名："))

        # 进程选择列表（仅上半部分）
        self.process_list = QListWidget()
        self.process_list.setSelectionMode(QListWidget.SelectionMode.MultiSelection)
        self.process_list.setStyleSheet("""
            QListWidget::item:selected { 
                background-color: #6fa8dc; 
                color: black; 
            }
        """)

        # 添加搜索框
        search_layout = QHBoxLayout()
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("搜索进程...")
        self.search_input.textChanged.connect(self.filter_processes)
        search_layout.addWidget(self.search_input)
        left_layout.addLayout(search_layout)

        left_layout.addWidget(self.process_list)
        left_layout.setStretch(1, 1)  # 让列表占据剩余空间

        # 右侧面板（图表）
        right_panel = QWidget()
        right_layout = QVBoxLayout(right_panel)

        # 图表画布
        self.figure = Figure(figsize=(10, 8))
        self.canvas = FigureCanvas(self.figure)
        self.toolbar = NavigationToolbar(self.canvas, self)
        right_layout.addWidget(self.toolbar)
        right_layout.addWidget(self.canvas)

        splitter.addWidget(left_panel)
        splitter.addWidget(right_panel)
        splitter.setSizes([300, 900])
        layout.addWidget(splitter)

        # 显示加载提示
        self.loading_label = QLabel("正在加载数据，请稍候...", self)
        self.loading_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.loading_label.setStyleSheet("font-size: 16px; color: #555;")
        self.loading_label.setGeometry(0, 0, self.width(), self.height())
        self.loading_label.show()

    def on_data_loaded(self, data, process_data, unique_names, args_to_pids):
        self.data = data
        self.process_data = process_data
        self.args_to_pids = args_to_pids
        self.unique_names = unique_names

        # 分配颜色（PID+指标维度组合）
        colors = plt.cm.tab20.colors
        metrics = ['res', '%cpu', '%mem']
        self.color_map = {}
        for idx, (pid, _) in enumerate(process_data.items()):
            for j, metric in enumerate(metrics):
                key = f"{pid}_{metric}"
                self.color_map[key] = colors[(3 * idx + j) % len(colors)]

        # 填充进程名
        self.process_list.clear()
        for name in unique_names:
            self.process_list.addItem(name)
        self.process_list.itemSelectionChanged.connect(self.update_plot)

        self.select_all_processes()
        self.loading_label.hide()
        self.update_plot()

    def select_all_processes(self):
        """选中所有进程"""
        for i in range(self.process_list.count()):
            self.process_list.item(i).setSelected(True)
        self.update_plot()

    def clear_selection(self):
        """清除所有选中"""
        self.process_list.clearSelection()
        self.update_plot()

    def filter_processes(self):
        """根据搜索框内容过滤进程"""
        search_text = self.search_input.text().lower()
        for i in range(self.process_list.count()):
            item = self.process_list.item(i)
            item.setHidden(search_text not in item.text().lower())

    def toggle_plot_mode(self):
        """切换多图/单图模式"""
        self.is_multi_plot = not self.is_multi_plot
        self.multi_plot_btn.setText("切换到单图模式" if self.is_multi_plot else "切换到多图模式")
        self.update_plot()

    def update_plot(self):
        """更新图表（修复布尔判断问题）"""
        # 检查数据是否加载 - 使用正确的方式
        if self.data is None or self.data.empty:
            return

        # 获取选中的进程名
        selected_names = set()
        for i in range(self.process_list.count()):
            if self.process_list.item(i).isSelected():
                selected_names.add(self.process_list.item(i).text())

        # 找出所有选中的进程名对应的process_id
        selected_pids = set()
        for name in selected_names:
            if name in self.args_to_pids:
                selected_pids.update(self.args_to_pids[name])

        # 更新可见PID集合
        self.visible_pids = selected_pids.copy()

        # 清除图表
        self.figure.clear()

        if not selected_pids:
            self.canvas.draw()
            return

        if self.is_multi_plot:
            # 多图模式
            self.create_multi_plot(selected_pids)
        else:
            # 单图模式
            self.create_single_plot(selected_pids)

        # 添加图例交互
        self.add_legend_interaction()

        self.figure.tight_layout()
        self.canvas.draw()

    def create_multi_plot(self, selected_pids):
        ax1 = self.figure.add_subplot(311)
        ax2 = self.figure.add_subplot(312)
        ax3 = self.figure.add_subplot(313)

        ax1.set_title('内存占用 (MB)', loc='left')
        ax2.set_title('CPU 使用率 (%)', loc='left')
        ax3.set_title('内存使用率 (%)', loc='left')

        handles1, labels1 = [], []
        handles2, labels2 = [], []
        handles3, labels3 = [], []

        self.line_map = {}  # 用于图例交互控制

        for pid in selected_pids:
            df = self.process_data[pid]
            alpha = 1.0 if pid in self.visible_pids else 0.3

            l1, = ax1.plot(df['timestamp'], df['res'], label=pid,
                           color=self.color_map.get(f"{pid}_res", 'tab:red'),
                           alpha=alpha, visible=(pid in self.visible_pids))
            handles1.append(l1)
            labels1.append(pid)
            self.line_map.setdefault(pid, []).append(l1)

            l2, = ax2.plot(df['timestamp'], df['%cpu'], label=pid,
                           color=self.color_map.get(f"{pid}_%cpu", 'tab:blue'),
                           alpha=alpha, visible=(pid in self.visible_pids))
            handles2.append(l2)
            labels2.append(pid)
            self.line_map.setdefault(pid, []).append(l2)

            l3, = ax3.plot(df['timestamp'], df['%mem'], label=pid,
                           color=self.color_map.get(f"{pid}_%mem", 'tab:green'),
                           alpha=alpha, visible=(pid in self.visible_pids))
            handles3.append(l3)
            labels3.append(pid)
            self.line_map.setdefault(pid, []).append(l3)

        for ax in [ax1, ax2, ax3]:
            ax.grid(True)
            ax.tick_params(axis='x', rotation=45)


        # 图例放右外侧
        leg1 = ax1.legend(handles1, labels1, loc='upper left', bbox_to_anchor=(1.01, 1))
        leg2 = ax2.legend(handles2, labels2, loc='upper left', bbox_to_anchor=(1.01, 1))
        leg3 = ax3.legend(handles3, labels3, loc='upper left', bbox_to_anchor=(1.01, 1))

        # 设置图例项可点击
        for leg, label_set in zip([leg1, leg2, leg3], [labels1, labels2, labels3]):
            for i, text in enumerate(leg.get_texts()):
                pid = label_set[i]
                text.set_picker(True)
                text.set_data = {"pid": pid}
                if pid not in self.visible_pids:
                    text.set_alpha(0.3)
                    text.set_fontstyle("italic")

        self.current_legends = [leg1, leg2, leg3]

    def create_single_plot(self, selected_pids):
        ax = self.figure.add_subplot(111)
        ax.set_title('性能指标趋势', loc='left')
        ax.grid(True)
        ax.tick_params(axis='x', rotation=45)

        ax2 = ax.twinx()
        ax3 = ax.twinx()
        ax3.spines['right'].set_position(('outward', 60))

        handles = []
        labels = []

        for pid in selected_pids:
            df = self.process_data[pid]
            alpha = 1.0 if pid in self.visible_pids else 0.3

            # 内存占用
            l1, = ax.plot(df['timestamp'], df['res'],
                          label=f"{pid} (内存)", color=self.color_map[f"{pid}_res"],
                          linestyle='-', alpha=alpha, visible=(pid in self.visible_pids))
            handles.append(l1)
            labels.append(f"{pid} (内存)")

            # CPU 使用率
            l2, = ax3.plot(df['timestamp'], df['%cpu'],
                           label=f"{pid} (CPU)", color=self.color_map[f"{pid}_%cpu"],
                           linestyle='--', alpha=alpha, visible=(pid in self.visible_pids))
            handles.append(l2)
            labels.append(f"{pid} (CPU)")

            # 内存使用率
            l3, = ax2.plot(df['timestamp'], df['%mem'],
                           label=f"{pid} (内存%)", color=self.color_map[f"{pid}_%mem"],
                           linestyle=':', alpha=alpha, visible=(pid in self.visible_pids))
            handles.append(l3)
            labels.append(f"{pid} (内存%)")

        ax.set_ylabel('内存占用 (MB)')
        ax2.set_ylabel('内存使用率 (%)', color='tab:blue')
        ax3.set_ylabel('CPU 使用率 (%)', color='tab:green')
        ax2.tick_params(axis='y', labelcolor='tab:blue')
        ax3.tick_params(axis='y', labelcolor='tab:green')

        # 合并图例，添加交互
        leg = ax.legend(handles, labels,
                        loc='upper left',
                        bbox_to_anchor=(1.01, 1),
                        fontsize=8,
                        frameon=True,
                        framealpha=0.9,
                        facecolor='white',
                        edgecolor='black',
                        labelspacing=0.3,
                        handlelength=2,
                        handler_map={})

        # 设置图例可交互
        for text, handle in zip(leg.get_texts(), leg.legend_handles):
            text.set_picker(True)
            handle.set_picker(True)

        for i, text in enumerate(leg.get_texts()):
            pid = labels[i].split(" (")[0]
            if pid not in self.visible_pids:
                text.set_alpha(0.3)
                text.set_fontstyle("italic")
            else:
                text.set_alpha(1.0)
                text.set_fontstyle("normal")

        self.current_legend = leg

    def add_legend_interaction(self):
        if hasattr(self, 'legend_pick_event'):
            self.canvas.mpl_disconnect(self.legend_pick_event)
        self.legend_pick_event = self.canvas.mpl_connect('pick_event', self.on_legend_click)

    def on_legend_click(self, event):
        label = getattr(event.artist, "get_text", lambda: None)()
        if not label:
            return
        pid = label.split(' (')[0] if ' (' in label else label

        if pid in self.visible_pids:
            self.visible_pids.remove(pid)
        else:
            self.visible_pids.add(pid)

        # 更新每条线可见性
        for line in self.line_map.get(pid, []):
            line.set_visible(pid in self.visible_pids)

        self.update_plot()


class LoadDataThread(QThread):
    """后台数据加载线程，避免界面卡死"""
    data_loaded = pyqtSignal(object, object, object, object)

    def __init__(self, file_path):
        super().__init__()
        self.file_path = file_path

    def run(self):
        """线程主函数"""
        try:
            # 加载数据
            data = pd.read_csv(self.file_path)

            # 检查数据是否为空
            if data.empty:
                self.data_loaded.emit(pd.DataFrame(), {}, [], {})
                return

            # 格式化列
            data['timestamp'] = pd.to_datetime(data['timestamp'])
            data['res'] = data['res'].apply(self.parse_memory)
            data['process_id'] = data['pid'].astype(str) + ' - ' + data['args']

            # 分组数据
            process_data = {}
            for pid, group in data.groupby('process_id'):
                process_data[pid] = group.sort_values('timestamp')

            # 获取唯一的进程名
            unique_names = data['args'].unique().tolist()

            # 构建进程名到PID的映射
            args_to_pids = {}
            for name in unique_names:
                args_to_pids[name] = []
                for pid in process_data:
                    if name in pid:
                        args_to_pids[name].append(pid)

            # 发送加载完成信号
            self.data_loaded.emit(data, process_data, unique_names, args_to_pids)

        except Exception as e:
            print(f"数据加载失败: {str(e)}")
            self.data_loaded.emit(pd.DataFrame(), {}, [], {})

    def parse_memory(self, value):
        """解析内存值"""
        try:
            if isinstance(value, str):
                value = value.lower()
                if value.endswith('g'):
                    return float(value[:-1]) * 1024
                elif value.endswith('m'):
                    return float(value[:-1])
                elif value.endswith('k'):
                    return float(value[:-1]) / 1024
            return float(value)
        except:
            return 0


if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = STBTool()
    window.show()
    sys.exit(app.exec())
