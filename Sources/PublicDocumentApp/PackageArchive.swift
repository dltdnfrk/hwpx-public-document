import Foundation

enum PackageArchive {
    static func validate(path: String) throws {
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

    static func isValidRange(offset: Int, length: Int, count: Int) -> Bool {
        offset >= 0 && length >= 0 && offset <= count && length <= count - offset
    }

    static func subdata(in data: Data, at offset: Int, length: Int) -> Data {
        let lowerBound = data.startIndex + offset
        return data.subdata(in: lowerBound..<(lowerBound + length))
    }

    static func uint16(in data: Data, at offset: Int) throws -> UInt16 {
        guard isValidRange(offset: offset, length: 2, count: data.count) else {
            throw PackageArchiveError.invalidArchive("16비트 필드 범위")
        }
        let start = data.startIndex + offset
        return UInt16(data[start]) | (UInt16(data[start + 1]) << 8)
    }

    static func uint32(in data: Data, at offset: Int) throws -> UInt32 {
        guard isValidRange(offset: offset, length: 4, count: data.count) else {
            throw PackageArchiveError.invalidArchive("32비트 필드 범위")
        }
        let start = data.startIndex + offset
        return UInt32(data[start])
            | (UInt32(data[start + 1]) << 8)
            | (UInt32(data[start + 2]) << 16)
            | (UInt32(data[start + 3]) << 24)
    }

    static func int32(in data: Data, at offset: Int) throws -> Int {
        Int(try uint32(in: data, at: offset))
    }

    static func crc32(_ data: Data) -> UInt32 {
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
