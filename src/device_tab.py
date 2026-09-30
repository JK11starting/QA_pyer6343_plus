# -*- coding: utf-8 -*-
"""pyer6343 - 设备管理页签。

设备列表、kill/start server、WiFi 连接（connect / tcpip 5555）、快捷预设。
"""

import os
import re
import tkinter as tk
from tkinter import filedialog, messagebox, scrolledtext, ttk

from adb_core import REAL_SERIAL, connect_emulator

# MuMu 等常见模拟器的 adb 端口
EMU_PORTS = (16384, 16416, 16448, 7555)


class DeviceTab:
    def __init__(self, app, parent):
        self.app = app
        self.ip_var = tk.StringVar(value=app.cfg.get("wifi_ip", ""))

        # ---- 快捷预设 ----
        lf0 = ttk.LabelFrame(parent, text="快捷预设", padding=6)
        lf0.pack(fill="x", pady=(0, 6))
        ttk.Button(lf0, text="连接模拟器 127.0.0.1:16384",
                   command=self.connect_emu).pack(side="left", padx=3)
        ttk.Button(lf0, text="选真机 %s" % REAL_SERIAL,
                   command=self.select_real).pack(side="left", padx=3)
        ttk.Label(lf0, text="（模拟器用 connect 连；真机需 USB 插着才可选）",
                  foreground="#888").pack(side="left", padx=8)

        # ---- 设备列表 / server ----
        lf1 = ttk.LabelFrame(parent, text="设备与服务", padding=6)
        lf1.pack(fill="x", pady=(0, 6))
        for t, c in (("刷新设备列表", self.list_devices),
                     ("杀掉 adb server（kill-server）", self.kill_server),
                     ("启动 adb server（start-server）", self.start_server),
                     ("查看 adb 版本", self.adb_version)):
            ttk.Button(lf1, text=t, command=c).pack(side="left", padx=3)

        # ---- WiFi 连接 ----
        lf2 = ttk.LabelFrame(parent, text="WiFi 无线连接", padding=6)
        lf2.pack(fill="x", pady=(0, 6))
        ttk.Label(lf2, text="设备 IP：").pack(side="left")
        ttk.Entry(lf2, textvariable=self.ip_var, width=20).pack(
            side="left", padx=4)
        ttk.Button(lf2, text="自动获取(当前设备)",
                   command=self.auto_ip).pack(side="left", padx=2)
        ttk.Button(lf2, text="开启 tcpip 5555",
                   command=self.tcpip).pack(side="left", padx=2)
        ttk.Button(lf2, text="连接", command=self.do_connect).pack(
            side="left", padx=2)
        ttk.Button(lf2, text="断开全部无线", command=self.disconnect_all).pack(
            side="left", padx=2)
        ttk.Label(lf2, text="（支持 ip:port，不带端口默认补 :5555；"
                            "tcpip 需先用 USB 连着）",
                  foreground="#888").pack(side="left", padx=8)

        # ---- adb 路径 ----
        lf3 = ttk.LabelFrame(parent, text="adb 路径设置", padding=6)
        lf3.pack(fill="x", pady=(0, 6))
        self.adb_path_var = tk.StringVar(value=self.app.adb.exe)
        ttk.Entry(lf3, textvariable=self.adb_path_var).pack(
            side="left", fill="x", expand=True, padx=4)
        ttk.Button(lf3, text="浏览…", command=self.pick_adb).pack(side="left")
        ttk.Button(lf3, text="应用并保存", command=self.apply_adb).pack(
            side="left", padx=4)

        out = ttk.LabelFrame(parent, text="输出结果", padding=4)
        out.pack(fill="both", expand=True)
        self.txt = scrolledtext.ScrolledText(
            out, height=12, wrap="none", font=("Consolas", 10),
            bg="#1e1e1e", fg="#dcdcdc", insertbackground="#dcdcdc")
        self.txt.pack(fill="both", expand=True)

    def _out(self, t):
        self.app.set_text(self.txt, t)

    # ---------- 设备列表 ----------
    def list_devices(self):
        self.app.refresh_devices()

        def work():
            devs = self.app.adb.devices()
            lines = ["共 %d 台设备：" % len(devs)]
            for d in devs:
                lines.append("  %-26s %-14s %s"
                             % (d["serial"], d["state"], d["desc"]))
            if not devs:
                lines.append("  （无。真机请插 USB 并开 USB 调试；"
                             "模拟器请点上方「连接模拟器」。）")
            self._out("\n".join(lines))
        self.app.async_run(work)

    # ---------- adb server ----------
    def kill_server(self):
        def work():
            rc, out, err = self.app.adb.run(["kill-server"], timeout=30)
            self.app.log("kill-server：%s" % ((out or err).strip() or "完成"))
            self.app.refresh_devices(silent=True)
        self.app.async_run(work)

    def start_server(self):
        def work():
            rc, out, err = self.app.adb.run(["start-server"], timeout=40)
            self.app.log("start-server：%s" % ((out or err).strip() or "完成"))
            self.app.refresh_devices(silent=True)
        self.app.async_run(work)

    def adb_version(self):
        def work():
            self.app.log("adb 版本：%s" % self.app.adb.version())
        self.app.async_run(work)

    # ---------- 快捷预设 ----------
    def connect_emu(self):
        def work():
            connect_emulator(self.app.adb, self.app.log)
            self.app.refresh_devices(silent=True)
        self.app.async_run(work)

    def select_real(self):
        devs = self.app.adb.devices()
        for d in devs:
            if d["serial"] == REAL_SERIAL:
                self.app.dev_var.set(d["label"])
                self.app.on_dev_change()
                self.app.log("已选中真机：%s" % REAL_SERIAL)
                return
        messagebox.showwarning(
            "未找到真机",
            "设备列表里没有 %s。\n请确认手机已用 USB 连接、"
            "USB 调试已开启并授权，然后点顶部「刷新」。" % REAL_SERIAL)

    # ---------- WiFi ----------
    def auto_ip(self):
        d = self.app.cur_dev()
        if not d:
            return

        def work():
            rc, out, err = self.app.adb.shell("ip addr show wlan0", d, timeout=25)
            m = re.search(r"inet\s+([\d.]+)/", out or "")
            if not m:
                # 回退：ifconfig wlan0（老 ROM）
                rc, out, err = self.app.adb.shell("ifconfig wlan0", d, timeout=25)
                m = re.search(r"inet addr:([\d.]+)", out or "")
            if not m:
                rc, out, err = self.app.adb.shell(
                    "getprop dhcp.wlan0.ipaddress", d, timeout=20)
                m = re.match(r"([\d.]+)$", (out or "").strip())
            if m:
                self.app.log("设备 IP：%s" % m.group(1))
                self.app.set_var(self.ip_var, m.group(1))
                self.app.cfg.set("wifi_ip", m.group(1))
                self.app.save_cfg()
            else:
                self.app.log("没拿到设备 IP（可能没连 WiFi）。")
        self.app.async_run(work)

    def tcpip(self):
        d = self.app.cur_dev()
        if not d:
            return

        def work():
            rc, out, err = self.app.adb.run(["tcpip", "5555"], d, timeout=40)
            self.app.log("tcpip 5555：%s" % ((out or err).strip() or "完成"))
            self.auto_ip()
        self.app.async_run(work)

    def do_connect(self):
        ip = self.ip_var.get().strip()
        if not ip:
            messagebox.showwarning("缺 IP", "先填设备 IP，或点「自动获取」。")
            return
        if ":" not in ip:
            ip = ip + ":5555"

        def work():
            rc, out, err = self.app.adb.run(["connect", ip], timeout=30)
            self.app.log("connect %s -> %s" % (ip, (out or err).strip()))
            self.app.cfg.set("wifi_ip", ip.split(":")[0])
            self.app.save_cfg()
            self.app.refresh_devices(silent=True)
        self.app.async_run(work)

    def disconnect_all(self):
        def work():
            rc, out, err = self.app.adb.run(["disconnect"], timeout=30)
            self.app.log("disconnect：%s" % ((out or err).strip() or "完成"))
            self.app.refresh_devices(silent=True)
        self.app.async_run(work)

    # ---------- adb 路径 ----------
    def pick_adb(self):
        p = filedialog.askopenfilename(
            title="选择 adb.exe",
            filetypes=[("adb.exe", "adb.exe"), ("exe", "*.exe")])
        if p:
            self.adb_path_var.set(p)

    def apply_adb(self):
        p = self.adb_path_var.get().strip()
        if not os.path.isfile(p):
            messagebox.showwarning("路径无效", "文件不存在：%s" % p)
            return
        self.app.adb.exe = p
        self.app.cfg.set("adb_path", p)
        self.app.save_cfg()
        self.app.log("adb 已切换为：%s" % p)
        self.app.update_statusbar()
        self.app.refresh_devices(silent=True)

