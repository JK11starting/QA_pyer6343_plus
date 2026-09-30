# -*- coding: utf-8 -*-
"""pyer6343 plus - 主入口。

主窗口 + 设备选择栏 + 8 个功能页签 + 公共输出区 + 状态栏。
所有后台线程的 UI 更新统一走 queue -> 主线程 drain()，高频输出攒批投递。
"""

import os
import queue
import threading
import tkinter as tk
from tkinter import messagebox, scrolledtext, ttk

from adb_core import APP_NAME, VERSION, Adb, app_dir, connect_emulator, find_adb
from config import Config
from shell_tab import ShellTab
from app_tab import AppTab
from file_tab import FileTab
from device_tab import DeviceTab
from reboot_tab import RebootTab
from info_tab import InfoTab
from log_tab import LogTab
from tools_tab import ToolsTab


class App:
    """主应用：持有 adb 封装、配置、设备映射与 UI 消息队列。"""

    def __init__(self, root):
        self.root = root
        self.uiq = queue.Queue()
        self.cfg = Config(os.path.join(app_dir(), "pyer6343_config.json"))
        p = self.cfg.get("adb_path")
        self.adb = Adb(p if p and os.path.isfile(p) else find_adb())
        self.out_dir = self.cfg.get("out_dir") or os.path.join(app_dir(), "out")
        os.makedirs(self.out_dir, exist_ok=True)

        # 下拉框显示文本(label) -> 真实序列号(serial) 的映射
        self.dev_map = {}
        self.dev_var = tk.StringVar(value=self.cfg.get("last_device", ""))
        self.status_var = tk.StringVar(value="就绪")

        root.title("%s %s - ADB QA 助手" % (APP_NAME, VERSION))
        root.geometry(self.cfg.get("geometry") or "1100x780")
        root.minsize(960, 660)
        root.protocol("WM_DELETE_WINDOW", self.on_close)

        self.build_top()
        self.build_tabs()
        self.build_output()
        self.build_statusbar()

        self.root.after(80, self.drain)
        self.log("工作目录：%s" % app_dir())
        self.log("adb：%s（版本 %s）" % (self.adb.exe, self.adb.version()))
        self.log("输出目录：%s" % self.out_dir)
        self.refresh_devices(silent=True)

    # ---------- 界面骨架 ----------
    def build_top(self):
        top = ttk.Frame(self.root, padding=(8, 8, 8, 4))
        top.pack(fill="x")

        ttk.Label(top, text="设备：").pack(side="left")
        self.dev_combo = ttk.Combobox(top, textvariable=self.dev_var,
                                      width=36, state="readonly")
        self.dev_combo.pack(side="left", padx=4)
        self.dev_combo.bind("<<ComboboxSelected>>", self.on_dev_change)

        for txt, fn in (("刷新", lambda: self.refresh_devices()),
                        ("连MuMu(16384)", self.connect_emu)):
            ttk.Button(top, text=txt, command=fn).pack(side="left", padx=2)

        ttk.Label(top, textvariable=self.status_var,
                  foreground="#2a7").pack(side="right")

    def build_tabs(self):
        nb = ttk.Notebook(self.root)
        nb.pack(fill="both", expand=True, padx=8, pady=4)

        titles = ("  交互终端  ", "  应用管理  ", "  文件传输  ", "  设备管理  ",
                  "  重启控制  ", "  设备信息  ", "  设备日志  ", "  实用工具  ")
        builders = (ShellTab, AppTab, FileTab, DeviceTab, RebootTab,
                    InfoTab, LogTab, ToolsTab)
        tabs = []
        for title, cls in zip(titles, builders):
            f = ttk.Frame(nb, padding=8)
            nb.add(f, text=title)
            tabs.append(cls(self, f))
        (self.tab_shell, self.tab_app, self.tab_file, self.tab_dev,
         self.tab_reboot, self.tab_info, self.tab_log, self.tab_tool) = tabs

    def build_output(self):
        frm = ttk.LabelFrame(self.root, text="执行命令", padding=6)
        frm.pack(fill="both", expand=True, padx=8, pady=(2, 4))

        txt_frm = ttk.Frame(frm)
        txt_frm.pack(fill="both", expand=True)
        self.txt = scrolledtext.ScrolledText(
            txt_frm, height=10, wrap="none", font=("Consolas", 10),
            bg="#1e1e1e", fg="#dcdcdc", insertbackground="#dcdcdc")
        self.txt.pack(side="top", fill="both", expand=True)
        self.hbar = ttk.Scrollbar(txt_frm, orient="horizontal",
                                   command=self.txt.xview)
        self.hbar.pack(side="bottom", fill="x")
        self.txt.configure(xscrollcommand=self.hbar.set)

        bar = ttk.Frame(frm)
        bar.pack(fill="x", pady=(4, 0))
        ttk.Button(bar, text="清空输出", command=self.clear_out).pack(side="left")
        ttk.Button(bar, text="复制全部", command=self.copy_all).pack(
            side="left", padx=4)
        ttk.Button(bar, text="打开输出目录",
                   command=lambda: self.open_dir(self.out_dir)).pack(side="left")

    def build_statusbar(self):
        bar = ttk.Frame(self.root, padding=(8, 2))
        bar.pack(fill="x", side="bottom")
        self.sb_adb = ttk.Label(bar, text="", foreground="#666")
        self.sb_adb.pack(side="left")
        self.sb_dev = ttk.Label(bar, text="", foreground="#666")
        self.sb_dev.pack(side="right")
        self.update_statusbar()

    def update_statusbar(self):
        """主线程调用：刷新底部状态栏。"""
        self.sb_adb.configure(text="adb: %s" % self.adb.exe)
        lab = self.dev_var.get().strip()
        serial = self.dev_map.get(lab) or (lab.split()[0] if lab else "")
        self.sb_dev.configure(text="当前设备: %s" % (serial or "（未选择）"))

    # ---------- 线程安全消息分发 ----------
    def log(self, msg=""):
        self.uiq.put(("log", msg))

    def status(self, msg):
        self.uiq.put(("status", msg))

    def save_cfg(self):
        """供各页签统一落盘配置（线程安全：Config.save 内部已静默降级）。"""
        self.cfg.save()

    def set_var(self, var, val):
        self.uiq.put(("setvar", (var, val)))

    def set_text(self, widget, text, follow=False):
        """线程安全地整体替换文本区内容。"""
        self.uiq.put(("settxt", (widget, text, follow)))

    def append_lines(self, widget, lines, maxlines=5000):
        """线程安全地批量追加行；超过 maxlines 时裁掉前 40%。"""
        self.uiq.put(("appendlines", (widget, lines, maxlines)))

    def call(self, fn):
        """让一个无参函数排到主线程执行（用于 UI 状态切换等）。"""
        self.uiq.put(("call", fn))

    def drain(self):
        """主线程定时消费 UI 消息队列——后台线程绝不直接操作控件。"""
        try:
            for _ in range(400):
                kind, payload = self.uiq.get_nowait()
                if kind == "log":
                    self.txt.insert("end", payload + "\n")
                    self.txt.see("end")
                elif kind == "status":
                    self.status_var.set(payload)
                elif kind == "devs":
                    self.apply_devices(payload)
                elif kind == "setvar":
                    payload[0].set(payload[1])
                elif kind == "settxt":
                    widget, text, follow = payload
                    widget.delete("1.0", "end")
                    widget.insert("1.0", text)
                    if follow:
                        widget.see("end")
                elif kind == "appendlines":
                    widget, lines, maxn = payload
                    if lines:
                        widget.insert("end", "\n".join(lines) + "\n")
                        n = int(widget.index("end-1c").split(".")[0])
                        if maxn and n > maxn:
                            widget.delete("1.0", "%d.0" % (n - int(maxn * 0.6)))
                        widget.see("end")
                elif kind == "call":
                    try:
                        payload()
                    except Exception as e:
                        self.log("回调异常：%r" % e)
        except queue.Empty:
            pass
        self.root.after(80, self.drain)

    def clear_out(self):
        self.txt.delete("1.0", "end")

    def copy_all(self):
        self.root.clipboard_clear()
        self.root.clipboard_append(self.txt.get("1.0", "end"))

    def open_dir(self, path):
        try:
            os.startfile(path)
        except Exception as e:
            self.log("打开失败：%r" % e)

    # ---------- 后台线程执行 ----------
    def async_run(self, fn):
        def wrap():
            self.status("执行中…")
            try:
                fn()
            except Exception as e:
                self.log("异常：%r" % e)
            finally:
                self.status("就绪")
        threading.Thread(target=wrap, daemon=True).start()

    # ---------- 设备选择 ----------
    def cur_dev(self, check=True):
        """返回当前选中的真实序列号。
        dev_var 存的是带型号后缀的显示文本，必须经 dev_map 还原成序列号。
        check=True 时先确认设备处于 device 状态，避免各功能静默失败。"""
        lab = self.dev_var.get().strip()
        if not lab:
            messagebox.showwarning("未选设备", "先在顶部选一个设备，或点「刷新」。")
            return None
        d = self.dev_map.get(lab)
        if not d:
            d = lab.split()[0] if lab.split() else lab
        if not check:
            return d
        st = self.dev_state(d)
        if st == "device":
            return d
        tips = {
            "offline":
                "设备状态 = offline（已连上但无法通信）。\n\n"
                "常见原因与处理：\n"
                "  1. 数据线/USB 口接触不良 —— 换线或换口（机箱背面口更稳）\n"
                "  2. 手机 USB 模式被切成「仅充电」—— 下拉通知改回「传输文件」\n"
                "  3. USB 调试授权失效 —— 撤销授权后重新插拔\n"
                "  4. adb server 卡死 —— 到「设备管理」页点 kill/start server",
            "unauthorized":
                "设备未授权（unauthorized）。\n\n"
                "请在手机屏幕上点「允许 USB 调试」，"
                "勾选「一律允许」后再操作。",
        }
        msg = tips.get(st) or (
            "设备 %s 已不在 adb 列表中（可能已拔出或断开）。\n\n"
            "请检查连接后点顶部「刷新」。" % d)
        self.log("【设备不可用】" + msg.replace("\n", " "))
        messagebox.showwarning("设备不可用", msg)
        return None

    def dev_state(self, serial):
        return self.adb.state(serial)

    def refresh_devices(self, silent=False):
        def work():
            devs = self.adb.devices()
            self.uiq.put(("devs", devs))
            if not silent:
                self.log("设备列表已刷新，共 %d 台：" % len(devs))
                for d in devs:
                    self.log("  %-26s %-8s %s"
                             % (d["serial"], d["state"], d["desc"]))
        self.async_run(work)

    def apply_devices(self, devs):
        """主线程：应用新设备列表到下拉框。"""
        vals = [d["label"] for d in devs]
        self.dev_map = {}
        for d in devs:
            # label 和 serial 都能反查 serial，双保险
            self.dev_map[d["label"]] = d["serial"]
            self.dev_map[d["serial"]] = d["serial"]
        self.dev_combo["values"] = vals
        cur = self.dev_var.get().strip()
        cur = self.dev_map.get(cur, cur)  # 兼容旧配置存显示文本的情况
        serials = [d["serial"] for d in devs]
        if cur in serials:
            lab = [d["label"] for d in devs if d["serial"] == cur][0]
            self.dev_var.set(lab)
        elif vals:
            self.dev_var.set(vals[0])
        else:
            self.dev_var.set("")
        self.update_statusbar()

    def on_dev_change(self, _e=None):
        lab = self.dev_var.get().strip()
        s = self.dev_map.get(lab) or (lab.split()[0] if lab else "")
        self.cfg.set("last_device", s)
        self.cfg.save()
        self.log("已选择设备：%s" % s)
        self.update_statusbar()

    def connect_emu(self):
        def work():
            connect_emulator(self.adb, self.log)
            self.refresh_devices(silent=True)
        self.async_run(work)

    # ---------- 生命周期 ----------
    def on_close(self):
        try:
            self.cfg.set("geometry", self.root.wm_geometry())
            lab = self.dev_var.get().strip()
            self.cfg.set("last_device",
                         self.dev_map.get(lab) or (lab.split()[0] if lab else ""))
            self.cfg.set("adb_path", self.adb.exe)
            self.cfg.set("out_dir", self.out_dir)
            self.cfg.save()
        except Exception:
            pass
        self.root.destroy()


def main():
    root = tk.Tk()
    App(root)
    root.mainloop()


if __name__ == "__main__":
    main()
