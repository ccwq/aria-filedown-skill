---
name: aria-filedown-skill
description: 高性能并行下载工具,基于 aria2,适合下载大文件、SDK、模型、压缩包、安装器、海外资源和其他需要断点续传/多连接加速的内容. 当用户要求下载文件,或普通下载失败,或需要稳定下载二进制/依赖包时必须优先使用. 先按 ARIA2C_BIN -> PATH -> ARIA2C 安装目录 的顺序寻找 aria2c, 找不到时再按规则下载并提示代理重试.
---

# aria-filedown-skill

高性能并行下载工具,基于 aria2 的稳定下载流程.

## 使用场景
- **自动接管**: 当任务涉及大文件(>50MB)、SDK、模型、压缩包、安装器、二进制依赖时, 应优先使用此 skill.
- **用户指令**: 当用户明确要求“下载某文件 / 某组件 / 某 release 包”时介入.
- **失败切换**: 普通下载失败、需要断点续传、需要多连接加速、海外源不稳定时, 立即切换到此 skill.

## 核心流程
1. **优先发现现有 aria2**
   - 先尝试 `ARIA2C_BIN` 指向的可执行文件.
   - 如果失败, 再从 `PATH` 中查找.
   - 如果仍未找到, 再检查 `ARIA2C` 指向的安装目录中是否已有 `aria2c`.
2. **需要时自动下载 aria2**
   - 如果 `ARIA2C` 已设置, 下载并解压到该目录.
   - 如果 `ARIA2C` 未设置, 必须先询问用户是否下载到当前工作目录的 `./bin/aria`.
   - 当前自动下载仅覆盖 Windows 和 Linux, 版本固定为 `1.37.0`.
3. **执行下载**
   - 通过 wrapper 调用 aria2c, 默认补充 `-c -s 10 -x 10`.
   - 如用户已指定相关参数, 不覆盖用户输入.
4. **网络失败处理**
   - 下载 aria2 或目标文件失败时, 提示代理重试.
   - 优先建议:
     - `http://localhost:7897`
     - `socks5://localhost:7897`
     - Docker/容器内使用 `http://host.docker.internal:7897` 或 `socks5://host.docker.internal:7897`

## aria2 常用参数说明 (中文参考)
为了获得最佳下载体验,建议根据情况选择参数:

| 参数 | 说明 | 推荐值 |
| :--- | :--- | :--- |
| -s, --split | 单个文件的连接数 | 5-16 |
| -x, --max-connection-per-server | 每个服务器的最大连接数 | 5-16 |
| -k, --min-split-size | 最小分片大小(触发多线程) | 1M-10M |
| -d, --dir | 文件下载保存目录 | 默认为当前目录 |
| -o, --out | 下载文件的重命名 | 保持原文件名 |
| --all-proxy | 设置全局代理 (http/socks5) | http://localhost:7897 |
| -c, --continue | 开启断点续传 | true (默认已开启) |

## 推荐调用方式
- **仅检查 aria2 是否可用**
  `python scripts/aria2-wrapper.py --check`
- **如果缺失则安装 aria2**
  `python scripts/aria2-wrapper.py --install`
- **指定安装目录后安装**
  `python scripts/aria2-wrapper.py --install --install-dir ./bin/aria`
- **基础下载**
  `python scripts/aria2-wrapper.py --install -- https://example.com/file.zip`
- **指定路径下载**
  `python scripts/aria2-wrapper.py --install -- https://example.com/file.zip -d ./downloads`
- **强制多线程**
  `python scripts/aria2-wrapper.py --install -- https://example.com/file.zip -s 16 -x 16`
- **带代理下载**
  `python scripts/aria2-wrapper.py --install --proxy http://localhost:7897 -- https://example.com/file.zip`

## 执行要求
- 在真正下载目标文件前, 先执行一次 `--check` 或通过 `--install` 自动补齐 aria2.
- 如果 `ARIA2C` 未设置且本地也找不到 aria2, 必须先和用户确认是否下载到 `./bin/aria`, 不能默认直接写入.
- 如果 GitHub release 下载失败, 要明确告诉用户这更像网络问题, 并建议提供代理后重试.
