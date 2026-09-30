# -*- coding: utf-8 -*-
"""pyer6343 - 交互式 Shell 页签。

伪终端：用户输入命令 -> adb -s <serial> shell "<cmd>" -> 输出流式回显。
不做真正的交互式 stdin，每条命令独立执行；高频输出攒批（>=60 行或 0.2s）投递。
"""

import subprocess
import threading
import time
import tkinter as tk
from tkinter import scrolledtext, ttk

from adb_core import CREATE_NO_WINDOW, startupinfo

# 常用命令快捷按钮：(显示文本, 实际命令)
QUICK_CMDS = (
    ("ls", "ls"),
    ("ls /sdcard", "ls -l /sdcard"),
    ("cat 版本", "cat /proc/version"),
    ("ps -A", "ps -A"),
    ("top -n 1", "top -n 1"),
    ("getprop", "getprop"),
    ("df", "df"),
    ("电池", "dumpsys battery"),
    ("分辨率", "wm size"),
    ("内存", "cat /proc/meminfo"),
    ("网络", "ip addr show wlan0"),
)


class ShellTab:
    def __init__(self, app, parent):
        self.app = app
        self.history = []
        self.hist_idx = 0
        self.running = False

        hint = ttk.Label(parent,
                         text="每条命令独立执行（非交互式）。提示：top 这类长驻命令"
                              "请加 -n 1 参数，否则会一直挂着不出结果。",
                         foreground="#888")
        hint.pack(fill="x", pady=(0, 4))

        row = ttk.Frame(parent)
        row.pack(fill="x", pady=4)
        self.cmd_var = tk.StringVar()
        self.entry = ttk.Entry(row, textvariable=self.cmd_var,
                              font=("Consolas", 10))
        self.entry.pack(side="left", fill="x", expand=True, padx=(0, 6))
        self.entry.bind("<Return>", lambda _e: self.run_cmd())
        self.entry.bind("<Up>", self.hist_prev)
        self.entry.bind("<Down>", self.hist_next)
        ttk.Button(row, text="执行", command=self.run_cmd).pack(side="left")
        ttk.Button(row, text="清空", command=self.clear).pack(side="left", padx=4)

        quick = ttk.Frame(parent)
        quick.pack(fill="x", pady=(0, 6))
        for txt, cmd in QUICK_CMDS:
            ttk.Button(quick, text=txt, width=10,
                       command=lambda c=cmd: self.fill_cmd(c)).pack(side="left", padx=2)

        out = ttk.LabelFrame(parent, text="输出结果", padding=4)
        out.pack(fill="both", expand=True, pady=(6, 0))
        txt_frm = ttk.Frame(out)
        txt_frm.pack(fill="both", expand=True)
        self.txt = scrolledtext.ScrolledText(
            txt_frm, height=16, wrap="none", font=("Consolas", 10),
            bg="#101010", fg="#cfcfcf", insertbackground="#cfcfcf")
        self.txt.pack(side="top", fill="both", expand=True)
        self.hbar = ttk.Scrollbar(txt_frm, orient="horizontal",
                                  command=self.txt.xview)
        self.hbar.pack(side="bottom", fill="x")
        self.txt.configure(xscrollcommand=self.hbar.set)

    # ---------- 历史记录 ----------
    def fill_cmd(self, cmd):
        self.cmd_var.set(cmd)
        self.entry.focus_set()

    def hist_prev(self, _e=None):
        if not self.history:
            return "break"
        self.hist_idx = max(0, self.hist_idx - 1)
        self.cmd_var.set(self.history[self.hist_idx])
        return "break"

    def hist_next(self, _e=None):
        if not self.history:
            return "break"
        self.hist_idx = min(len(self.history), self.hist_idx + 1)
        self.cmd_var.set(self.history[self.hist_idx]
                         if self.hist_idx < len(self.history) else "")
        return "break"

    def clear(self):
        self.txt.delete("1.0", "end")

    # ---------- 执行 ----------
    def run_cmd(self):
        d = self.app.cur_dev()
        if not d:
            return
        if self.running:
            self.app.log("上一条命令还没跑完，稍等。")
            return
        cmd = self.cmd_var.get().strip()
        if not cmd:
            return
        self.history.append(cmd)
        self.hist_idx = len(self.history)
        self.cmd_var.set("")

        # 命令回显（uiq.put 线程安全，主线程 drain 时插入）
        self.app.append_lines(self.txt, ["$ " + cmd])
        self.app.log("$ adb -s %s shell %s" % (d, cmd))
        self.running = True  # 在主线程置位，避免双击连发的竞态

        full = self.app.adb.base(d) + ["shell", cmd]

        def work():
            try:
                proc = subprocess.Popen(
                    full, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                    text=True, encoding="utf-8", errors="replace", bufsize=1,
                    startupinfo=startupinfo(), creationflags=CREATE_NO_WINDOW)
            except Exception as e:
                self.running = False
                self.app.log("命令启动失败：%r" % e)
                return
            buf, last = [], time.time()
            try:
                for line in proc.stdout:
                    buf.append(line.rstrip("\n"))
                    # 批量投递：逐行刷新会把主线程事件队列打爆，界面才卡
                    if len(buf) >= 60 or time.time() - last > 0.2:
                        self.app.append_lines(self.txt, buf)
                        buf, last = [], time.time()
                if buf:
                    self.app.append_lines(self.txt, buf)
            except Exception:
                pass
            finally:
                try:
                    proc.terminate()
                except Exception:
                    pass
                rc = proc.wait()
                self.running = False
                if rc != 0:
                    self.app.log("（shell 退出码 %d）" % rc)

        threading.Thread(target=work, daemon=True).start()
