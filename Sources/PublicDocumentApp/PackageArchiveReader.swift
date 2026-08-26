import Foundation

extension PackageArchive {
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
}
