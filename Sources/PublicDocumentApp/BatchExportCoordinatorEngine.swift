import Foundation

extension BatchExportCoordinator {
    func injectProcessFailure(_ fault: BatchExportFault, item: BatchExportItem) throws {
        if case .processFailure(let documentID, let format) = fault,
           documentID == item.documentID, format == item.format {
            throw BatchExportError.injectedProcessFailure
        }
    }

    func injectBeforeInitialManifest(_ fault: BatchExportFault) throws {
        if case .crashBeforeInitialManifest = fault {
            throw BatchExportError.simulatedCrash
        }
    }

    func injectBeforePublication(_ fault: BatchExportFault) throws {
        switch fault {
        case .crashBeforePublication: throw BatchExportError.simulatedCrash
        case .diskFullBeforePublication: throw CocoaError(.fileWriteOutOfSpace)
        case .none, .processFailure, .crashBeforeInitialManifest,
             .crashAfterPublicationMove: return
        }
    }

    func injectAfterPublicationMove(_ fault: BatchExportFault) throws {
        if case .crashAfterPublicationMove = fault {
            throw BatchExportError.simulatedCrash
        }
    }

    func destinationExists(_ error: ExportError) -> Bool {
        if case .destinationExists = error { return true }
        return false
    }

    func failed(
        _ manifest: BatchExportManifest,
        at index: Int,
        code: String,
        message: String
    ) -> BatchExportManifest {
        replacing(
            manifest,
            at: index,
            with: manifest.items[index].updating(
                state: .failed,
                progressCompleted: manifest.items[index].progressCompleted,
                diagnosticCode: code,
                diagnosticMessage: message
            )
        )
    }

    func cancelRemaining(
        _ manifest: BatchExportManifest,
        startingAt index: Int
    ) -> BatchExportManifest {
        var items = manifest.items
        for itemIndex in index..<items.count {
            items[itemIndex] = items[itemIndex].updating(
                state: .cancelled,
                progressCompleted: items[itemIndex].progressCompleted,
                diagnosticCode: "user-cancelled",
                diagnosticMessage: "사용자가 내보내기를 취소했습니다."
            )
        }
        return manifest.updating(items: items)
    }

    func replacing(
        _ manifest: BatchExportManifest,
        at index: Int,
        with item: BatchExportItem
    ) -> BatchExportManifest {
        var items = manifest.items
        items[index] = item
        return manifest.updating(items: items)
    }
}
