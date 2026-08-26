import Foundation

extension BatchExportSelfTest {
    static func crashAfterMoveRecovery(
        root: URL,
        coordinator: BatchExportCoordinator
    ) throws -> BatchExportManifest {
        let operationID = "batch-ac06-crash-after-move"
        let fixture = fixtures()[0]
        try expectCrash {
            _ = try coordinator.run(
                request: request(
                    operationID: operationID,
                    root: root,
                    documents: [BatchDocumentInput(
                        project: fixture.project,
                        fileStem: "생활안전-사후이동"
                    )],
                    formats: [.docx]
                ),
                execution: BatchExportExecution(
                    fault: .crashAfterPublicationMove,
                    cancelAfterPublishedCount: nil
                )
            )
        }
        return try coordinator.recover(destination: root, operationID: operationID)
    }

    static func startupRecovery(
        root: URL,
        coordinator: BatchExportCoordinator
    ) throws -> [BatchExportManifest] {
        let fixture = fixtures()[0]
        try expectCrash {
            _ = try coordinator.run(
                request: request(
                    operationID: "batch-ac06-pre-manifest",
                    root: root,
                    documents: [BatchDocumentInput(
                        project: fixture.project,
                        fileStem: "생활안전-사전매니페스트"
                    )],
                    formats: [.docx]
                ),
                execution: BatchExportExecution(
                    fault: .crashBeforeInitialManifest,
                    cancelAfterPublishedCount: nil
                )
            )
        }
        try expectCrash {
            _ = try coordinator.run(
                request: request(
                    operationID: "batch-ac06-startup-recoverable",
                    root: root,
                    documents: [BatchDocumentInput(
                        project: fixture.project,
                        fileStem: "생활안전-시작복구"
                    )],
                    formats: [.docx]
                ),
                execution: BatchExportExecution(
                    fault: .crashBeforePublication,
                    cancelAfterPublishedCount: nil
                )
            )
        }
        return try coordinator.recoverInterrupted(destination: root)
    }

    static func expectCrash(_ operation: () throws -> Void) throws {
        do {
            try operation()
        } catch BatchExportError.simulatedCrash {
            return
        }
        throw ExportError.invalidPackage("시험용 비정상 종료가 발생하지 않았습니다.")
    }
}
