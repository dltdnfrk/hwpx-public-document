import AppKit
import Foundation

final class PerformanceInteractionSession: NSObject {
    let root: URL
    let profile: PerformanceProfile
    let application = NSApplication.shared
    let surface = PerformanceObservationSurface()
    let consoleSession = PerformanceConsoleSession.current
    var result: PerformanceInteractionBenchmarkResult?
    var heartbeatTimer: Timer?
    var heartbeatCount = 0
    var previousHeartbeat = 0.0
    var maximumHeartbeatGap = 0.0
    var progressStart = 0.0
    var progressTimes: [Double] = []
    var progressIndicatorChanges = 0
    var progressLabelChanges = 0
    var progressObservedMainThreadOnly = true
    var cancellation: BatchExportCancellation?
    var cancellationRequestedAt: Double?
    var cancellationRequestDuration = 0.0
    var cancellationCompletionDuration = 0.0
    var cancelButtonActionInvocations = 0
    var cancelActionObservedOnMainThread = false
    var cancelledManifestState = "not-run"
    var nsApplicationRunning = false
    var windowVisible = false
    var windowIsKey = false
    var onScreenWindowCount = 0
    var finished = false

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

    func beginObservation() {
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

    func runProgressOperation() {
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

    func runCancellationOperation() {
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

    func observe(manifest: BatchExportManifest, phase: String) {
        progressObservedMainThreadOnly = progressObservedMainThreadOnly && Thread.isMainThread
        let changes = surface.update(manifest: manifest, phase: phase)
        if changes.progressChanged { progressIndicatorChanges += 1 }
        if changes.labelChanged { progressLabelChanges += 1 }
    }

    @objc func cancelFromButton(_ sender: NSButton) {
        cancelButtonActionInvocations += 1
        cancelActionObservedOnMainThread = Thread.isMainThread
        let start = ProcessInfo.processInfo.systemUptime
        cancellation?.cancel()
        cancellationRequestDuration = (ProcessInfo.processInfo.systemUptime - start) * 1000
        cancellationRequestedAt = ProcessInfo.processInfo.systemUptime
        sender.isEnabled = false
    }
}
