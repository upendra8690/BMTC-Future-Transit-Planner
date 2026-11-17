// Android wrapper for the Bengaluru Transit Planner web app (an independent, unofficial app).
//
// STATUS: built only by the GitHub "Android APK" workflow. This machine has no Flutter SDK, so changes here are
// checked for syntax only (python android/check_starter.py) until the workflow compiles them.
//
// The app shows the planner web page in a WebView. The planner's address is given at build time:
//   flutter run --dart-define=PLANNER_URL=https://your-planner.example.org/
//
// Links:
//   - pages on the planner's own host open inside the app;
//   - phone links (tel:, used by the SOS and helpline buttons) open the phone's dialler;
//   - other https links (official BMTC, BMRCL and government sites, map credits) open in the phone's browser.
//   Nothing else is followed.
// Back button: goes back one page inside the app while there is a page to go back to; otherwise Android closes it.

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:url_launcher/url_launcher.dart';
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
      title: 'Bengaluru Transit Planner',
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

  /// Opens a phone or web link outside the app. Returns quietly if the phone has no app for it.
  Future<void> _openOutside(Uri target) async {
    try {
      await launchUrl(target, mode: LaunchMode.externalApplication);
    } catch (_) {
      // No dialler or browser is available; the page stays as it is.
    }
  }

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
            final target = Uri.tryParse(request.url);
            if (target == null) {
              return NavigationDecision.prevent;
            }
            if (target.host == address.host && (target.scheme == 'https' || target.scheme == 'http')) {
              return NavigationDecision.navigate;
            }
            if (target.scheme == 'tel' || target.scheme == 'https') {
              _openOutside(target);
            }
            return NavigationDecision.prevent;
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
    return PopScope(
      canPop: false,
      onPopInvokedWithResult: (didPop, result) async {
        if (didPop) {
          return;
        }
        if (controller != null && await controller.canGoBack()) {
          await controller.goBack();
          return;
        }
        // No page to go back to: close the app, as the back button does in other Android apps.
        await SystemNavigator.pop();
      },
      child: Scaffold(
        body: SafeArea(
          child: controller == null || _problem != null
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
        ),
      ),
    );
  }
}
