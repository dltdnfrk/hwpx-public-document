from __future__ import annotations

import json
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_studio_exposes_easy_hangul_tools_on_enabled_ribbon_tabs() -> None:
    studio = ROOT / "Resources" / "Studio"
    html = (studio / "index.html").read_text(encoding="utf-8")
    script = (studio / "app.js").read_text(encoding="utf-8")
    library = (studio / "easy-library.js").read_text(encoding="utf-8")
    commands = (studio / "editor-commands.js").read_text(encoding="utf-8")
    state = (studio / "studio-state.js").read_text(encoding="utf-8")
    css = (studio / "styles.css").read_text(encoding="utf-8")

    assert 'src="easy-tools.js"' in html
    assert 'src="app.js"' in html
    assert html.index('src="easy-tools.js"') < html.index('src="app.js"')
    assert 'data-tab="insert"' in html
    assert 'data-tab="table"' in html
    assert 'data-tab="layout"' in html
    assert 'id="insert-tools"' in html
    assert 'id="table-tools"' in html
    assert 'id="layout-tools"' in html
    assert 'data-easy-action="insert-date"' in html
    assert 'data-easy-action="insert-date-range"' in html
    assert 'data-easy-action="insert-currency"' in html
    assert 'data-easy-action="normalize-markers"' in html
    assert 'data-easy-action="apply-official-block"' in html
    assert 'data-easy-action="apply-marker"' in html
    assert 'data-easy-action="insert-attachment"' in html
    assert 'data-easy-action="insert-end-mark"' in html
    assert 'data-easy-action="insert-report-structure"' in html
    assert 'data-easy-report="one-page"' in html
    assert 'data-easy-report="long-report"' in html
    assert 'data-easy-margin="official"' in html
    assert 'data-easy-action="insert-my-form"' in html
    assert 'data-easy-action="save-my-form"' in html
    assert 'data-easy-action="insert-table"' in html
    assert 'data-easy-action="add-table-row"' in html
    assert 'data-easy-action="clean-table"' in html
    assert 'data-easy-action="set-table-borders"' in html
    assert 'data-easy-action="set-table-fill"' in html
    assert 'data-easy-action="page-margins"' in html
    assert 'data-easy-action="hanging-indent"' in html
    assert 'data-easy="autosave-interval"' in html
    assert 'toggle-favorite' in script
    assert 'data-easy-action' in script
    assert 'data-easy-action="save-library"' in html
    assert 'data-easy-action="merge-library"' in html
    assert 'aria-labelledby="easy-tool-title"' in html
    assert 'aria-label="네모 글머리 적용"' in html
    assert 'aria-label="원 글머리 적용"' in html
    assert 'aria-label="바 글머리 적용"' in html
    assert 'aria-label="참고 글머리 적용"' in html
    assert 'aria-label="낫표로 묶기"' in html
    assert 'PublicDocumentEasyTools' in script
    assert "saveStudioPrefs" in script
    assert "saveLibraryDocument" in script
    assert "loadLibraryDocument" in script
    assert "localISODate" in script
    assert "revisionTimestamp" in script
    assert "insertTargetIndex" in script
    assert "elementsFromTemplate(plan" in script
    assert "libraryEntries = [" in script
    assert "libraryProjects[project.documentID] = project" in script
    assert "libraryProjects[documentID]" in script
    assert "input.selectedIndex = 0" in script
    assert "value: libraryEntries[0].documentID" in script
    assert "const fields = readEasyFields()" in script
    assert script.index("const fields = readEasyFields()") < script.index("closeDialog(easyToolDialog)")
    assert "종료일은 시작일 이후여야 합니다" in script
    assert "숫자 금액을 입력하세요" in script
    assert "data-easy-table" in script
    assert "isStaleBridgeProject" in script
    assert "revisionAncestors" in script
    assert "applyBridgeProject" in script
    assert "hangingIndentTargetIndex" in script
    assert "element-section-${index + 1}-body" in script
    assert "text: tablePlainText(html)" in script
    assert ".trim() || '표'" not in script
    assert "tablePlainText" in script
    assert "preserveTableMarkup" in script
    assert "tables.length === 1" in script
    assert "easyUndoStack" in state
    assert "easyRedoStack" in state
    assert "undoEasyProjectChange" in library
    assert "redoEasyProjectChange" in library
    assert "studio.undoEasyProjectChange" in commands
    assert "studio.redoEasyProjectChange" in commands
    assert ".ribbon[hidden]" in css
    assert "--easy-page-pad-top" in css
    assert ".page-preview-sheet th, .page-preview-sheet td { border: 1px solid var(--studio-document-rule)" in css
    assert ".page-preview-sheet th { background: var(--studio-document-fill)" in css
    assert 'data-tab="view"' in html
    assert html.count("disabled aria-disabled=\"true\"") == 0


def test_render_decorators_forward_easy_history_preservation_argument() -> None:
    studio = ROOT / "Resources" / "Studio"
    for name in ("view-tab.js", "title-lock.js", "review-tab.js"):
        source = (studio / name).read_text(encoding="utf-8")
        assert "studio.renderProject = (...args) =>" in source, name
        assert "previousRender" in source
        assert "previousRenderProject" in source or "previousRender(...args)" in source
        assert "(...args)" in source, name


def test_empty_project_event_clears_easy_history() -> None:
    events = ROOT / "Resources" / "Studio" / "studio-events.js"
    script = f"""
    const fs = require('fs');
    const vm = require('vm');
    const state = {{ easyUndoStack: [1], easyRedoStack: [2] }};
    const inert = {{
      hidden: false, open: false,
      querySelector: () => ({{ textContent: '', disabled: false, hidden: false }}),
    }};
    const studio = {{
      state,
      dom: {{
        aiProposalReview: inert,
        batchExportProgress: inert,
        byokSettings: inert,
        aiWorkspace: inert,
      }},
      initialProject: () => ({{ documentID: 'empty' }}),
      projectBridge: () => {{}},
      renderProject: () => {{}},
      announce: () => {{}},
      officialRuleWarning: () => '',
    }};
    const sandbox = {{
      console,
      document: {{ querySelector: () => ({{ value: '', checked: false }}) }},
      window: {{ PublicDocumentStudio: studio }},
    }};
    vm.runInNewContext(fs.readFileSync({json.dumps(str(events))}, 'utf8'), sandbox);
    const results = [];
    for (const event of ['empty', 'opened', 'recovered']) {{
      state.easyUndoStack = [event];
      state.easyRedoStack = [event];
      sandbox.window.projectStoreReceive({{
        event,
        payload: {{ project: {{ documentID: event }}, officialRuleState: null }},
      }});
      results.push([event, state.easyUndoStack.length, state.easyRedoStack.length]);
    }}
    process.stdout.write(JSON.stringify(results));
    """
    result = subprocess.run(
        ["node", "--input-type=commonjs", "-e", script],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=30,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    assert json.loads(result.stdout) == [
        ["empty", 0, 0],
        ["opened", 0, 0],
        ["recovered", 0, 0],
    ]


def test_normal_editor_change_invalidates_easy_tool_undo_history() -> None:
    library = ROOT / "Resources" / "Studio" / "easy-library.js"
    project_render = ROOT / "Resources" / "Studio" / "project-render.js"
    script = f"""
    const fs = require('fs');
    const vm = require('vm');
    const crypto = require('crypto').webcrypto;
    const project = {{
      documentID: 'document-undo-order',
      currentRevisionID: 'revision-1',
      elements: [{{ elementID: 'body', kind: 'paragraph', order: 0, text: 'before' }}],
      revisions: [],
      history: [],
    }};
    const state = {{
      currentProject: project,
      easyUndoStack: [],
      easyRedoStack: [],
      focusedEditorElementID: 'body',
    }};
    const messages = [];
    const editorListeners = {{}};
    const titleListeners = {{}};
    const editor = {{
      addEventListener: (name, handler) => {{ editorListeners[name] = handler; }},
    }};
    const titleInput = {{
      addEventListener: (name, handler) => {{ titleListeners[name] = handler; }},
    }};
    const studio = {{
      state,
      dom: {{
        page: {{}}, editor, titleInput,
        outlineList: {{}}, checklist: {{}}, templatePanel: {{}},
        inspector: {{}}, aiProposalReview: {{ hidden: false }},
      }},
      fallbackProjectElements: () => state.currentProject.elements,
      projectElements: () => state.currentProject.elements,
      isEasyTableElement: () => false,
      initialProject: () => project,
      revisionTimestamp: () => '2026-08-29T00:00:00Z',
      renderProject: (next) => {{ state.currentProject = next; }},
      projectBridge: () => {{}},
      announce: (message) => {{ messages.push(message); }},
      isTitleElement: () => false,
      runEditorCommand: () => false,
      easyTools: () => null,
      tablePlainText: () => '',
      isLocalWeb: () => true,
    }};
    const sandbox = {{
      console, crypto, structuredClone, TextEncoder,
      CSS: {{ escape: (value) => value }},
      document: {{
        querySelectorAll: () => [],
        querySelector: () => ({{ addEventListener: () => {{}} }}),
      }},
      window: {{
        PublicDocumentStudio: studio,
        clearTimeout: () => {{}},
        setTimeout: () => 1,
        requestAnimationFrame: (callback) => callback(),
      }},
    }};
    vm.runInNewContext(fs.readFileSync({json.dumps(str(library))}, 'utf8'), sandbox);
    studio.commitProjectElements(
      [{{ elementID: 'body', kind: 'paragraph', order: 0, text: 'easy change' }}],
      'easy-change',
      'changed',
    );
    if (state.easyUndoStack.length !== 1) throw new Error('easy undo snapshot missing');
    vm.runInNewContext(fs.readFileSync({json.dumps(str(project_render))}, 'utf8'), sandbox);
    state.editorReady = true;
    editorListeners['public-document-genoffice-change']({{ detail: {{ elements: [] }} }});
    const editorDepth = state.easyUndoStack.length;
    const productionRender = studio.renderProject;
    studio.renderProject = (next) => {{ state.currentProject = next; }};
    studio.commitProjectElements(
      [{{ elementID: 'body', kind: 'paragraph', order: 0, text: 'second easy change' }}],
      'easy-change',
      'changed',
    );
    studio.renderProject = productionRender;
    titleListeners.input();
    process.stdout.write(JSON.stringify({{
      editorDepth,
      undoDepth: state.easyUndoStack.length,
      redoDepth: state.easyRedoStack.length,
      undoHandled: studio.undoEasyProjectChange(),
    }}));
    """
    result = subprocess.run(
        ["node", "--input-type=commonjs", "-e", script],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    assert json.loads(result.stdout) == {
        "editorDepth": 0,
        "undoDepth": 0,
        "redoDepth": 0,
        "undoHandled": False,
    }


def test_editor_command_undo_and_redo_restore_distinct_projects() -> None:
    library = ROOT / "Resources" / "Studio" / "easy-library.js"
    commands = ROOT / "Resources" / "Studio" / "editor-commands.js"
    script = f"""
    const fs = require('fs');
    const vm = require('vm');
    const crypto = require('crypto').webcrypto;
    const project = {{
      documentID: 'document-undo-redo',
      currentRevisionID: 'revision-1',
      elements: [{{ elementID: 'body', kind: 'paragraph', order: 0, text: 'before' }}],
      revisions: [], history: [],
    }};
    const state = {{
      currentProject: project,
      easyUndoStack: [], easyRedoStack: [],
      focusedEditorElementID: 'body', editorReady: false,
    }};
    const bridges = [];
    const inert = {{
      addEventListener: () => {{}},
      setAttribute: () => {{}},
      classList: {{ toggle: () => false }},
    }};
    const studio = {{
      state,
      dom: {{ editor: {{}}, workspace: inert, outlineToggle: inert, outlineList: inert }},
      compactLayout: {{ matches: false, addEventListener: () => {{}} }},
      fallbackProjectElements: () => state.currentProject.elements,
      projectElements: () => state.currentProject.elements,
      isEasyTableElement: () => false,
      initialProject: () => project,
      revisionTimestamp: () => '2026-08-29T00:00:00Z',
      renderProject: (next) => {{ state.currentProject = next; }},
      projectBridge: (action, value) => {{ bridges.push([action, value.elements[0].text]); }},
      announce: () => {{}},
      isTitleElement: () => false,
      easyTools: () => null,
      tablePlainText: () => '',
      isLocalWeb: () => true,
    }};
    const sandbox = {{
      console, crypto, structuredClone, TextEncoder,
      HTMLElement: class {{}},
      document: {{
        querySelectorAll: () => [],
        querySelector: () => inert,
        addEventListener: () => {{}},
      }},
      window: {{ PublicDocumentStudio: studio }},
    }};
    vm.runInNewContext(fs.readFileSync({json.dumps(str(library))}, 'utf8'), sandbox);
    vm.runInNewContext(fs.readFileSync({json.dumps(str(commands))}, 'utf8'), sandbox);
    studio.commitProjectElements(
      [{{ elementID: 'body', kind: 'paragraph', order: 0, text: 'after' }}],
      'easy-change',
      'changed',
    );
    const undoHandled = studio.runEditorCommand('undo');
    const afterUndo = state.currentProject.elements[0].text;
    const redoHandled = studio.runEditorCommand('redo');
    const afterRedo = state.currentProject.elements[0].text;
    process.stdout.write(JSON.stringify({{
      undoHandled, afterUndo, redoHandled, afterRedo, bridges,
    }}));
    """
    result = subprocess.run(
        ["node", "--input-type=commonjs", "-e", script],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=30,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    assert json.loads(result.stdout) == {
        "undoHandled": True,
        "afterUndo": "before",
        "redoHandled": True,
        "afterRedo": "after",
        "bridges": [["save", "after"], ["save", "before"], ["save", "after"]],
    }


def test_easy_tool_undo_history_is_bounded_by_count_and_size() -> None:
    library = ROOT / "Resources" / "Studio" / "easy-library.js"
    script = f"""
    const fs = require('fs');
    const vm = require('vm');
    const crypto = require('crypto').webcrypto;
    const project = {{
      documentID: 'document-history-bound',
      currentRevisionID: 'revision-1',
      elements: [{{ elementID: 'body', kind: 'paragraph', order: 0, text: 'before' }}],
      revisions: [],
      history: [],
    }};
    const state = {{
      currentProject: project,
      easyUndoStack: [],
      easyRedoStack: [],
      focusedEditorElementID: 'body',
    }};
    const messages = [];
    const studio = {{
      state,
      fallbackProjectElements: () => state.currentProject.elements,
      projectElements: () => state.currentProject.elements,
      isEasyTableElement: () => false,
      initialProject: () => project,
      revisionTimestamp: () => '2026-08-29T00:00:00Z',
      renderProject: (next) => {{ state.currentProject = next; }},
      projectBridge: () => {{}},
      announce: (message) => {{ messages.push(message); }},
      isTitleElement: () => false,
      runEditorCommand: () => false,
      easyTools: () => null,
      tablePlainText: () => '',
      isLocalWeb: () => true,
    }};
    const sandbox = {{
      console, crypto, structuredClone, TextEncoder,
      window: {{ PublicDocumentStudio: studio }},
    }};
    vm.runInNewContext(fs.readFileSync({json.dumps(str(library))}, 'utf8'), sandbox);
    for (let index = 0; index < 30; index += 1) {{
      studio.commitProjectElements(
        [{{ elementID: 'body', kind: 'paragraph', order: 0, text: `change ${{index}}` }}],
        'easy-change',
        'changed',
      );
    }}
    const boundedDepth = state.easyUndoStack.length;
    state.currentProject = {{
      ...state.currentProject,
      elements: [{{
        elementID: 'body',
        kind: 'paragraph',
        order: 0,
        text: 'x'.repeat(8 * 1024 * 1024 + 1),
      }}],
      revisions: [],
      history: [],
    }};
    const oversizedCommitted = studio.commitProjectElements(
      [{{ elementID: 'body', kind: 'paragraph', order: 0, text: 'small' }}],
      'easy-change',
      'changed',
    );
    const undoHandled = studio.undoEasyProjectChange();
    process.stdout.write(JSON.stringify({{
      boundedDepth,
      oversizedDepth: state.easyUndoStack.length,
      oversizedCommitted,
      undoHandled,
      currentTextLength: state.currentProject.elements[0].text.length,
      warningCount: messages.filter((message) => message.includes('실행하지 않았습니다')).length,
    }}));
    """
    result = subprocess.run(
        ["node", "--input-type=commonjs", "-e", script],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=30,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    assert json.loads(result.stdout) == {
        "boundedDepth": 20,
        "oversizedDepth": 20,
        "oversizedCommitted": False,
        "undoHandled": False,
        "currentTextLength": 8 * 1024 * 1024 + 1,
        "warningCount": 2,
    }
