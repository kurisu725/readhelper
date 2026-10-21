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

前端 `index.js` 导出 `activate(ctx)`。`ctx` 提供 `S`、`api`、`post`、`patch`、`esc`、`icon`、`safeMarkdown`、`toast`、`refresh`、`showView`、`openPaper` 和 `registerView(id,title,ui)`。`ui.show()` 负责打开页面，`ui.hasUnsaved()` 用于离开页面前保护草稿。

资源访问地址为 `/plugins/插件ID/资源名`。插件停用时其 API 与静态资源返回 404；配置存储于 `settings` 表的 `plugin:插件ID`。新库默认全部停用。启停会刷新页面。

建筑史插件保留旧版 `history_records`、`history_revisions` 和 `history_comparisons` 表名，旧库无需转存。分析记录继续保存 `analysis_mode`；停用插件不会改写历史分析。

插件不是沙箱，必须与主程序一样审核。当前没有运行中安装、删除或独立升级插件的功能；升级插件通过发布新版应用完成。
