# -*- coding: utf-8 -*-
"""pyer6343 功能验证：真机 + 模拟器 两端跑通核心功能（不执行重启/卸载等破坏性操作）。

走的是应用自身的 adb_core 代码路径，验证真实可用性。
"""
import os
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src"))

from adb_core import (Adb, capture_png, find_adb, foreground_activity,  # noqa: E402
                      looks_blank, png_ok, resolve_activity, screen_off, ts)

OUT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "out")
os.makedirs(OUT, exist_ok=True)

# USB 通道 dm7d75fqory5izhy 当前物理掉线(offline)，改用同一台真机的 WiFi 通道
REAL = "192.168.1.101:5555"   # 真机（同一台 21091116C，经 WiFi）
EMU = "127.0.0.1:16384"       # MuMu 模拟器

adb = Adb(find_adb())
FAIL = []


def check(name, cond, extra=""):
    print(("    [OK]   " if cond else "    [FAIL] ") + name + ("  " + extra if extra else ""))
    if not cond:
        FAIL.append("%s|%s" % (CUR[0], name))


CUR = ["", ""]


def sh(serial, cmd, timeout=60):
    rc, out, err = adb.shell(cmd, serial, timeout=timeout)
    return rc, (out or "").strip(), (err or "").strip()


def section(t):
    print("\n" + "-" * 60)
    print(t)
    print("-" * 60)


def verify(serial, tag):
    CUR[0] = tag
    section("设备 %s（%s）" % (serial, tag))
    st = adb.state(serial)
    check("设备在线 (state=device)", st == "device", "实际=%s" % st)
    if st != "device":
        return

    # 1. 设备信息
    m = sh(serial, "getprop ro.product.model")[1]
    r = sh(serial, "getprop ro.build.version.release")[1]
    sz = sh(serial, "wm size")[1]
    den = sh(serial, "wm density")[1]
    print("    型号=%s  安卓=%s  分辨率=%s  密度=%s" % (m, r, sz.replace("\n", " "), den.replace("\n", " ")))
    check("getprop 型号", bool(m))
    check("安卓版本", bool(r))
    check("wm size", "x" in sz)
    check("wm density", bool(den))

    # 2. 电池 / 内存 / CPU / IP
    bat = sh(serial, "dumpsys battery")[1]
    check("电池信息", "level" in bat.lower())
    mem = sh(serial, "cat /proc/meminfo")[1]
    check("内存 meminfo", "MemTotal" in mem)
    top = sh(serial, ["top", "-n", "1"])[1]
    if not top:
        top = sh(serial, "dumpsys cpuinfo")[1]
    check("CPU 占用", bool(top))
    ip = sh(serial, "ip addr show wlan0")[1] or sh(serial, "ifconfig wlan0")[1]
    check("IP 地址（可为空=未连WiFi）", True, (ip.split("inet")[1][:20] if "inet" in ip else "无"))

    # 3. 交互 shell（带管道，验证转义没被吃掉）
    rc, out, _ = sh(serial, "dumpsys battery | grep -m1 level")
    check("shell 管道命令可用", "level" in out.lower(), out[:40])

    # 4. 前台包名回退链
    pkg, act, how = foreground_activity(adb, serial)
    check("前台包名解析", bool(pkg), "%s / %s  <- %s" % (pkg, act, how))

    # 5. 应用列表 + 启动入口解析
    rc, out, _ = sh(serial, "pm list packages -3", 40)
    pkgs = [l.replace("package:", "").strip() for l in out.splitlines() if l.strip()]
    check("第三方应用列表", len(pkgs) > 0, "共 %d 个" % len(pkgs))
    if pkg:
        act2 = resolve_activity(adb, serial, pkg)
        check("resolve-activity 入口解析", bool(act2), act2 or "空")
        if act2:
            rc, o2, e2 = sh(serial, ["am", "start", "-n", act2], 40)
            txt = (o2 + e2).strip()
            check("am start 输出可读", rc == 0 and "Error" not in txt, txt[:60].replace("\n", " "))

    # 6. 截图（含 PNG 完整性 + 黑屏检测）
    data, how = capture_png(adb, serial, OUT)
    check("截图抓取", bool(data), how)
    if data:
        ok, why = png_ok(data)
        check("截图 PNG 完整性校验", ok, "%s（%d 字节）" % (why, len(data)))
        check("黑屏/空白检测可用", True,
              "熄屏=%s 疑似空白=%s" % (screen_off(adb, serial), looks_blank(data)))
        p = os.path.join(OUT, "verify_%s_%s.png" % (tag, ts()))
        with open(p, "wb") as f:
            f.write(data)
        print("    已保存: %s" % p)

    # 7. 日志抓取 3 秒
    import subprocess
    from adb_core import CREATE_NO_WINDOW, startupinfo
    cmd = adb.base(serial) + ["logcat", "-v", "threadtime", "-t", "200"]
    try:
        pr = subprocess.run(cmd, capture_output=True, timeout=40,
                            startupinfo=startupinfo(), creationflags=CREATE_NO_WINDOW)
        lines = (pr.stdout or b"").decode("utf-8", "replace").splitlines()
        check("日志抓取", len(lines) > 0, "%d 行" % len(lines))
    except Exception as e:
        check("日志抓取", False, repr(e)[:60])

    # 8. push / pull 往返
    local = os.path.join(OUT, "verify_%s.txt" % tag)
    with open(local, "w", encoding="utf-8") as f:
        f.write("pyer6343 push/pull test %s\n" % ts())
    dev_path = "/sdcard/pyer6343_verify_%s.txt" % tag
    rc, o, e = adb.run(["push", local, dev_path], serial, timeout=120)
    check("push 到设备", rc == 0 and "1 file pushed" in (o + e), (o or e).strip()[:50])
    back = os.path.join(OUT, "verify_back_%s.txt" % tag)
    rc, o, e = adb.run(["pull", dev_path, back], serial, timeout=120)
    check("pull 回本地", os.path.isfile(back) and os.path.getsize(back) > 0,
          "%s 字节" % (os.path.getsize(back) if os.path.isfile(back) else 0))
    adb.shell(["rm", "-f", dev_path], serial, timeout=20)

    # 9. 指定包资源
    if pkg:
        rc, out, _ = sh(serial, ["dumpsys", "meminfo", pkg], 60)
        check("dumpsys meminfo 包资源", "TOTAL" in out or bool(out.strip()),
              "%d 字符" % len(out))

    # 10. 录屏 3 秒（验证 screenrecord 可用 + 可拉回）
    rec_dev = "/sdcard/pyer6343_rec_%s.mp4" % ts()
    rc, o, e = adb.run(["shell", "screenrecord", "--time-limit", "3", rec_dev],
                       serial, timeout=60)
    time.sleep(1)
    rec_local = os.path.join(OUT, "verify_rec_%s.mp4" % tag)
    rc2, o2, e2 = adb.run(["pull", rec_dev, rec_local], serial, timeout=120)
    adb.shell(["rm", "-f", rec_dev], serial, timeout=20)
    size = os.path.getsize(rec_local) if os.path.isfile(rec_local) else 0
    check("录屏 + 拉回本地", size > 0, "%d 字节" % size)


print("=" * 60)
print("pyer6343 功能验证（真机 + 模拟器）")
print("=" * 60)
verify(REAL, "real")
verify(EMU, "emu")

print("\n" + "=" * 60)
print("结果：%s（失败 %d 项）" % ("全部通过" if not FAIL else "存在问题", len(FAIL)))
for f in FAIL:
    print("  - " + f)
sys.exit(1 if FAIL else 0)
