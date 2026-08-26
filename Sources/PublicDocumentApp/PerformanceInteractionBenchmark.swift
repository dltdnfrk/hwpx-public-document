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
