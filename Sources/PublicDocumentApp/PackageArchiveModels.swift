import Foundation

struct PackagePart {
    let path: String
    let data: Data
}

enum PackageArchiveError: Error, LocalizedError {
    case invalidPath(String)
    case duplicatePath(String)
    case oversizedPart(String)
    case invalidArchive(String)
    case unsupportedCompression(String)
    case checksumMismatch(String)

    var errorDescription: String? {
        switch self {
        case .invalidPath(let path):
            return "패키지 경로가 올바르지 않습니다: \(path)"
        case .duplicatePath(let path):
            return "패키지 경로가 중복되었습니다: \(path)"
        case .oversizedPart(let path):
            return "패키지 항목이 ZIP32 범위를 초과합니다: \(path)"
        case .invalidArchive(let detail):
            return "ZIP 패키지 구조가 올바르지 않습니다: \(detail)"
        case .unsupportedCompression(let path):
            return "저장 방식이 아닌 ZIP 압축 항목은 지원하지 않습니다: \(path)"
        case .checksumMismatch(let path):
            return "ZIP 항목 체크섬이 일치하지 않습니다: \(path)"
        }
    }
}
