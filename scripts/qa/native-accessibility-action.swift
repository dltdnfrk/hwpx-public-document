import ApplicationServices
import Foundation

guard CommandLine.arguments.count == 4,
      let pid = Int32(CommandLine.arguments[1])
else {
    FileHandle.standardError.write(
        Data("usage: native-accessibility-action.swift <pid> <press|focus> <title>\n".utf8)
    )
    exit(2)
}

guard AXIsProcessTrusted() else {
    FileHandle.standardError.write(Data("Accessibility permission is not granted\n".utf8))
    exit(3)
}

let action = CommandLine.arguments[2]
let targetTitle = CommandLine.arguments[3]

func attribute(_ element: AXUIElement, _ name: CFString) -> CFTypeRef? {
    var value: CFTypeRef?
    let status = AXUIElementCopyAttributeValue(element, name, &value)
    return status == .success ? value : nil
}

func text(_ element: AXUIElement, _ name: CFString) -> String {
    guard let value = attribute(element, name) else { return "" }
    return String(describing: value)
}

func related(_ element: AXUIElement) -> [AXUIElement] {
    let names = [
        kAXChildrenAttribute,
        kAXWindowsAttribute,
        kAXContentsAttribute,
    ] as [CFString]
    var elements = names.flatMap {
        attribute(element, $0) as? [AXUIElement] ?? []
    }
    for name in [kAXFocusedWindowAttribute, kAXMainWindowAttribute] as [CFString] {
        if let value = attribute(element, name) {
            elements.append(value as! AXUIElement)
        }
    }
    return elements
}

var visited: Set<CFHashCode> = []
func find(_ element: AXUIElement) -> AXUIElement? {
    guard visited.insert(CFHash(element)).inserted else { return nil }
    let title = text(element, kAXTitleAttribute as CFString)
    let description = text(element, kAXDescriptionAttribute as CFString)
    if title == targetTitle || description == targetTitle {
        return element
    }
    for child in related(element) {
        if let match = find(child) { return match }
    }
    return nil
}

guard let target = find(AXUIElementCreateApplication(pid)) else {
    FileHandle.standardError.write(Data("AX target not found: \(targetTitle)\n".utf8))
    exit(4)
}

let status: AXError
switch action {
case "press":
    status = AXUIElementPerformAction(target, kAXPressAction as CFString)
case "focus":
    status = AXUIElementSetAttributeValue(
        target,
        kAXFocusedAttribute as CFString,
        kCFBooleanTrue
    )
default:
    FileHandle.standardError.write(Data("unsupported AX action: \(action)\n".utf8))
    exit(2)
}

guard status == .success else {
    FileHandle.standardError.write(
        Data("AX action failed: \(status.rawValue) \(targetTitle)\n".utf8)
    )
    exit(5)
}

let role = text(target, kAXRoleAttribute as CFString)
print("\(action)\t\(role)\t\(targetTitle)")
