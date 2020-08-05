import * as vscode from 'vscode';

const decorationTypeParseable = vscode.window.createTextEditorDecorationType({
	backgroundColor: '#21bf2b' //ff5959
})

const decorationTypeUnparseable = vscode.window.createTextEditorDecorationType({
	backgroundColor: '#8f1713' //138f34
})

var json = [{error_position: {startLine: 1, startColumn: 5, endLine: 1, endColumn: 9},
error_type: "REPLACEMENT",
replacedFrom: "WITH",
replacedTo: "BY"}]

// this method is called when the extension is activated
export function activate(context: vscode.ExtensionContext) {
	// The command has been defined in the package.json file
	let disposable = vscode.commands.registerCommand('vscode-query-breakdown.run', () => {
		// Display a message box to the user
		vscode.window.showInformationMessage('vscode_query_breakdown is running!');
		var currentEditor = vscode.window.activeTextEditor
		if (!currentEditor) {
			vscode.window.showInformationMessage('there is no editor open currently');
			return
		}

		// highlights and creates hovers for queries
		decorate(currentEditor)
	});

	context.subscriptions.push(disposable);
}

function decorate(editor: vscode.TextEditor) {
	let decorationUnparseableArray: vscode.DecorationOptions[] = []
	let decorationParseableArray: vscode.DecorationOptions[] = []

	// parses through the json objects
	for (let i = 0; i < json.length; i++) {
		// finds error position
		let errorRange = new vscode.Range(json[i].error_position.startLine, json[i].error_position.startColumn,
			json[i].error_position.endLine, json[i].error_position.endColumn)

		// deletion case
		if (json[i].error_type === "DELETION") {
			let deletionMessage = new vscode.MarkdownString("Deleted")
			decorationUnparseableArray.push({ range: errorRange, hoverMessage: deletionMessage })
		}
		// replacement case
		else if (json[i].error_type === "REPLACEMENT") {
			let replacementMessage = new vscode.MarkdownString("Replaced " + json[i].replacedFrom + " with " + json[i].replacedTo)
			decorationUnparseableArray.push({ range: errorRange, hoverMessage: replacementMessage })
		}
		else {
			// error handling
			continue
		}
	}

	// constructs decoration option for entire document
	let entireDocument = new vscode.Range(editor.document.lineAt(0).range.start,
	editor.document.lineAt(editor.document.lineCount - 1).range.end)
	decorationParseableArray.push({ range: entireDocument })

	// sets the decorations
	editor.setDecorations(decorationTypeParseable, decorationParseableArray)
	editor.setDecorations(decorationTypeUnparseable, decorationUnparseableArray)
}

// this method is called when your extension is deactivated
export function deactivate() {}
