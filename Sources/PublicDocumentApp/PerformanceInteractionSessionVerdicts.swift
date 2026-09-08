import AppKit
import CoreGraphics
import Foundation

extension PerformanceInteractionSession {
    func finishObservation() {
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

    func finishBlocked(_ reason: String) {
        result = blocked(reason: reason)
        surface.finish("UI 관찰을 실행할 수 없습니다: \(reason)")
        finishApplicationLoop()
    }

    func finishFailure(_ reason: String) {
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

    func blocked(reason: String) -> PerformanceInteractionBenchmarkResult {
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

    func makeResult(
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

    func endObservationActivity() {
        guard let observationActivity else { return }
        ProcessInfo.processInfo.endActivity(observationActivity)
        self.observationActivity = nil
    }

    func finishApplicationLoop() {
        guard !finished else { return }
        finished = true
        heartbeatTimer?.invalidate()
        endObservationActivity()
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

    func batchRequest(operationID: String) -> BatchExportRequest {
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

    static func onScreenWindowCount() -> Int {
        let windows = CGWindowListCopyWindowInfo([.optionOnScreenOnly], kCGNullWindowID)
            as? [[String: Any]] ?? []
        let processID = Int(getpid())
        return windows.filter { window in
            (window[kCGWindowOwnerPID as String] as? Int) == processID
                && (window[kCGWindowLayer as String] as? Int ?? 0) == 0
        }.count
    }
}
