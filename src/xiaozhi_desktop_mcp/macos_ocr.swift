import CoreGraphics
import Foundation
import ImageIO
import Vision

func fail(_ message: String) -> Never {
    FileHandle.standardError.write(Data(message.utf8))
    exit(1)
}

guard CommandLine.arguments.count >= 2 else {
    fail("usage: macos_ocr.swift <image-path> [languages]")
}

let imageURL = URL(fileURLWithPath: CommandLine.arguments[1])
guard
    let source = CGImageSourceCreateWithURL(imageURL as CFURL, nil),
    let image = CGImageSourceCreateImageAtIndex(source, 0, nil)
else {
    fail("unable to read image")
}

let request = VNRecognizeTextRequest()
request.recognitionLevel = .accurate
request.usesLanguageCorrection = true
if CommandLine.arguments.count >= 3 {
    let languages = CommandLine.arguments[2]
        .split(separator: ",")
        .map { $0.trimmingCharacters(in: .whitespacesAndNewlines) }
        .filter { !$0.isEmpty }
    if !languages.isEmpty {
        request.recognitionLanguages = languages
    }
}

do {
    try VNImageRequestHandler(cgImage: image, options: [:]).perform([request])
} catch {
    fail("vision OCR failed: \(error.localizedDescription)")
}

var blocks: [[String: Any]] = []
for observation in request.results ?? [] {
    guard let candidate = observation.topCandidates(1).first else { continue }
    let box = observation.boundingBox
    blocks.append([
        "text": candidate.string,
        "confidence": Double(candidate.confidence),
        "bounds": [
            "x": Double(box.origin.x),
            "y": Double(box.origin.y),
            "width": Double(box.size.width),
            "height": Double(box.size.height),
        ],
    ])
}

let payload: [String: Any] = [
    "text": blocks.compactMap { $0["text"] as? String }.joined(separator: "\n"),
    "blocks": blocks,
]

do {
    let data = try JSONSerialization.data(withJSONObject: payload, options: [])
    FileHandle.standardOutput.write(data)
} catch {
    fail("unable to encode OCR result")
}
