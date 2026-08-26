import Foundation

extension PackageArchive {
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
}

private extension Data {
    mutating func appendLittleEndian<T: FixedWidthInteger>(_ value: T) {
        var littleEndian = value.littleEndian
        Swift.withUnsafeBytes(of: &littleEndian) { append(contentsOf: $0) }
    }
}
