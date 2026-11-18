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
// Location: asked from Android only when the planner page asks for it ("Stops near me"), and only for the
//   planner's own address. It is never stored by the app and never retained by the WebView.
// Downloads: the page sends a timetable CSV or PDF through the PlannerAndroid channel. The file is written to the
//   app's temporary folder and handed to Android's share sheet, so the passenger chooses where to keep it.
// Errors: if the planner cannot be loaded, the app says so and offers "Try again".

import 'dart:convert';
import 'dart:io';

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:path_provider/path_provider.dart';
import 'package:permission_handler/permission_handler.dart';
import 'package:share_plus/share_plus.dart';
import 'package:url_launcher/url_launcher.dart';
import 'package:webview_flutter/webview_flutter.dart';
import 'package:webview_flutter_android/webview_flutter_android.dart';

const String plannerUrl = String.fromEnvironment('PLANNER_URL');

/// Files the page may hand over, and the largest size accepted (base64 text, so about 7.5 MB of file).
const Set<String> allowedDownloadTypes = {'text/csv', 'application/pdf', 'application/json'};
const int maxDownloadChars = 10 * 1024 * 1024;

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
  Uri? _address;
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

  /// Asked only when the planner page requests the location, and only for the planner's own address.
  Future<GeolocationPermissionsResponse> _locationPrompt(GeolocationPermissionsRequestParams request) async {
    final origin = Uri.tryParse(request.origin ?? '');
    final address = _address;
    if (origin == null || address == null || origin.host != address.host) {
      return const GeolocationPermissionsResponse(allow: false, retain: false);
    }
    final status = await Permission.locationWhenInUse.request();
    return GeolocationPermissionsResponse(allow: status.isGranted, retain: false);
  }

  /// Saves a file sent by the page and opens the share sheet. Anything unexpected is ignored.
  Future<void> _saveDownload(String message) async {
    try {
      if (message.length > maxDownloadChars) {
        return;
      }
      final data = jsonDecode(message);
      if (data is! Map) {
        return;
      }
      final type = data['type'];
      final encoded = data['data'];
      if (type is! String || encoded is! String || !allowedDownloadTypes.contains(type)) {
        return;
      }
      final rawName = data['name'] is String ? data['name'] as String : 'download';
      var name = rawName.replaceAll(RegExp(r'[^A-Za-z0-9._-]'), '_');
      if (name.isEmpty || name.startsWith('.')) {
        name = 'download';
      }
      if (name.length > 120) {
        name = name.substring(0, 120);
      }
      final folder = await getTemporaryDirectory();
      final file = File('${folder.path}/$name');
      await file.writeAsBytes(base64Decode(encoded), flush: true);
      await Share.shareXFiles([XFile(file.path, mimeType: type)], subject: name);
    } catch (_) {
      // A malformed message or a cancelled share leaves the page as it is.
    }
  }

  void _load() {
    final controller = _controller;
    final address = _address;
    if (controller == null || address == null) {
      return;
    }
    setState(() {
      _problem = null;
      _progress = 0;
    });
    controller.loadRequest(address);
  }

  @override
  void initState() {
    super.initState();
    final address = Uri.tryParse(plannerUrl);
    if (address == null || !address.hasScheme || address.host.isEmpty) {
      _problem = 'This build has no planner address. Rebuild it with --dart-define=PLANNER_URL=https://...';
      return;
    }
    _address = address;

    final controller = WebViewController()
      ..setJavaScriptMode(JavaScriptMode.unrestricted)
      ..addJavaScriptChannel('PlannerAndroid', onMessageReceived: (message) => _saveDownload(message.message))
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
              setState(() => _problem = 'The planner could not be loaded. Check the internet connection. '
                  '(${error.description})');
            }
          },
        ),
      );
    final platform = controller.platform;
    if (platform is AndroidWebViewController) {
      platform.setGeolocationPermissionsPromptCallbacks(onShowPrompt: _locationPrompt);
    }
    _controller = controller;
    controller.loadRequest(address);
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
                    child: Column(
                      mainAxisSize: MainAxisSize.min,
                      children: [
                        Text(_problem ?? 'The planner is not available.', textAlign: TextAlign.center),
                        if (controller != null) ...[
                          const SizedBox(height: 16),
                          FilledButton(onPressed: _load, child: const Text('Try again')),
                        ],
                      ],
                    ),
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
