# -*- coding: utf-8 -*-
"""pyer6343 冒烟测试：纯逻辑校验 + GUI 启动/销毁（不执行任何破坏性 adb 命令）。"""
import os
import sys
import traceback

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src"))

from adb_core import Adb, find_adb, find_tool, png_ok, looks_blank, tool_usable  # noqa: E402

FAIL = []


def check(name, cond, extra=""):
    print(("  [OK]   " if cond else "  [FAIL] ") + name + ("  " + extra if extra else ""))
    if not cond:
        FAIL.append(name)


print("== 1. 纯逻辑：PNG 校验 ==")
REAL_PNG = r"D:\adb\QA_toolsV1.0.3.2.0217\screencap.png"
if os.path.isfile(REAL_PNG):
    with open(REAL_PNG, "rb") as f:
        data = f.read()
    ok, why = png_ok(data)
    check("完整 PNG 校验通过（真实截图 %d 字节）" % len(data), ok, why)
    check("真实截图不被判为空白画面", not looks_blank(data))
else:
    print("  [跳过] 找不到样本截图")

import struct  # noqa: E402
import zlib  # noqa: E402

w = h = 2


def chunk(typ, body):
    return (struct.pack(">I", len(body)) + typ + body
            + struct.pack(">I", zlib.crc32(typ + body) & 0xFFFFFFFF))


raw = b"\x00" + b"\x7f\x7f\x7f" * w
raw += b"\x00" + b"\x7f\x7f\x7f" * w
mini = (b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0))
        + chunk(b"IDAT", zlib.compress(raw))
        + chunk(b"IEND", b""))
ok, why = png_ok(mini)
check("手工构造的最小合法 PNG 通过", ok, why)
trunc = mini[:len(mini) - 6]
ok2, why2 = png_ok(trunc)
check("截断 PNG 被判为不完整", not ok2, why2)
check("非 PNG 数据被拒绝", not png_ok(b"hello world" * 10)[0])

print("\n== 2. 工具查找 ==")
adb = find_adb()
check("找到 adb.exe", os.path.isfile(adb), adb)
aapt = find_tool("aapt.exe")
print("  aapt: %s (可用=%s)" % (aapt, tool_usable(aapt, "version") if aapt else False))
fb = find_tool("fastboot.exe")
print("  fastboot: %s" % fb)

print("\n== 3. adb 封装（只跑安全命令）==")
a = Adb(adb)
print("  version: %s" % a.version())
devs = a.devices()
print("  devices: %d 台" % len(devs))
for d in devs:
    print("    %-24s %-12s %s" % (d["serial"], d["state"], d["label"]))

print("\n== 4. GUI 启动 / 运行 / 销毁 ==")
try:
    import tkinter as tk
    import main as app_main

    root = tk.Tk()
    root.withdraw()  # 不弹窗，避免干扰
    err = []

    def tk_error(*args):
        err.append(args)

    root.report_callback_exception = lambda *a: err.append(a)
    app = app_main.App(root)
    ticks = {"n": 0}

    def pump():
        ticks["n"] += 1
        if ticks["n"] >= 60:  # 60 * 80ms ≈ 5s
            root.quit()
            return
        root.after(80, pump)

    root.after(200, pump)
    root.mainloop()
    try:
        root.destroy()
    except Exception:
        pass
    check("GUI 构建 + 事件循环运行 5 秒无异常", not err,
          ("异常: %r" % err[:2]) if err else "")
    check("drain 心跳正常（说明主线程队列在消费）", ticks["n"] >= 60)
except Exception:
    traceback.print_exc()
    FAIL.append("GUI 启动")

print("\n" + ("=" * 46))
print("结果：%s（失败 %d 项）" % ("全部通过" if not FAIL else "存在问题", len(FAIL)))
for f in FAIL:
    print("  - " + f)
sys.exit(1 if FAIL else 0)
