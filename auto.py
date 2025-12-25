import sys
import os
import re
import time
import tempfile
import hashlib
import traceback
import subprocess
import pandas as pd
import matplotlib.pyplot as plt
from matplotlib.backends.backend_qt import NavigationToolbar2QT as NavigationToolbar
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.figure import Figure
from PyQt6.QtCore import Qt, QDateTime, QThread, pyqtSignal
from PyQt6.QtWidgets import (QVBoxLayout, QFileDialog, QLabel, QDialog, QMessageBox, QTableWidget, QTableWidgetItem,
                             QHeaderView, QCheckBox, QAbstractItemView, QDialogButtonBox, QProgressDialog,
                             QApplication, QPushButton, QWidget, QHBoxLayout, QLineEdit, QTextEdit,
                             QListWidget, QSplitter, QFrame)

# 在文件开头添加类型忽略注释
# pyright: reportMissingImports=false
# pyright: reportOptionalMemberAccess=false
# pyright: reportOptionalIterable=false
# pyright: reportOptionalOperand=false
# pyright: reportAttributeAccessIssue=false
# pyright: reportUndefinedVariable=false
# pyright: reportPrivateImportUsage=false

# ✅ 防止中文乱码
import matplotlib

matplotlib.rcParams['font.sans-serif'] = ['SimHei']  # 支持中文，如“内存占用(MB)”
matplotlib.rcParams['axes.unicode_minus'] = False

# 将所有异常写入日志文件
def log_exceptions(exctype, value, tb):
    with open("error_log.txt", "w", encoding="utf-8") as f:
        traceback.print_exception(exctype, value, tb, file=f)
    sys.__excepthook__(exctype, value, tb)


sys.excepthook = log_exceptions


class LogFileSelector(QDialog):
    """日志文件选择对话框"""

    def __init__(self, parent_widget=None, log_type="log", custom_path=None, specific_files=None):
        super().__init__(parent_widget)
        self.parent_widget = parent_widget
        self.log_type = log_type
        self.custom_path = custom_path
        self.specific_files = specific_files

        # 动态设置窗口标题
        title = f"选择{log_type}日志文件" if not specific_files else "选择library/agent日志"
        self.setWindowTitle(title)

        # 创建界面组件
        self.table = QTableWidget()
        self.table.setColumnCount(4)
        self.table.setHorizontalHeaderLabels(["选择", "文件名", "修改时间", "大小"])
        # 添加类型检查
        header = self.table.horizontalHeader()
        if header is not None:
            header.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)

        # 按钮组
        self.btn_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Cancel |
                                        QDialogButtonBox.StandardButton.Ok)
        # 添加类型检查
        ok_button = self.btn_box.button(QDialogButtonBox.StandardButton.Ok)
        if ok_button is not None:
            ok_button.setText("提取选中")
        
        # 添加标准按钮
        select_all_btn = self.btn_box.addButton("全选", QDialogButtonBox.ButtonRole.ActionRole)
        invert_selection_btn = self.btn_box.addButton("反选", QDialogButtonBox.ButtonRole.ActionRole)
        
        if select_all_btn is not None:
            select_all_btn.clicked.connect(self.select_all)
        if invert_selection_btn is not None:
            invert_selection_btn.clicked.connect(self.invert_selection)
            
        # 绑定标准按钮信号
        self.btn_box.accepted.connect(self.extract_selected)
        self.btn_box.rejected.connect(self.reject)
        # 布局
        layout = QVBoxLayout()
        layout.addWidget(self.table)
        layout.addWidget(self.btn_box)
        self.setLayout(layout)

        self.load_file_list()
        self.base_path = custom_path if custom_path else f"/data/data/com.vixtel.stb.agent/files/{log_type}"

    def load_file_list(self):
        """改进后的文件加载方法,记录文件加载过程"""
        # 添加类型检查
        if self.parent_widget is not None:
            self.parent_widget.log(f"开始加载{self.log_type}日志列表...")

        if self.specific_files:
            # 特殊处理预定义文件列表
            self.handle_specific_files()
            return

        # 添加类型检查
        if self.parent_widget is not None and hasattr(self.parent_widget, 'ip_input') and self.parent_widget.ip_input is not None:
            cmd = (
                f'shell "su -c \'ls -l /data/data/com.vixtel.stb.agent/files/{self.log_type}\'"'
                if self.parent_widget.is_root_required()
                else f'shell ls -l /data/data/com.vixtel.stb.agent/files/{self.log_type}'
            )
            output = self.parent_widget.run_adb(
                f'-s {self.parent_widget.ip_input.text()} {cmd}'
            )
            self.parse_file_list(output)
            if self.parent_widget is not None:
                self.parent_widget.log(f"找到{self.table.rowCount()}个日志文件")

    def handle_specific_files(self):
        """处理预定义文件列表"""
        self.table.setRowCount(0)

        # 添加类型检查
        if self.parent_widget is not None and hasattr(self.parent_widget, 'ip_input') and self.parent_widget.ip_input is not None:
            ip = self.parent_widget.ip_input.text()
        else:
            ip = ""
            
        # 添加类型检查
        if self.custom_path is not None:
            device_path = self.custom_path + "/"
        else:
            device_path = "/"
            
        # 添加类型检查
        if self.specific_files is not None:
            file_list = " ".join([f'"{device_path}{f}"' for f in self.specific_files])
        else:
            file_list = ""
            
        cmd = f'shell ls -l {file_list}'
        
        # 添加类型检查
        if self.parent_widget is not None:
            output = self.parent_widget.run_adb(f'-s {ip} {cmd}')
        else:
            output = ""

        # 添加调试日志
        print(f"ADB命令输出：\n{output}")

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
        # 添加类型检查
        if self.table is None:
            return selected
            
        for row in range(self.table.rowCount()):
            # 添加类型检查
            widget = self.table.cellWidget(row, 0)
            if widget is not None and widget.isChecked():
                item = self.table.item(row, 1)
                if item is not None:
                    selected.append(item.text())
        return selected

    def select_all(self):
        """全选/取消全选"""
        # 添加类型检查
        if self.table is None:
            return
            
        current_state = not all(
            self.table.cellWidget(row, 0).isChecked()
            for row in range(self.table.rowCount())
            if self.table.cellWidget(row, 0) is not None
        )

        for row in range(self.table.rowCount()):
            widget = self.table.cellWidget(row, 0)
            # 添加类型检查
            if widget is not None and hasattr(widget, 'setChecked'):
                widget.setChecked(current_state)

    def invert_selection(self):
        """反选"""
        # 添加类型检查
        if self.table is None:
            return
            
        for row in range(self.table.rowCount()):
            check = self.table.cellWidget(row, 0)
            # 添加类型检查
            if check is not None and hasattr(check, 'setChecked') and hasattr(check, 'isChecked'):
                check.setChecked(not check.isChecked())

    def extract_selected(self):
        """增强日志记录的提取方法,记录文件提取详情"""
        files = self.get_selected_files()
        # 添加类型检查
        if not files:
            if self.parent_widget is not None:
                self.parent_widget.log("提取取消：未选择文件")
            QMessageBox.warning(self, "警告", "请先选择要提取的文件")
            return

        dest_dir = QFileDialog.getExistingDirectory(self, "选择保存目录")
        if not dest_dir:
            if self.parent_widget is not None:
                self.parent_widget.log("提取取消：未选择保存目录")
            return

        if self.parent_widget is not None:
            self.parent_widget.log(f"开始提取{len(files)}个文件到：{dest_dir}")

        # 添加类型检查
        if self.parent_widget is not None and hasattr(self.parent_widget, 'ip_input') and self.parent_widget.ip_input is not None:
            ip = self.parent_widget.ip_input.text()
        else:
            ip = ""

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
            # 添加类型检查
            if self.parent_widget is not None:
                output = self.parent_widget.run_adb(cmd)
            else:
                output = ""

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
            # 添加类型检查
            parent = self.parent()
            if parent is not None and hasattr(parent, 'ip_input') and parent.ip_input is not None and hasattr(parent, 'run_adb'):
                cmd = f"pull /data/data/com.vixtel.stb.agent/files/{log_type}"
                output = parent.run_adb(f'-s {parent.ip_input.text()} {cmd} "{dest_dir}"')
            QMessageBox.information(self, "完成", f"{log_type}日志提取完成！")

    def show_library_agent_selector(self):
        """显示library/agent日志选择器"""
        log_files = [
            "stbagent.log", "stblibrary.log",
            "stbsocketlibrary.log", "testagent.log",
            "testlibrary.log"
        ]
        # 添加类型检查
        parent = self.parent()
        if parent is not None:
            LogFileSelector(
                parent_widget=parent,
                log_type="sdcard",
                custom_path="/sdcard",
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
        self.deploy_btn.clicked.connect(self.show_deploy_options)
        self.other_ops_btn.clicked.connect(self.other_operations)
        self.reboot_btn.clicked.connect(self.reboot_stb)
        self.run_adb_btn.clicked.connect(self.run_adb_command)
        self.monitor_btn.clicked.connect(self.show_performance_monitor)
        self.storage_btn.clicked.connect(self.show_storage_monitor)
        self.analysis_btn.clicked.connect(self.show_performance_analysis)
        # 为ADB命令输入框绑定回车键事件
        self.adb_command_input.returnPressed.connect(self.run_adb_command)

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
        # 获取ADB路径 - 增强的路径处理
        if getattr(sys, 'frozen', False):  # 打包后环境
            if hasattr(sys, '_MEIPASS'):
                # PyInstaller单文件模式
                base_dir = sys._MEIPASS
            else:
                # PyInstaller目录模式
                base_dir = os.path.dirname(os.path.abspath(sys.executable))
        else:  # 开发环境
            base_dir = os.path.dirname(os.path.abspath(__file__))

        # 尝试多个可能的路径
        possible_paths = [
            os.path.join(base_dir, "platform-tools", "adb.exe"),
            os.path.join(base_dir, "platform-tools", "adb"),
            os.path.join(os.path.dirname(base_dir), "platform-tools", "adb.exe"),
        ]

        adb_path = None
        for path in possible_paths:
            if os.path.exists(path):
                adb_path = path
                break

        if not adb_path:
            self.log(f"错误：未找到ADB工具")
            return "ADB工具未找到"

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

    def get_adb_path(self):
        """统一获取 adb 路径（供 run_adb / fire_and_forget 共用）"""
        if getattr(sys, 'frozen', False):  # 打包后环境
            if hasattr(sys, '_MEIPASS'):
                base_dir = sys._MEIPASS
            else:
                base_dir = os.path.dirname(os.path.abspath(sys.executable))
        else:
            base_dir = os.path.dirname(os.path.abspath(__file__))

        possible_paths = [
            os.path.join(base_dir, "platform-tools", "adb.exe"),
            os.path.join(base_dir, "platform-tools", "adb"),
            os.path.join(os.path.dirname(base_dir), "platform-tools", "adb.exe"),
        ]

        for path in possible_paths:
            if os.path.exists(path):
                return path

        self.log("错误：未找到ADB工具")
        return None

    def run_adb_fire_and_forget(self, command, timeout=2):
        adb_path = self.get_adb_path()
        if not adb_path:
            return

        full_cmd = f'"{adb_path}" {command}'
        self.log(f"[FIRE] 执行命令: {full_cmd}", command=True)

        try:
            subprocess.run(
                full_cmd,
                shell=True,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=timeout
            )
        except subprocess.TimeoutExpired:
            # ⚠️ 这是 Android 4 下的【正常行为】
            self.log("[FIRE] adb 启动命令超时返回（预期行为）")

    def get_android_major_version(self):
        """
        获取 Android 主版本号，例如 4 / 9 / 11
        """
        output = self.run_adb(
            f'-s {self.ip_input.text()} shell "getprop ro.build.version.release"'
        ).strip()

        if not output:
            return None

        # 例如：4.4.4 / 9 / 11
        try:
            return int(output.split('.')[0])
        except Exception:
            return None

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

    def show_deploy_options(self):
        """显示部署选项对话框"""
        self.log("选择部署类型")
        dialog = QDialog(self)
        dialog.setWindowTitle("部署选项")
        dialog.setFixedSize(300, 150)

        layout = QVBoxLayout()

        # 整体部署按钮
        btn_folder_deploy = QPushButton("整体部署", dialog)
        btn_folder_deploy.clicked.connect(lambda: self.deploy_folder())
        layout.addWidget(btn_folder_deploy)

        # 单文件部署按钮
        btn_single_deploy = QPushButton("单文件部署", dialog)
        btn_single_deploy.clicked.connect(lambda: self.deploy_single_file())
        layout.addWidget(btn_single_deploy)

        dialog.setLayout(layout)
        dialog.exec()

    def deploy_folder(self):
        """整体部署（原有功能）"""
        self.log("开始整体部署流程")
        folder = QFileDialog.getExistingDirectory(self, "选择部署文件夹")
        if not folder:
            self.log("部署取消：未选择文件夹")
            return

        self.log(f"选择的部署文件夹: {folder}")
        self._perform_deployment(folder)

    def deploy_single_file(self):
        """单文件部署"""
        self.log("开始单文件部署流程")
        
        # 定义支持的文件类型
        supported_files = {
            "STBIQ APK文件 (STBIQ*.apk)": "STBIQ*.apk",
            "testagent文件 (testagent)": "testagent",
            "startstbagent.sh文件 (startstbagent.sh)": "startstbagent.sh",
            "所有支持文件 (*)": "*"
        }
        
        # 构建文件过滤器字符串
        file_filter = ";;".join(supported_files.keys())
        
        # 选择文件
        file_path, selected_filter = QFileDialog.getOpenFileName(
            self, 
            "选择要部署的文件", 
            "", 
            file_filter
        )
        
        if not file_path:
            self.log("部署取消：未选择文件")
            return
            
        self.log(f"选择的部署文件: {file_path}")
        
        # 获取文件名
        filename = os.path.basename(file_path)
        
        # 根据文件类型进行部署
        if filename == "startstbagent.sh":
            self._deploy_startstbagent(file_path)
        elif filename == "testagent":
            self._deploy_testagent(file_path)
        elif filename.startswith("STBIQ") and filename.endswith(".apk"):
            self._deploy_stbiq_apk(file_path)
        else:
            QMessageBox.warning(self, "警告", f"不支持的文件类型: {filename}")
            self.log(f"不支持的文件类型: {filename}")
            return
            
        self.log("单文件部署完成")
        QMessageBox.information(self, "完成", f"文件 {filename} 部署完成！")

    def _deploy_startstbagent(self, file_path):
        """部署startstbagent.sh文件"""
        self.log("部署startstbagent.sh...")
        ip = self.ip_input.text().strip()
        if not ip:
            QMessageBox.warning(self, "警告", "请先连接设备")
            return
            
        output = self.run_adb(f'-s {ip} push "{file_path}" /system/bin/')
        self.run_adb(f'-s {ip} shell chmod 755 /system/bin/startstbagent.sh')
        
    def _deploy_testagent(self, file_path):
        """部署testagent文件"""
        self.log("部署testagent...")
        ip = self.ip_input.text().strip()
        if not ip:
            QMessageBox.warning(self, "警告", "请先连接设备")
            return
            
        output = self.run_adb(f'-s {ip} push "{file_path}" /system/bin/')
        self.run_adb(f'-s {ip} shell chmod 755 /system/bin/testagent')
        
    def _deploy_stbiq_apk(self, file_path):
        """部署STBIQ APK文件"""
        self.log("部署STBIQ APK...")
        ip = self.ip_input.text().strip()
        if not ip:
            QMessageBox.warning(self, "警告", "请先连接设备")
            return
            
        # 先删除旧版本
        self.run_adb(f'-s {ip} shell rm -rf /system/app/STBIQ*.apk')
        # 部署新文件
        output = self.run_adb(f'-s {ip} push "{file_path}" /system/app/')
        
    def _perform_deployment(self, folder):
        """执行部署操作（原有逻辑）"""
        ip = self.ip_input.text().strip()
        if not ip:
            QMessageBox.warning(self, "警告", "请先连接设备")
            return
            
        # 部署startstbagent.sh
        sh_path = os.path.join(folder, 'startstbagent.sh')
        if os.path.exists(sh_path):
            self.log("部署startstbagent.sh...")
            output = self.run_adb(f'-s {ip} push "{sh_path}" /system/bin/')
            self.run_adb(f'-s {ip} shell chmod 755 /system/bin/startstbagent.sh')
        else:
            self.log("未找到startstbagent.sh文件", command=True)

        # 部署testagent
        testagent_path = os.path.join(folder, 'testagent')
        if os.path.exists(testagent_path):
            self.log("部署testagent...")
            output = self.run_adb(f'-s {ip} push "{testagent_path}" /system/bin/')
            self.run_adb(f'-s {ip} shell chmod 755 /system/bin/testagent')
        else:
            self.log("未找到testagent文件", command=True)

        # 处理 STBIQ APK
        apk_files = [f for f in os.listdir(folder) if f.startswith("STBIQ") and f.endswith(".apk")]
        if apk_files:
            apk_path = os.path.join(folder, apk_files[0])
            self.log("部署STBIQ APK...")
            self.run_adb(f'-s {ip} shell rm -rf /system/app/STBIQ*.apk')  # 删除旧版本
            self.run_adb(f'-s {ip} push "{apk_path}" /system/app/')
        else:
            self.log("未找到STBIQ APK文件", command=True)

        self.log("整体部署完成")
        QMessageBox.information(self, "完成", "整体部署完成！")

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

    # def get_top_headers(self):
    #     """动态解析列头（修复 S 列识别问题）"""
    #     # 执行命令获取输出
    #     output = self.run_adb(
    #         f'-s {self.ip_input.text()} shell "top -b -n 1 | grep -E \'PID|ARGS|COMMAND\' | grep -vE \'grep|sh -c\'"'
    #     )
    #
    #     # 处理编码问题
    #     try:
    #         cleaned_output = output.encode('latin-1').decode('utf-8', errors='ignore')
    #     except:
    #         cleaned_output = output
    #
    #     # 匹配列头行
    #     header_line = None
    #     for line in cleaned_output.split('\n'):
    #         line = line.strip()
    #         if re.search(r'\bPID\b.*\bARGS\b', line, re.IGNORECASE):
    #             header_line = line
    #             break
    #
    #     if not header_line:
    #         self.log("列头匹配失败")
    #         return None
    #
    #     # 关键修复：分离 S 和 %CPU
    #     cleaned_header = re.sub(r'(\bS)\[%CPU\]', r'\1 %CPU', header_line)  # S[%CPU] -> S %CPU
    #     cleaned_header = re.sub(r'\s{2,}', ' ', cleaned_header)
    #
    #     # 精准分割列名
    #     columns = re.findall(r'\b\w+\+?\b|\%?\w+', cleaned_header)
    #     columns = [col.upper().replace('%', '') for col in columns]
    #
    #     # 列名标准化映射
    #     key_mappings = {
    #         'PID': ['PID'],
    #         'USER': ['USER', 'UID'],
    #         'PR': ['PR', 'PRI'],
    #         'NI': ['NI', 'NICE'],
    #         'VIRT': ['VIRT', 'VSZ'],
    #         'RES': ['RES', 'RSS'],
    #         'SHR': ['SHR'],
    #         'S': ['S', 'STAT'],  # 确保匹配 S 列
    #         'CPU': ['CPU', '%CPU'],  # 映射清洗后的 CPU 列
    #         'MEM': ['MEM', '%MEM'],
    #         'TIME+': ['TIME+', 'TIME'],
    #         'COMMAND': ['ARGS', 'COMMAND']
    #     }
    #
    #     # 构建列映射
    #     final_headers = {}
    #     for std_name, variants in key_mappings.items():
    #         for var in variants:
    #             if var in columns:
    #                 final_headers[std_name] = columns.index(var)
    #                 break
    #         else:
    #             self.log(f"缺失关键列: {std_name}")
    #             return None
    #
    #     self.log(f"列头解析结果: {final_headers}")
    #     return final_headers

    # def get_top_headers_android11(self):
    #     """针对Android 11的top命令列头解析"""
    #     # 执行命令获取输出
    #     output = self.run_adb(
    #         f'-s {self.ip_input.text()} shell "top -b -n 1 | head -10"'
    #     )
    #
    #     # 处理编码问题
    #     try:
    #         cleaned_output = output.encode('latin-1').decode('utf-8', errors='ignore')
    #     except:
    #         cleaned_output = output
    #
    #     # 查找包含PID的行
    #     header_line = None
    #     for line in cleaned_output.split('\n'):
    #         line = line.strip()
    #         # Android 11的top输出格式可能不同，需要更灵活的匹配
    #         if re.search(r'\bPID\b', line, re.IGNORECASE) and re.search(r'\bCPU\b', line, re.IGNORECASE):
    #             header_line = line
    #             break
    #
    #     if not header_line:
    #         self.log("Android 11列头匹配失败")
    #         return None
    #
    #     # 清理并分割列名
    #     cleaned_header = re.sub(r'\s{2,}', ' ', header_line)
    #     columns = re.findall(r'\b\w+\+?\b|\%?\w+', cleaned_header)
    #     columns = [col.upper().replace('%', '').replace('[', '').replace(']', '') for col in columns]
    #
    #     # Android 11列名映射
    #     key_mappings = {
    #         'PID': ['PID'],
    #         'USER': ['USER', 'UID'],
    #         'PR': ['PR', 'PRI'],
    #         'NI': ['NI', 'NICE'],
    #         'VIRT': ['VIRT', 'VSZ'],
    #         'RES': ['RES', 'RSS'],
    #         'SHR': ['SHR'],
    #         'S': ['S', 'STAT'],
    #         'CPU': ['CPU', '%CPU'],
    #         'MEM': ['MEM', '%MEM'],
    #         'TIME+': ['TIME+', 'TIME'],
    #         'ARGS': ['ARGS', 'COMMAND']
    #     }
    #
    #     # 构建列映射
    #     final_headers = {}
    #     for std_name, variants in key_mappings.items():
    #         for var in variants:
    #             if var in columns:
    #                 final_headers[std_name] = columns.index(var)
    #                 break
    #         else:
    #             self.log(f"Android 11缺失关键列: {std_name}")
    #             return None
    #
    #     self.log(f"Android 11列头解析结果: {final_headers}")
    #     return final_headers

    # def get_top_headers_android11_from_dialog(self):
    #     """为PerformanceMonitorDialog提供的Android 11 top命令列头解析"""
    #     # 执行命令获取输出
    #     output = self.run_adb(
    #         f'-s {self.ip_input.text()} shell "top -b -n 1 | head -10"'
    #     )
    #
    #     # 处理编码问题
    #     try:
    #         cleaned_output = output.encode('latin-1').decode('utf-8', errors='ignore')
    #     except:
    #         cleaned_output = output
    #
    #     # 查找包含PID的行
    #     header_line = None
    #     for line in cleaned_output.split('\n'):
    #         line = line.strip()
    #         # Android 11的top输出格式可能不同，需要更灵活的匹配
    #         if re.search(r'\bPID\b', line, re.IGNORECASE) and re.search(r'\bCPU\b', line, re.IGNORECASE):
    #             header_line = line
    #             break
    #
    #     if not header_line:
    #         self.log("Android 11列头匹配失败")
    #         return None
    #
    #     # 清理并分割列名
    #     cleaned_header = re.sub(r'\s{2,}', ' ', header_line)
    #     columns = re.findall(r'\b\w+\+?\b|\%?\w+', cleaned_header)
    #     columns = [col.upper().replace('%', '').replace('[', '').replace(']', '') for col in columns]
    #
    #     # Android 11列名映射
    #     key_mappings = {
    #         'PID': ['PID'],
    #         'USER': ['USER', 'UID'],
    #         'PR': ['PR', 'PRI'],
    #         'NI': ['NI', 'NICE'],
    #         'VIRT': ['VIRT', 'VSZ'],
    #         'RES': ['RES', 'RSS'],
    #         'SHR': ['SHR'],
    #         'S': ['S', 'STAT'],
    #         'CPU': ['CPU', '%CPU'],
    #         'MEM': ['MEM', '%MEM'],
    #         'TIME+': ['TIME+', 'TIME'],
    #         'ARGS': ['ARGS', 'COMMAND']
    #     }
    #
    #     # 构建列映射
    #     final_headers = {}
    #     for std_name, variants in key_mappings.items():
    #         for var in variants:
    #             if var in columns:
    #                 final_headers[std_name] = columns.index(var)
    #                 break
    #         else:
    #             self.log(f"Android 11缺失关键列: {std_name}")
    #             return None
    #
    #     self.log(f"Android 11列头解析结果: {final_headers}")
    #     return final_headers

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
        """启动性能监测（Android 4 / 9 / 11 自动选择脚本）"""

        ip = self.parent.ip_input.text().strip()
        if not ip:
            QMessageBox.warning(self, "错误", "设备 IP 为空")
            return

        # 1️⃣ 获取 Android 主版本号
        android_major = self.parent.get_android_major_version()
        if android_major is None:
            QMessageBox.warning(self, "错误", "无法获取 Android 系统版本")
            return

        self.parent.log(f"检测到 Android 主版本号: {android_major}")

        # 2️⃣ 根据版本选择脚本
        if android_major < 5:

            script_name = "top_Performance-android4.sh"

        else:
            script_name = "top_Performance.sh"


        local_script = os.path.join(os.path.dirname(__file__), script_name)
        remote_script = f"/data/local/tmp/{script_name}"

        if not os.path.exists(local_script):
            QMessageBox.critical(self, "错误", f"未找到脚本文件:\n{local_script}")
            QMessageBox.critical(self, "错误", f"未找到脚本文件:\n{local_script}")
            return

        # 3️⃣ 防止重复启动（统一杀旧进程）
        self.parent.run_adb(
            f'-s {ip} shell "rm -f /sdcard/performance.pid"'
        )

        # 4️⃣ push + chmod
        self.parent.log(f"推送性能监测脚本: {script_name}")
        self.parent.run_adb(
            f'-s {ip} push "{local_script}" "{remote_script}"'
        )

        self.parent.run_adb(
            f'-s {ip} shell sed -i "s/\\r$//" {remote_script}'
        )
        self.parent.run_adb(
            f'-s {ip} shell chmod 755 "{remote_script}"'
        )

        # 5️⃣ 后台启动脚本
        if android_major < 5:
            self.parent.run_adb_fire_and_forget(
                f'-s {ip} shell sh -x {remote_script}',
                timeout=2
            )
        else:
            self.parent.run_adb(
                f'-s {self.parent.ip_input.text()} shell "nohup {remote_script} > /dev/null 2>&1 &"'
            )

        # 6️⃣ 等待 PID 文件生成
        pid = None
        for _ in range(5):
            pid_out = self.parent.run_adb(
                f'-s {ip} shell "cat /sdcard/performance.pid 2>/dev/null"'
            ).strip()
            if pid_out.isdigit():
                pid = pid_out
                break
            time.sleep(1)

        if not pid:
            QMessageBox.warning(self, "启动失败", "未检测到性能监测进程")
            return

        self.current_pid = pid
        self.parent.log(f"性能监测已启动，PID={pid}")
        QMessageBox.information(
            self,
            "成功",
            f"性能监测已启动\nAndroid {android_major}\nPID: {pid}"
        )

    def stop_monitoring(self):
        """停止性能监测（统一使用 PID 文件）"""

        ip = self.parent.ip_input.text().strip()
        if not ip:
            QMessageBox.warning(self, "错误", "设备 IP 为空")
            return

        # 1️⃣ 读取 PID
        pid = self.parent.run_adb(
            f'-s {ip} shell "cat /sdcard/performance.pid 2>/dev/null"'
        ).strip()

        if not pid.isdigit():
            QMessageBox.information(self, "提示", "当前没有正在运行的性能监测")
            return

        # 2️⃣ kill 进程
        self.parent.run_adb(
            f'-s {ip} shell "kill -9 {pid} 2>/dev/null"'
        )

        # 3️⃣ 清理 PID 文件（兜底）
        self.parent.run_adb(
            f'-s {ip} shell "rm -f /sdcard/performance.pid"'
        )

        self.current_pid = None
        self.parent.log(f"性能监测已停止，PID={pid}")
        QMessageBox.information(self, "成功", "性能监测已停止")

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

    def generate_script(self, headers, android_version=None):
        """生成动态脚本（确保系统指标解析正确）"""
        # 直接读取模板文件内容并返回，不进行动态替换
        try:
            with open('top_Performance.sh', 'r', encoding='utf-8') as f:
                script = f.read()
        except UnicodeDecodeError:
            with open('top_Performance.sh', 'r', encoding='gbk') as f:
                script = f.read()

        if android_version and android_version.startswith('11'):
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
            buffers="0"
            fi
            '''
        else:
            # 原有的解析逻辑
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
            f'-s {self.parent.ip_input.text()} shell "md5sum /data/local/tmp/top_Performance.sh 2>/dev/null"')
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
    """
    性能分析，将性能监测的数据分析成单表或多表折线图报表
    可以单选进程和pid以及通过图例进行筛选选择数据
    """
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

        # 添加指标筛选状态
        self.show_res = True
        self.show_cpu = True
        self.show_mem = True

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

        # 添加指标筛选框（初始隐藏，在单图模式下显示）
        self.metric_filter_frame = QFrame()
        # 修复：使用正确的枚举值
        self.metric_filter_frame.setFrameShape(QFrame.Shape.StyledPanel)
        self.metric_filter_layout = QHBoxLayout(self.metric_filter_frame)
        self.metric_filter_layout.addWidget(QLabel("显示指标:"))

        self.res_checkbox = QCheckBox("内存占用")
        self.res_checkbox.setChecked(True)
        self.res_checkbox.stateChanged.connect(self.update_plot)
        self.metric_filter_layout.addWidget(self.res_checkbox)

        self.cpu_checkbox = QCheckBox("CPU使用率")
        self.cpu_checkbox.setChecked(True)
        self.cpu_checkbox.stateChanged.connect(self.update_plot)
        self.metric_filter_layout.addWidget(self.cpu_checkbox)

        self.mem_checkbox = QCheckBox("内存使用率")
        self.mem_checkbox.setChecked(True)
        self.mem_checkbox.stateChanged.connect(self.update_plot)
        self.metric_filter_layout.addWidget(self.mem_checkbox)

        self.metric_filter_frame.setVisible(False)  # 初始隐藏
        switch_layout.addWidget(self.metric_filter_frame)

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
        # 使用布局而不是setGeometry
        layout.addWidget(self.loading_label)

        # 在UI完全初始化后启动数据加载
        self.load_thread = LoadDataThread(file_path)
        self.load_thread.data_loaded.connect(self.on_data_loaded)
        self.load_thread.start()

    def on_data_loaded(self, data, process_data, unique_names, args_to_pids):
        # 确保UI组件已初始化
        if not hasattr(self, 'process_list'):
            return

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

        # 显示/隐藏指标筛选框
        self.metric_filter_frame.setVisible(not self.is_multi_plot)

        self.update_plot()

    def update_plot(self):
        """更新图表"""
        # 检查数据是否加载
        if self.data is None or self.data.empty:
            # 如果没有数据，显示空图表
            self.figure.clear()
            ax = self.figure.add_subplot(111)
            ax.text(0.5, 0.5, '没有数据可显示\n请先加载性能监测数据',
                    horizontalalignment='center', verticalalignment='center',
                    transform=ax.transAxes, fontsize=12, color='gray')
            self.canvas.draw()
            return

        # 获取选中的进程名
        selected_names = set()
        for i in range(self.process_list.count()):
            item = self.process_list.item(i)
            if item.isSelected():
                selected_names.add(item.text())

        # 找出所有选中的进程名对应的PID
        selected_pids = set()
        for name in selected_names:
            if name in self.args_to_pids:
                selected_pids.update(self.args_to_pids[name])

        # 如果没有选中的PID，显示空图表
        if not selected_pids:
            self.figure.clear()
            ax = self.figure.add_subplot(111)
            ax.text(0.5, 0.5, '没有选中的进程\n请在左侧列表中选中进程',
                    horizontalalignment='center', verticalalignment='center',
                    transform=ax.transAxes, fontsize=12, color='gray')
            self.canvas.draw()
            return

        # 更新可见PID集合 - 保留原有的可见性状态
        # 如果之前没有定义visible_pids，或者visible_pids为空，则使用所有选中的PID
        if not hasattr(self, 'visible_pids') or not self.visible_pids:
            self.visible_pids = selected_pids.copy()
        else:
            # 只保留当前选中且之前可见的PID
            self.visible_pids = {pid for pid in self.visible_pids if pid in selected_pids}
            # 添加新选中的PID（默认为可见）
            new_pids = selected_pids - self.visible_pids
            if new_pids:
                self.visible_pids.update(new_pids)

        # 清除图表
        self.figure.clear()

        # 根据模式创建图表
        if self.is_multi_plot:
            # 多图模式
            self.create_multi_plot(selected_pids)
        else:
            # 单图模式
            self.create_single_plot(selected_pids)

        # 添加图例交互
        self.add_legend_interaction()

        # 调整布局
        try:
            self.figure.tight_layout(pad=2.0, h_pad=1.5, w_pad=1.5)
        except Exception:
            self.figure.set_constrained_layout(True)

        self.canvas.draw()

    def create_multi_plot(self, selected_pids):
        """创建多图模式图表"""
        # 清除图表
        self.figure.clear()

        # 如果没有选中的PID，返回
        if not selected_pids:
            self.canvas.draw()
            return

        # 重新初始化line_map
        self.line_map = {}

        # 创建三个子图
        ax1 = self.figure.add_subplot(311)
        ax2 = self.figure.add_subplot(312)
        ax3 = self.figure.add_subplot(313)

        # 设置标题
        ax1.set_title('内存占用 (MB)', loc='left')
        ax2.set_title('CPU 使用率 (%)', loc='left')
        ax3.set_title('内存使用率 (%)', loc='left')

        # 存储线条句柄和标签
        handles1, labels1 = [], []
        handles2, labels2 = [], []
        handles3, labels3 = [], []

        # 为每个选中的PID创建曲线
        for pid in selected_pids:
            # 获取该PID的数据
            if pid not in self.process_data:
                continue

            df = self.process_data[pid]

            # 确定该PID是否应该可见
            alpha = 1.0 if pid in self.visible_pids else 0.3
            visible = pid in self.visible_pids

            # 初始化该PID的线条列表
            self.line_map[pid] = []

            # 第一张图：内存占用
            l1, = ax1.plot(df['timestamp'], df['res'],
                           label=pid,
                           color=self.color_map.get(f"{pid}_res", 'tab:red'),
                           alpha=alpha,
                           visible=visible)
            handles1.append(l1)
            labels1.append(pid)
            self.line_map[pid].append(l1)

            # 第二张图：CPU使用率
            l2, = ax2.plot(df['timestamp'], df['%cpu'],
                           label=pid,
                           color=self.color_map.get(f"{pid}_%cpu", 'tab:blue'),
                           alpha=alpha,
                           visible=visible)
            handles2.append(l2)
            labels2.append(pid)
            self.line_map[pid].append(l2)

            # 第三张图：内存使用率
            l3, = ax3.plot(df['timestamp'], df['%mem'],
                           label=pid,
                           color=self.color_map.get(f"{pid}_%mem", 'tab:green'),
                           alpha=alpha,
                           visible=visible)
            handles3.append(l3)
            labels3.append(pid)
            self.line_map[pid].append(l3)

        # 设置网格和标签旋转
        for ax in [ax1, ax2, ax3]:
            ax.grid(True)
            ax.tick_params(axis='x', rotation=45)

        # 如果没有线条，显示空图表
        if not handles1:
            ax1.text(0.5, 0.5, '没有可显示的数据',
                     horizontalalignment='center', verticalalignment='center',
                     transform=ax1.transAxes, fontsize=12, color='gray')
            ax2.text(0.5, 0.5, '没有可显示的数据',
                     horizontalalignment='center', verticalalignment='center',
                     transform=ax2.transAxes, fontsize=12, color='gray')
            ax3.text(0.5, 0.5, '没有可显示的数据',
                     horizontalalignment='center', verticalalignment='center',
                     transform=ax3.transAxes, fontsize=12, color='gray')
            self.canvas.draw()
            return

        # 创建图例 - 修复：将图例放在图表外部右侧
        # 确保有足够的空间显示图例
        self.figure.subplots_adjust(right=0.75)  # 为图例留出25%的空间

        # 为每个子图创建图例
        leg1 = ax1.legend(handles1, labels1,
                          loc='upper left',
                          bbox_to_anchor=(1.02, 1),
                          borderaxespad=0,
                          fontsize=8,
                          frameon=True,
                          framealpha=0.9,
                          facecolor='white',
                          edgecolor='black')

        leg2 = ax2.legend(handles2, labels2,
                          loc='upper left',
                          bbox_to_anchor=(1.02, 1),
                          borderaxespad=0,
                          fontsize=8,
                          frameon=True,
                          framealpha=0.9,
                          facecolor='white',
                          edgecolor='black')

        leg3 = ax3.legend(handles3, labels3,
                          loc='upper left',
                          bbox_to_anchor=(1.02, 1),
                          borderaxespad=0,
                          fontsize=8,
                          frameon=True,
                          framealpha=0.9,
                          facecolor='white',
                          edgecolor='black')

        # 设置图例可交互
        for leg, labels in zip([leg1, leg2, leg3], [labels1, labels2, labels3]):
            for i, text in enumerate(leg.get_texts()):
                pid = labels[i]
                # 设置gid以便拾取事件使用
                text.set_gid(pid)

                # 根据可见性设置初始样式
                if pid in self.visible_pids:
                    text.set_alpha(1.0)
                    text.set_fontstyle("normal")
                else:
                    text.set_alpha(0.3)
                    text.set_fontstyle("italic")

                # 启用拾取
                text.set_picker(True)

        self.current_legends = [leg1, leg2, leg3]

        # 添加图例交互
        self.add_legend_interaction()

        # 调整布局
        try:
            self.figure.tight_layout(pad=2.0, h_pad=1.5, w_pad=1.5)
        except Exception:
            # 如果tight_layout失败，使用constrained_layout
            self.figure.set_constrained_layout(True)

        self.canvas.draw()




    def create_single_plot(self, selected_pids):
        """创建单图模式图表"""
        # 清除图表
        self.figure.clear()

        # 如果没有选中的PID，返回
        if not selected_pids:
            self.canvas.draw()
            return

        # 重新初始化line_map
        self.line_map = {}

        # 创建子图
        ax = self.figure.add_subplot(111)
        ax.set_title('性能指标趋势', loc='left')
        ax.grid(True)
        ax.tick_params(axis='x', rotation=45)

        # 创建辅助Y轴
        ax2 = ax.twinx()
        ax3 = ax.twinx()
        ax3.spines['right'].set_position(('outward', 60))

        # 获取指标筛选状态
        self.show_res = self.res_checkbox.isChecked()
        self.show_cpu = self.cpu_checkbox.isChecked()
        self.show_mem = self.mem_checkbox.isChecked()

        # 存储线条句柄和标签
        handles = []
        labels = []

        # 为每个选中的PID创建曲线
        for pid in selected_pids:
            # 获取该PID的数据
            if pid not in self.process_data:
                continue

            df = self.process_data[pid]

            # 确定该PID是否应该可见
            alpha = 1.0 if pid in self.visible_pids else 0.3

            # 初始化该PID的线条列表
            self.line_map[pid] = []

            # 内存占用曲线
            if self.show_res:
                l1, = ax.plot(df['timestamp'], df['res'],
                              label=f"{pid} (内存)",
                              color=self.color_map.get(f"{pid}_res", 'tab:red'),
                              linestyle='-',
                              alpha=alpha,
                              visible=(pid in self.visible_pids))
                handles.append(l1)
                labels.append(f"{pid} (内存)")
                self.line_map[pid].append(l1)

            # CPU使用率曲线
            if self.show_cpu:
                l2, = ax3.plot(df['timestamp'], df['%cpu'],
                               label=f"{pid} (CPU)",
                               color=self.color_map.get(f"{pid}_%cpu", 'tab:blue'),
                               linestyle='--',
                               alpha=alpha,
                               visible=(pid in self.visible_pids))
                handles.append(l2)
                labels.append(f"{pid} (CPU)")
                self.line_map[pid].append(l2)

            # 内存使用率曲线
            if self.show_mem:
                l3, = ax2.plot(df['timestamp'], df['%mem'],
                               label=f"{pid} (内存%)",
                               color=self.color_map.get(f"{pid}_%mem", 'tab:green'),
                               linestyle=':',
                               alpha=alpha,
                               visible=(pid in self.visible_pids))
                handles.append(l3)
                labels.append(f"{pid} (内存%)")
                self.line_map[pid].append(l3)

        # 设置Y轴标签
        ax.set_ylabel('内存占用 (MB)', color='tab:red')
        ax.tick_params(axis='y', labelcolor='tab:red')

        # 根据筛选状态显示/隐藏辅助Y轴
        if self.show_mem:
            ax2.set_ylabel('内存使用率 (%)', color='tab:green')
            ax2.tick_params(axis='y', labelcolor='tab:green')
        else:
            ax2.set_visible(False)

        if self.show_cpu:
            ax3.set_ylabel('CPU 使用率 (%)', color='tab:blue')
            ax3.tick_params(axis='y', labelcolor='tab:blue')
        else:
            ax3.set_visible(False)

        # 如果没有任何线条，显示空图表
        if not handles:
            ax.text(0.5, 0.5, '没有可显示的数据\n请选择要显示的指标',
                    horizontalalignment='center', verticalalignment='center',
                    transform=ax.transAxes, fontsize=12, color='gray')
            self.canvas.draw()
            return

        # 创建图例
        leg = ax.legend(handles, labels,
                        loc='upper left',
                        bbox_to_anchor=(1.01, 1),
                        fontsize=8,
                        frameon=True,
                        framealpha=0.9,
                        facecolor='white',
                        edgecolor='black',
                        labelspacing=0.3,
                        handlelength=2)

        # 设置图例可交互
        for i, text in enumerate(leg.get_texts()):
            # 从标签文本提取PID
            label_text = text.get_text()
            if ' (' in label_text:
                pid = label_text.split(' (')[0]
            else:
                pid = label_text

            # 设置gid以便拾取事件使用
            text.set_gid(pid)

            # 根据可见性设置初始样式
            if pid in self.visible_pids:
                text.set_alpha(1.0)
                text.set_fontstyle("normal")
            else:
                text.set_alpha(0.3)
                text.set_fontstyle("italic")

            # 启用拾取
            text.set_picker(True)

        self.current_legend = leg

        # 添加图例交互
        self.add_legend_interaction()

        # 调整布局
        try:
            self.figure.tight_layout(pad=2.0, h_pad=1.5, w_pad=1.5)
        except Exception:
            self.figure.set_constrained_layout(True)

        self.canvas.draw()

        # 确保线条的初始可见性正确（在 create_single_plot 和 create_multi_plot 的末尾添加）
        if hasattr(self, 'line_map'):
            for pid in selected_pids:
                if pid in self.line_map:
                    lines = self.line_map[pid]
                    visible = pid in self.visible_pids
                    for line in lines:
                        line.set_visible(visible)
                        line.set_alpha(1.0 if visible else 0.3)

    def add_legend_interaction(self):
        """添加图例交互功能"""
        # 确保已经连接到图例点击事件
        if hasattr(self, 'legend_pick_event'):
            self.canvas.mpl_disconnect(self.legend_pick_event)

        # 为所有图例项启用点击
        def setup_legend_interaction(legend):
            if legend is None:
                return

            # 为每个图例文本设置可点击
            for text in legend.get_texts():
                text.set_picker(True)
                # 确保设置了 gid
                if not text.get_gid():
                    # 尝试从文本中提取 pid
                    label_text = text.get_text()
                    if ' (' in label_text:
                        pid = label_text.split(' (')[0]
                    else:
                        pid = label_text
                    text.set_gid(pid)

        # 设置多图模式或单图模式的图例交互
        if self.is_multi_plot:
            for leg in getattr(self, 'current_legends', []):
                setup_legend_interaction(leg)
        else:
            setup_legend_interaction(getattr(self, 'current_legend', None))

        # 连接点击事件
        self.legend_pick_event = self.canvas.mpl_connect(
            'pick_event', self.on_legend_click
        )

    def create_legend_interaction(self, legend):
        """
        绑定图例点击交互
        """
        if legend is None:
            return

        # 为图例每个句柄建立映射
        for legend_item in legend.legend_handles:

            # 启动 picker，不然 pick_event 不会触发
            legend_item.set_picker(True)

            # 找到原始折线对象
            if hasattr(legend_item, "_legmarker_orig_handle"):
                legend_item.orig_line = legend_item._legmarker_orig_handle
            elif hasattr(legend_item, "_orig_handle"):
                legend_item.orig_line = legend_item._orig_handle
            else:
                # 如果无法找到原始曲线，说明 legend 生成方式不对
                continue

        # 只绑定一次 pick_event
        if not hasattr(self, "legend_pick_event"):
            self.legend_pick_event = self.canvas.mpl_connect(
                'pick_event', self.on_legend_click
            )

    def on_legend_click(self, event):
        """
        点击图例切换对应曲线的显示状态
        """
        # 获取被点击的图例文本
        legend_text = event.artist

        # 从文本的 gid 获取 pid（如果设置了 gid）
        pid = legend_text.get_gid()

        # 如果 gid 没有设置，尝试从文本内容中提取 pid
        if not pid:
            label_text = legend_text.get_text()
            # 尝试从标签文本提取PID
            if ' (' in label_text:
                pid = label_text.split(' (')[0]
            else:
                pid = label_text

        if not pid:
            return

        # 切换该 pid 在 visible_pids 中的状态
        if pid in self.visible_pids:
            self.visible_pids.remove(pid)
            new_visible = False
        else:
            self.visible_pids.add(pid)
            new_visible = True

        # 切换该 pid 对应的所有曲线的可见性
        if hasattr(self, 'line_map') and pid in self.line_map:
            lines = self.line_map[pid]
            for line in lines:
                line.set_visible(new_visible)
                line.set_alpha(1.0 if new_visible else 0.3)

        # 更新图例文本样式
        if new_visible:
            legend_text.set_alpha(1.0)
            legend_text.set_fontstyle("normal")
        else:
            legend_text.set_alpha(0.3)
            legend_text.set_fontstyle("italic")

        self.canvas.draw_idle()

    def update_legend_style(self):
        """更新所有图例项的样式（隐藏时置灰）"""
        # 更新多图模式下的图例
        if hasattr(self, 'current_legends'):
            for leg in self.current_legends:
                for text in leg.get_texts():
                    # 从文本中提取pid（处理带括号的情况）
                    label_text = text.get_text()
                    if ' (' in label_text:
                        pid = label_text.split(' (')[0]
                    else:
                        pid = label_text

                    if pid in self.visible_pids:
                        text.set_alpha(1.0)
                        text.set_fontstyle("normal")
                    else:
                        text.set_alpha(0.3)
                        text.set_fontstyle("italic")

        # 更新单图模式下的图例
        if hasattr(self, 'current_legend'):
            for text in self.current_legend.get_texts():
                # 从文本中提取pid（处理带括号的情况）
                label_text = text.get_text()
                if ' (' in label_text:
                    pid = label_text.split(' (')[0]
                else:
                    pid = label_text

                if pid in self.visible_pids:
                    text.set_alpha(1.0)
                    text.set_fontstyle("normal")
                else:
                    text.set_alpha(0.3)
                    text.set_fontstyle("italic")


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

            # 动态检测列名（不区分大小写）
            col_mapping = {}
            required_columns = ['timestamp', 'res', '%cpu', '%mem', 'args', 'pid']

            for col in required_columns:
                # 查找实际列名（兼容大小写和空格）
                actual_col = next(
                    (c for c in data.columns if c.lower().replace(' ', '') == col.lower().replace(' ', '')),
                    None
                )
                if actual_col:
                    col_mapping[col] = actual_col
                else:
                    raise ValueError(f"缺少必需列: {col}")

            # 重命名列为标准化名称
            data = data.rename(columns={v: k for k, v in col_mapping.items()})

            # 确保args列是字符串类型
            data['args'] = data['args'].astype(str)  # 关键修复：强制转换为字符串

            # 格式化时间戳
            data['timestamp'] = pd.to_datetime(data['timestamp'])

            # 转换内存单位（兼容不同格式）
            data['res'] = data['res'].apply(self.parse_memory)

            # 创建唯一进程ID（PID + 进程名）
            data['process_id'] = data['pid'].astype(str) + ' - ' + data['args']

            # 分组数据
            process_data = {}
            for pid, group in data.groupby('process_id'):
                process_data[pid] = group.sort_values('timestamp')

            # 获取唯一的进程名（确保字符串类型）
            unique_names = data['args'].unique().astype(str).tolist()  # 关键修复：转换为字符串列表

            # 构建进程名到PID的映射
            args_to_pids = {}
            for name in unique_names:
                # 确保name是字符串
                str_name = str(name)  # 双重保险：转换为字符串
                args_to_pids[str_name] = [
                    pid for pid in process_data
                    if str_name in pid.split(' - ', 1)[1]
                ]

            # 发送加载完成信号
            self.data_loaded.emit(data, process_data, unique_names, args_to_pids)

        except Exception as e:
            print(f"数据加载失败: {str(e)}")
            traceback.print_exc()
            self.data_loaded.emit(pd.DataFrame(), {}, [], {})

    def parse_memory(self, value):
        """更健壮的内存值解析"""
        try:
            # 处理空值
            if pd.isna(value):
                return 0.0

            # 如果是字符串，清理数据
            if isinstance(value, str):
                # 移除逗号（如1,024 -> 1024）
                value = value.replace(',', '').strip()

            # 尝试直接转换为浮点数
            num_value = float(value)

            # 假设单位是KB（Linux top默认）
            return num_value / 1024  # 转换为MB

        except ValueError:
            # 处理带单位的值
            try:
                text = str(value).strip().lower()
                if text.endswith('g'):
                    return float(text[:-1]) * 1024
                elif text.endswith('m'):
                    return float(text[:-1])
                elif text.endswith('k'):
                    return float(text[:-1]) / 1024
                else:
                    return 0.0
            except:
                return 0.0
        except Exception:
            return 0.0


if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = STBTool()
    window.show()
    sys.exit(app.exec())



