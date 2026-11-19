"""Static checks for the Flutter starter in android/flutter_app.

This does not compile the app. It parses the YAML files, parses lib/main.dart with the Dart grammar
(tree-sitter-dart) and checks that the calls the starter relies on are present. Install the checker packages first:

    python -m pip install pyyaml tree-sitter tree-sitter-dart

Then run:  python android/check_starter.py      (exit code 0 means the static checks passed)
"""

from __future__ import annotations

import sys
from pathlib import Path

import tree_sitter_dart as tsdart
import yaml
from tree_sitter import Language, Parser

APP = Path(__file__).resolve().parent / "flutter_app"
REQUIRED_IN_MAIN = {
    "reads the planner address from --dart-define": "String.fromEnvironment('PLANNER_URL')",
    "allows JavaScript, which the dashboard needs": "JavaScriptMode.unrestricted",
    "decides navigation for every link": "onNavigationRequest",
    "reports load errors for the main frame only": "isForMainFrame",
    "loads the planner address": "loadRequest(",
    "imports webview_flutter": "package:webview_flutter/webview_flutter.dart",
    "opens phone and official-site links outside the app": "launchUrl(target, mode: LaunchMode.externalApplication)",
    "sends tel: links (SOS and helplines) to the dialler": "target.scheme == 'tel'",
    "handles the Android back button inside the WebView": "onPopInvokedWithResult",
    "goes back a page when there is one": "controller.canGoBack()",
    "asks Android for location only when the page asks": "setGeolocationPermissionsPromptCallbacks",
    "never lets the WebView keep a location grant": "retain: false",
    "offers Try again after a failed load": "'Try again'",
    "receives downloads through one named channel": "addJavaScriptChannel('PlannerAndroid'",
    "accepts only expected download types": "allowedDownloadTypes.contains(type)",
}


def check_yaml(problems: list[str]) -> None:
    pubspec = yaml.safe_load((APP / "pubspec.yaml").read_text(encoding="utf-8"))
    yaml.safe_load((APP / "analysis_options.yaml").read_text(encoding="utf-8"))
    print("YAML ok: pubspec.yaml and analysis_options.yaml")
    if pubspec.get("name") != "bmtc_planner_app":
        problems.append("pubspec.yaml name is not bmtc_planner_app")


def check_dart(problems: list[str]) -> None:
    source = (APP / "lib" / "main.dart").read_bytes()
    tree = Parser(Language(tsdart.language())).parse(source)
    errors: list[tuple[int, int]] = []
    missing: list[int] = []
    stack = [tree.root_node]
    while stack:
        node = stack.pop()
        if node.type == "ERROR":
            errors.append((node.start_point[0] + 1, node.start_point[1] + 1))
        if node.is_missing:
            missing.append(node.start_point[0] + 1)
        stack.extend(node.children)
    print(f"Dart grammar: {len(errors)} ERROR node(s), {len(missing)} missing token(s) in lib/main.dart")
    for line, column in errors[:10]:
        print(f"   syntax error at line {line}, column {column}")
    if errors or missing:
        problems.append("the Dart grammar reports syntax errors")

    text = source.decode("utf-8")
    for label, needle in REQUIRED_IN_MAIN.items():
        found = needle in text
        print(f"{'found  ' if found else 'MISSING'} {label}: {needle}")
        if not found:
            problems.append(f"lib/main.dart does not contain {needle}")


def main() -> int:
    problems: list[str] = []
    check_yaml(problems)
    check_dart(problems)
    if problems:
        print("RESULT: problems found:\n  - " + "\n  - ".join(problems))
        return 1
    print("RESULT: static checks passed. The app itself has not been compiled.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
