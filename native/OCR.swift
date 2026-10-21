import Foundation
import AppKit
import PDFKit
import Vision

func emit(_ object: [String: Any]) {
    guard let data = try? JSONSerialization.data(withJSONObject: object, options: [.sortedKeys]),
          let line = String(data: data, encoding: .utf8) else { return }
    print(line)
    fflush(stdout)
}
let arguments = CommandLine.arguments
if arguments.count < 3 {
    emit(["error": "缺少 PDF 路径或页码。"]); exit(2)
}
guard let document = PDFDocument(url: URL(fileURLWithPath: arguments[1])) else {
    emit(["error": "无法打开 PDF。"]); exit(2)
}
if document.isLocked { _ = document.unlock(withPassword: "") }
let pages = arguments[2].split(separator: ",").compactMap { Int($0) }
for number in pages {
    autoreleasepool {
        guard let page = document.page(at: number - 1) else {
            emit(["page": number, "error": "此页无法读取。"]); return
        }
        let bounds = page.bounds(for: .mediaBox)
        guard bounds.width.isFinite, bounds.height.isFinite, bounds.width > 0, bounds.height > 0 else {
            emit(["page": number, "error": "此页尺寸无效。"]); return
        }
        let scale = min(3.5, 3200.0 / max(bounds.width, bounds.height))
        let target = NSSize(width: bounds.width * scale, height: bounds.height * scale)
        let thumbnail = page.thumbnail(of: target, for: .mediaBox)
        var imageRect = NSRect(origin: .zero, size: thumbnail.size)
        guard let image = thumbnail.cgImage(forProposedRect: &imageRect, context: nil, hints: nil) else {
            emit(["page": number, "error": "此页无法转换为图片。"]); return
        }
        let request = VNRecognizeTextRequest()
        request.recognitionLevel = .accurate
        request.recognitionLanguages = ["zh-Hans", "zh-Hant", "en-US"]
        request.usesLanguageCorrection = true
        request.minimumTextHeight = 0.003
        if #available(macOS 13.0, *) { request.automaticallyDetectsLanguage = true }
        do {
            try VNImageRequestHandler(cgImage: image, options: [:]).perform([request])
            let observations = request.results ?? []
            // Vision provides reading order, including language-aware line grouping.
            let lines = observations.compactMap { observation -> String? in
                guard let candidate = observation.topCandidates(1).first, candidate.confidence >= 0.15 else { return nil }
                return candidate.string
            }
            emit(["page": number, "text": lines.joined(separator: "\n"), "lines": lines.count])
        } catch {
            emit(["page": number, "error": "文字识别失败：\(error.localizedDescription)"])
        }
    }
}
emit(["done": true])
