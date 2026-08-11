import AppKit
import CoreGraphics
import Foundation

struct PerformanceInteractionBenchmarkResult {
    let interactionObservation: PerformanceInteractionObservation
    let uiObservation: PerformanceUIObservation
}

struct PerformanceUIObservation: Encodable {
    let status: String
    let blockReason: String?
    let observationSurface: String
    let screenLocked: Bool
    let consoleSessionOnConsole: Bool
    let nsApplicationRunning: Bool
    let windowVisible: Bool
    let windowIsKey: Bool
    let onScreenWindowCount: Int
    let windowTitle: String
    let progressIndicatorRole: String
    let progressIndicatorValueChangesOnMainThread: Int
    let progressLabelChangesOnMainThread: Int
    let progressObservedMainThreadOnly: Bool
    let cancelButtonClass: String
    let cancelButtonActionPath: String
    let cancelButtonActionInvocations: Int
    let cancelActionObservedOnMainThread: Bool
    let cancelledManifestState: String

    private enum CodingKeys: String, CodingKey {
        case status
        case blockReason
        case observationSurface
        case screenLocked
        case consoleSessionOnConsole
        case nsApplicationRunning
        case windowVisible
        case windowIsKey
        case onScreenWindowCount
        case windowTitle
        case progressIndicatorRole
        case progressIndicatorValueChangesOnMainThread
        case progressLabelChangesOnMainThread
        case progressObservedMainThreadOnly
        case cancelButtonClass
        case cancelButtonActionPath
        case cancelButtonActionInvocations
        case cancelActionObservedOnMainThread
        case cancelledManifestState
    }

    func encode(to encoder: Encoder) throws {
        var container = encoder.container(keyedBy: CodingKeys.self)
        try container.encode(status, forKey: .status)
        if let blockReason {
            try container.encode(blockReason, forKey: .blockReason)
        } else {
            try container.encodeNil(forKey: .blockReason)
        }
        try container.encode(observationSurface, forKey: .observationSurface)
        try container.encode(screenLocked, forKey: .screenLocked)
        try container.encode(consoleSessionOnConsole, forKey: .consoleSessionOnConsole)
        try container.encode(nsApplicationRunning, forKey: .nsApplicationRunning)
        try container.encode(windowVisible, forKey: .windowVisible)
        try container.encode(windowIsKey, forKey: .windowIsKey)
        try container.encode(onScreenWindowCount, forKey: .onScreenWindowCount)
        try container.encode(windowTitle, forKey: .windowTitle)
        try container.encode(progressIndicatorRole, forKey: .progressIndicatorRole)
        try container.encode(
            progressIndicatorValueChangesOnMainThread,
            forKey: .progressIndicatorValueChangesOnMainThread
        )
        try container.encode(
            progressLabelChangesOnMainThread,
            forKey: .progressLabelChangesOnMainThread
        )
        try container.encode(progressObservedMainThreadOnly, forKey: .progressObservedMainThreadOnly)
        try container.encode(cancelButtonClass, forKey: .cancelButtonClass)
        try container.encode(cancelButtonActionPath, forKey: .cancelButtonActionPath)
        try container.encode(cancelButtonActionInvocations, forKey: .cancelButtonActionInvocations)
        try container.encode(cancelActionObservedOnMainThread, forKey: .cancelActionObservedOnMainThread)
        try container.encode(cancelledManifestState, forKey: .cancelledManifestState)
    }
}

enum PerformanceInteractionBenchmark {
    static func run(
        root: URL,
        profile: PerformanceProfile
    ) throws -> PerformanceInteractionBenchmarkResult {
        guard Thread.isMainThread else {
            return blocked(profile: profile, reason: "performance-ui-observation-requires-main-thread")
        }
        let session = PerformanceInteractionSession(root: root, profile: profile)
        return session.run()
    }

    private static func blocked(
        profile: PerformanceProfile,
        reason: String
    ) -> PerformanceInteractionBenchmarkResult {
        let thresholds = profile.thresholds
        return PerformanceInteractionBenchmarkResult(
            interactionObservation: PerformanceInteractionObservation(
                heartbeatCount: 0,
                maximumHeartbeatGapMilliseconds: thresholds.mainThreadHeartbeatMilliseconds + 1,
                firstProgressMilliseconds: thresholds.firstProgressMilliseconds + 1,
                maximumProgressGapMilliseconds: thresholds.progressGapMilliseconds + 1,
                progressEventCount: 0,
                cancellationRequestMilliseconds: thresholds.cancellationRequestMilliseconds + 1,
                cancellationCompletionMilliseconds: thresholds.cancellationCompletionMilliseconds + 1,
                responsive: false,
                progressPassed: false,
                cancellationPassed: false
            ),
            uiObservation: PerformanceUIObservation(
                status: "blocked",
                blockReason: reason,
                observationSurface: "AppKit",
                screenLocked: PerformanceConsoleSession.current.screenLocked,
                consoleSessionOnConsole: PerformanceConsoleSession.current.onConsole,
                nsApplicationRunning: false,
                windowVisible: false,
                windowIsKey: false,
                onScreenWindowCount: 0,
                windowTitle: PerformanceObservationSurface.windowTitle,
                progressIndicatorRole: "AXProgressIndicator",
                progressIndicatorValueChangesOnMainThread: 0,
                progressLabelChangesOnMainThread: 0,
                progressObservedMainThreadOnly: true,
                cancelButtonClass: "NSButton",
                cancelButtonActionPath: "NSButton.performClick",
                cancelButtonActionInvocations: 0,
                cancelActionObservedOnMainThread: false,
                cancelledManifestState: "not-run"
            )
        )
    }
}

private struct PerformanceConsoleSession {
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

private final class PerformanceObservationSurface {
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

private final class PerformanceInteractionSession: NSObject {
    private let root: URL
    private let profile: PerformanceProfile
    private let application = NSApplication.shared
    private let surface = PerformanceObservationSurface()
    private let consoleSession = PerformanceConsoleSession.current
    private var result: PerformanceInteractionBenchmarkResult?
    private var heartbeatTimer: Timer?
    private var heartbeatCount = 0
    private var previousHeartbeat = 0.0
    private var maximumHeartbeatGap = 0.0
    private var progressStart = 0.0
    private var progressTimes: [Double] = []
    private var progressIndicatorChanges = 0
    private var progressLabelChanges = 0
    private var progressObservedMainThreadOnly = true
    private var cancellation: BatchExportCancellation?
    private var cancellationRequestedAt: Double?
    private var cancellationRequestDuration = 0.0
    private var cancellationCompletionDuration = 0.0
    private var cancelButtonActionInvocations = 0
    private var cancelActionObservedOnMainThread = false
    private var cancelledManifestState = "not-run"
    private var nsApplicationRunning = false
    private var windowVisible = false
    private var windowIsKey = false
    private var onScreenWindowCount = 0
    private var finished = false

    init(root: URL, profile: PerformanceProfile) {
        self.root = root
        self.profile = profile
        super.init()
        surface.cancelButton.target = self
        surface.cancelButton.action = #selector(cancelFromButton(_:))
    }

    func run() -> PerformanceInteractionBenchmarkResult {
        guard consoleSession.onConsole, !consoleSession.screenLocked else {
            return blocked(reason: consoleSession.screenLocked ? "console-screen-locked" : "console-session-not-active")
        }
        guard !application.isRunning else {
            return blocked(reason: "nested-nsapplication-run-loop-not-supported")
        }

        application.setActivationPolicy(.regular)
        application.finishLaunching()
        application.activate(ignoringOtherApps: true)
        surface.show()
        DispatchQueue.main.asyncAfter(deadline: .now() + 0.2) { [weak self] in
            self?.beginObservation()
        }
        DispatchQueue.main.asyncAfter(deadline: .now() + 60) { [weak self] in
            guard let self, !self.finished else { return }
            self.finishFailure("native-ui-observation-timeout")
        }
        application.run()
        heartbeatTimer?.invalidate()
        surface.window.orderOut(nil)
        surface.window.close()
        return result ?? blocked(reason: "native-ui-observation-ended-without-result")
    }

    private func beginObservation() {
        nsApplicationRunning = application.isRunning
        windowVisible = surface.window.isVisible
        windowIsKey = surface.window.isKeyWindow
        onScreenWindowCount = Self.onScreenWindowCount()
        guard nsApplicationRunning, windowVisible, windowIsKey || onScreenWindowCount > 0 else {
            finishBlocked("appkit-window-not-observable")
            return
        }
        previousHeartbeat = ProcessInfo.processInfo.systemUptime
        let timer = Timer(timeInterval: 0.01, repeats: true) { [weak self] _ in
            guard let self else { return }
            let now = ProcessInfo.processInfo.systemUptime
            self.maximumHeartbeatGap = max(self.maximumHeartbeatGap, (now - self.previousHeartbeat) * 1000)
            self.previousHeartbeat = now
            self.heartbeatCount += 1
        }
        heartbeatTimer = timer
        RunLoop.main.add(timer, forMode: .common)
        progressStart = ProcessInfo.processInfo.systemUptime
        runProgressOperation()
    }

    private func runProgressOperation() {
        DispatchQueue.global(qos: .userInitiated).async { [weak self] in
            guard let self else { return }
            do {
                let manifest = try BatchExportCoordinator().run(
                    request: self.batchRequest(operationID: "performance-ui-progress")
                ) { manifest in
                    DispatchQueue.main.sync {
                        self.observe(manifest: manifest, phase: "진행률")
                        self.progressTimes.append(ProcessInfo.processInfo.systemUptime)
                    }
                }
                DispatchQueue.main.async {
                    guard manifest.state == .completed else {
                        self.finishFailure("progress-operation-\(manifest.state.rawValue)")
                        return
                    }
                    self.runCancellationOperation()
                }
            } catch {
                DispatchQueue.main.async {
                    self.finishFailure("progress-operation-error: \(error.localizedDescription)")
                }
            }
        }
    }

    private func runCancellationOperation() {
        let cancellation = BatchExportCancellation()
        self.cancellation = cancellation
        DispatchQueue.global(qos: .userInitiated).async { [weak self] in
            guard let self else { return }
            do {
                let manifest = try BatchExportCoordinator().run(
                    request: self.batchRequest(operationID: "performance-ui-cancel"),
                    cancellation: cancellation
                ) { manifest in
                    DispatchQueue.main.sync {
                        self.observe(manifest: manifest, phase: "취소")
                        if self.cancelButtonActionInvocations == 0 {
                            self.surface.cancelButton.performClick(nil)
                        }
                    }
                }
                DispatchQueue.main.async {
                    self.cancelledManifestState = manifest.state.rawValue
                    if let requestedAt = self.cancellationRequestedAt {
                        self.cancellationCompletionDuration = (
                            ProcessInfo.processInfo.systemUptime - requestedAt
                        ) * 1000
                    }
                    self.finishObservation()
                }
            } catch {
                DispatchQueue.main.async {
                    self.finishFailure("cancellation-operation-error: \(error.localizedDescription)")
                }
            }
        }
    }

    private func observe(manifest: BatchExportManifest, phase: String) {
        progressObservedMainThreadOnly = progressObservedMainThreadOnly && Thread.isMainThread
        let changes = surface.update(manifest: manifest, phase: phase)
        if changes.progressChanged { progressIndicatorChanges += 1 }
        if changes.labelChanged { progressLabelChanges += 1 }
    }

    @objc private func cancelFromButton(_ sender: NSButton) {
        cancelButtonActionInvocations += 1
        cancelActionObservedOnMainThread = Thread.isMainThread
        let start = ProcessInfo.processInfo.systemUptime
        cancellation?.cancel()
        cancellationRequestDuration = (ProcessInfo.processInfo.systemUptime - start) * 1000
        cancellationRequestedAt = ProcessInfo.processInfo.systemUptime
        sender.isEnabled = false
    }

    private func finishObservation() {
        let firstProgress = progressTimes.first.map { ($0 - progressStart) * 1000 }
            ?? profile.thresholds.firstProgressMilliseconds + 1
        let maximumProgressGap = zip(progressTimes, progressTimes.dropFirst())
            .map { ($1 - $0) * 1000 }
            .max() ?? 0
        let thresholds = profile.thresholds
        let responsive = heartbeatCount > 0
            && maximumHeartbeatGap <= thresholds.mainThreadHeartbeatMilliseconds
        let progressPassed = !progressTimes.isEmpty
            && firstProgress <= thresholds.firstProgressMilliseconds
            && maximumProgressGap <= thresholds.progressGapMilliseconds
        let cancellationPassed = cancelledManifestState == BatchOperationState.cancelled.rawValue
            && cancelButtonActionInvocations == 1
            && cancelActionObservedOnMainThread
            && cancellationRequestDuration <= thresholds.cancellationRequestMilliseconds
            && cancellationCompletionDuration <= thresholds.cancellationCompletionMilliseconds
        let uiPassed = nsApplicationRunning
            && windowVisible
            && (windowIsKey || onScreenWindowCount > 0)
            && progressIndicatorChanges > 0
            && progressLabelChanges > 0
            && progressObservedMainThreadOnly
            && cancellationPassed
        let status = responsive && progressPassed && cancellationPassed && uiPassed ? "pass" : "fail"
        result = makeResult(
            status: status,
            blockReason: nil,
            interaction: PerformanceInteractionObservation(
                heartbeatCount: heartbeatCount,
                maximumHeartbeatGapMilliseconds: maximumHeartbeatGap,
                firstProgressMilliseconds: firstProgress,
                maximumProgressGapMilliseconds: maximumProgressGap,
                progressEventCount: progressTimes.count,
                cancellationRequestMilliseconds: cancellationRequestDuration,
                cancellationCompletionMilliseconds: cancellationCompletionDuration,
                responsive: responsive,
                progressPassed: progressPassed,
                cancellationPassed: cancellationPassed
            )
        )
        surface.finish(status == "pass" ? "UI 응답성·진행률·취소 관찰을 통과했습니다." : "UI 성능 관찰이 기준을 충족하지 못했습니다.")
        finishApplicationLoop()
    }

    private func finishBlocked(_ reason: String) {
        result = blocked(reason: reason)
        surface.finish("UI 관찰을 실행할 수 없습니다: \(reason)")
        finishApplicationLoop()
    }

    private func finishFailure(_ reason: String) {
        let thresholds = profile.thresholds
        result = makeResult(
            status: "fail",
            blockReason: reason,
            interaction: PerformanceInteractionObservation(
                heartbeatCount: heartbeatCount,
                maximumHeartbeatGapMilliseconds: max(
                    maximumHeartbeatGap,
                    thresholds.mainThreadHeartbeatMilliseconds + 1
                ),
                firstProgressMilliseconds: thresholds.firstProgressMilliseconds + 1,
                maximumProgressGapMilliseconds: thresholds.progressGapMilliseconds + 1,
                progressEventCount: progressTimes.count,
                cancellationRequestMilliseconds: thresholds.cancellationRequestMilliseconds + 1,
                cancellationCompletionMilliseconds: thresholds.cancellationCompletionMilliseconds + 1,
                responsive: false,
                progressPassed: false,
                cancellationPassed: false
            )
        )
        surface.finish("UI 성능 관찰 실패: \(reason)")
        finishApplicationLoop()
    }

    private func blocked(reason: String) -> PerformanceInteractionBenchmarkResult {
        let thresholds = profile.thresholds
        return makeResult(
            status: "blocked",
            blockReason: reason,
            interaction: PerformanceInteractionObservation(
                heartbeatCount: heartbeatCount,
                maximumHeartbeatGapMilliseconds: thresholds.mainThreadHeartbeatMilliseconds + 1,
                firstProgressMilliseconds: thresholds.firstProgressMilliseconds + 1,
                maximumProgressGapMilliseconds: thresholds.progressGapMilliseconds + 1,
                progressEventCount: progressTimes.count,
                cancellationRequestMilliseconds: thresholds.cancellationRequestMilliseconds + 1,
                cancellationCompletionMilliseconds: thresholds.cancellationCompletionMilliseconds + 1,
                responsive: false,
                progressPassed: false,
                cancellationPassed: false
            )
        )
    }

    private func makeResult(
        status: String,
        blockReason: String?,
        interaction: PerformanceInteractionObservation
    ) -> PerformanceInteractionBenchmarkResult {
        PerformanceInteractionBenchmarkResult(
            interactionObservation: interaction,
            uiObservation: PerformanceUIObservation(
                status: status,
                blockReason: blockReason,
                observationSurface: "AppKit",
                screenLocked: consoleSession.screenLocked,
                consoleSessionOnConsole: consoleSession.onConsole,
                nsApplicationRunning: nsApplicationRunning,
                windowVisible: windowVisible,
                windowIsKey: windowIsKey,
                onScreenWindowCount: onScreenWindowCount,
                windowTitle: PerformanceObservationSurface.windowTitle,
                progressIndicatorRole: surface.progressIndicator.accessibilityRole()?.rawValue
                    ?? "unavailable",
                progressIndicatorValueChangesOnMainThread: progressIndicatorChanges,
                progressLabelChangesOnMainThread: progressLabelChanges,
                progressObservedMainThreadOnly: progressObservedMainThreadOnly,
                cancelButtonClass: String(describing: type(of: surface.cancelButton)),
                cancelButtonActionPath: "NSButton.performClick",
                cancelButtonActionInvocations: cancelButtonActionInvocations,
                cancelActionObservedOnMainThread: cancelActionObservedOnMainThread,
                cancelledManifestState: cancelledManifestState
            )
        )
    }

    private func finishApplicationLoop() {
        guard !finished else { return }
        finished = true
        heartbeatTimer?.invalidate()
        DispatchQueue.main.asyncAfter(deadline: .now() + 0.25) { [weak self] in
            guard let self else { return }
            self.application.stop(nil)
            if let event = NSEvent.otherEvent(
                with: .applicationDefined,
                location: .zero,
                modifierFlags: [],
                timestamp: ProcessInfo.processInfo.systemUptime,
                windowNumber: 0,
                context: nil,
                subtype: 0,
                data1: 0,
                data2: 0
            ) {
                self.application.postEvent(event, atStart: false)
            }
        }
    }

    private func batchRequest(operationID: String) -> BatchExportRequest {
        BatchExportRequest(
            operationID: operationID,
            retryOfOperationID: nil,
            destination: root.appendingPathComponent(operationID, isDirectory: true),
            documents: [BatchDocumentInput(
                project: PerformanceFixtures.interaction(),
                fileStem: operationID
            )],
            formats: DocumentFormat.allCases,
            flatteningConsent: Set(DocumentFormat.allCases)
        )
    }

    private static func onScreenWindowCount() -> Int {
        let windows = CGWindowListCopyWindowInfo([.optionOnScreenOnly], kCGNullWindowID)
            as? [[String: Any]] ?? []
        let processID = Int(getpid())
        return windows.filter { window in
            (window[kCGWindowOwnerPID as String] as? Int) == processID
                && (window[kCGWindowLayer as String] as? Int ?? 0) == 0
        }.count
    }
}
