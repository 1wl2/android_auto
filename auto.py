import sys
import os
import re
import time
import tempfile
import hashlib
import subprocess
import json
import base64
import datetime
import requests
from email.utils import parsedate_to_datetime
from cryptography.hazmat.primitives.asymmetric import rsa, padding
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.exceptions import InvalidSignature
from PyQt6.QtCore import Qt, QDateTime
from PyQt6.QtWidgets import (QVBoxLayout, QFileDialog, QLabel, QDialog, QMessageBox, QTableWidget, QTableWidgetItem,
                             QHeaderView, QCheckBox, QAbstractItemView, QDialogButtonBox, QProgressDialog, QApplication,
                             QPushButton, QWidget, QHBoxLayout, QLineEdit, QTextEdit, )


# ====================== 新增授权管理器类 ======================
class LicenseManager:
    def __init__(self, parent):
        self.parent = parent
        """
        home_dir = os.path.expanduser("~"
        if not os.access(home_dir, os.W_OK):
            self.parent.log(f"[ERROR] 无写入权限: {home_dir}")
        else:
            self.parent.log(f"[DEBUG] 有写入权限: {home_dir}")
        """
        # 本地授权文件路径（隐藏目录）
        self.local_license_path = os.path.join(os.path.expanduser("~"), ".stb_tool_license")
        # --self.parent.log(f"[DEBUG] 本地授权文件路径: {os.path.abspath(self.local_license_path)}")
        # 设备授权文件路径
        self.device_license_path = "/sdcard/.android_tool_license"
        # 程序发布日期（硬编码防止时间篡改）
        self.release_date = datetime.datetime(2025, 5, 23)
        # 最大使用次数
        self.max_uses = 5
        # 最多授权设备数
        self.max_devices = 3

    def generate_key_pair(self):
        private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        private_pem = private_key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption()
        )

        public_pem = private_key.public_key().public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo
        )
        return private_pem, public_pem

    def encrypt_data(self, data, public_key_pem):
        public_key = serialization.load_pem_public_key(public_key_pem)
        encrypted = public_key.encrypt(
            data.encode(),
            padding.OAEP(
                mgf=padding.MGF1(algorithm=hashes.SHA256()),
                algorithm=hashes.SHA256(),
                label=None
            )
        )
        return base64.b64encode(encrypted).decode()

    def generate_device_fingerprint(self, device_ip):
        """获取设备硬件指纹（序列号 + MAC）"""
        try:
            serial = self.get_device_serial(device_ip)
            mac = self.parent.run_adb(f'-s {device_ip} shell cat /sys/class/net/wlan0/address').strip()
            if not mac or "No such file" in mac or "Permission denied" in mac:
                # 尝试 eth0 替代
                mac = self.parent.run_adb(f'-s {device_ip} shell cat /sys/class/net/eth0/address').strip()

            if not serial or not mac:
                self.parent.log(f"[ERROR] 获取设备指纹失败 (serial: {serial}, mac: {mac})")
                return None

            raw_fp = f"{serial}_{mac}"
            return hashlib.sha256(raw_fp.encode()).hexdigest()
        except Exception as e:
            self.parent.log(f"[ERROR] 指纹生成异常: {str(e)}")
            return None

    def read_fingerprint_records(self):
        path = os.path.expanduser("~/.stb_fingerprint_records.json")
        if not os.path.exists(path):
            return []
        try:
            with open(path, "r") as f:
                return json.load(f).get("fingerprints", [])
        except Exception as e:
            self.parent.log(f"[ERROR] 读取指纹记录失败: {str(e)}")
            return []

    def append_fingerprint_record(self, record):
        path = os.path.expanduser("~/.stb_fingerprint_records.json")
        try:
            data = {"fingerprints": []}
            if record not in data["fingerprints"]:
                data["fingerprints"].append(record)

            if os.path.exists(path):
                with open(path, "r") as f:
                    data = json.load(f)

            with open(path, "w") as f:
                json.dump(data, f, indent=2)
        except Exception as e:
            self.parent.log(f"[ERROR] 写入指纹记录失败: {str(e)}")

    def get_device_serial(self, device_ip):
        """获取设备序列号（替代IP作为设备ID）"""
        output = self.parent.run_adb(f'-s {device_ip} shell getprop ro.serialno')
        return output.strip()

    def decrypt_data(self, encrypted_data, private_key_pem):
        """使用私钥解密数据"""
        private_key_pem_bytes = private_key_pem.encode()  # 转换私钥为字节字符串
        private_key = serialization.load_pem_private_key(private_key_pem_bytes, password=None)
        decrypted = private_key.decrypt(
            base64.b64decode(encrypted_data),
            padding.OAEP(
                mgf=padding.MGF1(algorithm=hashes.SHA256()),
                algorithm=hashes.SHA256(),
                label=None
            )
        )
        return decrypted.decode()

    def sign_data(self, data, private_key_pem):
        """使用私钥签名数据"""
        try:
            # 确保传入的是字节或字符串
            if isinstance(private_key_pem, str):
                private_key_pem = private_key_pem.encode()

            private_key = serialization.load_pem_private_key(private_key_pem, password=None)
            signature = private_key.sign(
                data.encode(),
                padding.PSS(
                    mgf=padding.MGF1(hashes.SHA256()),
                    salt_length=padding.PSS.MAX_LENGTH
                ),
                hashes.SHA256()
            )
            return base64.b64encode(signature).decode()
        except Exception as e:
            self.parent.log(f"[ERROR] 签名失败: {str(e)}")
            return ""

    def verify_signature(self, data, signature, public_key_pem):
        """使用公钥验证签名"""
        try:
            # --self.parent.log(f"[DEBUG] 验证签名数据: {data}")
            # --self.parent.log(f"[DEBUG] 公钥内容: {public_key_pem[:100]}...")
            public_key_pem_bytes = public_key_pem.encode()
            public_key = serialization.load_pem_public_key(public_key_pem_bytes)

            public_key.verify(
                base64.b64decode(signature),
                data.encode(),
                padding.PSS(
                    mgf=padding.MGF1(algorithm=hashes.SHA256()),
                    salt_length=padding.PSS.MAX_LENGTH
                ),
                hashes.SHA256()
            )
            return True
        except InvalidSignature:
            self.parent.log("[ERROR] 签名验证失败: 无效签名")
            return False
        except Exception as e:
            self.parent.log(f"[ERROR] 签名验证异常: {str(e)}")
            return False

    def get_network_time(self):
        """从可靠网站响应头的 Date 字段获取网络时间"""
        time_servers = [
            'https://www.baidu.com',
            'https://www.google.com',
            'http://time.aliyun.com'
        ]

        for url in time_servers:
            try:
                response = requests.get(url, timeout=2, headers={'User-Agent': 'Mozilla/5.0'})
                date_str = response.headers.get('Date')
                if date_str:
                    aware_time = parsedate_to_datetime(date_str)
                    # 转换为本地时间并去除 tzinfo
                    local_time = aware_time.astimezone().replace(tzinfo=None)
                    self.parent.log(f"[INFO] 成功从 {url} 获取时间: {local_time}")
                    return local_time
            except Exception as e:
                self.parent.log(f"[WARN] 尝试从 {url} 获取时间失败: {str(e)}")

        self.parent.log("[WARN] 所有时间服务器不可用，使用本地时间")
        return datetime.datetime.now()

    def create_device_fingerprint(self, device_id):
        """生成设备指纹"""
        # 获取设备序列号作为唯一标识
        serial = self.parent.run_adb(f'-s {device_id} shell getprop ro.serialno').strip()
        return hashlib.sha256(serial.encode()).hexdigest() if serial else ""

    def save_local_license(self, device_id, uses_count, expiry_date, device_public_key,
                           all_devices, device_private_key=None, device_fingerprint=None):
        """保存本地授权文件（增强版本）"""
        try:
            # ---- 处理密钥 ----
            def ensure_str(val):
                if val is None:
                    return None
                if isinstance(val, bytes):
                    try:
                        return val.decode('utf-8')
                    except Exception:
                        # 如果 decode 失败，使用 base64 编码处理
                        return base64.b64encode(val).decode('utf-8')
                return str(val)

            device_public_str = ensure_str(device_public_key)
            device_private_str = ensure_str(device_private_key)
            device_ip = self.parent.ip_input.text().strip()
            device_fingerprint = self.generate_device_fingerprint(device_ip)
            # ---- 构造授权数据 ----
            license_data = {
                "device_id": device_id,
                "uses": uses_count,
                "expiry": expiry_date.isoformat(),
                "device_public_key": device_public_str,
                "device_private_key": device_private_str,
                "last_update": datetime.datetime.now().isoformat(),
                "all_devices": list(set(all_devices)) if all_devices else [device_id],
                "fingerprint": device_fingerprint
            }

            # 测试能否被序列化（可删除此段，但更安全）
            json.dumps(license_data)

            # ---- 写入文件 ----
            license_dir = os.path.dirname(self.local_license_path)
            if not os.path.exists(license_dir):
                os.makedirs(license_dir, exist_ok=True)

            # --self.parent.log(f"[DEBUG] 正在写入授权文件: {self.local_license_path}")

            with open(self.local_license_path, "w", encoding="utf-8") as f:
                json.dump(license_data, f, indent=2, ensure_ascii=False)

            return True

        except Exception as e:
            import traceback
            self.parent.log(f"[ERROR] 保存本地授权文件失败: {str(e)}")
            self.parent.log(traceback.format_exc())
            return False

    def read_local_license(self):
        """读取本地授权文件"""
        try:
            with open(self.local_license_path, "r") as f:
                data = json.load(f)
                # 添加调试日志
                if "device_public_key" in data:
                    self.parent.log(f"[DEBUG] 读取本地公钥: {data['device_public_key'][:100]}...")
                return data
        except Exception as e:
            self.parent.log(f"[ERROR] 读取本地授权文件失败: {str(e)}")
            return None

    def read_device_license(self, device_ip):
        """从设备读取授权文件（增强错误处理）"""
        try:
            # 创建临时文件接收内容
            with tempfile.NamedTemporaryFile(mode="w+", delete=False, suffix=".json") as tmp:
                tmp_path = tmp.name

            # 使用ADB拉取文件到临时位置 - 使用IP地址作为设备标识
            pull_cmd = f'-s {device_ip} pull "{self.device_license_path}" "{tmp_path}"'
            output = self.parent.run_adb(pull_cmd)

            # 检查是否拉取成功
            if not os.path.exists(tmp_path) or os.path.getsize(tmp_path) == 0:
                self.parent.log(f"[ERROR] 设备授权文件拉取失败: {output}")
                return None

            # 读取并解析JSON
            with open(tmp_path, "r") as f:
                license_data = json.load(f)

            return license_data
        except Exception as e:
            self.parent.log(f"[ERROR] 读取设备授权文件异常: {str(e)}")
            return None
        finally:
            # 清理临时文件
            if tmp_path and os.path.exists(tmp_path):
                os.remove(tmp_path)

    def save_device_license(self, device_identifier, device_id, uses_count, expiry_date, local_public_key, signature):
        """保存设备端授权文件（增强版本）"""
        try:
            license_data = {
                "device_id": device_id,  # 关键修复：使用设备序列号
                "uses": uses_count,
                "expiry": expiry_date.isoformat(),
                "local_public_key": local_public_key.decode() if isinstance(local_public_key,
                                                                            bytes) else local_public_key,
                "signature": signature
            }

            # 创建临时文件
            with tempfile.NamedTemporaryFile(mode="w", delete=False, suffix=".json") as tmp:
                json.dump(license_data, tmp, indent=2)
                tmp_path = tmp.name

            # 使用ADB推送文件到设备（使用设备标识符IP）
            push_cmd = f'-s {device_identifier} push "{tmp_path}" "{self.device_license_path}"'
            output = self.parent.run_adb(push_cmd)
            # --self.parent.log(f"[DEBUG] 推送命令输出: {output}")

            # 验证是否推送成功
            check_cmd = f'-s {device_identifier} shell "ls -l {self.device_license_path}"'
            check_output = self.parent.run_adb(check_cmd)

            if "No such file" in check_output:
                # 尝试创建父目录
                dir_path = os.path.dirname(self.device_license_path)
                mkdir_cmd = f'-s {device_identifier} shell "mkdir -p {dir_path}"'
                self.parent.run_adb(mkdir_cmd)

                # 再次尝试推送
                output = self.parent.run_adb(push_cmd)
                check_output = self.parent.run_adb(check_cmd)

                if "No such file" in check_output:
                    self.parent.log(f"[ERROR] 设备授权文件创建失败: {check_output}")
                    return False

            # --self.parent.log(f"[DEBUG] 成功创建设备授权文件: {self.device_license_path}")
            # --self.parent.log(f"[DEBUG] 文件详情: {check_output}")
            return True

        except Exception as e:
            self.parent.log(f"[ERROR] 保存设备授权文件失败: {str(e)}")
            return False
        finally:
            # 清理临时文件
            if 'tmp_path' in locals() and os.path.exists(tmp_path):
                os.remove(tmp_path)

    def initialize_license(self):
        """初始化授权（增强版本，解决文件未生成问题）"""
        try:
            device_ip = self.parent.ip_input.text().strip()
            if not device_ip:
                self.parent.log("[ERROR] 未输入设备IP")
                return False

            # --self.parent.log(f"[DEBUG] 开始初始化授权 for {device_ip}")
            # 0. 获取指纹并检查是否已授权
            device_fingerprint = self.generate_device_fingerprint(device_ip)
            if not device_fingerprint:
                self.parent.log("授权失败：无法生成指纹")
                return False

            # 检查指纹是否已授权过（防止绕过）
            existing_fps = self.read_fingerprint_records()
            if device_fingerprint in [r["fingerprint"] for r in existing_fps]:
                self.parent.log("授权失败：该设备已注册过授权，禁止重复授权")
                return False

            # 1. 检查设备连接状态 - 修复匹配逻辑
            devices_output = self.parent.run_adb('devices')
            connected = False
            for line in devices_output.splitlines():
                if device_ip in line and "device" in line:
                    connected = True
                    break

            if not connected:
                # 尝试通过序列号匹配
                serial = self.get_device_serial(device_ip)
                if serial:
                    for line in devices_output.splitlines():
                        if serial in line and "device" in line:
                            connected = True
                            break

            if not connected:
                self.parent.log(f"[ERROR] 设备未连接: {device_ip}")
                # --self.parent.log(f"[DEBUG] ADB设备列表:\n{devices_output}")
                return False

            # 2. 检查/sdcard写入权限（使用IP地址作为设备标识）
            # --self.parent.log("[DEBUG] 检查/sdcard写入权限...")
            test_file = "/sdcard/.license_test_file"
            test_cmd = f'-s {device_ip} shell "touch {test_file} && rm {test_file}"'
            perm_output = self.parent.run_adb(test_cmd)

            if "Permission denied" in perm_output:
                # 尝试请求存储权限
                # --self.parent.log("[DEBUG] 尝试请求存储权限...")
                perm_grant_cmd = (
                    f'-s {device_ip} shell appops set --uid com.vixtel.stb.agent '
                    f'MANAGE_EXTERNAL_STORAGE allow'
                )
                grant_output = self.parent.run_adb(perm_grant_cmd)

                # 再次检查权限
                perm_output = self.parent.run_adb(test_cmd)
                if "Permission denied" in perm_output:
                    self.parent.log(f"[ERROR] 无法获取/sdcard写入权限: {perm_output}")
                    return False
                else:
                    self.parent.log("[DEBUG] 存储权限已授予")

            # 3. 获取设备序列号作为唯一标识
            serial_cmd = f'-s {device_ip} shell getprop ro.serialno'
            device_serial = self.parent.run_adb(serial_cmd).strip()
            if not device_serial:
                self.parent.log("[ERROR] 无法获取设备序列号")
                return False
            # --self.parent.log(f"[DEBUG] 设备序列号: {device_serial}")

            # 4. 获取当前授权设备列表
            local_license = self.read_local_license()
            all_devices = local_license.get("all_devices", []) if local_license else []
            # -- self.parent.log(f"[DEBUG] 当前已授权设备列表: {all_devices}")

            # 5. 检查设备是否已授权
            if device_serial in all_devices:
                self.parent.log("设备已授权，无需重复授权")
                return True

            # 6. 检查设备数量限制
            if len(all_devices) >= self.max_devices:
                self.parent.log(f"授权失败：已授权设备数已达上限（{self.max_devices}）")
                return False

            # 7. 添加新设备到授权列表
            all_devices.append(device_serial)
            # --self.parent.log(f"[DEBUG] 更新后授权设备列表: {all_devices}")

            # 8. 生成本地密钥对
            # --self.parent.log("[DEBUG] 生成本地密钥对...")
            local_private, local_public = self.generate_key_pair()

            # 9. 生成设备密钥对（使用序列号作为种子）
            # --self.parent.log("[DEBUG] 生成设备密钥对...")
            device_private, device_public = self.generate_key_pair()

            # 10. 计算有效期（使用网络时间或本地时间）
            current_time = self.get_network_time() or datetime.datetime.now()
            expiry_date = current_time + datetime.timedelta(days=1)
            # --self.parent.log(f"[DEBUG] 授权有效期至: {expiry_date}")

            # 11. 保存本地授权文件
            # --self.parent.log("[DEBUG] 保存本地授权文件...")
            if not self.save_local_license(
                    device_serial,
                    0,
                    expiry_date,
                    device_public,
                    all_devices,
                    device_private,  # 保存设备私钥用于后续签名
                    device_fingerprint
            ):
                self.parent.log("保存本地授权文件失败")
                return False

            # 12. 准备设备授权数据
            device_data = {
                "device_id": device_serial,
                "uses": 0,
                "expiry": expiry_date.isoformat(),
                "local_public_key": local_public.decode() if isinstance(local_public, bytes) else local_public
            }
            device_data_str = json.dumps(device_data, separators=(',', ':'))  # 紧凑格式确保一致性
            # --self.parent.log(f"[DEBUG] 设备授权数据: {device_data_str}")

            # 13. 使用设备私钥签名
            signature = self.sign_data(device_data_str, device_private)
            # --self.parent.log(f"[DEBUG] 使用设备私钥生成的签名: {signature[:20]}...")

            # 添加调试信息
            # --self.parent.log(f"[DEBUG] 设备公钥内容: {device_public[:100]}...")

            # 14. 保存设备授权文件（确保目录存在）
            # --self.parent.log("[DEBUG] 创建设备授权目录...")
            license_dir = os.path.dirname(self.device_license_path)
            self.parent.run_adb(f'-s {device_ip} shell "mkdir -p {license_dir}"')

            # 15. 保存设备授权文件
            # --self.parent.log("[DEBUG] 保存设备授权文件...")
            if not self.save_device_license(
                    device_ip,  # 用于ADB命令的设备标识符(IP)
                    device_serial,  # 真正的设备ID(序列号)
                    0,
                    expiry_date,
                    local_public,
                    signature
            ):
                self.parent.log("保存设备授权文件失败")
                return False

            # 16. 验证文件是否创建成功
            check_cmd = f'-s {device_ip} shell "ls -l {self.device_license_path}"'
            check_output = self.parent.run_adb(check_cmd)
            if "No such file" in check_output:
                self.parent.log(f"[ERROR] 设备授权文件未创建: {check_output}")
                return False

            # --self.parent.log(f"[DEBUG] 设备授权文件已创建: {check_output}")
            # --self.parent.log("[DEBUG] 授权初始化成功")

            # 记录指纹
            self.append_fingerprint_record({
                "fingerprint": device_fingerprint,
                "device_id": device_serial,
                "first_auth_time": datetime.datetime.now().isoformat(),
                "auth_count": 1
            })

            return True

        except Exception as e:
            self.parent.log(f"[ERROR] 初始化授权异常: {str(e)}")
            import traceback
            self.parent.log(traceback.format_exc())
            return False

    def verify_licenses(self, device_ip, device_id):
        """双向验证本地和设备授权文件"""
        # 读取本地授权
        local_license = self.read_local_license()
        if not local_license:
            self.parent.log("授权失败：本地授权文件不存在")
            return False

        # 检查设备是否被授权
        if device_id not in local_license.get("all_devices", []):
            self.parent.log(f"授权失败：该设备未在授权设备列表中")
            return False

        # 读取设备授权
        device_license = self.read_device_license(device_ip)  # 传入device_ip
        if not device_license:
            self.parent.log("授权失败：设备授权文件不存在")
            return False

        # 1. 验证设备ID是否匹配
        if local_license["device_id"] != device_id or device_license["device_id"] != device_id:
            self.parent.log(f"授权失败：设备ID不匹配 (本地:{local_license['device_id']}, 设备:{device_license['device_id']})")
            return False

        # 2. 验证时间有效性
        current_time = self.get_network_time() or datetime.datetime.now()
        expiry_date = datetime.datetime.fromisoformat(local_license["expiry"])

        # 检查是否过期
        if current_time > expiry_date:
            self.parent.log(f"授权失败：授权已过期 (有效期至:{expiry_date})")
            return False

        # 3. 双向密钥验证
        # 验证设备签名（使用设备公钥验证设备授权文件）
        # 使用紧凑JSON格式确保一致性
        device_data = json.dumps({
            "device_id": device_license["device_id"],
            "uses": device_license["uses"],
            "expiry": device_license["expiry"],
            "local_public_key": device_license["local_public_key"]
        }, separators=(',', ':'))  # 关键修复

        # --self.parent.log(f"[DEBUG] 验证数据: {device_data}")
        # --self.parent.log(f"[DEBUG] 设备签名: {device_license['signature'][:100]}...")
        # --self.parent.log(f"[DEBUG] 本地公钥: {local_license['device_public_key'][:100]}...")

        if not self.verify_signature(
                device_data,
                device_license["signature"],
                local_license["device_public_key"]
        ):
            self.parent.log("授权失败：设备签名验证失败")
            return False

        # 验证本地授权数据（使用本地私钥"解密"验证）
        # 这里我们验证关键数据一致性
        if (local_license["uses"] != device_license["uses"] or
                local_license["expiry"] != device_license["expiry"]):
            self.parent.log(f"授权失败：数据不一致 (本地使用次数:{local_license['uses']}, 设备使用次数:{device_license['uses']})")
            return False

        # 4. 检查使用次数
        if int(local_license["uses"]) >= self.max_uses:
            self.parent.log(f"授权失败：使用次数已达上限 ({local_license['uses']}/{self.max_uses})")
            return False

        # 5.设备指纹校验
        fp = self.generate_device_fingerprint(device_ip)
        if not fp:
            self.parent.log("授权失败：无法生成设备指纹")
            return False  # 必须强制中断

        expected_fp = local_license.get("fingerprint")
        if expected_fp and fp and expected_fp != fp:
            self.parent.log("授权失败：设备指纹不匹配，可能是伪造授权文件")
            return False

        # 所有验证通过
        self.parent.log("授权验证成功")
        return True

    def update_usage(self, device_ip, device_id):
        """更新使用次数"""
        local_license = self.read_local_license()
        device_license = self.read_device_license(device_ip)

        if not local_license or not device_license:
            return False

        # 增加使用计数
        new_count = int(local_license["uses"]) + 1
        expiry_date = datetime.datetime.fromisoformat(local_license["expiry"])

        # 获取当前的授权设备列表
        all_devices = local_license.get("all_devices", [])

        # 关键修复：添加 all_devices 参数
        # 更新本地授权
        if not self.save_local_license(
                device_id,
                new_count,
                expiry_date,
                local_license["device_public_key"],
                all_devices,  # 添加这个参数
                device_private_key=local_license.get("device_private_key")
        ):
            self.parent.log("更新本地授权文件失败")
            return False

        # 更新设备授权
        device_data = json.dumps({
            "device_id": device_id,
            "uses": new_count,
            "expiry": expiry_date.isoformat(),
            "local_public_key": device_license["local_public_key"]
        }, separators=(',', ':'))  # 紧凑格式确保一致性

        # 重新签名（使用设备私钥）
        device_private_key = local_license.get("device_private_key")
        if not device_private_key:
            self.parent.log("更新失败：未找到设备私钥")
            return False

        signature = self.sign_data(device_data, device_private_key)

        # 保存设备授权文件（确保传递正确的参数）
        if not self.save_device_license(
                device_ip,  # ADB标识符
                device_id,  # 设备序列号
                new_count,
                expiry_date,
                device_license["local_public_key"],
                signature
        ):
            self.parent.log("更新设备授权文件失败")
            return False

        self.parent.log(f"使用次数更新: {new_count}/{self.max_uses}")
        return True

    def is_fingerprint_blocked(self, fingerprint):
        """检查是否存在指纹记录或被拉黑"""
        fp_records = self.read_fingerprint_records()
        for record in fp_records:
            if record["fingerprint"] == fingerprint:
                return record.get("blocked", False)
        return False

    def check_license(self):
        """执行完整的授权检查流程"""
        device_ip = self.parent.ip_input.text().strip()
        if not device_ip:
            self.parent.log("[ERROR] 未输入设备IP")
            return False

        # 获取当前设备指纹
        device_fingerprint = self.generate_device_fingerprint(device_ip)
        if not device_fingerprint:
            self.parent.log("授权失败：无法生成设备指纹")
            return False

        # 若已有授权记录或被拉黑，则拒绝初始化
        if self.is_fingerprint_blocked(device_fingerprint):
            self.parent.log("授权失败：该设备指纹已存在或被禁止初始化")
            return False

        # 获取设备序列号
        device_id = self.get_device_serial(device_ip)
        if not device_id:
            self.parent.log("[ERROR] 无法获取设备序列号")
            return False

        # 检查当前时间有效性（防止时间回绕）
        current_time = self.get_network_time() or datetime.datetime.now()
        if current_time < self.release_date:
            self.parent.log("错误：系统时间早于程序发布日期")
            return False

        # 读取本地授权文件
        local_license = self.read_local_license()

        if not local_license:
            self.parent.log("[DEBUG] 首次运行，初始化授权")
            if not self.initialize_license():
                self.parent.log("授权初始化失败")
                return False
            local_license = self.read_local_license()
            if not local_license:
                self.parent.log("初始化后仍无法读取授权文件")
                return False
        else:
            self.parent.log("[DEBUG] 找到现有授权文件")

        # ✅ 判断当前设备是否已授权，否则尝试新增授权
        all_devices = local_license.get("all_devices", [])
        if device_id not in all_devices:
            self.parent.log(f"[DEBUG] 当前设备（{device_id}）未授权，尝试添加授权...")
            if not self.initialize_license():
                self.parent.log("授权失败：无法为新设备初始化授权")
                return False
            local_license = self.read_local_license()
            if not local_license or device_id not in local_license.get("all_devices", []):
                self.parent.log("授权失败：新设备仍未记录在授权文件中")
                return False

        # 执行双向验证
        if not self.verify_licenses(device_ip, device_id):
            self.parent.log("授权验证失败")
            return False

        # 更新使用次数
        if not self.update_usage(device_ip, device_id):
            self.parent.log("使用计数更新失败")
            return False

        return True


# ====================== 授权管理器类结束 ======================

# ====================== 日志文件选择对话框类开始 ======================
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

        adb_layout = QHBoxLayout()
        adb_layout.addWidget(self.adb_command_input)
        adb_layout.addWidget(self.run_adb_btn)

        main_layout = QVBoxLayout()
        main_layout.addLayout(top_layout)
        main_layout.addLayout(adb_layout)
        main_layout.addWidget(self.log_output)

        self.setLayout(main_layout)

        # 绑定事件
        self.license_manager = LicenseManager(self)
        self.connect_btn.clicked.connect(self.connect_stb)
        self.deploy_btn.clicked.connect(self.deploy_files)
        self.other_ops_btn.clicked.connect(self.other_operations)
        self.reboot_btn.clicked.connect(self.reboot_stb)
        self.run_adb_btn.clicked.connect(self.run_adb_command)
        self.monitor_btn.clicked.connect(self.show_performance_monitor)
        self.storage_btn.clicked.connect(self.show_storage_monitor)

    def log(self, message, command=False):
        """增强日志方法，实时刷新界面"""
        prefix = "[CMD] " if command else ""
        self.log_output.append(f"{prefix}{message}")
        QApplication.processEvents()  # 强制刷新界面

    def run_adb_command(self):
        """执行自定义 ADB 命令"""
        command = self.adb_command_input.text().strip()
        if command:
            # 检查授权 - 修改这里
            if not self.license_manager.check_license():
                QMessageBox.warning(self, "授权失败", "工具未授权或授权已过期")
                return

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
        # 检查授权
        if not self.license_manager.check_license():
            QMessageBox.warning(self, "授权失败", "工具未授权或授权已过期")
            return

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
        # 检查授权
        if not self.license_manager.check_license():
            QMessageBox.warning(self, "授权失败", "工具未授权或授权已过期")
            return

        self.run_adb("reboot")
        self.log("机顶盒已重启")

    def other_operations(self):
        """其他操作功能主界面"""
        # 检查授权
        if not self.license_manager.check_license():
            QMessageBox.warning(self, "授权失败", "工具未授权或授权已过期")
            return

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
        # 检查授权
        if not self.license_manager.check_license():
            QMessageBox.warning(self, "授权失败", "工具未授权或授权已过期")
            return

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
        # 检查授权
        if not self.license_manager.check_license():
            QMessageBox.warning(self, "授权失败", "工具未授权或授权已过期")
            return
        StorageMonitorDialog(self).exec()


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


if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = STBTool()
    window.show()
    sys.exit(app.exec())
