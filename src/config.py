# -*- coding: utf-8 -*-
"""pyer6343 - 配置持久化（json）。

记住 adb 路径、输出目录、上次设备、窗口位置等。
"""

import json
import os


class Config:
    """配置读写。任何读写失败都静默降级为默认值，绝不能让 GUI 起不来。"""

    DEFAULTS = {
        "adb_path": "",
        "out_dir": "",
        "last_device": "",
        "geometry": "",
        "wifi_ip": "",
    }

    def __init__(self, path):
        self.path = path
        self.data = dict(self.DEFAULTS)
        self.load()

    def load(self):
        try:
            with open(self.path, "r", encoding="utf-8") as f:
                loaded = json.load(f)
            if isinstance(loaded, dict):
                self.data.update(loaded)
        except Exception:
            pass

    def get(self, key, default=None):
        return self.data.get(key, default)

    def set(self, key, value):
        self.data[key] = value

    def save(self):
        try:
            with open(self.path, "w", encoding="utf-8") as f:
                json.dump(self.data, f, ensure_ascii=False, indent=2)
        except Exception:
            pass
