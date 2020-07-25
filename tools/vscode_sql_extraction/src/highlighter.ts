import * as path from 'path';
import * as vscode from 'vscode';
import {Query, locationToRange} from './query';
import randomColor from 'randomcolor';

/**
 * Highlights found queries in the text editor.
 */
export class Highlighter {
  decorations: vscode.TextEditorDecorationType[] = [];

  /**
   * Highlights all queries in the open document.
   * @param openEditor currently open editor.
   * @param workspaceRoot root path of the open workspace.
   * @param queries list of found queries.
   */
  highlight(
    openEditor: vscode.TextEditor,
    workspaceRoot: string,
    queries: Query[]
  ) {
    let openPath = openEditor.document.uri.path.toString();
    if (!path.isAbsolute(openPath)) {
      openPath = path.join(workspaceRoot, openPath);
    }

    const currentQueries = queries.filter(query => {
      let filePath = query.file;
      if (!path.isAbsolute(filePath)) {
        filePath = path.join(workspaceRoot!, query.file);
      }
      return filePath === openPath;
    });
    if (currentQueries.length <= 0) {
      return;
    }

    currentQueries.forEach((query, index) => {
      const ranges: vscode.Range[] = [];

      const stack = [query.query];
      while (stack.length > 0) {
        const fragment = stack.pop()!;
        if (fragment.literal) {
          ranges.push(locationToRange(fragment.location));
        } else {
          fragment.complex!.forEach(child => {
            stack.push(child);
          });
        }
      }

      query.usages.forEach(usage => {
        ranges.push(locationToRange(usage));
      });

      openEditor.setDecorations(this.getColor(index), ranges);
    });
  }

  /**
   * Updates the cache if needed, and then returns the relevant decoration.
   * @param index decoration number to return.
   */
  private getColor(index: number): vscode.TextEditorDecorationType {
    while (this.decorations.length <= index) {
      const color = randomColor({luminosity: 'light', hue: 'random'}) + '29';
      const decoration = vscode.window.createTextEditorDecorationType({
        backgroundColor: color,
      });
      this.decorations.push(decoration);
    }

    return this.decorations[index];
  }
}
