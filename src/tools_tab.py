# -*- coding: utf-8 -*-
"""pyer6343 - 实用工具页签。

截图（PNG 完整性校验 + 黑屏提示 + 预览）、录屏（限时 180s、可停、自动拉回）、
前台包名/activity、指定包内存占用。
"""

import os
import re
import subprocess
import threading
import time
import tkinter as tk
from tkinter import scrolledtext, ttk

from adb_core import (CREATE_NO_WINDOW, capture_png, foreground_activity,
                      looks_blank, screen_off, startupinfo, ts)

RECORD_MAX_SECS = 180


class ToolsTab:
    def __init__(self, app, parent):
        self.app = app
        self.cap_img = None       # 必须持有 PhotoImage 引用，否则被回收
        self.last_cap = None
        self.rec_proc = None
        self.recording = False

        # ---- 截图 / 录屏 ----
        lf1 = ttk.LabelFrame(parent, text="截图 / 录屏", padding=6)
        lf1.pack(fill="x", pady=(0, 6))
        ttk.Button(lf1, text="截图并保存", command=self.screenshot).pack(
            side="left", padx=3)
        self.rec_btn = ttk.Button(lf1, text="开始录屏(最长180秒)",
                                  command=self.start_record)
        self.rec_btn.pack(side="left", padx=3)
        self.rec_stop_btn = ttk.Button(lf1, text="停止录屏并拉回本地",
                                       command=self.stop_record,
                                       state="disabled")
        self.rec_stop_btn.pack(side="left", padx=3)
        ttk.Label(lf1, text="（保存到输出目录 out\\，截图自动校验完整性）",
                  foreground="#888").pack(side="left", padx=6)

        # ---- 前台应用 / 包资源 ----
        lf2 = ttk.LabelFrame(parent, text="应用资源", padding=6)
        lf2.pack(fill="x", pady=(0, 6))
        ttk.Label(lf2, text="包名：").pack(side="left")
        self.pkg_var = tk.StringVar()
        ttk.Entry(lf2, textvariable=self.pkg_var, width=34).pack(
            side="left", padx=4, fill="x", expand=True)
        ttk.Button(lf2, text="取前台包名", command=self.current_pkg).pack(
            side="left", padx=2)
        ttk.Button(lf2, text="查看该包内存占用", command=self.meminfo).pack(
            side="left", padx=2)

        body = ttk.Frame(parent)
        body.pack(fill="both", expand=True)

        out = ttk.LabelFrame(body, text="输出结果", padding=4)
        out.pack(side="left", fill="both", expand=True)
        self.txt = scrolledtext.ScrolledText(
            out, height=14, wrap="none", font=("Consolas", 10),
            bg="#1e1e1e", fg="#dcdcdc", insertbackground="#dcdcdc")
        self.txt.pack(fill="both", expand=True)

        pv = ttk.LabelFrame(body, text="截图预览", padding=6)
        pv.pack(side="right", fill="y", padx=(8, 0))
        self.cap_label = ttk.Label(pv, text="（暂无截图）")
        self.cap_label.pack()
        self.cap_tip = tk.StringVar(value="")
        ttk.Label(pv, textvariable=self.cap_tip, foreground="#888",
                  wraplength=200).pack(pady=(4, 0))
        ttk.Button(pv, text="打开这张图",
                   command=self.open_last_cap).pack(pady=(6, 0))
        ttk.Button(pv, text="打开输出目录",
                   command=lambda: self.app.open_dir(self.app.out_dir)).pack(pady=2)

    def _out(self, t):
        self.app.set_text(self.txt, t)

    # ---------- 截图 ----------
    def screenshot(self):
        d = self.app.cur_dev()
        if not d:
            return

        def work():
            for attempt in (1, 2, 3):
                st = self.app.dev_state(d)
                if st == "unauthorized":
                    self.app.log("设备未授权：请在手机上点「允许 USB 调试」后重试。")
                    return
                if st in ("offline", None):
                    self.app.log("设备 %s（第 %d 次），尝试 reconnect…"
                                 % (st or "已消失", attempt))
                    self.app.adb.run(["reconnect"], d, timeout=25)
                    time.sleep(3)
                    continue

                data, how = capture_png(self.app.adb, d, self.app.out_dir)
                if data:
                    path = os.path.join(self.app.out_dir,
                                        "screencap_%s.png" % ts())
                    with open(path, "wb") as f:
                        f.write(data)
                    self.last_cap = path
                    self.app.log("截图已保存：%s (%d 字节，方式：%s)"
                                 % (path, len(data), how))
                    self.app.call(lambda p=path: self.show_preview(p))
                    # 黑屏检测：熄屏/锁屏时截到纯黑图，明确提示避免误判
                    if screen_off(self.app.adb, d):
                        self.app.log("注意：设备屏幕当前熄灭，这张截图很可能是纯黑。"
                                     "点亮屏幕后重截即可。")
                    elif looks_blank(data):
                        self.app.log("提示：截图疑似纯色/空白画面（可能锁屏或未点亮）。")
                    return
                self.app.log("第 %d 次截图失败：%s" % (attempt, how))
                time.sleep(2)
            self.app.log("三次都失败了。常见原因：USB 线接触不良、手机切成了"
                         "「仅充电」模式、USB 调试被关闭、adb server 卡死。")
        self.app.async_run(work)

    def show_preview(self, path):
        """主线程调用：显示缩略图。Tk 的 PhotoImage 原生支持 PNG，无需 PIL。"""
        try:
            img = tk.PhotoImage(file=path)
            w, h = img.width(), img.height()
            k = max(1, max(w // 220, h // 320))
            if k > 1:
                img = img.subsample(k, k)
            self.cap_img = img
            self.cap_label.configure(image=img, text="")
            self.cap_tip.set("%s\n%dx%d" % (os.path.basename(path), w, h))
        except Exception as e:
            self.cap_label.configure(image="", text="预览失败")
            self.cap_tip.set(repr(e))

    def open_last_cap(self):
        if self.last_cap and os.path.isfile(self.last_cap):
            self.app.open_dir(self.last_cap)
        else:
            self.app.log("还没有截图。")

    # ---------- 录屏 ----------
    def start_record(self):
        d = self.app.cur_dev()
        if not d:
            return
        if self.recording:
            self.app.log("录屏已在进行中。")
            return
        if self.app.dev_state(d) != "device":
            self.app.log("设备不可用，无法录屏。")
            return
        self.recording = True
        self._rec_dev = d
        dev_path = "/sdcard/pyer6343_rec_%s.mp4" % ts()
        cmd = self.app.adb.base(d) + [
            "shell", "screenrecord", "--time-limit", str(RECORD_MAX_SECS),
            dev_path]
        self.app.call(lambda: self._set_rec_ui(True))

        def work():
            try:
                proc = subprocess.Popen(
                    cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                    text=True, encoding="utf-8", errors="replace",
                    startupinfo=startupinfo(), creationflags=CREATE_NO_WINDOW)
            except Exception as e:
                self.recording = False
                self.app.call(lambda: self._set_rec_ui(False))
                self.app.log("录屏启动失败：%r" % e)
                return
            self.rec_proc = proc
            self.app.log("录屏已开始（最长 %d 秒），可随时点「停止录屏」"
                         "，结束后自动拉回本地。" % RECORD_MAX_SECS)
            proc.wait()   # 设备端结束（到时/被杀）后返回
            self.rec_proc = None
            time.sleep(1)  # 等设备端把文件收尾
            local = os.path.join(self.app.out_dir, "screenrecord_%s.mp4" % ts())
            rc, out, err = self.app.adb.run(["pull", dev_path, local],
                                            d, timeout=300)
            self.app.adb.shell(["rm", "-f", dev_path], d, timeout=20)
            if os.path.isfile(local) and os.path.getsize(local) > 0:
                self.app.log("录屏已保存：%s（%d 字节）"
                             % (local, os.path.getsize(local)))
            else:
                self.app.log("录屏拉取失败：%s" % ((out or err).strip()[:200]))
            self.recording = False
            self.app.call(lambda: self._set_rec_ui(False))
        threading.Thread(target=work, daemon=True).start()

    def stop_record(self):
        if not self.recording:
            self.app.log("当前没有在录屏。")
            return

        def work():
            # 向设备端 screenrecord 发 SIGINT，让它正常收尾写入 mp4 尾部
            self.app.log("正在停止录屏…")
            self.app.adb.shell(["pkill", "-l", "2", "screenrecord"],
                               self._rec_dev, timeout=15)
            self.app.adb.shell(
                "kill -2 $(pidof screenrecord)", self._rec_dev, timeout=15)
        self.app.async_run(work)

    def _set_rec_ui(self, running):
        self.rec_btn.configure(state="normal" if not running else "disabled")
        self.rec_stop_btn.configure(state="normal" if running else "disabled")

    # ---------- 前台 / 内存 ----------
    def current_pkg(self):
        d = self.app.cur_dev()
        if not d:
            return

        def work():
            pkg, act, how = foreground_activity(self.app.adb, d)
            if pkg:
                self.app.log("当前前台：%s / %s（来源：%s）" % (pkg, act, how))
                self.app.set_var(self.pkg_var, pkg)
                self._out("包名    : %s\nActivity: %s\n来源    : %s"
                          % (pkg, act, how))
            else:
                self.app.log("没解析到前台 Activity。%s" % how)
                self._out(how)
        self.app.async_run(work)

    def meminfo(self):
        d = self.app.cur_dev()
        p = self.pkg_var.get().strip()
        if not (d and p):
            self.app.log("先填包名，或点「取前台包名」。")
            return

        def work():
            rc, out, err = self.app.adb.shell(["dumpsys", "meminfo", p],
                                              d, timeout=60)
            txt = (out or err).strip()
            keep = [l.rstrip() for l in txt.splitlines()
                    if re.search(r"TOTAL|TOTAL PSS|Native Heap|Dalvik Heap|"
                                 r"Graphics|Java Heap", l)]
            self._out("$ dumpsys meminfo %s\n\n== 关键行 ==\n%s\n\n"
                      "== 完整输出（前 80 行）==\n%s"
                      % (p, "\n".join(keep[:10]), "\n".join(txt.splitlines()[:80])))
            self.app.log("已查询 %s 的内存占用。" % p)
        self.app.async_run(work)
