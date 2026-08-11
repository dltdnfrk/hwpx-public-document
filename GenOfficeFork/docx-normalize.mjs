import { createHash } from 'node:crypto'
import { readFile, writeFile } from 'node:fs/promises'
import { parseDocx, saveDocx } from '@genoffice/docx-engine'
import JSZip from 'jszip'

class UsageError extends Error {}

const digest = (bytes) => createHash('sha256').update(bytes).digest('hex')
const upstreamCommit = 'd8305ff2dc152593a1ec5639d77e6860c6a512bd'

async function main() {
  const inputPath = process.argv[2]
  const outputPath = process.argv[3]
  const savedAt = process.argv[4]
  if (!inputPath || !outputPath || !savedAt || Number.isNaN(Date.parse(savedAt))) throw new UsageError('usage: genoffice-docx-normalize <input.docx> <output.docx> <savedAt-ISO8601>')
  const input = await readFile(inputPath)
  const parsed = await parseDocx(input)
  const originalBlocks = parsed.blocks.filter((block) => !block.hidden).map((block) => ({ kind: 'original', docxIndex: block.docxIndex }))
  const output = await saveDocx(parsed, originalBlocks, { savedAt })
  await writeFile(outputPath, output)
  const archive = await JSZip.loadAsync(output)
  const preservedPartNames = Object.keys(archive.files).filter((name) => name.startsWith('customXml/') || name === 'word/document.xml').sort()
  process.stdout.write(`${JSON.stringify({ schemaVersion: 1, packageName: '@genoffice/docx-engine', upstreamCommit, savedAt, inputSha256: digest(input), outputSha256: digest(output), blockCount: originalBlocks.length, preservedPartNames })}\n`)
}

main().catch((error) => { // no-excuse-ok: catch
  process.stderr.write(`${error instanceof Error ? error.message : String(error)}\n`)
  process.exitCode = 1
})
