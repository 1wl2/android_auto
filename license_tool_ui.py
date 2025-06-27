import sys
import json
import hmac
import base64
import hashlib
import socket
import uuid
from datetime import datetime
from PyQt6.QtWidgets import (
    QApplication, QWidget, QLabel, QVBoxLayout, QLineEdit,
    QPushButton, QSpinBox, QMessageBox
)

SECRET_KEY = b"your_secret_here"


def get_fingerprint_from_input(raw_id):
    return hashlib.sha256(raw_id.encode()).hexdigest()


def generate_license_code(fingerprint, max_devices, max_uses, days_valid):
    license_data = {
        "license_id": str(uuid.uuid4()),  # 👈 自动生成唯一ID
        "fingerprint": fingerprint,
        "max_devices": max_devices,
        "max_uses": max_uses,
        "start_time": datetime.now().strftime("%Y-%m-%d"),
        "expire_days": days_valid
    }
    message = json.dumps(license_data, sort_keys=True).encode()
    signature = hmac.new(SECRET_KEY, message, hashlib.sha256).hexdigest()
    license_data["signature"] = signature
    encoded = base64.urlsafe_b64encode(json.dumps(license_data).encode()).decode()
    return encoded


class LicenseGenerator(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("授权码生成工具")
        self.resize(400, 300)

        layout = QVBoxLayout()

        # 单个输入框，输入设备ID|产品ID
        self.input_label = QLabel("请输入设备唯一标识（格式：设备ID|产品ID）：")
        self.input_id = QLineEdit()
        layout.addWidget(self.input_label)
        layout.addWidget(self.input_id)

        # 授权参数
        self.device_label = QLabel("授权连接机顶盒数量：")
        self.device_count = QSpinBox()
        self.device_count.setRange(1, 100)
        layout.addWidget(self.device_label)
        layout.addWidget(self.device_count)

        self.use_label = QLabel("允许操作次数：")
        self.use_count = QSpinBox()
        self.use_count.setRange(1, 10000)
        layout.addWidget(self.use_label)
        layout.addWidget(self.use_count)

        self.expire_label = QLabel("授权有效天数：")
        self.expire_days = QSpinBox()
        self.expire_days.setRange(1, 3650)
        layout.addWidget(self.expire_label)
        layout.addWidget(self.expire_days)

        # 输出授权码
        self.output = QLineEdit()
        self.output.setReadOnly(True)
        layout.addWidget(QLabel("生成的授权码："))
        layout.addWidget(self.output)

        self.generate_btn = QPushButton("生成授权码")
        self.generate_btn.clicked.connect(self.generate)
        layout.addWidget(self.generate_btn)

        self.setLayout(layout)

    def generate(self):
        raw = self.input_id.text().strip()
        if not raw or "|" not in raw:
            QMessageBox.warning(self, "错误", "请输入格式正确的标识（设备ID|产品ID）")
            return

        fingerprint = get_fingerprint_from_input(raw)
        license_code = generate_license_code(
            fingerprint,
            self.device_count.value(),
            self.use_count.value(),
            self.expire_days.value()
        )
        self.output.setText(license_code)

        with open("generated_license.txt", "w") as f:
            f.write(license_code)

        QMessageBox.information(self, "完成", "授权码已生成并保存为 generated_license.txt")


if __name__ == '__main__':
    app = QApplication(sys.argv)
    win = LicenseGenerator()
    win.show()
    sys.exit(app.exec())
