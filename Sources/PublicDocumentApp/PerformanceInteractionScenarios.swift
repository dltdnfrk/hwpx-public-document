import AppKit
import CoreGraphics
import Foundation

struct PerformanceConsoleSession {
    let onConsole: Bool
    let screenLocked: Bool

    static var current: PerformanceConsoleSession {
        let values = CGSessionCopyCurrentDictionary() as? [String: Any] ?? [:]
        return PerformanceConsoleSession(
            onConsole: values[kCGSessionOnConsoleKey as String] as? Bool ?? false,
            screenLocked: values["CGSSessionScreenIsLocked"] as? Bool ?? false
        )
    }
}

final class PerformanceObservationSurface {
    static let windowTitle = "AC-09 UI 성능 관찰"

    let window: NSWindow
    let progressIndicator: NSProgressIndicator
    let statusLabel: NSTextField
    let cancelButton: NSButton

    init() {
        window = NSWindow(
            contentRect: NSRect(x: 0, y: 0, width: 520, height: 220),
            styleMask: [.titled, .closable],
            backing: .buffered,
            defer: false
        )
        window.title = Self.windowTitle
        window.isReleasedWhenClosed = false
        window.collectionBehavior = [.moveToActiveSpace]

        let heading = NSTextField(labelWithString: "내보내기 성능을 실제 UI에서 확인하고 있습니다.")
        heading.font = .boldSystemFont(ofSize: 15)
        heading.setAccessibilityRole(.staticText)

        statusLabel = NSTextField(labelWithString: "UI 관찰을 준비하고 있습니다.")
        statusLabel.lineBreakMode = .byWordWrapping
        statusLabel.maximumNumberOfLines = 2
        statusLabel.setAccessibilityLabel("AC-09 내보내기 상태")

        progressIndicator = NSProgressIndicator()
        progressIndicator.isIndeterminate = false
        progressIndicator.minValue = 0
        progressIndicator.maxValue = 1
        progressIndicator.doubleValue = 0
        progressIndicator.setAccessibilityLabel("AC-09 문서별 형식 내보내기 진행률")

        cancelButton = NSButton(title: "일괄 내보내기 취소", target: nil, action: nil)
        cancelButton.bezelStyle = .rounded
        cancelButton.setAccessibilityLabel("AC-09 일괄 내보내기 취소")

        let stack = NSStackView(views: [heading, statusLabel, progressIndicator, cancelButton])
        stack.orientation = .vertical
        stack.alignment = .leading
        stack.spacing = 16
        stack.translatesAutoresizingMaskIntoConstraints = false
        progressIndicator.translatesAutoresizingMaskIntoConstraints = false
        cancelButton.translatesAutoresizingMaskIntoConstraints = false
        window.contentView?.addSubview(stack)
        NSLayoutConstraint.activate([
            stack.leadingAnchor.constraint(equalTo: window.contentView!.leadingAnchor, constant: 28),
            stack.trailingAnchor.constraint(equalTo: window.contentView!.trailingAnchor, constant: -28),
            stack.topAnchor.constraint(equalTo: window.contentView!.topAnchor, constant: 28),
            stack.bottomAnchor.constraint(lessThanOrEqualTo: window.contentView!.bottomAnchor, constant: -24),
            progressIndicator.widthAnchor.constraint(equalTo: stack.widthAnchor),
            cancelButton.trailingAnchor.constraint(lessThanOrEqualTo: stack.trailingAnchor),
        ])
        window.center()
    }

    func show() {
        window.makeKeyAndOrderFront(nil)
        window.orderFrontRegardless()
        window.displayIfNeeded()
    }

    func update(manifest: BatchExportManifest, phase: String) -> (progressChanged: Bool, labelChanged: Bool) {
        let completed = manifest.items.reduce(0) { $0 + $1.progressCompleted }
        let total = max(1, manifest.items.reduce(0) { $0 + $1.progressTotal })
        let previousProgress = progressIndicator.doubleValue
        let nextProgress = Double(completed)
        progressIndicator.maxValue = Double(total)
        progressIndicator.doubleValue = nextProgress
        let nextLabel = "\(phase) · \(completed) / \(total) · \(manifest.state.rawValue)"
        let labelChanged = statusLabel.stringValue != nextLabel
        statusLabel.stringValue = nextLabel
        window.displayIfNeeded()
        return (previousProgress != nextProgress, labelChanged)
    }

    func finish(_ message: String) {
        statusLabel.stringValue = message
        window.displayIfNeeded()
    }
}
