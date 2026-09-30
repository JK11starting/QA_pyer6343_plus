# -*- coding: utf-8 -*-
"""pyer6343 - 设备信息查询页签。

getprop（重点属性置顶）/ CPU+内存 / 电池 / 分辨率 / 密度 / IP。
"""

import re
from tkinter import scrolledtext, ttk

# getprop 重点属性（置顶展示）
KEY_PROPS = (
    ("ro.product.model", "型号"),
    ("ro.product.brand", "品牌"),
    ("ro.product.device", "设备代号"),
    ("ro.build.version.release", "安卓版本"),
    ("ro.build.version.sdk", "SDK 版本"),
    ("ro.build.display.id", "ROM 版本"),
    ("ro.product.cpu.abi", "CPU 架构"),
    ("ro.serialno", "序列号"),
)

MEM_KEYS = ("MemTotal", "MemFree", "MemAvailable", "Buffers", "Cached",
            "SwapTotal", "SwapFree")


class InfoTab:
    def __init__(self, app, parent):
        self.app = app

        row1 = ttk.Frame(parent)
        row1.pack(fill="x", pady=4)
        ttk.Button(row1, text="系统属性(getprop)", command=self.getprop).pack(
            side="left", padx=3)
        ttk.Button(row1, text="CPU/内存使用", command=self.cpu_mem).pack(
            side="left", padx=3)
        ttk.Button(row1, text="电池状态", command=self.battery).pack(
            side="left", padx=3)

        row2 = ttk.Frame(parent)
        row2.pack(fill="x", pady=4)
        ttk.Button(row2, text="屏幕分辨率(wm size)", command=self.wm_size).pack(
            side="left", padx=3)
        ttk.Button(row2, text="屏幕密度(wm density)",
                   command=self.wm_density).pack(side="left", padx=3)
        ttk.Button(row2, text="设备 IP 地址", command=self.ip_info).pack(
            side="left", padx=3)

        out = ttk.LabelFrame(parent, text="输出结果", padding=4)
        out.pack(fill="both", expand=True)
        self.txt = scrolledtext.ScrolledText(
            out, height=18, wrap="none", font=("Consolas", 10),
            bg="#1e1e1e", fg="#dcdcdc", insertbackground="#dcdcdc")
        self.txt.pack(fill="both", expand=True)

    def _out(self, t):
        self.app.set_text(self.txt, t)

    # ---------- 系统属性 ----------
    def getprop(self):
        d = self.app.cur_dev()
        if not d:
            return

        def work():
            rc, out, err = self.app.adb.shell("getprop", d, timeout=40)
            props, order = {}, []
            for line in (out or "").splitlines():
                m = re.match(r"\[([^\]]*)\]:\s*\[(.*)\]", line.strip())
                if m:
                    props[m.group(1)] = m.group(2)
                    order.append(m.group(1))
            lines = ["== 重点属性 =="]
            for k, name in KEY_PROPS:
                lines.append("%-30s %-8s %s" % (k, name, props.get(k, "-")))
            lines.append("")
            lines.append("== 全部属性（共 %d 条）==" % len(order))
            for k in order:
                lines.append("%-32s %s" % (k, props[k]))
            self._out("\n".join(lines))
            self.app.log("getprop 完成：共 %d 条属性。" % len(order))
        self.app.async_run(work)

    # ---------- CPU / 内存 ----------
    def cpu_mem(self):
        d = self.app.cur_dev()
        if not d:
            return

        def work():
            lines = []
            rc, out, err = self.app.adb.shell(["top", "-n", "1"], d, timeout=60)
            txt = (out or "").strip()
            if txt:
                lines.append("== CPU 占用（top -n 1，前 22 行）==")
                lines += txt.splitlines()[:22]
            else:
                # 回退：部分 ROM 的 top 不可用或参数不同
                rc, out, err = self.app.adb.shell("dumpsys cpuinfo", d, timeout=60)
                txt = (out or "").strip()
                lines.append("== CPU 占用（dumpsys cpuinfo 摘要）==")
                lines += [l for l in txt.splitlines()
                          if re.match(r"\s*\d+(\.\d+)?%", l)][:22]
            lines.append("")

            rc, out, err = self.app.adb.shell("cat /proc/meminfo", d, timeout=30)
            lines.append("== 内存（/proc/meminfo 摘要）==")
            found = False
            for key in MEM_KEYS:
                m = re.search(key + r":\s+(\d+) kB", out or "")
                if m:
                    found = True
                    lines.append("  %-14s %.2f GB" % (key, int(m.group(1)) / 1048576))
            if not found:
                lines.append("  （未取到 meminfo：%s）" % (err or "").strip()[:120])
            self._out("\n".join(lines))
            self.app.log("CPU/内存信息已刷新。")
        self.app.async_run(work)

    # ---------- 电池 ----------
    def battery(self):
        d = self.app.cur_dev()
        if not d:
            return

        def work():
            rc, out, err = self.app.adb.shell("dumpsys battery", d, timeout=30)
            keep = [l.strip() for l in (out or err).splitlines()
                    if re.search(r"level|scale|status|health|plugged|"
                                 r"temperature|voltage|powered|Charge counter",
                                 l, re.I)]
            self._out("$ dumpsys battery\n" + "\n".join(keep))
            self.app.log("电池信息：\n  " + "\n  ".join(keep[:12]))
        self.app.async_run(work)

    # ---------- 分辨率 / 密度 ----------
    def wm_size(self):
        d = self.app.cur_dev()
        if not d:
            return

        def work():
            rc, out, err = self.app.adb.shell("wm size", d, timeout=25)
            txt = (out or err).strip()
            self._out("$ wm size\n%s" % txt)
            self.app.log("分辨率：%s" % txt.replace("\n", " | "))
        self.app.async_run(work)

    def wm_density(self):
        d = self.app.cur_dev()
        if not d:
            return

        def work():
            rc, out, err = self.app.adb.shell("wm density", d, timeout=25)
            txt = (out or err).strip()
            self._out("$ wm density\n%s" % txt)
            self.app.log("屏幕密度：%s" % txt.replace("\n", " | "))
        self.app.async_run(work)

    # ---------- IP ----------
    def ip_info(self):
        d = self.app.cur_dev()
        if not d:
            return

        def work():
            lines = []
            ip = None
            for cmd in ("ip addr show wlan0", "ifconfig wlan0"):
                rc, out, err = self.app.adb.shell(cmd, d, timeout=25)
                txt = (out or "").strip()
                if txt:
                    lines.append("$ %s\n%s" % (cmd, txt[:600]))
                    m = re.search(r"inet\s+(?:addr:)?([\d.]+)/", txt)
                    if m:
                        ip = m.group(1)
                        break
            if ip:
                lines.insert(0, "设备 IP（wlan0）：%s" % ip)
                self.app.log("设备 IP：%s" % ip)
            else:
                lines.insert(0, "未取到 wlan0 IP（可能没连 WiFi，或接口名不同）。")
                self.app.log("未取到设备 IP。")
            self._out("\n\n".join(lines))
        self.app.async_run(work)
