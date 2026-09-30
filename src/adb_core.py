# -*- coding: utf-8 -*-
"""pyer6343 - adb 核心封装模块

包含：
- 外部进程启动参数（隐藏控制台窗口）
- adb / aapt / fastboot 等工具查找与可用性校验
- Adb 命令封装类（run / run_bytes / shell / devices / 设备状态）
- PNG 完整性校验、截图抓取、前台包名解析等底层纯逻辑
"""

import os
import re
import struct
import subprocess
import sys
import zlib
from datetime import datetime

APP_NAME = "pyer6343"
VERSION = "2.0.0"

CREATE_NO_WINDOW = 0x08000000
TOOLS_DIR_HINT = r"D:\adb\QA_toolsV1.0.3.2.0217"

# 快捷预设设备（来自用户需求原文）
EMU_SERIAL = "127.0.0.1:16384"
REAL_SERIAL = "dm7d75fqory5izhy"


def app_dir():
    """程序工作目录：打包成 exe 后取 exe 所在目录；源码运行取项目根目录。"""
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def startupinfo():
    si = subprocess.STARTUPINFO()
    si.dwFlags |= subprocess.STARTF_USESHOWWINDOW
    si.wShowWindow = 0
    return si


def ts():
    return datetime.now().strftime("%Y%m%d_%H%M%S")


def find_adb():
    """查找 adb.exe：默认工具包 -> 程序目录 -> 旧版工具目录 -> PATH。"""
    here = app_dir()
    cands = [
        os.path.join(TOOLS_DIR_HINT, "adb.exe"),
        os.path.join(here, "adb.exe"),
        os.path.join(os.path.dirname(here), "QA_toolsV1.0.3.2.0217", "adb.exe"),
        os.path.join(here, "platform-tools", "adb.exe"),
    ]
    for c in cands:
        if os.path.isfile(c):
            return c
    from shutil import which
    w = which("adb")
    return w or cands[0]


def find_tool(name):
    """查找外部工具（aapt / fastboot / keytool 等）。"""
    for d in (TOOLS_DIR_HINT, app_dir()):
        p = os.path.join(d, name)
        if os.path.isfile(p):
            return p
    from shutil import which
    return which(name)


def tool_usable(path, arg="-help"):
    """验证外部工具真能跑起来（返回码为 0）。
    QA 工具包自带的 keytool.exe 缺 Java 运行时，一跑就崩，必须筛掉。"""
    if not path or not os.path.isfile(path):
        return False
    try:
        p = subprocess.run(
            [path, arg], stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            timeout=25, startupinfo=startupinfo(),
            creationflags=CREATE_NO_WINDOW)
        return p.returncode == 0
    except Exception:
        return False


def png_ok(data):
    """严格校验 PNG 完整性：签名 + 每个块的 CRC + 必须以 IEND 结尾。
    exec-out 在 USB 掉线时会返回被截断的数据，只查文件头会误判为成功。
    返回 (ok, 说明)。"""
    if not data or len(data) < 67 or data[:8] != b"\x89PNG\r\n\x1a\n":
        return False, "不是 PNG"
    i, n = 8, len(data)
    while i + 12 <= n:
        ln = struct.unpack(">I", data[i:i + 4])[0]
        typ = data[i + 4:i + 8]
        if i + 12 + ln > n:
            return False, "数据被截断（缺 %d 字节）" % (i + 12 + ln - n)
        body = data[i + 8:i + 8 + ln]
        crc = struct.unpack(">I", data[i + 8 + ln:i + 12 + ln])[0]
        if zlib.crc32(typ + body) & 0xFFFFFFFF != crc:
            return False, "CRC 校验失败（块 %s）" % typ.decode("latin1", "ignore")
        i += 12 + ln
        if typ == b"IEND":
            if i != n:
                return False, "IEND 之后还有 %d 字节多余数据" % (n - i)
            return True, "完整"
    return False, "缺少 IEND 结束块"


def looks_blank(png):
    """PNG 压缩比极低 -> 画面几乎无内容（纯黑/纯色）。
    正常截图压缩比通常 >2%，全黑屏可低到 0.2%。用于黑屏检测提示。"""
    try:
        if not png or png[:8] != b"\x89PNG\r\n\x1a\n":
            return False
        w, h = struct.unpack(">II", png[16:24])
        if w <= 0 or h <= 0:
            return False
        return (len(png) * 100.0 / (w * h * 4)) < 0.3
    except Exception:
        return False


class Adb:
    """adb 命令封装：所有子进程都在无窗口模式下执行，统一超时与错误提示。"""

    def __init__(self, exe):
        self.exe = exe

    def base(self, serial):
        """构造 [adb, -s, serial] 基础命令。"""
        cmd = [self.exe]
        if serial:
            cmd += ["-s", serial]
        return cmd

    def run(self, args, serial=None, timeout=90):
        """执行 adb 命令，返回 (rc, stdout文本, stderr文本)。"""
        cmd = self.base(serial) + list(args)
        try:
            p = subprocess.run(
                cmd, capture_output=True, timeout=timeout,
                startupinfo=startupinfo(), creationflags=CREATE_NO_WINDOW)
            return (p.returncode,
                    p.stdout.decode("utf-8", "replace"),
                    p.stderr.decode("utf-8", "replace"))
        except subprocess.TimeoutExpired:
            return -1, "", "执行超时（%s 秒）" % timeout
        except FileNotFoundError:
            return -2, "", "找不到 adb：%s" % self.exe
        except Exception as e:
            return -3, "", repr(e)

    def run_bytes(self, args, serial=None, timeout=120):
        """二进制输出执行（截图等），返回 (rc, stdout字节, stderr文本)。"""
        cmd = self.base(serial) + list(args)
        try:
            p = subprocess.run(
                cmd, capture_output=True, timeout=timeout,
                startupinfo=startupinfo(), creationflags=CREATE_NO_WINDOW)
            return p.returncode, p.stdout, p.stderr.decode("utf-8", "replace")
        except Exception as e:
            return -9, b"", repr(e)

    def shell(self, cmd, serial=None, timeout=90):
        """执行 shell 命令，cmd 可为字符串或列表。"""
        return self.run(["shell"] + (cmd if isinstance(cmd, list) else [cmd]),
                        serial, timeout)

    def devices(self):
        """解析 adb devices -l，返回设备 dict 列表（serial/state/model/label）。"""
        rc, out, err = self.run(["devices", "-l"], timeout=30)
        res = []
        for line in (out or "").splitlines():
            line = line.strip()
            if not line or line.lower().startswith("list of devices"):
                continue
            parts = line.split()
            if len(parts) < 2:
                continue
            desc = " ".join(parts[2:])
            m = re.search(r"model:(\S+)", desc)
            model = m.group(1) if m else ""
            prod = re.search(r"product:(\S+)", desc)
            state = parts[1]
            label = parts[0]
            # 状态异常要直接标出来，否则用户不知道为什么命令没反应
            if state != "device":
                label += "  [不可用:%s]" % {
                    "offline": "offline",
                    "unauthorized": "未授权",
                    "recovery": "recovery",
                    "sideload": "sideload",
                }.get(state, state)
            if model:
                label += "  [%s]" % model
            if prod and prod.group(1) != model:
                label += " (%s)" % prod.group(1)
            res.append({"serial": parts[0], "state": state,
                        "desc": desc, "model": model, "label": label})
        return res

    def state(self, serial):
        """查询单个设备的当前状态；不在列表中返回 None。"""
        for d in self.devices():
            if d["serial"] == serial:
                return d["state"]
        return None

    def version(self):
        rc, out, err = self.run(["version"], timeout=20)
        txt = (out or err).strip()
        return txt.splitlines()[0] if txt else "未知"


# ---------------------------------------------------------------------------
# 常用多命令回退链（纯逻辑，便于复用与测试）
# ---------------------------------------------------------------------------

# 取前台应用。不同 Android 版本字段名不同，且 adb shell 里 grep 的多模式
# （'a\|b'）会静默失败，所以这里逐个命令单跑，在 Python 侧做正则。
# 每项 = (shell 命令, 捕获 包名 + activity 的正则)
FG_CMDS = (
    ("dumpsys activity activities | grep -m1 topResumedActivity",
     r"topResumedActivity=ActivityRecord\{[^\s]+\s+[^\s]+\s+([^\s/]+)/([^\s}]+)"),
    ("dumpsys window | grep -m1 mCurrentFocus",
     r"mCurrentFocus=Window\{[^\s]+\s+[^\s]+\s+([^\s/]+)/([^\s}]+)"),
    ("dumpsys activity activities | grep -m1 mResumedActivity",
     r"mResumedActivity=ActivityRecord\{[^\s]+\s+[^\s]+\s+([^\s/]+)/([^\s}]+)"),
    ("cmd activity get-current-activity",
     r"([A-Za-z0-9_.]+)/([A-Za-z0-9_.$]+)"),
    ("dumpsys activity activities",
     r"ActivityRecord\{[^\s]+\s+[^\s]+\s+([^\s/]+)/([^\s}]+)"),
)


def foreground_activity(adb, serial):
    """取当前前台应用。返回 (包名, activity全名, 来源说明)；
    失败返回 (None, None, 诊断文本)。"""
    tried = []
    for cmd, pat in FG_CMDS:
        rc, out, err = adb.shell(cmd, serial, timeout=40)
        m = re.search(pat, (out or "").strip())
        if m:
            return m.group(1), m.group(2), cmd
        tried.append("%-58s -> %s" % (
            cmd[:58], "空" if not (out or "").strip() else "未匹配"))
    return None, None, "已尝试 %d 种方式：\n  %s" % (len(tried), "\n  ".join(tried))


def resolve_activity(adb, serial, pkg):
    """取应用的启动入口，返回 'pkg/.Activity' 形式字符串，失败返回 ''。

    回退链（单一命令必挂）：
      1) cmd package resolve-activity --brief —— 部分 Android 版本可用；
         Android 15 上对纯包名会直接回 "No activity found"。
      2) pm dump + MAIN action —— 通用兜底：MAIN action 块下第一个
         "pkg/.Activity filter" 行就是入口（实测 Android 13/15 均可用）。
    """
    rc, out, _ = adb.shell(["cmd", "package", "resolve-activity", "--brief", pkg],
                           serial, timeout=40)
    act = ""
    for ln in (out or "").splitlines():
        ln = ln.strip()
        if "/" in ln and not ln.startswith("priority"):
            act = ln
    if act:
        return act

    rc, out, _ = adb.shell(
        "pm dump %s | grep -A4 'android.intent.action.MAIN:'" % pkg,
        serial, timeout=60)
    m = re.search(r"^\s+[0-9a-f]+\s+([\w.$]+)/([\w.$]+)\s+filter",
                  out or "", re.M)
    if m:
        return "%s/%s" % (m.group(1), m.group(2))
    return ""


def capture_png(adb, serial, tmp_dir):
    """一次截图抓取。优先 exec-out（快），数据不完整则回退 screencap+pull（稳）。
    返回 (png_bytes, 方式) 或 (None, 错误信息)。"""
    rc, data, err = adb.run_bytes(["exec-out", "screencap", "-p"], serial,
                                  timeout=60)
    ok, why = png_ok(data)
    if ok:
        return data, "exec-out"
    first = (err or "").strip() or why

    tmp = "/sdcard/pyer6343_cap.png"
    adb.shell(["screencap", "-p", tmp], serial, timeout=60)
    local = os.path.join(tmp_dir, "_cap_tmp.png")
    rc2, out2, err2 = adb.run(["pull", tmp, local], serial, timeout=120)
    adb.shell(["rm", "-f", tmp], serial, timeout=20)
    if os.path.isfile(local):
        with open(local, "rb") as f:
            data2 = f.read()
        try:
            os.remove(local)
        except OSError:
            pass
        ok2, why2 = png_ok(data2)
        if ok2:
            return data2, "screencap+pull"
        first = why2
    return None, "exec-out：%s；pull：%s" % (
        first, (err2 or "").strip() or "未取到文件")


def screen_off(adb, serial):
    """判断设备屏幕是否熄灭。熄屏时 screencap 会拿到纯黑图。"""
    try:
        rc, out, _ = adb.shell("dumpsys power | grep -m1 mWakefulness",
                               serial, timeout=15)
        return "Asleep" in (out or "")
    except Exception:
        return False


def connect_emulator(adb, logger):
    """依次尝试常见模拟器端口 connect（MuMu 16384/16416/16448、通用 7555）。
    logger 为线程安全日志函数。"""
    for port in (16384, 16416, 16448, 7555):
        rc, out, err = adb.run(["connect", "127.0.0.1:%d" % port], timeout=20)
        msg = (out or err).strip()
        if "connected" in msg.lower() or "already" in msg.lower():
            logger("connect 127.0.0.1:%d -> %s" % (port, msg))
