// Starter Flutter wrapper for the BMTC Future Transit Planner web app.
//
// STATUS: NOT COMPILED. The build environment for this project had no Flutter SDK, so this file has been checked
// for syntax only. Build it on a developer machine as described in android/README.md.
//
// The app shows the planner web page in a WebView. The planner's address is given at build time:
//   flutter run --dart-define=PLANNER_URL=https://your-planner.example.org/

import 'package:flutter/material.dart';
import 'package:webview_flutter/webview_flutter.dart';

const String plannerUrl = String.fromEnvironment('PLANNER_URL');

void main() {
  runApp(const PlannerApp());
}

class PlannerApp extends StatelessWidget {
  const PlannerApp({super.key});

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      title: 'BMTC Future Transit Planner',
      theme: ThemeData(colorSchemeSeed: const Color(0xFF1F5C99), useMaterial3: true),
      home: const PlannerPage(),
    );
  }
}

class PlannerPage extends StatefulWidget {
  const PlannerPage({super.key});

  @override
  State<PlannerPage> createState() => _PlannerPageState();
}

class _PlannerPageState extends State<PlannerPage> {
  WebViewController? _controller;
  double _progress = 0;
  String? _problem;

  @override
  void initState() {
    super.initState();
    final address = Uri.tryParse(plannerUrl);
    if (address == null || !address.hasScheme || address.host.isEmpty) {
      _problem = 'This build has no planner address. Rebuild it with --dart-define=PLANNER_URL=https://...';
      return;
    }

    _controller = WebViewController()
      ..setJavaScriptMode(JavaScriptMode.unrestricted)
      ..setNavigationDelegate(
        NavigationDelegate(
          onProgress: (progress) => setState(() => _progress = progress / 100),
          onNavigationRequest: (request) {
            // Only pages on the planner's own host open inside the app. Other links are not followed.
            final target = Uri.tryParse(request.url);
            final sameHost = target != null && target.host == address.host;
            return sameHost ? NavigationDecision.navigate : NavigationDecision.prevent;
          },
          onWebResourceError: (error) {
            if (error.isForMainFrame == true) {
              setState(() => _problem = 'The planner could not be loaded: ${error.description}');
            }
          },
        ),
      )
      ..loadRequest(address);
  }

  @override
  Widget build(BuildContext context) {
    final controller = _controller;
    return Scaffold(
      appBar: AppBar(title: const Text('BMTC Future Transit Planner')),
      body: controller == null || _problem != null
          ? Center(
              child: Padding(
                padding: const EdgeInsets.all(24),
                child: Text(_problem ?? 'The planner is not available.', textAlign: TextAlign.center),
              ),
            )
          : Column(
              children: [
                if (_progress < 1) LinearProgressIndicator(value: _progress),
                Expanded(child: WebViewWidget(controller: controller)),
              ],
            ),
    );
  }
}
