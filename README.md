# aria-filedown-skill

一个基于 `aria2` 的下载加速 skill，用来稳定下载大文件、SDK、模型、压缩包、安装器和海外资源。

## 这是什么

这个仓库包含一个可直接使用的 skill：

- `aria-filedown/`：核心 skill 目录
- `aria-filedown/scripts/aria2-wrapper.py`：`aria2c` 启动与进度封装

## 能做什么

- 自动发现本机 `aria2c`
- 按需下载安装到本地目录
- 支持断点续传和多连接加速
- 支持 `tty` / `jsonl` / `off` 进度输出
- 支持代理下载，适合网络不稳定场景

## 安装

### 1. 通过 `npx skills add` 安装

本地仓库安装：

```bash
npx skills add ./aria-filedown
```

GitHub 仓库安装：

```bash
npx skills add https://github.com/<owner>/<repo>
```

常用参数：

- `-g, --global`：安装到用户目录
- `-a, --agent <agents...>`：指定 agent
- `-s, --skill <skills...>`：只安装指定 skill

### 3. skills CLI 的环境变量

`npx skills add/remove` 还支持这些通用环境变量：

- `DISABLE_TELEMETRY=1`：关闭匿名 telemetry
- `DO_NOT_TRACK=1`：同样可关闭 telemetry
- `INSTALL_INTERNAL_SKILLS=1`：允许安装标记为 internal 的技能

## 使用前的环境变量

这个 skill 会按下面的优先级寻找 `aria2c`：

1. `ARIA2C_BIN`
2. `PATH`
3. `ARIA2C` 指定的安装目录

推荐这样配置：

- `ARIA2C_BIN`：直接指向 `aria2c` 可执行文件
- `ARIA2C`：指向 `aria2` 的安装目录，脚本会在这里查找或下载安装到这里

如果你只想让 `npx skills add` 本身不上传匿名使用数据，可以设置：

```powershell
$env:DISABLE_TELEMETRY = "1"
```

示例：

```powershell
$env:ARIA2C_BIN = "E:\tools\aria2\aria2c.exe"
$env:ARIA2C = "E:\tools\aria2"
```

## 代理

如果下载失败，优先尝试下面这些代理：

- `http://localhost:7897`
- `socks5://localhost:7897`
- 容器内可用 `http://host.docker.internal:7897`
- 容器内可用 `socks5://host.docker.internal:7897`

也可以在执行脚本时直接传 `--proxy`。

## 快速开始

检查当前环境是否可用：

```bash
python aria-filedown/scripts/aria2-wrapper.py --check
```

自动补齐 `aria2` 并下载：

```bash
python aria-filedown/scripts/aria2-wrapper.py --install -- https://example.com/file.zip
```

带终端进度：

```bash
python aria-filedown/scripts/aria2-wrapper.py --install --progress tty -- https://example.com/file.zip
```

输出 JSONL 进度：

```bash
python aria-filedown/scripts/aria2-wrapper.py --install --progress jsonl --progress-file ./progress.jsonl -- https://example.com/file.zip
```

## 卸载

如果是通过 `npx skills add` 安装的，可以直接移除：

```bash
npx skills remove aria-filedown
```

如果是全局安装的：

```bash
npx skills remove --global aria-filedown
```

## 备注

- Windows 和 Linux 支持自动下载安装 `aria2`
- 当前默认版本是 `aria2 1.37.0`
- 如果你在 Docker 里用代理，优先用 `host.docker.internal:7897`
