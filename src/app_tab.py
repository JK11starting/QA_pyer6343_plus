# -*- coding: utf-8 -*-
"""pyer6343 - 应用管理页签。

安装/覆盖安装/卸载/保留数据卸载/第三方包列表/启动应用/强制停止/清除数据。
"""

import os
import re
import tkinter as tk
from tkinter import filedialog, messagebox, scrolledtext, ttk

from adb_core import foreground_activity, resolve_activity


class AppTab:
    def __init__(self, app, parent):
        self.app = app

        r1 = ttk.Frame(parent)
        r1.pack(fill="x", pady=4)
        ttk.Label(r1, text="包名：").pack(side="left")
        self.pkg_var = tk.StringVar()
        ttk.Entry(r1, textvariable=self.pkg_var, width=38).pack(
            side="left", padx=4, fill="x", expand=True)
        ttk.Button(r1, text="取当前前台应用",
                   command=self.current_pkg).pack(side="left", padx=2)
        ttk.Button(r1, text="列出第三方应用",
                   command=self.list_pkg3).pack(side="left", padx=2)

        r2 = ttk.Frame(parent)
        r2.pack(fill="x", pady=4)
        for t, c in (("启动应用", self.start_app),
                     ("强制停止", self.stop_app),
                     ("清除数据", self.clear_app),
                     ("版本信息", self.app_version)):
            ttk.Button(r2, text=t, command=c).pack(side="left", padx=3)

        r3 = ttk.Frame(parent)
        r3.pack(fill="x", pady=4)
        ttk.Button(r3, text="选择 APK 并安装",
                   command=lambda: self.install_apk(keep_data=False)).pack(
            side="left", padx=3)
        ttk.Button(r3, text="覆盖安装保留数据(-r)",
                   command=lambda: self.install_apk(keep_data=True)).pack(
            side="left", padx=3)

        r4 = ttk.Frame(parent)
        r4.pack(fill="x", pady=4)
        ttk.Button(r4, text="卸载", command=self.uninstall_app).pack(
            side="left", padx=3)
        ttk.Button(r4, text="卸载但保留数据和缓存(-k)",
                   command=self.uninstall_keep_app).pack(side="left", padx=3)

        out = ttk.LabelFrame(parent, text="输出结果", padding=4)
        out.pack(fill="both", expand=True, pady=(6, 0))
        self.txt = scrolledtext.ScrolledText(
            out, height=16, wrap="none", font=("Consolas", 10),
            bg="#1e1e1e", fg="#dcdcdc", insertbackground="#dcdcdc")
        self.txt.pack(fill="both", expand=True)

    def _out(self, t):
        self.app.set_text(self.txt, t)

    def _pkg(self):
        p = self.pkg_var.get().strip()
        if not p:
            messagebox.showwarning("缺包名", "先填包名，或点「取当前前台应用」。")
            return None
        return p

    # ---------- 查询 ----------
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

    def list_pkg3(self):
        d = self.app.cur_dev()
        if not d:
            return

        def work():
            rc, out, err = self.app.adb.shell("pm list packages -3", d, timeout=40)
            pkgs = sorted(l.replace("package:", "").strip()
                          for l in (out or "").splitlines() if l.strip())
            self.app.log("第三方应用共 %d 个。" % len(pkgs))
            self._out("\n".join(pkgs))
        self.app.async_run(work)

    def app_version(self):
        d = self.app.cur_dev()
        p = self._pkg()
        if not (d and p):
            return

        def work():
            rc, out, err = self.app.adb.shell(["dumpsys", "package", p],
                                              d, timeout=40)
            vn = re.search(r"versionName=([^\s]+)", out or "")
            vc = re.search(r"versionCode=(\d+)", out or "")
            fp = re.search(r"firstInstallTime=([\d-]+ [\d:]+)", out or "")
            lu = re.search(r"lastUpdateTime=([\d-]+ [\d:]+)", out or "")
            self._out("\n".join([
                "包名        : %s" % p,
                "版本名      : %s" % (vn.group(1) if vn else "-"),
                "版本号      : %s" % (vc.group(1) if vc else "-"),
                "首次安装    : %s" % (fp.group(1) if fp else "-"),
                "最后更新    : %s" % (lu.group(1) if lu else "-")]))
            self.app.log("已查询 %s 版本信息" % p)
        self.app.async_run(work)

    # ---------- 启动 / 停止 / 清数据 ----------
    def start_app(self):
        d = self.app.cur_dev()
        p = self._pkg()
        if not (d and p):
            return

        def work():
            # 优先 resolve-activity + am start：输出干净可读。
            # monkey 在不少 ROM 上输出全是噪音，且部分定制系统没有 monkey.jar，
            # 故仅作回退。
            act = resolve_activity(self.app.adb, d, p)
            if act:
                rc, out, err = self.app.adb.shell(["am", "start", "-n", act],
                                                  d, timeout=40)
                txt = (out or err or "").strip()
                if rc == 0 and "Error" not in txt:
                    self.app.log("已启动：%s\n%s" % (act, txt[-600:]))
                    return
                self.app.log("am start 失败，回退 monkey：%s" % txt[-300:])
            else:
                self.app.log("resolve-activity 未取到入口，回退 monkey。")
            rc, out, err = self.app.adb.shell(
                ["monkey", "-p", p, "-c", "android.intent.category.LAUNCHER", "1"],
                d, timeout=60)
            txt = (out or err or "").strip()
            inj = re.search(r"Events injected:\s*(\d+)", txt)
            if inj:
                self.app.log("已启动 %s（monkey 注入 %s 个事件）" % (p, inj.group(1)))
            else:
                self.app.log(txt[-800:] or "启动完成")
        self.app.async_run(work)

    def stop_app(self):
        d = self.app.cur_dev()
        p = self._pkg()
        if not (d and p):
            return

        def work():
            rc, out, err = self.app.adb.shell(["am", "force-stop", p],
                                              d, timeout=30)
            self.app.log((out or err or "已强制停止 " + p).strip())
        self.app.async_run(work)

    def clear_app(self):
        d = self.app.cur_dev()
        p = self._pkg()
        if not (d and p):
            return
        if not messagebox.askyesno("确认", "清除 %s 的全部数据？" % p):
            return

        def work():
            rc, out, err = self.app.adb.shell(["pm", "clear", p], d, timeout=40)
            self.app.log((out or err or "已清除").strip())
        self.app.async_run(work)

    # ---------- 安装 / 卸载 ----------
    def install_apk(self, keep_data):
        d = self.app.cur_dev()
        if not d:
            return
        path = filedialog.askopenfilename(
            title="选择 APK", initialdir=self.app.out_dir,
            filetypes=[("APK 文件", "*.apk"), ("所有文件", "*.*")])
        if not path:
            return
        # -r = 覆盖安装并保留数据；普通安装不加参数
        args = (["install", "-r"] if keep_data else ["install"]) + [path]

        def work():
            self.app.log("安装中：%s（%s）"
                         % (os.path.basename(path),
                            "覆盖安装 -r" if keep_data else "全新安装"))
            rc, out, err = self.app.adb.run(args, d, timeout=600)
            txt = (out or err or "").strip()
            self.app.log(txt or "安装流程结束（rc=%d）" % rc)
            if rc == 0 and ("Success" in txt or "成功" in txt):
                self._out("安装成功：%s\n%s" % (os.path.basename(path), txt))
            else:
                self._out("安装结果（rc=%d）：\n%s" % (rc, txt or "无输出"))
        self.app.async_run(work)

    def uninstall_app(self):
        self._uninstall(keep_cache=False)

    def uninstall_keep_app(self):
        self._uninstall(keep_cache=True)

    def _uninstall(self, keep_cache):
        d = self.app.cur_dev()
        p = self._pkg()
        if not (d and p):
            return
        if keep_cache:
            if not messagebox.askyesno(
                    "确认",
                    "卸载 %s 但保留数据和缓存目录？\n"
                    "（卸载后应用图标会消失，残留 /data/data 与 "
                    "/sdcard/Android/data，重装可恢复）" % p):
                return
        else:
            if not messagebox.askyesno("确认", "确定卸载 %s ？" % p):
                return

        def work():
            # Android 13+ 的 adb uninstall -k 已弃用，会直接提示改用
            # cmd package uninstall -k；老版本用 cmd package 也通用。
            if keep_cache:
                args = ["shell", "cmd", "package", "uninstall", "-k", p]
                label = "cmd package uninstall -k"
            else:
                args = ["uninstall", p]
                label = "adb uninstall"
            rc, out, err = self.app.adb.run(args, d, timeout=90)
            txt = (out or err or "").strip()
            self.app.log(txt or "已卸载")
            self._out("卸载结果（%s，rc=%d）：\n%s"
                      % (label, rc, txt or "无输出"))
        self.app.async_run(work)
