# -*- coding: utf-8 -*-
"""pyer6343 - 文件传输页签（push / pull）。"""

import os
import tkinter as tk
from tkinter import filedialog, scrolledtext, ttk


class FileTab:
    def __init__(self, app, parent):
        self.app = app

        # ---- push ----
        lf1 = ttk.LabelFrame(parent, text="推送本地文件到设备（push）", padding=6)
        lf1.pack(fill="x", pady=(0, 6))
        r1 = ttk.Frame(lf1)
        r1.pack(fill="x", pady=2)
        ttk.Label(r1, text="本地文件：").pack(side="left")
        self.push_src_var = tk.StringVar()
        ttk.Entry(r1, textvariable=self.push_src_var).pack(
            side="left", fill="x", expand=True, padx=4)
        ttk.Button(r1, text="浏览…", command=self.pick_push_src).pack(side="left")

        r2 = ttk.Frame(lf1)
        r2.pack(fill="x", pady=2)
        ttk.Label(r2, text="设备路径：").pack(side="left")
        self.push_dst_var = tk.StringVar(value="/sdcard/")
        ttk.Entry(r2, textvariable=self.push_dst_var, width=42).pack(
            side="left", padx=4)
        ttk.Label(r2, text="（填目录则保持原文件名）",
                  foreground="#888").pack(side="left", padx=4)
        ttk.Button(r2, text="推送到设备", command=self.push_file).pack(
            side="left", padx=8)

        # ---- pull ----
        lf2 = ttk.LabelFrame(parent, text="从设备拉取文件（pull）", padding=6)
        lf2.pack(fill="x", pady=(0, 6))
        r3 = ttk.Frame(lf2)
        r3.pack(fill="x", pady=2)
        ttk.Label(r3, text="设备文件：").pack(side="left")
        self.pull_src_var = tk.StringVar(value="/sdcard/")
        ttk.Entry(r3, textvariable=self.pull_src_var, width=42).pack(
            side="left", padx=4)
        ttk.Label(r3, text="（可以是目录或文件）",
                  foreground="#888").pack(side="left", padx=4)

        r4 = ttk.Frame(lf2)
        r4.pack(fill="x", pady=2)
        ttk.Label(r4, text="保存到：").pack(side="left")
        self.pull_dst_var = tk.StringVar(value=self.app.out_dir)
        ttk.Entry(r4, textvariable=self.pull_dst_var).pack(
            side="left", fill="x", expand=True, padx=4)
        ttk.Button(r4, text="浏览…", command=self.pick_pull_dst).pack(side="left")
        ttk.Button(r4, text="拉取到电脑", command=self.pull_file).pack(
            side="left", padx=8)

        out = ttk.LabelFrame(parent, text="输出结果", padding=4)
        out.pack(fill="both", expand=True)
        self.txt = scrolledtext.ScrolledText(
            out, height=14, wrap="none", font=("Consolas", 10),
            bg="#1e1e1e", fg="#dcdcdc", insertbackground="#dcdcdc")
        self.txt.pack(fill="both", expand=True)

    def _out(self, t):
        self.app.set_text(self.txt, t)

    def pick_push_src(self):
        p = filedialog.askopenfilename(title="选择要推送的文件")
        if p:
            self.push_src_var.set(p)

    def pick_pull_dst(self):
        p = filedialog.askdirectory(title="选择保存目录",
                                    initialdir=self.pull_dst_var.get()
                                    or self.app.out_dir)
        if p:
            self.pull_dst_var.set(p)

    def push_file(self):
        d = self.app.cur_dev()
        if not d:
            return
        src = self.push_src_var.get().strip()
        dst = self.push_dst_var.get().strip() or "/sdcard/"
        if not src or not os.path.isfile(src):
            self.app.log("本地文件不存在：%s" % src)
            return
        # 目标是目录（以 / 结尾）则补上原文件名
        if dst.endswith("/"):
            dst = dst + os.path.basename(src)

        def work():
            self.app.log("push %s -> %s:%s" % (src, d, dst))
            rc, out, err = self.app.adb.run(["push", src, dst], d, timeout=900)
            txt = (out or err or "").strip()
            self.app.log(txt or "已推送到 %s" % dst)
            self._out("$ adb push %s %s\n%s" % (src, dst, txt))
        self.app.async_run(work)

    def pull_file(self):
        d = self.app.cur_dev()
        if not d:
            return
        src = self.pull_src_var.get().strip()
        dst_dir = self.pull_dst_var.get().strip() or self.app.out_dir
        if not src:
            self.app.log("先填设备上的文件路径，例如 /sdcard/xxx.png")
            return
        if not os.path.isdir(dst_dir):
            try:
                os.makedirs(dst_dir, exist_ok=True)
            except Exception as e:
                self.app.log("本地目录无效：%s（%r）" % (dst_dir, e))
                return
        dst = os.path.join(dst_dir, os.path.basename(src.rstrip("/"))) \
            if src.rstrip("/").rpartition("/")[2] else dst_dir

        def work():
            self.app.log("pull %s:%s -> %s" % (d, src, dst))
            rc, out, err = self.app.adb.run(["pull", src, dst], d, timeout=900)
            txt = (out or err or "").strip()
            self.app.log(txt or "已保存到 %s" % dst)
            self._out("$ adb pull %s %s\n%s" % (src, dst, txt))
            if os.path.isfile(dst):
                self.app.log("文件已就位：%s（%d 字节）"
                             % (dst, os.path.getsize(dst)))
        self.app.async_run(work)
