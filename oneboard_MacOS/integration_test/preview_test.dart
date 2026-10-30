import 'dart:io';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:integration_test/integration_test.dart';
import 'package:webview_flutter/webview_flutter.dart';
import 'package:oneboard_flutter/board_api.dart';
import 'package:oneboard_flutter/preview_panel.dart';

class FixtureApi extends BoardApi {
  FixtureApi(super.address);
  bool edited = false;
  Map<String, Object?>? applied;
  Map<String, Object?>? selection;
  final calls = <String>[];
  @override
  Map<String, String> get sessionCookies => {'session': 'preview-test'};
  @override
  Future<Map<String, dynamic>> get(String path) async => {
    'manager': {
      'updates': [],
      'directory': {'path': '/fixture'},
    },
  };
  @override
  Future<Map<String, dynamic>> post(
    String path, [
    Map<String, Object?>? data,
  ]) async {
    calls.add(path);
    if (path.endsWith('/select')) {
      selection = data;
      return {'selection': data};
    }
    if (path.endsWith('/codex-update')) {
      applied = data;
      edited = true;
      return {
        'terminal': {'exit_code': 0, 'output': 'Fixture changed'},
      };
    }
    throw StateError('Unexpected mutation: $path');
  }
}

Future<void> waitFor(WidgetTester tester, bool Function() ready) async {
  for (var i = 0; i < 100; i++) {
    await tester.pump(const Duration(milliseconds: 100));
    if (ready()) return;
  }
  fail('Timed out waiting for native preview.');
}

void main() {
  IntegrationTestWidgetsFlutterBinding.ensureInitialized();
  testWidgets('macOS renders, navigates, selects and reloads after an AI edit', (
    tester,
  ) async {
    final server = await HttpServer.bind(InternetAddress.loopbackIPv4, 0);
    final api = FixtureApi('http://127.0.0.1:${server.port}');
    final loaded = <String>[];
    final authenticatedRequests = <bool>[];
    server.listen((request) async {
      loaded.add(request.uri.path);
      authenticatedRequests.add(
        request.cookies.any(
          (c) => c.name == 'session' && c.value == 'preview-test',
        ),
      );
      request.response.headers.contentType = ContentType.html;
      request.response.headers.set(
        'Content-Security-Policy',
        "sandbox allow-scripts; form-action 'none'",
      );
      request.response.write(
        '<html><body><h1 id="hero">${api.edited ? 'Edited heading' : 'Preview fixture'}</h1><a href="about.html">About</a></body></html>',
      );
      await request.response.close();
    });
    Map<String, dynamic>? result;
    await tester.pumpWidget(
      MaterialApp(
        home: Scaffold(
          body: SingleChildScrollView(
            child: PreviewPanel(
              api: api,
              workspacePath: '',
              onAssistantResult: (value) => result = value,
            ),
          ),
        ),
      ),
    );
    try {
      await waitFor(
        tester,
        () => find.byType(CircularProgressIndicator).evaluate().isEmpty,
      );
      final texts = tester
          .widgetList<Text>(find.byType(Text))
          .map((t) => t.data)
          .toList();
      expect(
        find.text('Preview could not start.'),
        findsNothing,
        reason: texts.toString(),
      );
      expect(find.text('Visual Preview'), findsOneWidget);
      final controller = tester
          .widget<WebViewWidget>(find.byType(WebViewWidget))
          .platform
          .params
          .controller;
      expect(
        await controller.runJavaScriptReturningResult(
          "document.querySelector('#hero').textContent",
        ),
        'Preview fixture',
      );
      await controller.runJavaScript("document.querySelector('a').click();");
      await waitFor(
        tester,
        () =>
            tester
                .widget<TextField>(find.byType(TextField).first)
                .controller!
                .text ==
            'about.html',
      );
      await tester.tap(find.text('Select element'));
      await tester.pump();
      await controller.runJavaScript(
        "document.querySelector('#hero').click();",
      );
      await waitFor(
        tester,
        () => find.text('Selected element').evaluate().isNotEmpty,
      );
      expect(api.selection?['page'], 'about.html');
      expect(api.selection?['selector'], '#hero');
      expect(api.selection?['expected_directory_path'], '/fixture');
      final prompt = find.byWidgetPredicate(
        (w) =>
            w is TextField && w.decoration?.labelText == 'Describe the change',
      );
      await tester.ensureVisible(prompt);
      await tester.enterText(prompt, 'Change the heading');
      await tester.ensureVisible(find.text('Apply'));
      await tester.tap(find.text('Apply'));
      await waitFor(
        tester,
        () =>
            result != null &&
            find.byType(CircularProgressIndicator).evaluate().isEmpty,
      );
      expect(api.applied?['prompt'], 'Change the heading');
      expect(api.applied?['expected_directory_path'], '/fixture');
      expect(api.calls, [
        '/api/site-manager/preview/select',
        '/api/site-manager/preview/select',
        '/api/site-manager/codex-update',
      ]);
      expect(
        await controller.runJavaScriptReturningResult(
          "document.querySelector('#hero').textContent",
        ),
        'Edited heading',
      );
      expect(
        loaded.where((p) => p.endsWith('about.html')).length,
        greaterThanOrEqualTo(2),
      );
      expect(find.text('Visual Preview'), findsOneWidget);
      expect(authenticatedRequests, everyElement(isTrue));
      expect(tester.takeException(), isNull);
    } finally {
      await tester.pumpWidget(const SizedBox());
      api.close();
      await server.close(force: true);
    }
  });
}
