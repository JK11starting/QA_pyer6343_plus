# pyer6343 Plus — ADB QA 助手

一个带可视化界面的 Windows 桌面 adb 工具，用来减少日常 Android 调试/测试中的重复命令操作。

## 功能模块

| 页签 | 能力 |
|------|------|
| 交互终端 | adb shell 伪终端、历史命令、快捷按钮、横向滚动 |
| 应用管理 | 安装 / 覆盖安装(-r) / 卸载 / 保留数据卸载(-k) / 强停 / 清数据 / 启动 |
| 文件传输 | adb push / pull，带文件选择器 |
| 设备管理 | 设备列表、kill-server / start-server、WiFi connect、adb 路径选择 |
| 重启控制 | reboot / recovery / bootloader / fastboot |
| 设备信息 | getprop、CPU/内存、电池、分辨率、密度、IP |
| 设备日志 | logcat 实时抓取、关键字过滤、保存（可选目录）、清空缓冲区 |
| 实用工具 | 截图（PNG 校验 + 黑屏检测）、录屏、前台包名/Activity、包内存占用 |

## 快速开始

### 直接使用

下载 `pyer6343.exe`（见 [Releases](../../releases)），双击运行即可。

### 从源码运行

需要 Python 3.10+（带 tkinter）。

```bash
# 创建虚拟环境（可选）
python -m venv .venv
.venv\Scripts\activate        # Windows

# 安装依赖
pip install pyinstaller pillow

# 运行源码
python src\main.py
```

### 打包成 exe

```bash
python -m PyInstaller _build/pyer6343.spec --noconfirm --distpath _build/dist --workpath _build/build
```

## 技术要点

- tkinter 线程安全：后台线程通过 `queue` 投递，主线程 `drain()` 消费，避免 `main thread is not in main loop`。
- adb 命令回退链：截图支持 `exec-out` → `screencap + pull`；前台包名支持多种 Android 版本字段回退。
- PNG 完整性校验：逐块 CRC + IEND 校验，防止 USB 不稳定导致截断 PNG。
- Android 13+ 兼容：`adb uninstall -k` 已弃用，使用 `adb shell cmd package uninstall -k`。

## 项目结构

```
QA_pyer6343_plus/
├── src/                    # Python 源码
│   ├── main.py             # 主入口
│   ├── adb_core.py         # adb 封装与工具查找
│   ├── shell_tab.py        # 交互终端
│   ├── app_tab.py          # 应用管理
│   ├── file_tab.py         # 文件传输
│   ├── device_tab.py       # 设备管理
│   ├── reboot_tab.py       # 重启控制
│   ├── info_tab.py         # 设备信息
│   ├── log_tab.py          # 设备日志
│   ├── tools_tab.py        # 实用工具
│   └── config.py           # 配置持久化
├── _build/                 # PyInstaller 配置与构建脚本
├── out/                    # 运行时输出（截图/日志/录屏）
└── pyer6343.exe            # Windows 可执行文件（Releases 中分发）
```

## 注意事项

- 首次使用请在顶部选择/刷新设备；模拟器可点「连MuMu(16384)」。
- 真机请确认已开启 USB 调试并授权。
- 高危操作（卸载、清数据、重启、fastboot）均有二次确认。

## License

MIT
