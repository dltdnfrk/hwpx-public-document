#!/bin/sh
set -eu

root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
destination=${1:-"$root/Resources/Engines/rhwp"}
commit=2dced7bfe10c6597cead634264c7c1781c01f1e7
cargo_lock_sha256=64ff4041c1874c01c7a901b28df2639082836ced44df392cd37b3227d4772279
contract_streams_sha256=daedc635befbcf06486b1c41ec67dfa6510e66f8707b5c41d93b56bfeb45f781
hwpx_to_hwp_sha256=2ce236705aa981d58434214956cef9b723fd2dee84a301a4ef21acb4a1de2ef3
mini_cfb_sha256=21cae90a3bf750a9d2dd005b8381d33f15311c88671f8639ad0673b7a10289f5
source_root=$(mktemp -d "${TMPDIR:-/tmp}/public-document-rhwp.XXXXXX")

cleanup() {
    case "$source_root" in
        "${TMPDIR:-/tmp}"/public-document-rhwp.*) rm -rf -- "$source_root" ;;
        *) printf '%s\n' "refusing to clean unexpected path: $source_root" >&2 ;;
    esac
}
trap cleanup EXIT INT TERM

git -C "$source_root" init -q
git -C "$source_root" remote add origin https://github.com/edwardkim/rhwp.git
git -C "$source_root" -c protocol.version=2 fetch --depth=1 --filter=blob:none origin "$commit"
git -C "$source_root" sparse-checkout init --no-cone
git -C "$source_root" sparse-checkout set \
    /src/ \
    /tools/rhwp-subsecond/ \
    /examples/ \
    /saved/blank2010.hwp \
    /Cargo.toml \
    /Cargo.lock \
    /rust-toolchain.toml
git -C "$source_root" checkout --detach FETCH_HEAD
test "$(git -C "$source_root" rev-parse HEAD)" = "$commit"
test "$(shasum -a 256 "$source_root/Cargo.lock" | awk '{print $1}')" = "$cargo_lock_sha256"
git -C "$source_root" apply - <<'PATCH'
diff --git a/src/document_core/converters/hwpx_to_hwp.rs b/src/document_core/converters/hwpx_to_hwp.rs
index a4751d7..4a2cc38 100644
--- a/src/document_core/converters/hwpx_to_hwp.rs
+++ b/src/document_core/converters/hwpx_to_hwp.rs
@@ -69,6 +69,8 @@ pub struct AdapterReport {
     pub bin_data_order_materialized: u32,
     /// `Control::SectionDef` 컨트롤 삽입 횟수 (Stage 4 — 섹션 개수)
     pub section_def_controls_inserted: u32,
+    /// HWPX SectionDef의 누락된 EVEN/ODD page-border slots 보강 횟수
+    pub section_def_page_border_fill_slots_materialized: u32,
     /// HWPX `hp:pic@href` 를 HWP CTRL_DATA ParameterSet 으로 materialize한 횟수
     pub picture_href_ctrl_data_materialized: u32,
     /// HWPX 3x2 row-break table의 HWP5 layout CTRL_DATA ParameterSet materialize 횟수
@@ -139,6 +141,7 @@ impl AdapterReport {
                 + self.bin_data_metadata_normalized
                 + self.bin_data_order_materialized
                 + self.section_def_controls_inserted
+                + self.section_def_page_border_fill_slots_materialized
                 + self.picture_href_ctrl_data_materialized
                 + self.table_layout_ctrl_data_materialized
                 + self.text_box_list_header_tail_materialized
@@ -1120,6 +1123,12 @@ fn materialize_para_header_tail(para: &mut Paragraph, report: &mut AdapterReport
 }
 
 fn adapt_section_def(section_def: &mut SectionDef, report: &mut AdapterReport) {
+    while section_def.extra_page_border_fills.len() < 2 {
+        section_def
+            .extra_page_border_fills
+            .push(section_def.page_border_fill.clone());
+        report.section_def_page_border_fill_slots_materialized += 1;
+    }
     materialize_section_def_hide_empty_line_flag(section_def, report);
     materialize_single_master_page_flags(section_def, report);
     materialize_multi_master_page_flags(section_def, report);
@@ -1226,13 +1235,13 @@ fn materialize_section_def_master_page_tail(
     section_def: &mut SectionDef,
     report: &mut AdapterReport,
 ) {
-    if section_def.master_pages.is_empty() || !section_def.raw_ctrl_extra.is_empty() {
+    if !section_def.raw_ctrl_extra.is_empty() {
         return;
     }
 
-    // HWPX 출처 SectionDef는 HWP 원본 CTRL_HEADER tail이 없지만, 한컴이 HWPX를
-    // HWP5로 저장한 정답지는 바탕쪽이 있는 구역에서 대표Language(0) 뒤에
-    // 17 byte 확장 영역을 붙여 총 43 byte ctrl_data (CTRL_HEADER 47 byte)를 만든다.
+    // HWPX 출처 SectionDef는 HWP 원본 CTRL_HEADER tail이 없지만, 한컴 HWP5 5.1은
+    // 대표Language(0) 뒤에 17 byte 확장 영역을 붙여 총 43 byte ctrl_data
+    // (CTRL_HEADER 47 byte)를 만든다. 바탕쪽이 없는 구역도 같은 zero tail을 쓴다.
     //
     // 관찰된 계약:
     // - exam_kor: masterPageCnt=3 -> 0x0001 marker + 15 byte zero
diff --git a/src/parser/hwpx/contract_streams.rs b/src/parser/hwpx/contract_streams.rs
index 7d6c707..02eeb38 100644
--- a/src/parser/hwpx/contract_streams.rs
+++ b/src/parser/hwpx/contract_streams.rs
@@ -114,12 +114,10 @@ pub(super) fn extract_contract_streams(reader: &mut HwpxReader) -> ContractStrea
     // [Stage 2.2] HWPX 컨테이너에 동등 데이터가 없는 contract 3 스트림 fallback.
     // 한컴 정답지가 모든 HWP 파일에 요구하는 최소 OLE Property Set / 메타.
     //
-    // 주의: 스트림 경로는 OLE 표준의 `\x05` 선두 prefix (Property Set 표시) 가
-    // 정답지의 실제 이름이나, mini_cfb 가 path 형식으로 처리하므로 일반
-    // ASCII path 로 작성 후 한컴이 정상 인식. form-01 정답지의 실제 경로
-    // `\x05HwpSummaryInformation` 와 byte-level 차이는 Stage 2.3 검증.
+    // OLE property-set streams require the U+0005 name prefix used by the
+    // blank2010 reference. Some consumers do not recognize the ASCII-only name.
     streams.push((
-        "/HwpSummaryInformation".to_string(),
+        "/\u{0005}HwpSummaryInformation".to_string(),
         FALLBACK_HWP_SUMMARY.to_vec(),
     ));
     streams.push((
diff --git a/src/serializer/mini_cfb.rs b/src/serializer/mini_cfb.rs
index f964968..1e766a1 100644
--- a/src/serializer/mini_cfb.rs
+++ b/src/serializer/mini_cfb.rs
@@ -133,6 +133,10 @@ pub fn build_cfb(named_streams: &[(&str, &[u8])]) -> Result<Vec<u8>, String> {
         mini_fat_start = next_sector;
         mini_fat_sector_count =
             ((mini_fat.len() + FAT_ENTRIES_PER_SECTOR - 1) / FAT_ENTRIES_PER_SECTOR) as u32;
+        mini_fat.resize(
+            mini_fat_sector_count as usize * FAT_ENTRIES_PER_SECTOR,
+            FREESECT,
+        );
         next_sector += mini_fat_sector_count;
     } else {
         mini_fat_start = ENDOFCHAIN;
@@ -172,7 +176,7 @@ pub fn build_cfb(named_streams: &[(&str, &[u8])]) -> Result<Vec<u8>, String> {
     let total_sectors = non_meta_sectors + fat_count + difat_count;
 
     // 5. FAT 구축
-    let mut fat = vec![FREESECT; total_sectors as usize];
+    let mut fat = vec![FREESECT; fat_count as usize * FAT_ENTRIES_PER_SECTOR];
 
     // 디렉토리 체인
     for i in 0..dir_sectors {
@@ -255,6 +259,10 @@ pub fn build_cfb(named_streams: &[(&str, &[u8])]) -> Result<Vec<u8>, String> {
         let offset = 512 + sector_idx * SECTOR_SIZE + entry_in_sector * DIR_ENTRY_SIZE;
         write_dir_entry(&mut output, offset, entry);
     }
+    for i in entries.len()..dir_sectors * ENTRIES_PER_DIR_SECTOR {
+        let offset = 512 + i * DIR_ENTRY_SIZE;
+        output[offset + 68..offset + 80].fill(0xFF);
+    }
 
     // 큰 스트림 데이터 작성
     for entry in &entries {
@@ -514,10 +522,10 @@ fn write_dir_entry(output: &mut [u8], offset: usize, entry: &DirEntry) {
     // State bits — 이미 0
 
     // Creation/Modified time (FILETIME, 8 bytes each)
-    // Root Entry(5)와 Storage(1)에 고정 타임스탬프 설정
+    // Storage(1)에 고정 타임스탬프 설정; Root Entry(5)는 CFB 사양상 zero 유지
     // WASM에서 SystemTime::now()를 사용할 수 없으므로 고정값 사용
     // 2024-01-01 00:00:00 UTC ≈ 0x01DA5E8B_80000000
-    if entry.obj_type == 5 || entry.obj_type == 1 {
+    if entry.obj_type == 1 {
         let filetime: u64 = 0x01DA_5E8B_8000_0000;
         let ft_bytes = filetime.to_le_bytes();
         buf[100..108].copy_from_slice(&ft_bytes); // Creation time
PATCH
test "$(shasum -a 256 "$source_root/src/document_core/converters/hwpx_to_hwp.rs" | awk '{print $1}')" = "$hwpx_to_hwp_sha256"
test "$(shasum -a 256 "$source_root/src/parser/hwpx/contract_streams.rs" | awk '{print $1}')" = "$contract_streams_sha256"
test "$(shasum -a 256 "$source_root/src/serializer/mini_cfb.rs" | awk '{print $1}')" = "$mini_cfb_sha256"
cargo build --locked --manifest-path "$source_root/Cargo.toml" --release --bin rhwp
mkdir -p "$(dirname -- "$destination")"
cp "$source_root/target/release/rhwp" "$destination"
chmod 755 "$destination"
test "$(lipo -archs "$destination")" = "arm64"
printf '%s\n' "$destination"
