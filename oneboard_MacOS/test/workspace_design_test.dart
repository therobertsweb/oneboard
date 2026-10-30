import 'dart:io';
import 'dart:ui' as ui;
import 'package:flutter/material.dart';
import 'package:flutter/rendering.dart';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:oneboard_flutter/apple_design.dart';
import 'package:oneboard_flutter/workspace_dashboard.dart';
import 'package:oneboard_flutter/workspace_chrome.dart';

void main() {
  setUpAll(() async {
    final icons = FontLoader('MaterialIcons');
    icons.addFont(rootBundle.load('fonts/MaterialIcons-Regular.otf'));
    await icons.load();
    final cupertino = FontLoader('packages/cupertino_icons/CupertinoIcons');
    cupertino.addFont(
      rootBundle.load('packages/cupertino_icons/assets/CupertinoIcons.ttf'),
    );
    await cupertino.load();
    final font = File('/System/Library/Fonts/SFNS.ttf');
    if (await font.exists()) {
      final loader = FontLoader('.AppleSystemUIFont');
      loader.addFont(
        font.readAsBytes().then((bytes) => ByteData.sublistView(bytes)),
      );
      await loader.load();
    }
  });
  for (final width in [1000.0, 1320.0]) {
    testWidgets('Desktop dashboard fits $width and connects its actions', (
      tester,
    ) async {
      debugDisableShadows = false;
      addTearDown(() => debugDisableShadows = true);
      tester.view.devicePixelRatio = 1;
      tester.view.physicalSize = Size(width, 900);
      addTearDown(tester.view.resetPhysicalSize);
      addTearDown(tester.view.resetDevicePixelRatio);
      var connections = 0;
      int? destination;
      final boundaryKey = GlobalKey();
      await tester.pumpWidget(
        MaterialApp(
          theme: boardTheme,
          home: RepaintBoundary(
            key: boundaryKey,
            child: Scaffold(
              body: WorkspaceChrome(
                userName: '',
                selectedSection: 0,
                busy: false,
                usingCachedData: false,
                onLogout: () {},
                onRefresh: () {},
                onNavigate: (index) => destination = index,
                child: Padding(
                  padding: const EdgeInsets.all(30),
                  child: WorkspaceDashboard(
                    data: const {},
                    userName: '',
                    onConnect: () => connections++,
                    onOpenStudio: () => destination = 1,
                    onNavigate: (index) => destination = index,
                  ),
                ),
              ),
            ),
          ),
        ),
      );
      await tester.pumpAndSettle();
      expect(tester.takeException(), isNull);
      expect(find.text('Not connected'), findsOneWidget);
      await tester.tap(find.text('Connect project'));
      expect(connections, 1);
      await tester.ensureVisible(find.text('Plan ahead'));
      await tester.tap(find.text('Plan ahead'));
      expect(destination, 6);
      await tester.tap(find.text('Create & share'));
      expect(destination, 9);
      expect(find.text('Better together'), findsNothing);
      await tester.pumpAndSettle();
      expect(tester.takeException(), isNull);
      if (const bool.fromEnvironment('ONEBOARD_CAPTURE_PREVIEW') &&
          width == 1320) {
        final boundary =
            boundaryKey.currentContext!.findRenderObject()!
                as RenderRepaintBoundary;
        await tester.runAsync(() async {
          final image = await boundary.toImage(pixelRatio: 2);
          final bytes = await image.toByteData(format: ui.ImageByteFormat.png);
          final file = File('build/previews/dashboard.png');
          await file.parent.create(recursive: true);
          await file.writeAsBytes(bytes!.buffer.asUint8List());
          image.dispose();
        });
      }
      debugDisableShadows = true;
    });
  }
}
