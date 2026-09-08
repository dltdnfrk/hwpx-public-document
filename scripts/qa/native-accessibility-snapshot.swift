import ApplicationServices
import Foundation

guard CommandLine.arguments.count == 2,
      let pid = Int32(CommandLine.arguments[1])
else {
    FileHandle.standardError.write(Data("usage: native-accessibility-snapshot.swift <pid>\n".utf8))
    exit(2)
}

guard AXIsProcessTrusted() else {
    FileHandle.standardError.write(Data("Accessibility permission is not granted\n".utf8))
    exit(3)
}

func attribute(_ element: AXUIElement, _ name: CFString) -> CFTypeRef? {
    var value: CFTypeRef?
    let status = AXUIElementCopyAttributeValue(element, name, &value)
    return status == .success ? value : nil
}

func textAttribute(_ element: AXUIElement, _ name: CFString) -> String {
    guard let value = attribute(element, name) else { return "" }
    return String(describing: value)
        .replacingOccurrences(of: "\t", with: " ")
        .replacingOccurrences(of: "\r", with: " ")
        .replacingOccurrences(of: "\n", with: " ")
}

func children(_ element: AXUIElement) -> [AXUIElement] {
    let direct = attribute(
        element,
        kAXChildrenAttribute as CFString
    ) as? [AXUIElement] ?? []
    let windows = attribute(
        element,
        kAXWindowsAttribute as CFString
    ) as? [AXUIElement] ?? []
    let focusedWindow = attribute(
        element,
        kAXFocusedWindowAttribute as CFString
    ).flatMap { $0 as! AXUIElement? }
    let mainWindow = attribute(
        element,
        kAXMainWindowAttribute as CFString
    ).flatMap { $0 as! AXUIElement? }
    return direct + windows + [focusedWindow, mainWindow].compactMap { $0 }
}

var count = 0
var visited: Set<CFHashCode> = []
func walk(_ element: AXUIElement, depth: Int) {
    guard count < 10_000, depth < 100 else { return }
    guard visited.insert(CFHash(element)).inserted else { return }
    count += 1
    let fields = [
        String(depth),
        textAttribute(element, kAXRoleAttribute as CFString),
        textAttribute(element, kAXTitleAttribute as CFString),
        textAttribute(element, kAXDescriptionAttribute as CFString),
        textAttribute(element, kAXValueAttribute as CFString),
        textAttribute(element, kAXIdentifierAttribute as CFString),
    ]
    print(fields.joined(separator: "\t"))
    for child in children(element) {
        walk(child, depth: depth + 1)
    }
}

walk(AXUIElementCreateApplication(pid), depth: 0)
guard count > 1 else {
    FileHandle.standardError.write(Data("packaged app exposed no accessibility descendants\n".utf8))
    exit(4)
}
