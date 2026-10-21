import AppKit
import WebKit
import UniformTypeIdentifiers

final class ResearchDeskApp: NSObject, NSApplicationDelegate, WKNavigationDelegate, WKUIDelegate, WKDownloadDelegate {
    var window: NSWindow!
    var webView: WKWebView!
    var server: Process?
    var readyTimer: Timer?
    var readyFile: URL!
    var configFile: URL!
    var logFile: URL!
    var serverURL: URL?
    var attempts = 0
    let fileManager = FileManager.default

    func applicationDidFinishLaunching(_ notification: Notification) {
        NSApp.setActivationPolicy(.regular)
        buildMenus()
        window = NSWindow(contentRect: NSRect(x: 0, y: 0, width: 1280, height: 820),
                          styleMask: [.titled, .closable, .miniaturizable, .resizable], backing: .buffered, defer: false)
        window.title = "研读 · 文献、图书与规范"
        window.minSize = NSSize(width: 900, height: 640)
        window.setFrameAutosaveName("ResearchDeskMain")
        window.center()
        let configuration = WKWebViewConfiguration()
        configuration.preferences.javaScriptCanOpenWindowsAutomatically = false
        webView = WKWebView(frame: window.contentView!.bounds, configuration: configuration)
        webView.autoresizingMask = [.width, .height]
        webView.navigationDelegate = self
        webView.uiDelegate = self
        webView.allowsBackForwardNavigationGestures = false
        window.contentView = webView
        window.makeKeyAndOrderFront(nil)
        NSApp.activate(ignoringOtherApps: true)
        webView.loadHTMLString("<html><meta charset='utf-8'><body style='margin:0;background:#f5f6ee;color:#476244;font:16px -apple-system;display:flex;height:100vh;align-items:center;justify-content:center'><div style='text-align:center'><h1 style='font:38px serif'>研读</h1><p>正在打开你的阅读空间…</p></div></body></html>", baseURL: nil)
        launchServer()
    }

    func buildMenus() {
        let menu = NSMenu()
        let appItem = NSMenuItem(); menu.addItem(appItem)
        let appMenu = NSMenu(); appItem.submenu = appMenu
        appMenu.addItem(withTitle: "关于研读", action: #selector(showAbout), keyEquivalent: "")
        appMenu.addItem(withTitle: "插件与更新…", action: #selector(showUpdates), keyEquivalent: "")
        appMenu.addItem(.separator())
        appMenu.addItem(withTitle: "配置 API 密钥…", action: #selector(openConfiguration), keyEquivalent: ",")
        appMenu.addItem(withTitle: "打开资料文件夹", action: #selector(openDataFolder), keyEquivalent: "")
        appMenu.addItem(.separator())
        appMenu.addItem(withTitle: "隐藏研读", action: #selector(NSApplication.hide(_:)), keyEquivalent: "h")
        appMenu.addItem(withTitle: "退出研读", action: #selector(NSApplication.terminate(_:)), keyEquivalent: "q")
        let editItem = NSMenuItem(); menu.addItem(editItem)
        let editMenu = NSMenu(title: "编辑"); editItem.submenu = editMenu
        editMenu.addItem(withTitle: "撤销", action: Selector(("undo:")), keyEquivalent: "z")
        editMenu.addItem(withTitle: "重做", action: Selector(("redo:")), keyEquivalent: "Z")
        editMenu.addItem(.separator())
        editMenu.addItem(withTitle: "剪切", action: #selector(NSText.cut(_:)), keyEquivalent: "x")
        editMenu.addItem(withTitle: "拷贝", action: #selector(NSText.copy(_:)), keyEquivalent: "c")
        editMenu.addItem(withTitle: "粘贴", action: #selector(NSText.paste(_:)), keyEquivalent: "v")
        editMenu.addItem(withTitle: "全选", action: #selector(NSText.selectAll(_:)), keyEquivalent: "a")
        let viewItem = NSMenuItem(); menu.addItem(viewItem)
        let viewMenu = NSMenu(title: "窗口"); viewItem.submenu = viewMenu
        viewMenu.addItem(withTitle: "重新载入", action: #selector(reloadPage), keyEquivalent: "r")
        viewMenu.addItem(withTitle: "最小化", action: #selector(NSWindow.performMiniaturize(_:)), keyEquivalent: "m")
        NSApp.mainMenu = menu
    }

    func launchServer() {
        guard let resources = Bundle.main.resourceURL else { fail("找不到应用资源。"); return }
        let source = resources.appendingPathComponent("server")
        let support = ProcessInfo.processInfo.environment["PAPER_SUPPORT_DIR"].map { URL(fileURLWithPath: $0) } ?? fileManager.homeDirectoryForCurrentUser.appendingPathComponent("Library/Application Support/研读助手")
        do {
            try fileManager.createDirectory(at: support, withIntermediateDirectories: true, attributes: [.posixPermissions: 0o700])
            configFile = support.appendingPathComponent(".env")
            logFile = support.appendingPathComponent("运行日志.txt")
            if !fileManager.fileExists(atPath: configFile.path) {
                try fileManager.copyItem(at: source.appendingPathComponent(".env.example"), to: configFile)
            }
            try fileManager.setAttributes([.posixPermissions: 0o600], ofItemAtPath: configFile.path)
            readyFile = support.appendingPathComponent("ready-\(ProcessInfo.processInfo.processIdentifier).txt")
            try? fileManager.removeItem(at: readyFile)
            let process = Process()
            process.executableURL = source.appendingPathComponent("ResearchDeskServer")
            process.currentDirectoryURL = source
            process.arguments = ["--no-browser", "--port", "0", "--ready-file", readyFile.path]
            var environment = ProcessInfo.processInfo.environment
            environment["PAPER_CONFIG_FILE"] = configFile.path
            environment["PAPER_DATA_DIR"] = environment["PAPER_DATA_DIR"] ?? support.appendingPathComponent("data").path
            environment["PAPER_NATIVE"] = "1"
            environment["PYTHONPATH"] = source.appendingPathComponent("lib").path
            environment["PYTHONDONTWRITEBYTECODE"] = "1"
            process.environment = environment
            fileManager.createFile(atPath: logFile.path, contents: nil, attributes: [.posixPermissions: 0o600])
            let logHandle = try FileHandle(forWritingTo: logFile)
            process.standardOutput = logHandle; process.standardError = logHandle
            try process.run(); server = process
            readyTimer = Timer.scheduledTimer(withTimeInterval: 0.15, repeats: true) { [weak self] _ in self?.checkReady() }
        } catch { fail("本地服务未能启动：\(error.localizedDescription)") }
    }

    func checkReady() {
        attempts += 1
        if let text = try? String(contentsOf: readyFile, encoding: .utf8), let url = URL(string: text), url.host == "127.0.0.1" {
            readyTimer?.invalidate(); readyTimer = nil; serverURL = url
            webView.load(URLRequest(url: url)); return
        }
        if server?.isRunning == false || attempts > 200 {
            readyTimer?.invalidate(); readyTimer = nil
            fail("无法打开本地阅读服务。请查看“打开资料文件夹”中的运行日志，或尝试重新启动应用。")
        }
    }

    func fail(_ text: String) {
        let alert = NSAlert(); alert.messageText = "研读未能启动"; alert.informativeText = text
        alert.addButton(withTitle: "关闭"); alert.runModal(); NSApp.terminate(nil)
    }
    @objc func showAbout() {
        let alert = NSAlert(); alert.messageText = "研读助手 " + (Bundle.main.object(forInfoDictionaryKey: "CFBundleShortVersionString") as? String ?? "")
        alert.informativeText = "文献、图书与规范的阅读工作台。\n支持 PDF、EPUB、DOCX、TXT 与 Markdown，提供带出处的 AI 问答、分析和笔记。\n\n资料与笔记本地保存；使用远程 AI 时发送相关摘录。"
        alert.addButton(withTitle: "好"); alert.runModal()
    }
    @objc func openConfiguration() {
        if let path = configFile { NSWorkspace.shared.open([path], withApplicationAt: URL(fileURLWithPath: "/System/Applications/TextEdit.app"), configuration: NSWorkspace.OpenConfiguration()) }
    }
    @objc func openDataFolder() {
        if let path = configFile { NSWorkspace.shared.open(path.deletingLastPathComponent()) }
    }
    @objc func showUpdates() { webView.evaluateJavaScript("document.querySelector('[data-view=extensions]')?.click()", completionHandler: nil) }
    @objc func reloadPage() { webView.reload() }
    func applicationShouldTerminateAfterLastWindowClosed(_ sender: NSApplication) -> Bool { true }
    func applicationWillTerminate(_ notification: Notification) {
        readyTimer?.invalidate()
        if let process = server, process.isRunning { process.terminate() }
        if let file = readyFile { try? fileManager.removeItem(at: file) }
    }
    func applicationShouldHandleReopen(_ sender: NSApplication, hasVisibleWindows flag: Bool) -> Bool {
        window.makeKeyAndOrderFront(nil); return true
    }
    func webView(_ webView: WKWebView, decidePolicyFor action: WKNavigationAction, decisionHandler: @escaping (WKNavigationActionPolicy) -> Void) {
        guard let url = action.request.url else { decisionHandler(.cancel); return }
        if action.shouldPerformDownload { decisionHandler(.download); return }
        if url.scheme == "about" { decisionHandler(.allow); return }
        if url.host == "127.0.0.1" && url.port == serverURL?.port {
            if action.targetFrame == nil && url.path.hasSuffix("/pdf") {
                NSWorkspace.shared.open(url); decisionHandler(.cancel)
            } else { decisionHandler(.allow) }
            return
        }
        if ["https", "http"].contains(url.scheme ?? "") { NSWorkspace.shared.open(url) }
        decisionHandler(.cancel)
    }
    func webView(_ webView: WKWebView, decidePolicyFor response: WKNavigationResponse, decisionHandler: @escaping (WKNavigationResponsePolicy) -> Void) {
        if let response = response.response as? HTTPURLResponse,
           (response.value(forHTTPHeaderField: "Content-Disposition")?.lowercased().contains("attachment") ?? false) {
            decisionHandler(.download)
        } else { decisionHandler(.allow) }
    }
    func webView(_ webView: WKWebView, navigationAction: WKNavigationAction, didBecome download: WKDownload) { download.delegate = self }
    func webView(_ webView: WKWebView, navigationResponse: WKNavigationResponse, didBecome download: WKDownload) { download.delegate = self }
    func download(_ download: WKDownload, decideDestinationUsing response: URLResponse, suggestedFilename: String, completionHandler: @escaping (URL?) -> Void) {
        let panel = NSSavePanel(); panel.nameFieldStringValue = suggestedFilename; panel.canCreateDirectories = true
        panel.beginSheetModal(for: window) { result in completionHandler(result == .OK ? panel.url : nil) }
    }
    func download(_ download: WKDownload, didFailWithError error: Error, resumeData: Data?) {
        let alert = NSAlert(); alert.messageText = "导出未完成"; alert.informativeText = error.localizedDescription
        alert.beginSheetModal(for: window)
    }
    func webView(_ webView: WKWebView, runOpenPanelWith parameters: WKOpenPanelParameters, initiatedByFrame frame: WKFrameInfo, completionHandler: @escaping ([URL]?) -> Void) {
        let panel = NSOpenPanel(); panel.allowsMultipleSelection = parameters.allowsMultipleSelection
        panel.canChooseDirectories = false; panel.canChooseFiles = true
        panel.allowedContentTypes = ["pdf","epub","docx","txt","md"].compactMap { UTType(filenameExtension: $0) }
        panel.beginSheetModal(for: window) { result in completionHandler(result == .OK ? panel.urls : nil) }
    }
    func webView(_ webView: WKWebView, runJavaScriptConfirmPanelWithMessage message: String, initiatedByFrame frame: WKFrameInfo, completionHandler: @escaping (Bool) -> Void) {
        let alert = NSAlert(); alert.messageText = message; alert.addButton(withTitle: "确定"); alert.addButton(withTitle: "取消")
        alert.beginSheetModal(for: window) { result in completionHandler(result == .alertFirstButtonReturn) }
    }
    func webView(_ webView: WKWebView, runJavaScriptAlertPanelWithMessage message: String, initiatedByFrame frame: WKFrameInfo, completionHandler: @escaping () -> Void) {
        let alert = NSAlert(); alert.messageText = message; alert.addButton(withTitle: "好")
        alert.beginSheetModal(for: window) { _ in completionHandler() }
    }
}

let app = NSApplication.shared
let delegate = ResearchDeskApp()
app.delegate = delegate
app.run()
