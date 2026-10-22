# 研读助手 · ResearchDesk

本地资料库、带出处的 AI 阅读分析、知识卡片与笔记。支持 PDF、EPUB、DOCX、TXT、Markdown，以及网络文献、网络案例和任务书解读。

建筑史研究采用可选插件：史料证据卡、建筑沿革时间轴、学术观点与争议对照、建筑史分析模式。新安装默认通用研读；有旧版史料表的资料库会自动启用对应插件。停用插件不会删除记录，完整备份和导出仍包含已保存的史料。

## 安装与使用

- **Windows 10/11 x64**：运行 Release 中的 `ResearchDesk-版本-windows-x64.exe`，按当前用户安装，不需要管理员或额外安装 Python。桌面快捷方式打开默认浏览器中的本地工作台。关闭网页不会结束后台服务，在“插件与更新”点击“退出本地阅读服务”可完全退出。
- **macOS 14+、Apple Silicon**：打开 `ResearchDesk-版本-macos-arm64.dmg`，将“研读助手”拖到 Applications。
- **macOS 14+、Intel**：使用 `ResearchDesk-版本-macos-x64.dmg`，由 GitHub Actions 的 Intel 构建任务生成。

Mac 使用原生窗口，Windows 使用默认浏览器。资料服务只监听 `127.0.0.1`。Mac 使用 Vision OCR；Windows 使用 RapidOCR + ONNX Runtime CPU 离线识别中英文扫描 PDF，模型与 PDFium 渲染组件随安装包提供，无需显卡或联网下载模型。

目前安装包未配置商业代码签名 / Apple Developer 公证。Mac 的签名是本地临时签名；系统可能要求手动允许打开。不要通过关闭全局系统保护来安装。

首次运行进入“AI 设置”，点击“打开密钥配置文件”，填写 `PAPER_API_KEY` 后保存；在界面配置兼容 Chat Completions 的 API 地址和模型。密钥不会发送给更新服务，也不会显示在页面中。使用远程 AI 会将所选资料摘录发送到你配置的服务。

在“插件与更新”启用建筑史研究。分析模式可选择“通用研读”或已启用插件提供的模式；已有分析保留原模式含义。

## 扫描 PDF 与研究方向

扫描 PDF 导入后，在阅读页点击“识别本页”或“识别全书”。全书识别跳过有文字和已经处理的页；进度和完成结果逐页保存，停止后可以继续。识别完成切换到“文字”视图即可复制、选段提问；全文搜索与 AI 引用会使用识别结果。原始 PDF 保持原样，OCR 不会向原文件写入隐藏文字层。复杂双栏、公式、表格仍需对照原图核对。

Windows 源码版安装 `requirements.txt` 即包含 OCR 依赖。OCR 在独立、隐藏窗口的进程内执行，按页渲染并释放图片，不会把整本书同时载入模型；当前页超时会保留先前识别结果。文字块坐标、置信度与引擎名称随页面存储。

在“插件与更新”启用“研究方向与导图”，侧栏出现“研究方向”，阅读页也可从当前论文或选段发起：

1. 输入主题，可补充英文检索词、限制年份、选择来源及最多 8 / 16 / 24 篇。
2. 从 OpenAlex、Semantic Scholar、Crossref 获取论文，可选 arXiv 预印本；默认使用配置的 AI 模型补充英文检索词，允许关闭。
3. 依据检索摘要生成研究分支、相关问题与候选方向。导图区分“摘要明确报告”与“分析推断 / 待验证”，每个节点可展开原文证据，点击编号查看论文摘要及来源链接。
4. 支持导图 / 大纲切换、折叠、取消任务、历史恢复以及 Markdown / JSON 导出。失败时保留已获取的题录和摘要，可复用结果重试分析；调整检索条件应新建任务。

插件默认关闭。关闭后不接受新任务，会取消进行中的任务，保留历史数据和备份导出。已经发出的网络请求可能需要等待返回或超时。论文服务可能限流，界面会显示不完整的来源。研究分析仅使用摘要，不宣称已阅读全文或覆盖整个领域。请求使用“AI 设置”中的密钥、地址和模型，摘要分析会消耗该服务额度；文献来源不会收到 AI 密钥。

## 资料与配置

| 系统 | 本机资料根目录 |
| --- | --- |
| macOS | `~/Library/Application Support/研读助手/` |
| Windows | `%LOCALAPPDATA%\ResearchDesk\` |
| Linux 源码运行 | `~/.local/share/ResearchDesk/` |

根目录中的 `data/` 保存数据库和文件，`.env` 保存密钥，`updates/` 保存校验通过的安装包。安装、更新或卸载应用不会主动清除这些个人资料。Mac 的位置与旧桌面版兼容，无需复制原数据库。早期源码版若把资料保存在项目下的 `data/`，可通过 `PAPER_DATA_DIR` 指定该目录；操作前请先备份并关闭另一个实例。

## 源码运行

Python 3.12 或 3.13：

```sh
python -m venv .venv
# macOS/Linux: source .venv/bin/activate
# Windows PowerShell: .venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python app.py
```

可用参数：`--port 8765`、`--no-browser`、`--ready-file PATH`。`--port 0` 自动分配空闲端口。
可用环境变量：`PAPER_DATA_DIR`、`PAPER_CONFIG_FILE`、`PAPER_API_KEY`、`PAPER_BASE_URL`、`PAPER_MODEL`。

## GitHub 上传与更新

上传此项目目录中的源码，**包括 `.github/workflows/release.yml`**。不要上传个人资料根目录、`.env` 或任何数据库；`.gitignore` 已排除这些内容。安装文件应作为 Release 附件上传。

当前发布仓库为 `kurisu725/readhelper`，保持私有。在项目目录执行：

```sh
git add .
git commit -m "Prepare ResearchDesk 1.7.3 release"
git remote add origin https://github.com/kurisu725/readhelper.git
git push -u origin main
git tag v1.7.3
git push origin v1.7.3
```

若从 ZIP 解压并且目录尚未初始化 Git，先执行 `git init -b main`。
若已经存在提交或远端，无需重复初始化、提交或添加远端。本项目开源许可证尚未选择；公开代码前请按你的意愿配置。

推送 `v1.7.3` 标签后，工作流会：

1. 校验标签与 `release.json` 的版本一致，把当前 GitHub 仓库写入安装包的默认更新配置。
2. 在 Windows、Mac Apple Silicon、Mac Intel 上分别测试和打包。
3. 安装 Windows 包并启动其内置 Python 服务；启动 Mac 包中的独立服务，检查核心接口和插件。
4. 所有构建通过后，发布正式 GitHub Release，附三种安装包与 `SHA256SUMS.txt`。

在 Actions 中手动运行工作流只生成构建产物，不自动发布正式 Release。GitHub 首次发布尚未执行前，工作流中的平台测试不能视为已通过。

以后更新：修改 `release.json` 中的版本，更新 `packaging/RELEASE_NOTES.md`，提交并推送同名 `vX.Y.Z` 标签。版本号采用三段数字；预发布版、草稿版不作为稳定更新推送。

应用内点击“插件与更新”，配置 `用户名/仓库名` 并“检查更新”。从 GitHub Actions 生成的安装包已自动绑定该仓库。更新流程：**检查版本 → 下载匹配系统的附件 → 校验 GitHub 提供的 SHA-256 → 打开安装包 → 退出旧程序后安装**。此版本不在后台静默替换程序，不自动拉取 Git 仓库覆盖本地源码。

公开仓库无需登录。私有仓库需要每位使用者在自己的本机 `.env` 中设置 `PAPER_GITHUB_TOKEN`：使用有该仓库访问权限的 GitHub 账号创建 fine-grained token，限定到 `kurisu725/readhelper`，仅授予 **Contents: Read-only**。可从“插件与更新 → 私有仓库访问配置”打开配置文件。令牌只发送到 GitHub API，不显示在页面中，不随安装包分发；下载重定向时会移除授权头。GitHub CLI 的发布授权与客户端的读取令牌分别配置。

仓库不存在、没有正式 Release、限流、网络中断、文件损坏或缺少对应系统安装包时会提示原因。不会执行未校验的安装包。校验防止文件损坏和错误附件，不等同于操作系统开发者签名。

## 本地打包与测试

```sh
python -m pip install -r requirements-build.txt
python -m unittest discover -s tests -v
python packaging/build_macos.py          # macOS + Xcode 命令行工具
python packaging/build_windows.py        # Windows、macOS、Linux 均可生成 Windows 安装包
```

产物在 `release/`。Mac 包包含 PyInstaller 冻结运行环境，不依赖 `/usr/bin/python3`、Codex 或开发者机器路径。Windows 包包含经过固定 SHA-256 校验的官方 CPython 嵌入式运行环境，以及 NSIS 3.12 安装程序。

Windows 安装包可在 Mac 上组装，**执行验证仍需 Windows**；工作流已配置 Windows 安装和启动检查。Mac Intel 构建应在 Intel runner 运行；本地 Apple Silicon 构建不声称通用于 Intel。

## 插件开发

见 [插件接口说明](docs/PLUGINS.md)。插件与主程序一同审核、打包和发布。没有任意网址下载并执行第三方 Python 的安装入口。

## 第三方组件

PDF 解析使用 pypdf，阅读器使用 PDF.js，Markdown 使用 marked。Windows OCR 使用 RapidOCR（含 PP-OCR 模型）、ONNX Runtime、PDFium / pypdfium2 及其依赖。保留的第三方声明位于 `licenses/` 和 `static/vendor/`；Windows OCR 依赖及模型许可保留在 `server/lib` 各包和 dist-info 中。打包时还会包含 Python 与 NSIS 的许可文本。原始个人文献、配置和数据库不属于发行内容。
