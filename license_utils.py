import os, json, hmac, base64, hashlib, subprocess
from datetime import datetime, timedelta
import urllib.request
from PyQt6.QtWidgets import (
    QDialog, QLabel, QVBoxLayout, QHBoxLayout,
    QLineEdit, QPushButton, QMessageBox, QApplication
)

SECRET_KEY = b"your_secret_here"
LICENSE_FILE = "license.dat"
USED_IDS_FILE = "used_licenses.json"


class LicenseInputDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("授权码输入")
        self.setFixedSize(500, 220)

        self.layout = QVBoxLayout()

        # 授权码输入框
        self.input_field = QLineEdit()
        self.input_field.setPlaceholderText("请输入授权码")
        self.layout.addWidget(QLabel("请输入授权码："))
        self.layout.addWidget(self.input_field)

        # 显示设备唯一标识区域
        self.device_id_field = QLineEdit()
        self.device_id_field.setReadOnly(True)
        self.device_id_field.setStyleSheet("color: gray;")
        raw_id = get_device_raw_string()
        self.device_id_field.setText(raw_id)

        row = QHBoxLayout()
        row.addWidget(QLabel("本机唯一标识（请复制提供给授权方）："))
        btn_copy = QPushButton("复制")
        btn_copy.clicked.connect(lambda: QApplication.clipboard().setText(raw_id))
        row.addWidget(btn_copy)
        self.layout.addLayout(row)
        self.layout.addWidget(self.device_id_field)

        # 按钮组
        btn_row = QHBoxLayout()
        btn_ok = QPushButton("确认")
        btn_cancel = QPushButton("取消")
        btn_ok.clicked.connect(self.accept)
        btn_cancel.clicked.connect(self.reject)
        btn_row.addWidget(btn_ok)
        btn_row.addWidget(btn_cancel)
        self.layout.addLayout(btn_row)

        self.setLayout(self.layout)

    def get_license_code(self):
        return self.input_field.text().strip()


class LicenseError(Exception): pass


def get_windows_device_id():
    try:
        result = subprocess.check_output("wmic csproduct get UUID", shell=True).decode().split('\n')
        return result[1].strip()
    except:
        return "UNKNOWN_DEVICE"


def get_windows_product_id():
    try:
        result = subprocess.check_output("wmic os get SerialNumber", shell=True).decode().split('\n')
        return result[1].strip()
    except:
        return "UNKNOWN_PRODUCT"


def get_device_raw_string():
    return f"{get_windows_device_id()}|{get_windows_product_id()}"


def get_local_fingerprint():
    raw = get_device_raw_string()
    print("[DEBUG] 指纹原始字符串:", raw)
    return hashlib.sha256(raw.encode()).hexdigest()


_network_time_cache = None


def get_network_time():
    global _network_time_cache
    if _network_time_cache:
        return _network_time_cache
    try:
        with urllib.request.urlopen("http://worldtimeapi.org/api/timezone/Asia/Shanghai", timeout=3) as res:
            data = json.loads(res.read().decode())
            _network_time_cache = datetime.fromisoformat(data['datetime'][:19])
            return _network_time_cache
    except Exception:
        return datetime.now()


def encode_license(data: dict) -> str:
    raw = {k: v for k, v in data.items() if k != "signature"}
    sig = hmac.new(SECRET_KEY, json.dumps(raw, sort_keys=True).encode(), hashlib.sha256).hexdigest()
    data["signature"] = sig
    return base64.urlsafe_b64encode(json.dumps(data).encode()).decode()


def decode_license(encoded: str) -> dict:
    try:
        decoded = base64.urlsafe_b64decode(encoded.encode()).decode()
        return json.loads(decoded)
    except Exception as e:
        raise LicenseError(f"授权解码失败: {str(e)}")


def save_license(encoded):
    with open(LICENSE_FILE, 'w') as f:
        f.write(encoded)


def load_license():
    if not os.path.exists(LICENSE_FILE): return None
    with open(LICENSE_FILE, 'r') as f:
        return f.read().strip()


def verify_license(data):
    try:
        if data.get("fingerprint") != get_local_fingerprint():
            raise LicenseError("设备指纹不匹配")
        sig = data.pop("signature")
        msg = json.dumps(data, sort_keys=True).encode()
        expected = hmac.new(SECRET_KEY, msg, hashlib.sha256).hexdigest()
        if expected != sig:
            raise LicenseError("授权签名无效")
        start = datetime.strptime(data['start_time'], "%Y-%m-%d")
        now = get_network_time()
        if now > start + timedelta(days=data['expire_days']):
            raise LicenseError("授权已过期")
        if data.get("used", 0) >= data["max_uses"]:
            raise LicenseError("已超出最大使用次数")
        return True
    except Exception as e:
        raise LicenseError(str(e))


def get_adb_device_id():
    try:
        out = subprocess.check_output("adb devices", shell=True).decode()
        lines = out.strip().splitlines()
        devices = [line.split()[0] for line in lines if '\tdevice' in line]
        return devices[0] if devices else None
    except:
        return None


def consume_license():
    encoded = load_license()
    if not encoded:
        raise LicenseError("未找到授权文件")

    data = decode_license(encoded)
    verify_license(data)

    device_id = get_adb_device_id() or "default_device"

    if "bound_devices" not in data:
        data["bound_devices"] = []

    if device_id not in data["bound_devices"]:
        if len(data["bound_devices"]) >= data["max_devices"]:
            raise LicenseError("已超过授权的设备数量")
        data["bound_devices"].append(device_id)

    data["used"] = data.get("used", 0) + 1
    if data["used"] > data["max_uses"]:
        raise LicenseError("已超出最大使用次数")

    updated = encode_license(data)
    save_license(updated)


def record_license_id(license_id):
    try:
        if os.path.exists(USED_IDS_FILE):
            used = json.load(open(USED_IDS_FILE))
        else:
            used = []
        if license_id in used:
            return False
        used.append(license_id)
        json.dump(used, open(USED_IDS_FILE, 'w'))
        return True
    except:
        return False


def prompt_license_in_window(ui_parent, force=False):
    if os.path.exists(LICENSE_FILE) and not force:
        return

    dialog = LicenseInputDialog(ui_parent)
    result = dialog.exec()
    if result != QDialog.DialogCode.Accepted:
        QMessageBox.critical(ui_parent, "未授权", "必须授权后才能使用")
        raise SystemExit

    license_text = dialog.get_license_code()
    if not license_text:
        QMessageBox.critical(ui_parent, "未授权", "授权码不能为空")
        raise SystemExit

    try:
        data = decode_license(license_text)
        verify_license(data)

        if not record_license_id(data.get("license_id", "")):
            QMessageBox.critical(ui_parent, "授权失败", "该授权码已激活过，无法重复使用")
            raise SystemExit

        data["used"] = 0
        data["bound_devices"] = []
        save_license(encode_license(data))
        QMessageBox.information(ui_parent, "授权成功", "授权码验证成功")
    except LicenseError as e:
        QMessageBox.warning(ui_parent, "授权失败", str(e))
        prompt_license_in_window(ui_parent, force=True)


def handle_license_failure(ui_parent, message):
    msg = QMessageBox(ui_parent)
    msg.setWindowTitle("授权失败")
    msg.setText(message)
    msg.setIcon(QMessageBox.Icon.Critical)
    retry_btn = msg.addButton("重新输入授权码", QMessageBox.ButtonRole.AcceptRole)
    exit_btn = msg.addButton("退出", QMessageBox.ButtonRole.RejectRole)
    msg.exec()
    if msg.clickedButton() == retry_btn:
        prompt_license_in_window(ui_parent, force=True)  # 👈 强制重新授权
        return True
    else:
        return False
