import SwiftUI

@main
struct PublicDocumentApp: App {
    var body: some Scene {
        WindowGroup("공공문서") {
            DocumentWorkspace()
        }
    }
}

struct DocumentWorkspace: View {
    @State private var title = "정책·기획 문서"
    @State private var period = ""
    @State private var audience = ""
    @State private var consentGranted = false

    var body: some View {
        NavigationStack {
            Form {
                Section("문서 식별") {
                    TextField("제목", text: $title)
                    TextField("기간", text: $period)
                    TextField("대상", text: $audience)
                }
                Section("외부 제공 동의") {
                    Toggle("선택한 문서만 외부 AI에 전송 허용", isOn: $consentGranted)
                    Text(consentGranted ? "동의됨: 선택한 문서 범위에서만 전송됩니다." : "동의 없음: 로컬 초안 작성만 사용할 수 있습니다.")
                        .foregroundStyle(consentGranted ? .green : .secondary)
                }
                Section("상태") {
                    Label("HWPX 편집 가능한 초안", systemImage: "doc.richtext")
                    Label("최대 5쪽 export gate", systemImage: "checkmark.shield")
                }
            }
            .formStyle(.grouped)
            .navigationTitle("공공문서 작업공간")
            .frame(minWidth: 560, minHeight: 420)
        }
    }
}
