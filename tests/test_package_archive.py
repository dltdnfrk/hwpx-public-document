from __future__ import annotations

import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_store_only_archive_reader_rejects_ambiguous_or_corrupt_entries(
    tmp_path: Path,
) -> None:
    runner = tmp_path / "main.swift"
    _ = runner.write_text(
        "\n".join(
            [
                "import Foundation",
                "",
                "func expectRejected(_ label: String, _ operation: () throws -> Void) {",
                "    var rejected = false",
                "    do {",
                "        try operation()",
                "    } catch {",
                "        rejected = true",
                "    }",
                "    precondition(rejected, label)",
                "}",
                "",
                'let path = "word/document.xml"',
                'let payload = Data("<document/>".utf8)',
                "let archive = try PackageArchive.data(parts: [PackagePart(path: path, data: payload)])",
                "let decoded = try PackageArchive.parts(from: archive)",
                'precondition(decoded == [path: payload], "round trip")',
                "",
                "var framed = Data([0xaa, 0xbb])",
                "framed.append(archive)",
                "let slicedDecoded = try PackageArchive.parts(from: framed.dropFirst(2))",
                'precondition(slicedDecoded == [path: payload], "slice")',
                "",
                'expectRejected("writer duplicate") {',
                "    _ = try PackageArchive.data(parts: [",
                '        PackagePart(path: "duplicate", data: payload),',
                '        PackagePart(path: "duplicate", data: payload),',
                "    ])",
                "}",
                "",
                "let oneByte = Data([0x78])",
                "var duplicateArchive = try PackageArchive.data(parts: [",
                '    PackagePart(path: "a", data: oneByte),',
                '    PackagePart(path: "b", data: oneByte),',
                "])",
                "let localRecordLength = 30 + 1 + oneByte.count",
                "let centralDirectoryOffset = localRecordLength * 2",
                "let centralRecordLength = 46 + 1",
                "duplicateArchive[localRecordLength + 30] = 0x61",
                "duplicateArchive[centralDirectoryOffset + centralRecordLength + 46] = 0x61",
                'expectRejected("reader duplicate") {',
                "    _ = try PackageArchive.parts(from: duplicateArchive)",
                "}",
                "",
                "var compressedArchive = archive",
                "compressedArchive[8] = 8",
                "let centralSignature = Data([0x50, 0x4b, 0x01, 0x02])",
                "let centralHeader = compressedArchive.range(of: centralSignature)!.lowerBound",
                "compressedArchive[centralHeader + 10] = 8",
                'expectRejected("compression") {',
                "    _ = try PackageArchive.parts(from: compressedArchive)",
                "}",
                "",
                "var corruptArchive = archive",
                "corruptArchive[30 + Data(path.utf8).count] ^= 0xff",
                'expectRejected("CRC") {',
                "    _ = try PackageArchive.parts(from: corruptArchive)",
                "}",
                "",
                'expectRejected("bounds") {',
                "    _ = try PackageArchive.parts(from: Data(archive.dropLast()))",
                "}",
                "",
                'print("round-trip duplicate compression CRC bounds slice: pass")',
                "",
            ]
        ),
        encoding="utf-8",
    )
    binary = tmp_path / "package-archive-test"
    _ = subprocess.run(
        [
            "swiftc",
            str(ROOT / "Sources" / "PublicDocumentApp" / "PackageArchive.swift"),
            str(ROOT / "Sources" / "PublicDocumentApp" / "PackageArchiveModels.swift"),
            str(ROOT / "Sources" / "PublicDocumentApp" / "PackageArchiveReader.swift"),
            str(ROOT / "Sources" / "PublicDocumentApp" / "PackageArchiveWriter.swift"),
            str(runner),
            "-o",
            str(binary),
        ],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    result = subprocess.run(
        [str(binary)],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    assert result.stdout == "round-trip duplicate compression CRC bounds slice: pass\n"
