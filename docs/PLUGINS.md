# 插件接口 v1

每个插件位于 `plugins/目录名/`，包含 `manifest.json`、Python 包 `__init__.py`，以及 `static/` 前端资源。只加载与应用共同分发的受信任代码。

主程序通过 `plugin_manager.py` 扫描清单，注册路径、研究模式和界面入口。主程序移除 `plugins/architecture_history/` 后仍可启动并使用通用阅读。

```json
{
  "id": "your-research-plugin",
  "name": "研究插件名称",
  "version": "1.0.0",
  "api_version": 1,
  "description": "功能说明",
  "routes": ["/api/your-plugin"],
  "modes": {"your_mode": "研究模式名称"},
  "frontend": "index.js"
}
```

Python 包公开：

- `init_schema(conn)`：幂等建立 / 迁移插件表，不删除数据。
- `handle(handler, method, path, query, app)`：处理清单中的 API 路径。
- `has_data(conn)`：判断旧库是否存在插件表；首次升级时据此迁移启用状态。
- `markdown(conn)`：完整导出中的插件内容。停用后仍可导出已经保存的记录。
- `labels(mode)` / `instruction(mode)`：研究模式的字段标签与模型指令。
- `on_disable(app)`（可选）：停用后取消后台工作，保留已保存的数据。
- `shutdown(app)`（可选）：本地服务退出时取消后台工作。

前端 `index.js` 导出 `activate(ctx)`。`ctx` 提供 `S`、`api`、`post`、`patch`、`esc`、`icon`、`safeMarkdown`、`toast`、`refresh`、`showView`、`openPaper` 和 `registerView(id,title,ui)`。`ui.show()` 负责打开页面，`ui.hasUnsaved()` 用于离开页面前保护草稿。

资源访问地址为 `/plugins/插件ID/资源名`。插件停用时其 API 与静态资源返回 404；配置存储于 `settings` 表的 `plugin:插件ID`。新库默认全部停用。启停会刷新页面。

建筑史插件保留旧版 `history_records`、`history_revisions` 和 `history_comparisons` 表名，旧库无需转存。分析记录继续保存 `analysis_mode`；停用插件不会改写历史分析。

插件不是沙箱，必须与主程序一样审核。当前没有运行中安装、删除或独立升级插件的功能；升级插件通过发布新版应用完成。

## 研究方向与导图

`plugins/research_directions/` 提供可选的跨学科研究梳理，不注册全局分析模式，不影响建筑史插件的模式选择。

- API：`GET/POST /api/research-directions` 列出历史 / 启动后台任务；`GET /api/research-directions/{id}` 读取进度与结果。
- `POST .../{id}/cancel` 取消任务；`POST .../{id}/retry` 新建任务并复用已有题录、摘要和检索词；`GET .../{id}/export?format=md|json` 导出。
- 任务及证据快照保存在 `direction_runs` 表。新库默认关闭，停用与退出取消进行中的任务；重新启动把未完成任务标为中断。
- 检索 OpenAlex、Semantic Scholar、Crossref，可选 arXiv。每个来源独立失败提示，依据 DOI / 标题去重，按年份筛选，最多纳入 24 篇。
- 生成前区分可用摘要和仅题录；每个节点保存原文摘录和来源编号，保存前验证编号存在、摘录确实在摘要中。该校验确认出处与摘录一致，不代替对模型推论的人工核对。
- 外部请求有超时；取消后不再保存新结果或发起下一个请求，已在途的网络请求可能需等到返回或超时才能释放任务。
- 导图使用本地 HTML/CSS，可展开分支、核对摘要、切换大纲，不依赖远程脚本或图形服务。
