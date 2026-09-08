import AppKit
import Darwin

final class PublicDocumentStudioApp: NSObject, NSApplicationDelegate {
    private var studioWindowController: StudioWindowController?

    static func run() {
        let arguments = CommandLine.arguments
        if arguments.count == 2, arguments[1] == "--ai-bridge-stdin" {
            let input = FileHandle.standardInput.readDataToEndOfFile()
            FileHandle.standardOutput.write(AIBridgeCLI.run(input: input))
            FileHandle.standardOutput.write(Data("\n".utf8))
            return
        }
        if arguments.count == 3, arguments[1] == "--ai-settings-self-test" {
            do {
                let receipt = try AISettingsSelfTest.run(
                    at: URL(fileURLWithPath: arguments[2], isDirectory: true)
                )
                try ProjectSelfTest.printJSON(receipt)
                return
            } catch {
                FileHandle.standardError.write(Data("\(error.localizedDescription)\n".utf8))
                Darwin.exit(EXIT_FAILURE)
            }
        }
        if arguments.count == 3, arguments[1] == "--studio-host-security-self-test" {
            do {
                let application = NSApplication.shared
                application.setActivationPolicy(.prohibited)
                application.finishLaunching()
                let receipt = try StudioHostSecuritySelfTest(
                    resourcesRoot: URL(fileURLWithPath: arguments[2], isDirectory: true)
                ).run()
                try ProjectSelfTest.printJSON(receipt)
                return
            } catch {
                FileHandle.standardError.write(Data("\(error.localizedDescription)\n".utf8))
                Darwin.exit(EXIT_FAILURE)
            }
        }
        if arguments.count == 3, arguments[1] == "--ai-governance-self-test" {
            do {
                let receipt = try AIGovernanceSelfTest.run(at: URL(fileURLWithPath: arguments[2]))
                try ProjectSelfTest.printJSON(receipt)
                return
            } catch {
                FileHandle.standardError.write(Data("\(error)\n".utf8))
                Darwin.exit(EXIT_FAILURE)
            }
        }
        if arguments.count == 3, arguments[1] == "--template-catalog-self-test" {
            do {
                let receipt = try TemplateCatalogSelfTest.run(at: URL(fileURLWithPath: arguments[2]))
                try ProjectSelfTest.printJSON(receipt)
                return
            } catch {
                FileHandle.standardError.write(Data("\(error)\n".utf8))
                Darwin.exit(EXIT_FAILURE)
            }
        }
        if arguments.count == 3, arguments[1] == "--export-official-samples" {
            do {
                try OfficialStyleSamples.export(to: URL(fileURLWithPath: arguments[2], isDirectory: true))
                return
            } catch {
                FileHandle.standardError.write(Data("\(error)\n".utf8))
                Darwin.exit(EXIT_FAILURE)
            }
        }
        if arguments.count == 4, arguments[1] == "--rhwp-compile-self-test" {
            do {
                let project = try JSONDecoder().decode(
                    DocumentProject.self,
                    from: Data(contentsOf: URL(fileURLWithPath: arguments[2]))
                )
                let output = URL(fileURLWithPath: arguments[3])
                let data = try RhwpExportAdapter().export(
                    project: project,
                    format: .hwpx,
                    workingDirectory: output.deletingLastPathComponent()
                )
                try data.write(to: output, options: .withoutOverwriting)
                return
            } catch {
                FileHandle.standardError.write(Data("\(error.localizedDescription)\n".utf8))
                Darwin.exit(EXIT_FAILURE)
            }
        }
        if arguments.count == 5, arguments[1] == "--official-layout-profile-self-test" {
            do {
                let receipt = try OfficialLayoutProfileSelfTest.run(
                    toolkit: URL(fileURLWithPath: arguments[2]),
                    tokens: URL(fileURLWithPath: arguments[3]),
                    output: URL(fileURLWithPath: arguments[4])
                )
                FileHandle.standardOutput.write(
                    try JSONSerialization.data(withJSONObject: receipt, options: [.sortedKeys])
                )
                FileHandle.standardOutput.write(Data("\n".utf8))
                return
            } catch {
                FileHandle.standardError.write(Data("\(error.localizedDescription)\n".utf8))
                Darwin.exit(EXIT_FAILURE)
            }
        }
        if arguments.count >= 4, arguments[1] == "--export-project" {
            do {
                let project = try JSONDecoder().decode(
                    DocumentProject.self,
                    from: Data(contentsOf: URL(fileURLWithPath: arguments[2]))
                )
                var formats: [DocumentFormat] = [.docx, .hwpx]
                var consent = false
                var index = 4
                while index < arguments.count {
                    if arguments[index] == "--formats", index + 1 < arguments.count {
                        formats = arguments[index + 1]
                            .split(separator: ",")
                            .compactMap { DocumentFormat(rawValue: String($0)) }
                        index += 2
                    } else if arguments[index] == "--flattening-consent" {
                        consent = true
                        index += 1
                    } else {
                        index += 1
                    }
                }
                guard !formats.isEmpty else { throw ExportError.noFormatSelected }
                let receipt = try DocumentExportEngine().export(
                    project: project,
                    request: ExportRequest(
                        operationID: "web-export-\(UUID().uuidString)",
                        destination: URL(fileURLWithPath: arguments[3], isDirectory: true),
                        formats: formats,
                        flatteningConsent: consent ? Set(formats) : []
                    )
                )
                try ProjectSelfTest.printJSON(receipt)
                Darwin.exit(EXIT_SUCCESS)
            } catch {
                FileHandle.standardError.write(Data("\(error)\n".utf8))
                Darwin.exit(EXIT_FAILURE)
            }
        }
        if arguments.count == 3, arguments[1] == "--verify-template-catalog-envelope" {
            do {
                let envelope = try Data(contentsOf: URL(fileURLWithPath: arguments[2]))
                let store = try TemplateCatalogStore(
                    root: FileManager.default.temporaryDirectory,
                    bundledEnvelope: envelope
                )
                try ProjectSelfTest.printJSON(store.verifiedCatalog(from: envelope))
                return
            } catch {
                FileHandle.standardError.write(Data("\(error)\n".utf8))
                Darwin.exit(EXIT_FAILURE)
            }
        }
        if arguments.count == 3, arguments[1] == "--project-store-self-test" {
            do {
                let receipt = try ProjectSelfTest.runLifecycle(at: URL(fileURLWithPath: arguments[2]))
                try ProjectSelfTest.printJSON(receipt)
                return
            } catch {
                FileHandle.standardError.write(Data("\(error)\n".utf8))
                Darwin.exit(EXIT_FAILURE)
            }
        }
        if arguments.count == 3, arguments[1] == "--project-migration-self-test" {
            do {
                let receipt = try ProjectSelfTest.runMigration(at: URL(fileURLWithPath: arguments[2]))
                try ProjectSelfTest.printJSON(receipt)
                return
            } catch {
                FileHandle.standardError.write(Data("\(error)\n".utf8))
                Darwin.exit(EXIT_FAILURE)
            }
        }
        if arguments.count == 4, arguments[1] == "--export-self-test" {
            do {
                guard let scenario = ExportSelfTestScenario(rawValue: arguments[3]) else {
                    throw ExportError.invalidPackage("알 수 없는 내보내기 자체 시험")
                }
                let receipt = try ExportSelfTest.run(
                    at: URL(fileURLWithPath: arguments[2], isDirectory: true),
                    scenario: scenario
                )
                try ProjectSelfTest.printJSON(receipt)
                return
            } catch {
                FileHandle.standardError.write(Data("\(error)\n".utf8))
                Darwin.exit(EXIT_FAILURE)
            }
        }
        if arguments.count == 4, arguments[1] == "--batch-export-self-test" {
            do {
                guard let scenario = BatchExportSelfTestScenario(rawValue: arguments[3]) else {
                    throw ExportError.invalidPackage("알 수 없는 배치 내보내기 자체 시험")
                }
                let root = URL(fileURLWithPath: arguments[2], isDirectory: true)
                switch scenario {
                case .partialFailure, .cancelAfterFirst, .cancelBeforePublication, .existingDestination:
                    try ProjectSelfTest.printJSON(BatchExportSelfTest.run(at: root, scenario: scenario))
                case .crashAndRetry, .diskFullAndRetry:
                    try ProjectSelfTest.printJSON(BatchExportSelfTest.runRecovery(at: root, scenario: scenario))
                }
                return
            } catch {
                FileHandle.standardError.write(Data("\(error)\n".utf8))
                Darwin.exit(EXIT_FAILURE)
            }
        }
        if arguments.count == 3, arguments[1] == "--compatibility-self-test" {
            do {
                let receipt = try CompatibilitySelfTest.run(
                    at: URL(fileURLWithPath: arguments[2], isDirectory: true)
                )
                try ProjectSelfTest.printJSON(receipt)
                return
            } catch {
                FileHandle.standardError.write(Data("\(error.localizedDescription)\n".utf8))
                Darwin.exit(EXIT_FAILURE)
            }
        }
        if arguments.count == 3, arguments[1] == "--performance-self-test" {
            do {
                let receipt = try PerformanceSelfTest.run(
                    at: URL(fileURLWithPath: arguments[2], isDirectory: true)
                )
                try ProjectSelfTest.printJSON(receipt)
                return
            } catch {
                FileHandle.standardError.write(Data("\(error.localizedDescription)\n".utf8))
                Darwin.exit(EXIT_FAILURE)
            }
        }
        if arguments.count == 4, arguments[1] == "--verify-compatibility-observations" {
            do {
                let receipt = try CompatibilitySelfTest.verify(
                    receipt: URL(fileURLWithPath: arguments[2]),
                    observations: URL(fileURLWithPath: arguments[3])
                )
                try ProjectSelfTest.printJSON(receipt)
                return
            } catch {
                FileHandle.standardError.write(Data("\(error.localizedDescription)\n".utf8))
                Darwin.exit(EXIT_FAILURE)
            }
        }
        let application = NSApplication.shared
        let delegate = PublicDocumentStudioApp()
        application.delegate = delegate
        application.setActivationPolicy(.regular)
        application.finishLaunching()
        if arguments.count == 2, arguments[1] == "--window-lifecycle-self-test" {
            DispatchQueue.main.asyncAfter(deadline: .now() + 0.5) {
                let receipt = WindowLifecycleSelfTestReceipt(
                    visibleWindowCount: application.windows.filter(\.isVisible).count
                )
                try? ProjectSelfTest.printJSON(receipt)
                application.terminate(nil)
            }
        }
        application.run()
    }

    func applicationDidFinishLaunching(_ notification: Notification) {
        do {
            let controller = try StudioWindowController.make()
            studioWindowController = controller
            controller.showWindow(nil)
            NSApplication.shared.activate(ignoringOtherApps: true)
        } catch {
            FileHandle.standardError.write(Data("\(error.localizedDescription)\n".utf8))
            NSApplication.shared.terminate(nil)
        }
    }

    func applicationShouldTerminateAfterLastWindowClosed(_ sender: NSApplication) -> Bool {
        true
    }
}

PublicDocumentStudioApp.run()
