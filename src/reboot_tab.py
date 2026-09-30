# -*- coding: utf-8 -*-
"""pyer6343 - 重启控制页签。

普通重启 / 恢复模式 / 引导模式 / Fastboot 模式，外加 fastboot devices 查询。
"""

import subprocess
from tkinter import messagebox, scrolledtext, ttk

from adb_core import (CREATE_NO_WINDOW, TOOLS_DIR_HINT, find_tool,
                      startupinfo, tool_usable)

MODES = (
    ("重启设备\n(adb reboot)", ["reboot"],
     "普通重启"),
    ("进入恢复模式\n(reboot recovery)", ["reboot", "recovery"],
     "Recovery 模式（刷机/清除缓存）"),
    ("进入引导模式\n(reboot bootloader)", ["reboot", "bootloader"],
     "Bootloader/引导模式（fastboot 刷引导）"),
    ("进入 Fastboot\n(reboot fastboot)", ["reboot", "fastboot"],
     "Fastbootd 模式（刷系统分区）"),
)


class RebootTab:
    def __init__(self, app, parent):
        self.app = app

        lf = ttk.LabelFrame(parent, text="重启控制（危险操作，均有确认提示）", padding=8)
        lf.pack(fill="x", pady=(0, 6))
        for i, (title, args, desc) in enumerate(MODES):
            btn = ttk.Button(lf, text=title, width=20,
                             command=lambda a=args: self.confirm_reboot(a))
            btn.grid(row=i // 2, column=i % 2, padx=6, pady=5, sticky="w")
            ttk.Label(lf, text=desc, foreground="#888").grid(
                row=i // 2, column=2 if i % 2 == 0 else 3,
                padx=6, pady=5, sticky="w")
        lf.columnconfigure(4, weight=1)

        lf2 = ttk.LabelFrame(parent, text="Fastboot（需设备已进入 bootloader/fastboot 模式）",
                             padding=6)
        lf2.pack(fill="x", pady=(0, 6))
        ttk.Label(lf2, text="fastboot.exe 路径自动从工具包查找。若设备已进入 "
                           "bootloader，本页「进入引导模式」不可用（adb 已断开），"
                           "直接用下面的查询。").pack(side="top", anchor="w")
        row = ttk.Frame(lf2)
        row.pack(fill="x", pady=4)
        ttk.Button(row, text="fastboot devices",
                   command=self.fastboot_devices).pack(side="left", padx=3)
        ttk.Label(row, text="（进阶刷机命令请自行在命令行使用 fastboot.exe）",
                  foreground="#888").pack(side="left", padx=8)

        out = ttk.LabelFrame(parent, text="输出结果", padding=4)
        out.pack(fill="both", expand=True)
        self.txt = scrolledtext.ScrolledText(
            out, height=12, wrap="none", font=("Consolas", 10),
            bg="#1e1e1e", fg="#dcdcdc", insertbackground="#dcdcdc")
        self.txt.pack(fill="both", expand=True)

    def _out(self, t):
        self.app.set_text(self.txt, t)

    def confirm_reboot(self, args):
        d = self.app.cur_dev()
        if not d:
            return
        title = " -> ".join(args)
        if not messagebox.askyesno(
                "确认重启", "确定让设备 %s 执行\n\n    adb %s\n\n？"
                % (d, title)):
            return

        def work():
            rc, out, err = self.app.adb.run(args, d, timeout=60)
            self.app.log("%s：%s" % (title, (out or err).strip()
                                     or "指令已发送（设备将断开重启）"))
            self._out("$ adb -s %s %s\n%s" % (d, " ".join(args),
                                               (out or err).strip()
                                               or "指令已发送。"))
            self.app.refresh_devices(silent=True)
        self.app.async_run(work)

    def fastboot_devices(self):
        fb = find_tool("fastboot.exe")
        if not fb:
            self.app.log("没找到 fastboot.exe（应在工具包目录：%s）" % TOOLS_DIR_HINT)
            return
        if not tool_usable(fb, "--help"):
            self.app.log("fastboot.exe 校验不可用，跳过。")
            return

        def work():
            try:
                p = subprocess.run(
                    [fb, "devices"], capture_output=True, timeout=40,
                    startupinfo=startupinfo(), creationflags=CREATE_NO_WINDOW)
                out = (p.stdout or b"").decode("utf-8", "replace")
                err = (p.stderr or b"").decode("utf-8", "replace")
                txt = (out + err).strip() or "（fastboot 下无设备）"
                self.app.log("fastboot devices：\n%s" % txt)
                self._out("$ fastboot devices\n%s" % txt)
            except Exception as e:
                self.app.log("fastboot 执行失败：%r" % e)
        self.app.async_run(work)
