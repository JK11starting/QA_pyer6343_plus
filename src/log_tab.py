# -*- coding: utf-8 -*-
"""pyer6343 - 设备日志（logcat）页签。

启动/停止/保存/清空缓冲区；关键字过滤；攒批回显 + 行数上限裁剪。
"""

import os
import subprocess
import threading
import time
import tkinter as tk
from tkinter import filedialog, scrolledtext, ttk

from adb_core import CREATE_NO_WINDOW, startupinfo, ts

LOG_MAX_LINES = 5000   # 文本区行数上限，超过后裁掉前面 40%
BATCH_LINES = 60       # 攒批行数阈值
BATCH_SECS = 0.2       # 攒批时间阈值（秒）


class LogTab:
    def __init__(self, app, parent):
        self.app = app
        self.proc = None
        self.stop_evt = None
        self.lines = []          # 全量日志（含未过滤），用于保存
        self.state_var = tk.StringVar(value="未开始")

        r1 = ttk.Frame(parent)
        r1.pack(fill="x", pady=4)
        ttk.Label(r1, text="过滤关键字：").pack(side="left")
        self.kw_var = tk.StringVar()
        ttk.Entry(r1, textvariable=self.kw_var, width=26).pack(
            side="left", padx=4)
        ttk.Label(r1, text="（留空抓全部，多个用空格分隔）",
                  foreground="#888").pack(side="left")
        ttk.Label(r1, textvariable=self.state_var,
                  foreground="#c83").pack(side="right", padx=8)

        r2 = ttk.Frame(parent)
        r2.pack(fill="x", pady=4)
        for t, c in (("开始抓取", self.start),
                     ("停止", self.stop),
                     ("保存日志", self.save),
                     ("清空设备日志缓冲区", self.clear_buffer),
                     ("清空显示", lambda: self.txt.delete("1.0", "end"))):
            ttk.Button(r2, text=t, command=c).pack(side="left", padx=3)

        r3 = ttk.Frame(parent)
        r3.pack(fill="x", pady=2)
        ttk.Label(r3, text="日志保存目录：").pack(side="left")
        self.save_dir_var = tk.StringVar(value=app.cfg.get("log_save_dir") or app.out_dir)
        ttk.Entry(r3, textvariable=self.save_dir_var).pack(
            side="left", fill="x", expand=True, padx=4)
        ttk.Button(r3, text="浏览…", command=self.pick_save_dir).pack(side="left")

        out = ttk.LabelFrame(parent, text="输出结果", padding=4)
        out.pack(fill="both", expand=True, pady=(6, 0))
        self.txt = scrolledtext.ScrolledText(
            out, height=16, wrap="none", font=("Consolas", 9),
            bg="#101010", fg="#cfcfcf", insertbackground="#cfcfcf")
        self.txt.pack(fill="both", expand=True)

    def _state(self, s):
        self.app.set_var(self.state_var, s)

    def start(self):
        d = self.app.cur_dev()
        if not d:
            return
        if self.proc:
            self.app.log("日志已在抓取中，先点「停止」。")
            return
        st = self.app.dev_state(d)
        if st and st != "device":
            self.app.log("设备状态 = %s，无法抓取日志。" % st)
            return

        self.lines = []
        self.txt.delete("1.0", "end")
        self.stop_evt = threading.Event()
        kws = [k for k in self.kw_var.get().split() if k]
        cmd = self.app.adb.base(d) + ["logcat", "-v", "threadtime"]

        def work():
            try:
                proc = subprocess.Popen(
                    cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                    text=True, encoding="utf-8", errors="replace", bufsize=1,
                    startupinfo=startupinfo(), creationflags=CREATE_NO_WINDOW)
            except Exception as e:
                self.stop_evt = None
                self.app.log("启动 logcat 失败：%r" % e)
                return
            self.proc = proc
            self._state("抓取中…")
            self.app.log("logcat 已启动（关键字：%s）" % (" ".join(kws) or "全部"))
            buf, last = [], time.time()
            try:
                for line in proc.stdout:
                    if self.stop_evt.is_set():
                        break
                    line = line.rstrip("\n")
                    self.lines.append(line)
                    if not kws or any(k in line for k in kws):
                        buf.append(line)
                    # 批量投递：逐行刷新会把主线程事件队列打爆
                    if len(buf) >= BATCH_LINES or time.time() - last > BATCH_SECS:
                        if buf:
                            self.app.append_lines(self.txt, buf, LOG_MAX_LINES)
                            buf, last = [], time.time()
                if buf:
                    self.app.append_lines(self.txt, buf, LOG_MAX_LINES)
            except Exception:
                pass
            finally:
                try:
                    proc.terminate()
                except Exception:
                    pass
                self.proc = None
                if self.lines:
                    self._state("已停止（共 %d 行）" % len(self.lines))
                    self.app.log("logcat 结束，共 %d 行。" % len(self.lines))
                else:
                    self._state("已结束（无输出）")
                    self.app.log("logcat 没有任何输出 —— 检查设备是否还在线。")
        threading.Thread(target=work, daemon=True).start()

    def stop(self):
        if self.stop_evt:
            self.stop_evt.set()
        if self.proc:
            try:
                self.proc.terminate()
            except Exception:
                pass

    def pick_save_dir(self):
        d = filedialog.askdirectory(
            title="选择日志保存目录",
            initialdir=self.save_dir_var.get() or self.app.out_dir)
        if d:
            self.save_dir_var.set(d)
            self.app.cfg.set("log_save_dir", d)
            self.app.save_cfg()

    def save(self):
        if not self.lines:
            self.app.log("还没抓到日志内容，先点「开始抓取」。")
            return
        save_dir = self.save_dir_var.get().strip() or self.app.out_dir
        try:
            os.makedirs(save_dir, exist_ok=True)
        except Exception as e:
            self.app.log("保存目录无效：%r" % e)
            return
        path = os.path.join(save_dir, "logcat_%s.txt" % ts())
        try:
            with open(path, "w", encoding="utf-8") as f:
                f.write("\n".join(self.lines))
            self.app.log("日志已保存：%s（%d 行）" % (path, len(self.lines)))
        except Exception as e:
            self.app.log("保存失败：%r" % e)

    def clear_buffer(self):
        d = self.app.cur_dev()
        if not d:
            return

        def work():
            rc, out, err = self.app.adb.run(["logcat", "-c"], d, timeout=30)
            self.app.log("logcat -c：%s" % ((out or err).strip() or "设备日志缓冲区已清空"))
        self.app.async_run(work)
