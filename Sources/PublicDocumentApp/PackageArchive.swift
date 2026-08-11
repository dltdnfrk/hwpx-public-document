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

enum PackageArchive {
    static func data(parts: [PackagePart]) throws -> Data {
        var archive = Data()
        var centralDirectory = Data()
        var paths: Set<String> = []
        for part in parts {
            try validate(path: part.path)
            guard paths.insert(part.path).inserted else {
                throw PackageArchiveError.duplicatePath(part.path)
            }
            guard
                let name = part.path.data(using: .utf8),
                name.count <= Int(UInt16.max),
                part.data.count <= Int(UInt32.max),
                archive.count <= Int(UInt32.max)
            else {
                throw PackageArchiveError.oversizedPart(part.path)
            }
            let checksum = crc32(part.data)
            let offset = UInt32(archive.count)
            let size = UInt32(part.data.count)
            archive.appendLittleEndian(UInt32(0x04034b50))
            archive.appendLittleEndian(UInt16(20))
            archive.appendLittleEndian(UInt16(0x0800))
            archive.appendLittleEndian(UInt16(0))
            archive.appendLittleEndian(UInt16(0))
            archive.appendLittleEndian(UInt16(0x0021))
            archive.appendLittleEndian(checksum)
            archive.appendLittleEndian(size)
            archive.appendLittleEndian(size)
            archive.appendLittleEndian(UInt16(name.count))
            archive.appendLittleEndian(UInt16(0))
            archive.append(name)
            archive.append(part.data)

            centralDirectory.appendLittleEndian(UInt32(0x02014b50))
            centralDirectory.appendLittleEndian(UInt16(20))
            centralDirectory.appendLittleEndian(UInt16(20))
            centralDirectory.appendLittleEndian(UInt16(0x0800))
            centralDirectory.appendLittleEndian(UInt16(0))
            centralDirectory.appendLittleEndian(UInt16(0))
            centralDirectory.appendLittleEndian(UInt16(0x0021))
            centralDirectory.appendLittleEndian(checksum)
            centralDirectory.appendLittleEndian(size)
            centralDirectory.appendLittleEndian(size)
            centralDirectory.appendLittleEndian(UInt16(name.count))
            centralDirectory.appendLittleEndian(UInt16(0))
            centralDirectory.appendLittleEndian(UInt16(0))
            centralDirectory.appendLittleEndian(UInt16(0))
            centralDirectory.appendLittleEndian(UInt16(0))
            centralDirectory.appendLittleEndian(UInt32(0))
            centralDirectory.appendLittleEndian(offset)
            centralDirectory.append(name)
        }
        guard
            parts.count <= Int(UInt16.max),
            centralDirectory.count <= Int(UInt32.max),
            archive.count <= Int(UInt32.max)
        else {
            throw PackageArchiveError.oversizedPart("central-directory")
        }
        let directoryOffset = UInt32(archive.count)
        archive.append(centralDirectory)
        archive.appendLittleEndian(UInt32(0x06054b50))
        archive.appendLittleEndian(UInt16(0))
        archive.appendLittleEndian(UInt16(0))
        archive.appendLittleEndian(UInt16(parts.count))
        archive.appendLittleEndian(UInt16(parts.count))
        archive.appendLittleEndian(UInt32(centralDirectory.count))
        archive.appendLittleEndian(directoryOffset)
        archive.appendLittleEndian(UInt16(0))
        return archive
    }

    static func parts(from data: Data) throws -> [String: Data] {
        let endRecordOffset = try endOfCentralDirectoryOffset(in: data)
        let diskNumber = try uint16(in: data, at: endRecordOffset + 4)
        let centralDirectoryDisk = try uint16(in: data, at: endRecordOffset + 6)
        let entriesOnDisk = try uint16(in: data, at: endRecordOffset + 8)
        let entryCount = try uint16(in: data, at: endRecordOffset + 10)
        let centralDirectorySize = try int32(in: data, at: endRecordOffset + 12)
        let centralDirectoryOffset = try int32(in: data, at: endRecordOffset + 16)

        guard diskNumber == 0, centralDirectoryDisk == 0, entriesOnDisk == entryCount else {
            throw PackageArchiveError.invalidArchive("다중 디스크 ZIP")
        }
        guard
            entryCount != UInt16.max,
            centralDirectorySize != Int(UInt32.max),
            centralDirectoryOffset != Int(UInt32.max)
        else {
            throw PackageArchiveError.invalidArchive("ZIP64")
        }
        guard
            isValidRange(
                offset: centralDirectoryOffset,
                length: centralDirectorySize,
                count: data.count
            ),
            centralDirectoryOffset + centralDirectorySize == endRecordOffset
        else {
            throw PackageArchiveError.invalidArchive("중앙 디렉터리 범위")
        }

        var result: [String: Data] = [:]
        var localRanges: [Range<Int>] = []
        var cursor = centralDirectoryOffset
        let centralDirectoryEnd = centralDirectoryOffset + centralDirectorySize

        for _ in 0..<Int(entryCount) {
            guard
                isValidRange(offset: cursor, length: 46, count: centralDirectoryEnd),
                try uint32(in: data, at: cursor) == 0x02014b50
            else {
                throw PackageArchiveError.invalidArchive("중앙 디렉터리 항목")
            }

            let flags = try uint16(in: data, at: cursor + 8)
            let compression = try uint16(in: data, at: cursor + 10)
            let expectedChecksum = try uint32(in: data, at: cursor + 16)
            let compressedSize = try int32(in: data, at: cursor + 20)
            let uncompressedSize = try int32(in: data, at: cursor + 24)
            let nameLength = Int(try uint16(in: data, at: cursor + 28))
            let extraLength = Int(try uint16(in: data, at: cursor + 30))
            let commentLength = Int(try uint16(in: data, at: cursor + 32))
            let startingDisk = try uint16(in: data, at: cursor + 34)
            let localHeaderOffset = try int32(in: data, at: cursor + 42)
            let recordLength = 46 + nameLength + extraLength + commentLength

            guard isValidRange(offset: cursor, length: recordLength, count: centralDirectoryEnd) else {
                throw PackageArchiveError.invalidArchive("중앙 디렉터리 항목 범위")
            }
            let nameData = subdata(in: data, at: cursor + 46, length: nameLength)
            guard let path = String(data: nameData, encoding: .utf8) else {
                throw PackageArchiveError.invalidArchive("UTF-8 항목 이름")
            }
            try validate(path: path)
            guard result[path] == nil else {
                throw PackageArchiveError.duplicatePath(path)
            }
            guard startingDisk == 0 else {
                throw PackageArchiveError.invalidArchive("다중 디스크 항목: \(path)")
            }
            guard flags & ~UInt16(0x0800) == 0 else {
                throw PackageArchiveError.invalidArchive("지원하지 않는 항목 플래그: \(path)")
            }
            guard compression == 0 else {
                throw PackageArchiveError.unsupportedCompression(path)
            }
            guard compressedSize == uncompressedSize else {
                throw PackageArchiveError.invalidArchive("저장 항목 크기: \(path)")
            }

            let localEntry = try localEntry(
                in: data,
                at: localHeaderOffset,
                before: centralDirectoryOffset,
                expectedName: nameData,
                expectedFlags: flags,
                expectedChecksum: expectedChecksum,
                expectedSize: compressedSize,
                path: path
            )
            guard crc32(localEntry.data) == expectedChecksum else {
                throw PackageArchiveError.checksumMismatch(path)
            }
            result[path] = localEntry.data
            localRanges.append(localEntry.range)
            cursor += recordLength
        }

        guard cursor == centralDirectoryEnd else {
            throw PackageArchiveError.invalidArchive("중앙 디렉터리 항목 수")
        }
        let orderedRanges = localRanges.sorted { $0.lowerBound < $1.lowerBound }
        for (previous, next) in zip(orderedRanges, orderedRanges.dropFirst()) where previous.upperBound > next.lowerBound {
            throw PackageArchiveError.invalidArchive("겹치는 로컬 항목")
        }
        return result
    }

    private static func localEntry(
        in archive: Data,
        at offset: Int,
        before centralDirectoryOffset: Int,
        expectedName: Data,
        expectedFlags: UInt16,
        expectedChecksum: UInt32,
        expectedSize: Int,
        path: String
    ) throws -> (data: Data, range: Range<Int>) {
        guard
            isValidRange(offset: offset, length: 30, count: centralDirectoryOffset),
            try uint32(in: archive, at: offset) == 0x04034b50
        else {
            throw PackageArchiveError.invalidArchive("로컬 항목 헤더: \(path)")
        }

        let flags = try uint16(in: archive, at: offset + 6)
        let compression = try uint16(in: archive, at: offset + 8)
        let checksum = try uint32(in: archive, at: offset + 14)
        let compressedSize = try int32(in: archive, at: offset + 18)
        let uncompressedSize = try int32(in: archive, at: offset + 22)
        let nameLength = Int(try uint16(in: archive, at: offset + 26))
        let extraLength = Int(try uint16(in: archive, at: offset + 28))
        let headerLength = 30 + nameLength + extraLength

        guard
            flags == expectedFlags,
            flags & ~UInt16(0x0800) == 0,
            compression == 0
        else {
            throw PackageArchiveError.unsupportedCompression(path)
        }
        guard
            checksum == expectedChecksum,
            compressedSize == expectedSize,
            uncompressedSize == expectedSize,
            isValidRange(offset: offset, length: headerLength, count: centralDirectoryOffset)
        else {
            throw PackageArchiveError.invalidArchive("로컬 항목 메타데이터: \(path)")
        }
        let localName = subdata(in: archive, at: offset + 30, length: nameLength)
        guard localName == expectedName else {
            throw PackageArchiveError.invalidArchive("로컬 항목 이름: \(path)")
        }
        let dataOffset = offset + headerLength
        guard isValidRange(offset: dataOffset, length: expectedSize, count: centralDirectoryOffset) else {
            throw PackageArchiveError.invalidArchive("로컬 항목 데이터 범위: \(path)")
        }
        let end = dataOffset + expectedSize
        return (subdata(in: archive, at: dataOffset, length: expectedSize), offset..<end)
    }

    private static func endOfCentralDirectoryOffset(in data: Data) throws -> Int {
        guard data.count >= 22 else {
            throw PackageArchiveError.invalidArchive("종료 레코드 없음")
        }
        let earliestOffset = max(0, data.count - 22 - Int(UInt16.max))
        for offset in stride(from: data.count - 22, through: earliestOffset, by: -1) {
            guard try uint32(in: data, at: offset) == 0x06054b50 else { continue }
            let commentLength = Int(try uint16(in: data, at: offset + 20))
            if offset + 22 + commentLength == data.count { return offset }
        }
        throw PackageArchiveError.invalidArchive("종료 레코드 없음")
    }

    private static func validate(path: String) throws {
        let components = path.split(separator: "/", omittingEmptySubsequences: false)
        guard
            !path.isEmpty,
            !path.hasPrefix("/"),
            !path.hasSuffix("/"),
            !path.contains("\\"),
            !path.unicodeScalars.contains(where: { $0.value == 0 }),
            components.allSatisfy({ !$0.isEmpty && $0 != "." && $0 != ".." })
        else {
            throw PackageArchiveError.invalidPath(path)
        }
    }

    private static func isValidRange(offset: Int, length: Int, count: Int) -> Bool {
        offset >= 0 && length >= 0 && offset <= count && length <= count - offset
    }

    private static func subdata(in data: Data, at offset: Int, length: Int) -> Data {
        let lowerBound = data.startIndex + offset
        return data.subdata(in: lowerBound..<(lowerBound + length))
    }

    private static func uint16(in data: Data, at offset: Int) throws -> UInt16 {
        guard isValidRange(offset: offset, length: 2, count: data.count) else {
            throw PackageArchiveError.invalidArchive("16비트 필드 범위")
        }
        let start = data.startIndex + offset
        return UInt16(data[start]) | (UInt16(data[start + 1]) << 8)
    }

    private static func uint32(in data: Data, at offset: Int) throws -> UInt32 {
        guard isValidRange(offset: offset, length: 4, count: data.count) else {
            throw PackageArchiveError.invalidArchive("32비트 필드 범위")
        }
        let start = data.startIndex + offset
        return UInt32(data[start])
            | (UInt32(data[start + 1]) << 8)
            | (UInt32(data[start + 2]) << 16)
            | (UInt32(data[start + 3]) << 24)
    }

    private static func int32(in data: Data, at offset: Int) throws -> Int {
        Int(try uint32(in: data, at: offset))
    }

    private static func crc32(_ data: Data) -> UInt32 {
        var checksum = UInt32.max
        for byte in data {
            checksum ^= UInt32(byte)
            for _ in 0..<8 {
                let mask = UInt32(bitPattern: -Int32(checksum & 1))
                checksum = (checksum >> 1) ^ (0xedb88320 & mask)
            }
        }
        return checksum ^ UInt32.max
    }
}

private extension Data {
    mutating func appendLittleEndian<T: FixedWidthInteger>(_ value: T) {
        var littleEndian = value.littleEndian
        Swift.withUnsafeBytes(of: &littleEndian) { append(contentsOf: $0) }
    }
}
